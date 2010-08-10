from scrapy.xlib.pydispatch import dispatcher
from twisted.internet.defer import Deferred, DeferredList

from scrapy.utils.defer import mustbe_deferred, defer_result
from scrapy import log
from scrapy import signals
from scrapy.core.manager import scrapymanager
from scrapy.utils.request import request_fingerprint
from scrapy.utils.misc import arg_to_iter


class MediaPipeline(object):

    DOWNLOAD_PRIORITY = 1000
    LOG_FAILED_RESULTS = True

    class SpiderInfo(object):
        def __init__(self, spider):
            self.spider = spider
            self.downloading = {}
            self.downloaded = {}
            self.waiting = {}

    def __init__(self):
        self.spiderinfo = {}
        dispatcher.connect(self.spider_opened, signals.spider_opened)
        dispatcher.connect(self.spider_closed, signals.spider_closed)

    def spider_opened(self, spider):
        self.spiderinfo[spider] = self.SpiderInfo(spider)

    def spider_closed(self, spider):
        del self.spiderinfo[spider]

    def process_item(self, spider, item):
        info = self.spiderinfo[spider]
        requests = arg_to_iter(self.get_media_requests(item, info))
        dlist = [self._enqueue(r, info) for r in requests]
        dfd = DeferredList(dlist, consumeErrors=1)
        return dfd.addCallback(self.item_completed, item, info)

    def _enqueue(self, request, info):
        fp = request_fingerprint(request)
        cb = request.callback or (lambda _: _)
        eb = request.errback

        # if already downloaded, return cached result.
        if fp in info.downloaded:
            return defer_result(info.downloaded[fp]).addCallbacks(cb, eb)

        wad = Deferred().addCallbacks(cb, eb)
        # add to pending list for this request, and wait for result like the others.
        info.waiting.setdefault(fp, []).append(wad)

        # if request is not downloading, download it.
        if fp not in info.downloading:
            self._download(request, info, fp)

        return wad

    def _download(self, request, info, fp):
        def _downloaded(result):
            info.downloading.pop(fp)
            info.downloaded[fp] = result
            for wad in info.waiting.pop(fp): # pass result to each waiting client
                defer_result(result).chainDeferred(wad)

        def _post_media_to_download(result):
            if result is None: # continue with download
                dwld = mustbe_deferred(self.download, request, info)
                dwld.addCallbacks(
                        callback=self.media_downloaded,
                        callbackArgs=(request, info),
                        errback=self.media_failed,
                        errbackArgs=(request, info))
            else: # or use media_to_download return value as result
                dwld = defer_result(result)

            info.downloading[fp] = (request, dwld) # fill downloading state data
            dwld.addBoth(_downloaded) # append post-download hook
            dwld.addErrback(log.err, spider=info.spider)

        # declare request in downloading state (None is used as place holder)
        info.downloading[fp] = None

        # defer pre-download request processing
        dfd = mustbe_deferred(self.media_to_download, request, info)
        dfd.addCallback(_post_media_to_download)

    ### Overradiable Interface
    def download(self, request, info):
        """Defines how to download the media request"""
        request.priority = self.DOWNLOAD_PRIORITY
        return scrapymanager.engine.download(request, info.spider)

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
            for success, result in results:
                if not success:
                    log.err(result, '%s found errors proessing %s' % (self.__class__.__name__, item))
        return item

