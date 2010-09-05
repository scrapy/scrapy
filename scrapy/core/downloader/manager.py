"""
Download web pages using asynchronous IO
"""

import random
from time import time

from twisted.internet import reactor, defer
from twisted.python.failure import Failure

from scrapy.exceptions import IgnoreRequest
from scrapy.conf import settings
from scrapy.utils.defer import mustbe_deferred
from scrapy import log
from .middleware import DownloaderMiddlewareManager
from .handlers import DownloadHandlers


class SpiderInfo(object):
    """Simple class to keep information and state for each open spider"""

    def __init__(self, download_delay=None, max_concurrent_requests=None):
        if download_delay is None:
            self._download_delay = settings.getfloat('DOWNLOAD_DELAY')
        else:
            self._download_delay = float(download_delay)
        if self._download_delay:
            self.max_concurrent_requests = 1
        elif max_concurrent_requests is None:
            self.max_concurrent_requests = settings.getint('CONCURRENT_REQUESTS_PER_SPIDER')
        else:
            self.max_concurrent_requests =  max_concurrent_requests
        if self._download_delay and settings.getbool('RANDOMIZE_DOWNLOAD_DELAY'):
            # same policy as wget --random-wait
            self.random_delay_interval = (0.5*self._download_delay, \
                1.5*self._download_delay)
        else:
            self.random_delay_interval = None

        self.active = set()
        self.queue = []
        self.transferring = set()
        self.closing = False
        self.lastseen = 0
        self.next_request_calls = set()

    def free_transfer_slots(self):
        return self.max_concurrent_requests - len(self.transferring)

    def needs_backout(self):
        # use self.active to include requests in the downloader middleware
        return len(self.active) > 2 * self.max_concurrent_requests

    def download_delay(self):
        if self.random_delay_interval:
            return random.uniform(*self.random_delay_interval)
        else:
            return self._download_delay

    def cancel_request_calls(self):
        for call in self.next_request_calls:
            call.cancel()
        self.next_request_calls.clear()


class Downloader(object):
    """Mantain many concurrent downloads and provide an HTTP abstraction.
    It supports a limited number of connections per spider and many spiders in
    parallel.
    """

    def __init__(self):
        self.sites = {}
        self.handlers = DownloadHandlers()
        self.middleware = DownloaderMiddlewareManager()
        self.concurrent_spiders = settings.getint('CONCURRENT_SPIDERS')

    def fetch(self, request, spider):
        """Main method to use to request a download

        This method includes middleware mangling. Middleware can returns a
        Response object, then request never reach downloader queue, and it will
        not be downloaded from site.
        """
        site = self.sites[spider]
        if site.closing:
            raise IgnoreRequest('Cannot fetch on a closing spider')

        site.active.add(request)
        def _deactivate(_):
            site.active.remove(request)
            self._close_if_idle(spider)
            return _

        dfd = self.middleware.download(self.enqueue, request, spider)
        return dfd.addBoth(_deactivate)

    def enqueue(self, request, spider):
        """Enqueue a Request for a effective download from site"""
        site = self.sites[spider]
        if site.closing:
            raise IgnoreRequest
        deferred = defer.Deferred()
        site.queue.append((request, deferred))
        self._process_queue(spider)
        return deferred

    def _process_queue(self, spider):
        """Effective download requests from site queue"""
        site = self.sites.get(spider)
        if not site:
            return

        # Delay queue processing if a download_delay is configured
        now = time()
        delay = site.download_delay()
        if delay:
            penalty = delay - now + site.lastseen
            if penalty > 0:
                d = defer.Deferred()
                d.addCallback(self._process_queue)
                call = reactor.callLater(penalty, d.callback, spider)
                site.next_request_calls.add(call)
                d.addBoth(lambda x: site.next_request_calls.remove(call))
                return
        site.lastseen = now

        # Process enqueued requests if there are free slots to transfer for this site
        while site.queue and site.free_transfer_slots() > 0:
            request, deferred = site.queue.pop(0)
            if site.closing:
                dfd = defer.fail(Failure(IgnoreRequest()))
            else:
                dfd = self._download(site, request, spider)
            dfd.chainDeferred(deferred)

        self._close_if_idle(spider)

    def _close_if_idle(self, spider):
        site = self.sites.get(spider)
        if site and site.closing and not site.active:
            del self.sites[spider]
            site.closing.callback(None)

    def _download(self, site, request, spider):
        # The order is very important for the following deferreds. Do not change!

        # 1. Create the download deferred
        dfd = mustbe_deferred(self.handlers.download_request, request, spider)

        # 2. After response arrives,  remove the request from transferring
        # state to free up the transferring slot so it can be used by the
        # following requests (perhaps those which came from the downloader
        # middleware itself)
        site.transferring.add(request)
        def finish_transferring(_):
            site.transferring.remove(request)
            self._process_queue(spider)
            # avoid partially downloaded responses from propagating to the
            # downloader middleware, to speed-up the closing process
            if site.closing:
                log.msg("Crawled while closing spider: %s" % request, \
                    level=log.DEBUG, spider=spider)
                raise IgnoreRequest
            return _
        return dfd.addBoth(finish_transferring)

    def open_spider(self, spider):
        """Allocate resources to begin processing a spider"""
        assert spider not in self.sites, "Spider already opened: %s" % spider
        self.sites[spider] = SpiderInfo(
            download_delay=getattr(spider, 'download_delay', None),
            max_concurrent_requests=getattr(spider, 'max_concurrent_requests', None)
        )

    def close_spider(self, spider):
        """Free any resources associated with the given spider"""
        assert spider in self.sites, "Spider not opened: %s" % spider
        site = self.sites.get(spider)
        site.closing = defer.Deferred()
        site.cancel_request_calls()
        self._process_queue(spider)
        return site.closing

    def is_idle(self):
        return not self.sites

