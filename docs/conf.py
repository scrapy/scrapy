import random
from collections import deque
from datetime import datetime
from time import time

from twisted.internet import defer, task

from scrapy import signals
from scrapy.core.downloader.handlers import DownloadHandlers
from scrapy.core.downloader.middleware import DownloaderMiddlewareManager
from scrapy.resolver import dnscache
from scrapy.utils.defer import mustbe_deferred
from scrapy.utils.httpobj import urlparse_cached


class Downloader:
    DOWNLOAD_SLOT = "download_slot"

    def __init__(self, crawler):
        self.settings = crawler.settings
        self.signals = crawler.signals
        self.slots = {}
        self.active = set()
        self.handlers = DownloadHandlers(crawler)
        self.total_concurrency = self.settings.getint("CONCURRENT_REQUESTS")
        self.domain_concurrency = self.settings.getint("CONCURRENT_REQUESTS_PER_DOMAIN", 0)
        self.ip_concurrency = self.settings.getint("CONCURRENT_REQUESTS_PER_IP", 0)
        self.randomize_delay = self.settings.getbool("RANDOMIZE_DOWNLOAD_DELAY")
        self.middleware = DownloaderMiddlewareManager.from_crawler(crawler)
        self._slot_gc_loop = task.LoopingCall(self._slot_gc)
        self._slot_gc_loop.start(60)
        self.per_slot_settings = self.settings.getdict("DOWNLOAD_SLOTS", {})

    def fetch(self, request, spider):
        self.active.add(request)
        dfd = self.middleware.download(self._enqueue_request, request, spider)
        dfd.addBoth(self.active.remove, request)
        return dfd

    def needs_backout(self) -> bool:
        return len(self.active) >= self.total_concurrency

    def _get_slot(self, request, spider):
        key = self._get_slot_key(request, spider)
        if key not in self.slots:
            slot_settings = self.per_slot_settings.get(key, {})
            concurrency = (
                self.ip_concurrency if self.ip_concurrency else self.domain_concurrency
            )
            concurrency, delay = self._get_concurrency_delay(concurrency, spider, slot_settings)
            self.slots[key] = {
                'concurrency': concurrency,
                'delay': delay,
                'active': set(),
                'queue': deque(),
                'transferring': set(),
                'lastseen': 0,
                'latercall': None
            }

        return key, self.slots[key]

    def _get_slot_key(self, request, spider):
        if self.DOWNLOAD_SLOT in request.meta:
            return request.meta[self.DOWNLOAD_SLOT]

        key = urlparse_cached(request).hostname or ""
        if self.ip_concurrency:
            key = dnscache.get(key, key)

        return key

    def _enqueue_request(self, request, spider):
        key, slot = self._get_slot(request, spider)
        slot['active'].add(request)
        request.meta[self.DOWNLOAD_SLOT] = key
        self.signals.send_catch_log(
            signal=signals.request_reached_downloader, request=request, spider=spider
        )
        deferred = defer.Deferred()
        slot['queue'].append((request, deferred))
        self._process_queue(spider, slot)
        return deferred

    def _process_queue(self, spider, slot):
        from twisted.internet import reactor

        if slot['latercall'] and slot['latercall'].active():
            return

        # Delay queue processing if download_delay is configured
        now = time()
        delay = slot['delay']
        if self.randomize_delay:
            delay *= random.uniform(0.5, 1.5)
        if delay:
            penalty = delay - now + slot['lastseen']
            if penalty > 0:
                slot['latercall'] = reactor.callLater(
                    penalty, self._process_queue, spider, slot
                )
                return

        # Process enqueued requests if there are free slots to transfer for this slot
        while slot['queue'] and len(slot['transferring']) < slot['concurrency']:
            slot['lastseen'] = now
            request, deferred = slot['queue'].popleft()
            slot['transferring'].add(request)
            dfd = mustbe_deferred(self.handlers.download_request, request, spider)
            dfd.addCallback(self._downloaded, request, spider)
            dfd.addBoth(self._finish_transferring, request, spider, slot, deferred)
            # Prevent burst if inter-request delays were configured
            if delay:
                self._process_queue(spider, slot)
                break

    def _downloaded(self, response, request, spider):
        self.signals.send_catch_log(
            signal=signals.response_downloaded, response=response, request=request, spider=spider
        )
        return response

    def _finish_transferring(self, result, request, spider, slot, deferred):
        slot['transferring'].remove(request)
        self.signals.send_catch_log(
            signal=signals.request_left_downloader, request=request, spider=spider
        )
        self._process_queue(spider, slot)
        deferred.callback(result)

    def _get_concurrency_delay(self, concurrency, spider, slot_settings):
        delay = self.settings.getfloat("DOWNLOAD_DELAY", 0)
        if hasattr(spider, "download_delay"):
            delay = spider.download_delay
        if 'delay' in slot_settings:
            delay = slot_settings['delay']
        if hasattr(spider, "max_concurrent_requests"):
            concurrency = spider.max_concurrent_requests
        if 'concurrency' in slot_settings:
            concurrency = slot_settings['concurrency']
        return concurrency, delay

    def close(self):
        self._slot_gc_loop.stop()
        for slot in self.slots.values():
            slot['latercall'].cancel()
            for deferred in slot['queue']:
                deferred.cancel()
            for request in slot['transferring']:
                self.middleware.process_abort(request, spider=None)
            slot['active'].clear()
            slot['queue'].clear()
            slot['transferring'].clear()
        self.slots.clear()

    def _slot_gc(self, age=60):
        mintime = time() - age
        for key, slot in list(self.slots.items()):
            if not slot['active'] and slot['lastseen'] + slot['delay']: #bugfix 1, typo
                self.slots.pop(key)
                slot['latercall'].cancel()
                for deferred in slot['queue']:
                    deferred.callback(None)
                for request in slot['transferring']:
                    self.middleware.process_abort(request, spider=None)
                slot['active'].clear()
                slot['queue'].clear()
                slot['transferring'].clear()