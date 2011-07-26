import random
from time import time
from collections import deque

from twisted.internet import reactor, defer
from twisted.python.failure import Failure

from scrapy.conf import settings
from scrapy.utils.python import setattr_default
from scrapy.utils.defer import mustbe_deferred
from scrapy.utils.signal import send_catch_log
from scrapy import signals
from scrapy import log
from .middleware import DownloaderMiddlewareManager
from .handlers import DownloadHandlers

class Slot(object):
    """Downloader spider slot"""

    def __init__(self, spider):
        setattr_default(spider, 'download_delay', spider.settings.getfloat('DOWNLOAD_DELAY'))
        setattr_default(spider, 'randomize_download_delay', spider.settings.getbool('RANDOMIZE_DOWNLOAD_DELAY'))
        setattr_default(spider, 'max_concurrent_requests', spider.settings.getint('CONCURRENT_REQUESTS_PER_SPIDER'))
        if spider.download_delay > 0 and spider.max_concurrent_requests > 1:
            spider.max_concurrent_requests = 1
            msg = "Setting max_concurrent_requests=1 because of download_delay=%s" % spider.download_delay
            log.msg(msg, spider=spider)
        self.spider = spider
        self.active = set()
        self.queue = deque()
        self.transferring = set()
        self.lastseen = 0
        self.next_request_calls = set()

    def free_transfer_slots(self):
        return self.spider.max_concurrent_requests - len(self.transferring)

    def needs_backout(self):
        # use self.active to include requests in the downloader middleware
        return len(self.active) > 2 * self.spider.max_concurrent_requests

    def download_delay(self):
        delay = self.spider.download_delay
        if self.spider.randomize_download_delay:
            delay = random.uniform(0.5*delay, 1.5*delay)
        return delay

    def cancel_request_calls(self):
        for call in self.next_request_calls:
            call.cancel()
        self.next_request_calls.clear()


class Downloader(object):

    def __init__(self):
        self.slots = {}
        self.handlers = DownloadHandlers()
        self.middleware = DownloaderMiddlewareManager.from_settings(settings)

    def fetch(self, request, spider):
        slot = self.slots[spider]

        slot.active.add(request)
        def _deactivate(response):
            slot.active.remove(request)
            return response

        dfd = self.middleware.download(self._enqueue_request, request, spider)
        return dfd.addBoth(_deactivate)

    def _enqueue_request(self, request, spider):
        slot = self.slots[spider]

        def _downloaded(response):
            send_catch_log(signal=signals.response_downloaded, \
                    response=response, request=request, spider=spider)
            return response

        deferred = defer.Deferred().addCallback(_downloaded)
        slot.queue.append((request, deferred))
        self._process_queue(spider, slot)
        return deferred

    def _process_queue(self, spider, slot):
        # Delay queue processing if a download_delay is configured
        now = time()
        delay = slot.download_delay()
        if delay:
            penalty = delay - now + slot.lastseen
            if penalty > 0 and slot.free_transfer_slots():
                d = defer.Deferred()
                d.addCallback(self._process_queue)
                call = reactor.callLater(penalty, d.callback, spider, slot)
                slot.next_request_calls.add(call)
                d.addBoth(lambda x: slot.next_request_calls.remove(call))
                return
        slot.lastseen = now

        # Process enqueued requests if there are free slots to transfer for this slot
        while slot.queue and slot.free_transfer_slots() > 0:
            request, deferred = slot.queue.popleft()
            dfd = self._download(slot, request, spider)
            dfd.chainDeferred(deferred)

    def _download(self, slot, request, spider):
        # The order is very important for the following deferreds. Do not change!

        # 1. Create the download deferred
        dfd = mustbe_deferred(self.handlers.download_request, request, spider)

        # 2. After response arrives,  remove the request from transferring
        # state to free up the transferring slot so it can be used by the
        # following requests (perhaps those which came from the downloader
        # middleware itself)
        slot.transferring.add(request)
        def finish_transferring(_):
            slot.transferring.remove(request)
            self._process_queue(spider, slot)
            return _
        return dfd.addBoth(finish_transferring)

    def open_spider(self, spider):
        assert spider not in self.slots, "Spider already opened: %s" % spider
        self.slots[spider] = Slot(spider)

    def close_spider(self, spider):
        assert spider in self.slots, "Spider not opened: %s" % spider
        slot = self.slots.pop(spider)
        slot.cancel_request_calls()

    def is_idle(self):
        return not self.slots

