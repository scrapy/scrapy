from scrapy.xlib.pydispatch import dispatcher
from twisted.internet.defer import Deferred, DeferredList

from scrapy.utils.defer import mustbe_deferred, defer_result
from scrapy import log
from scrapy.core import signals
from scrapy.core.engine import scrapyengine
from scrapy.utils.request import request_fingerprint
from scrapy.utils.misc import arg_to_iter


class MediaPipeline(object):
    DOWNLOAD_PRIORITY = 1000

    class DomainInfo(object):
        def __init__(self, spider):
            self.domain = spider.domain_name
            self.spider = spider
            self.downloading = {}
            self.downloaded = {}
            self.waiting = {}

    def __init__(self):
        self.domaininfo = {}
        dispatcher.connect(self.spider_opened, signals.spider_opened)
        dispatcher.connect(self.spider_closed, signals.spider_closed)

    def spider_opened(self, spider):
        self.domaininfo[spider.domain_name] = self.DomainInfo(spider)

    def spider_closed(self, spider):
        del self.domaininfo[spider.domain_name]

    def process_item(self, domain, item):
        info = self.domaininfo[domain]
        requests = arg_to_iter(self.get_media_requests(item, info))
        dlist = []
        for request in requests:
            dfd = self._enqueue(request, info)
            dfd.addCallbacks(
                    callback=self.item_media_downloaded,
                    callbackArgs=(item, request, info),
                    errback=self.item_media_failed,
                    errbackArgs=(item, request, info),)
            dlist.append(dfd)

        return DeferredList(dlist, consumeErrors=1).addCallback(self.item_completed, item, info)

    def _enqueue(self, request, info):
        wad = request.deferred or Deferred()
        fp = request_fingerprint(request)

        # if already downloaded, return cached result.
        if fp in info.downloaded:
            return defer_result(info.downloaded[fp]).chainDeferred(wad)

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
            dwld.addErrback(log.err, domain=info.domain)

        # declare request in downloading state (None is used as place holder)
        info.downloading[fp] = None

        # defer pre-download request processing
        dfd = mustbe_deferred(self.media_to_download, request, info)
        dfd.addCallback(_post_media_to_download)

    ### Overradiable Interface
    def download(self, request, info):
        """ Defines how to request the download of media

        Default gives high priority to media requests and use scheduler,
        shouldn't be necessary to override.

        This methods is called only if result for request isn't cached,
        request fingerprint is used as cache key.

        """
        request.priority = self.DOWNLOAD_PRIORITY
        return scrapyengine.download(request, info.spider)

    def media_to_download(self, request, info):
        """ Ongoing request hook pre-cache

        This method is called every time a media is requested for download, and
        only once for the same request because return value is cached as media
        result.

        returning a non-None value implies:
            - the return value is cached and piped into `item_media_downloaded` or `item_media_failed`
            - prevents downloading, this means calling `download` method.
            - `media_downloaded` or `media_failed` isn't called.

        """

    def get_media_requests(self, item, info):
        pass

    def media_downloaded(self, response, request, info):
        """ Method called on success download of media request

        Return value is cached and used as input for `item_media_downloaded` method.
        Default implementation returns None.

        WARNING: returning the response object can eat your memory.

        """

    def media_failed(self, failure, request, info):
        """ Method called when media request failed due to any kind of download error.

        Return value is cached and used as input for `item_media_failed` method.
        Default implementation returns same Failure object.
        """
        return failure

    def item_media_downloaded(self, result, item, request, info):
        """ Method to handle result of requested media for item.

        result is the return value of `media_downloaded` hook, or the non-Failure instance
        returned by `media_failed` hook.

        return value of this method is used for results parameter of item_completed hook
        """
        return result

    def item_media_failed(self, failure, item, request, info):
        """ Method to handle failed result of requested media for item.

        result is the returned Failure instance of `media_failed` hook, or Failure instance
        of an exception raised by `media_downloaded` hook.

        return value of this method is used for results parameter of item_completed hook
        """
        return failure

    def item_completed(self, results, item, info):
        return item

