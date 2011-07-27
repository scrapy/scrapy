import socket
import random
import warnings
from time import time
from collections import deque
from functools import partial

from twisted.internet import reactor, defer
from twisted.python.failure import Failure

from scrapy.utils.python import setattr_default
from scrapy.utils.defer import mustbe_deferred
from scrapy.utils.signal import send_catch_log
from scrapy.utils.reactor import CallLaterOnce
from scrapy.utils.httpobj import urlparse_cached
from scrapy.resolver import gethostbyname
from scrapy import signals
from scrapy import log
from .middleware import DownloaderMiddlewareManager
from .handlers import DownloadHandlers

class Slot(object):
    """Downloader slot"""

    def __init__(self, concurrency, settings):
        self.concurrency = concurrency
        self.delay = settings.getfloat('DOWNLOAD_DELAY')
        self.randomize_delay = settings.getbool('RANDOMIZE_DOWNLOAD_DELAY')
        self.active = set()
        self.queue = deque()
        self.transferring = set()
        self.lastseen = 0

    def free_transfer_slots(self):
        return self.concurrency - len(self.transferring)

    def download_delay(self):
        if self.randomize_delay:
            return random.uniform(0.5*self.delay, 1.5*self.delay)
        return self.delay


class Downloader(object):

    def __init__(self, settings):
        self.settings = settings
        self.slots = {}
        self.active = set()
        self.handlers = DownloadHandlers()
        self.total_concurrency = settings.getint('CONCURRENT_REQUESTS')
        self.domain_concurrency = settings.getint('CONCURRENT_REQUESTS_PER_DOMAIN')
        self.ip_concurrency = settings.getint('CONCURRENT_REQUESTS_PER_IP')
        self.middleware = DownloaderMiddlewareManager.from_settings(settings)

        # TODO: remove for Scrapy 0.15
        c = settings.getint('CONCURRENT_REQUESTS_PER_SPIDER')
        if c:
            warnings.warn("CONCURRENT_REQUESTS_PER_SPIDER setting is deprecated, use CONCURRENT_REQUESTS_PER_DOMAIN instead", DeprecationWarning)
            self.domain_concurrency = c

    def fetch(self, request, spider):
        key, slot = self._get_slot(request)

        self.active.add(request)
        slot.active.add(request)
        def _deactivate(response):
            self.active.remove(request)
            slot.active.remove(request)
            if not slot.active: # remove empty slots
                del self.slots[key]
            return response

        dlfunc = partial(self._enqueue_request, slot=slot)
        dfd = self.middleware.download(dlfunc, request, spider)
        return dfd.addBoth(_deactivate)

    def needs_backout(self):
        return len(self.active) >= self.total_concurrency

    def _get_slot(self, request):
        key = urlparse_cached(request).hostname
        if self.ip_concurrency:
            concurrency = self.ip_concurrency
            try:
                key = gethostbyname(key)
            except socket.error: # resolution error
                pass
        else:
            concurrency = self.domain_concurrency
        if key not in self.slots:
            self.slots[key] = Slot(concurrency, self.settings)
        return key, self.slots[key]

    def _enqueue_request(self, request, spider, slot):
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
                reactor.callLater(penalty, d.callback, spider, slot)
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

    def is_idle(self):
        return not self.slots

