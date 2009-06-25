from pydispatch import dispatcher
from twisted.internet import defer

from scrapy.utils.defer import mustbe_deferred, defer_result
from scrapy import log
from scrapy.core import signals
from scrapy.core.engine import scrapyengine
from scrapy.utils.request import request_fingerprint
from scrapy.spider import spiders


class MediaPipeline(object):
    DOWNLOAD_PRIORITY = 1000

    class DomainInfo(object):
        def __init__(self, domain):
            self.domain = domain
            self.spider = spiders.fromdomain(domain)
            self.downloading = {}
            self.downloaded = {}
            self.waiting = {}

    def __init__(self):
        self.domaininfo = {}
        dispatcher.connect(self.domain_open, signals.domain_open)
        dispatcher.connect(self.domain_closed, signals.domain_closed)

    def domain_open(self, domain):
        self.domaininfo[domain] = self.DomainInfo(domain)

    def domain_closed(self, domain):
        del self.domaininfo[domain]

    def process_item(self, domain, item):
        info = self.domaininfo[domain]
        requests = self.get_media_requests(item, info)
        assert requests is None or hasattr(requests, '__iter__'), \
                'get_media_requests should return None or iterable'

        def _bugtrap(_failure, request):
            log.msg('Unhandled ERROR in MediaPipeline.item_media_{downloaded,failed} for %s: %s' \
                    % (request, _failure), log.ERROR, domain=domain)

        lst = []
        for request in requests or ():
            dfd = self._enqueue(request, info)
            dfd.addCallbacks(
                    callback=self.item_media_downloaded,
                    callbackArgs=(item, request, info),
                    errback=self.item_media_failed,
                    errbackArgs=(item, request, info),
                    )
            dfd.addErrback(_bugtrap, request)
            lst.append(dfd)

        dlst = defer.DeferredList(lst, consumeErrors=False)
        dlst.addBoth(self.item_completed, item, info)
        return dlst

    def _enqueue(self, request, info):
        wad = request.deferred or defer.Deferred()
        fp = request_fingerprint(request)

        # if already downloaded, return cached result.
        if fp in info.downloaded:
            cached = info.downloaded[fp]
            defer_result(cached).chainDeferred(wad)
            return wad # break

        # add to pending list for this request, and wait for result like the others.
        info.waiting.setdefault(fp, []).append(wad)

        # if request is not downloading, download it.
        if fp not in info.downloading:
            self._download(request, info, fp)

        return wad

    def _download(self, request, info, fp):
        def _bugtrap(_failure):
            log.msg('Unhandled ERROR in MediaPipeline._downloaded: %s' \
                    % (_failure), log.ERROR, domain=info.domain)

        def _downloaded(result):
            info.downloaded[fp] = result # cache result
            waiting = info.waiting[fp] # client list
            del info.waiting[fp]
            del info.downloading[fp]
            for wad in waiting: # call each waiting client with result
                defer_result(result).chainDeferred(wad)

        def _evaluated(result):
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
            dwld.addErrback(_bugtrap) # catch media_downloaded and media_failed unhandled errors

        # declare request in downloading state (None is used as place holder)
        info.downloading[fp] = None

        # defer pre-download request processing
        dfd = mustbe_deferred(self.media_to_download, request, info)
        dfd.addCallback(_evaluated)

    ### Overradiable Interface
    def download(self, request, info):
        """ Defines how to request the download of media

        Default gives high priority to media requests and use scheduler,
        shouldn't be necessary to override.

        This methods is called only if result for request isn't cached,
        request fingerprint is used as cache key.

        """
        request.priority = self.DOWNLOAD_PRIORITY
        return scrapyengine.schedule(request, info.spider)

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
        """ Return a list of Request objects to download for this item

        Should return None or an iterable

        Defaults return None (no media to download)

        """

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

        return value of this method isn't important and is recommended to return None.
        """

    def item_media_failed(self, failure, item, request, info):
        """ Method to handle failed result of requested media for item.

        result is the returned Failure instance of `media_failed` hook, or Failure instance
        of an exception raised by `media_downloaded` hook.

        return value of this method isn't important and is recommended to return None.
        """

    def item_completed(self, results, item, info):
        """ Method called when all media requests for a single item has returned a result or failure.

        The return value of this method is used as output of pipeline stage.

        `item_completed` can return item itself or raise DropItem exception.

        Default returns item
        """
        return item

