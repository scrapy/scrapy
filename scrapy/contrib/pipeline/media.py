from __future__ import print_function
from collections import defaultdict
from twisted.internet.defer import Deferred, DeferredList
from twisted.python.failure import Failure

from scrapy.utils.defer import mustbe_deferred, defer_result
from scrapy import log
from scrapy.utils.request import request_fingerprint
from scrapy.utils.misc import arg_to_iter


class MediaPipeline(object):

    LOG_FAILED_RESULTS = True

    class SpiderInfo(object):
        def __init__(self, spider):
            self.spider = spider
            self.downloading = set()
            self.downloaded = {}
            self.waiting = defaultdict(list)

    def __init__(self, download_func=None):
        self.download_func = download_func

    @classmethod
    def from_crawler(cls, crawler):
        try:
            pipe = cls.from_settings(crawler.settings)
        except AttributeError:
            pipe = cls()
        pipe.crawler = crawler
        return pipe

    def open_spider(self, spider):
        self.spiderinfo = self.SpiderInfo(spider)

    def process_item(self, item, spider):
        info = self.spiderinfo
        requests = arg_to_iter(self.get_media_requests(item, info))
        dlist = [self._process_request(r, info) for r in requests]
        dfd = DeferredList(dlist, consumeErrors=1)
        return dfd.addCallback(self.item_completed, item, info)

    def _process_request(self, request, info):
        fp = request_fingerprint(request)
        cb = request.callback or (lambda _: _)
        eb = request.errback
        request.callback = None
        request.errback = None

        # Return cached result if request was already seen
        if fp in info.downloaded:
            return defer_result(info.downloaded[fp]).addCallbacks(cb, eb)

        # Otherwise, wait for result
        wad = Deferred().addCallbacks(cb, eb)
        info.waiting[fp].append(wad)

        # Check if request is downloading right now to avoid doing it twice
        if fp in info.downloading:
            return wad

        # Download request checking media_to_download hook output first
        info.downloading.add(fp)
        dfd = mustbe_deferred(self.media_to_download, request, info)
        dfd.addCallback(self._check_media_to_download, request, info)
        dfd.addBoth(self._cache_result_and_execute_waiters, fp, info)
        dfd.addErrback(log.err, spider=info.spider)
        return dfd.addBoth(lambda _: wad)  # it must return wad at last

    def _check_media_to_download(self, result, request, info):
        if result is not None:
            return result
        if self.download_func:
            # this ugly code was left only to support tests. TODO: remove
            dfd = mustbe_deferred(self.download_func, request, info.spider)
            dfd.addCallbacks(
                callback=self.media_downloaded, callbackArgs=(request, info),
                errback=self.media_failed, errbackArgs=(request, info))
        else:
            request.meta['handle_httpstatus_all'] = True
            dfd = self.crawler.engine.download(request, info.spider)
            dfd.addCallbacks(
                callback=self.media_downloaded, callbackArgs=(request, info),
                errback=self.media_failed, errbackArgs=(request, info))
        return dfd

    def _cache_result_and_execute_waiters(self, result, fp, info):
        if isinstance(result, Failure):
            # minimize cached information for failure
            result.cleanFailure()
            result.frames = []
            result.stack = None
        info.downloading.remove(fp)
        info.downloaded[fp] = result  # cache result
        for wad in info.waiting.pop(fp):
            defer_result(result).chainDeferred(wad)

    ### Overridable Interface
    def media_to_download(self, request, info):
        """Check request before starting download"""
        pass

    def get_media_requests(self, item, info):
        """Returns the media requests to download"""
        pass

    def media_downloaded(self, response, request, info):
        """Handler for success downloads"""
        return response

    def media_failed(self, failure, request, info):
        """Handler for failed downloads"""
        return failure

    def item_completed(self, results, item, info):
        """Called per item when all media requests has been processed"""
        if self.LOG_FAILED_RESULTS:
            msg = '%s found errors proessing %s' % (self.__class__.__name__, item)
            for ok, value in results:
                if not ok:
                    log.err(value, msg, spider=info.spider)
        return item
