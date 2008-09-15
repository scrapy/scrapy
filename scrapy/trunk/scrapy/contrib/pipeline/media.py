from twisted.internet import defer

from scrapy.utils.misc import mustbe_deferred, defer_result
from scrapy.core import log
from scrapy.core.engine import scrapyengine
from scrapy.core.exceptions import DropItem, NotConfigured
from scrapy.http import Request
from scrapy.spider import spiders
from scrapy.conf import settings


class DomainInfo(object):
    def __init__(self, domain):
        self.domain = domain
        self.spider = spiders.fromdomain(domain)
        self.downloading = {}
        self.downloaded = {}
        self.waiting = {}
        self.extra = {}


class MediaPipeline(object):
    def __init__(self):
        self.cache = {}

    def open_domain(self, domain):
        self.cache[domain] = DomainInfo(domain)

    def close_domain(self, domain):
        del self.cache[domain]

    def process_item(self, domain, response, item):
        info = self.cache[domain]
        urls = self.get_urls_from_item(item, info)
        assert urls is None or hasattr(urls, '__iter__'), \
                'get_urls_from_item should return None or iterable'

        lst = []
        for url in urls or ():
            request = url if isinstance(url, Request) else Request(url=url)
            dfd = self._enqueue(request, info)
            dfd.addCallbacks(
                    callback=self.new_item_media,
                    callbackArgs=(item, request, info),
                    errback=self.failed_item_media,
                    errbackArgs=(item, request, info),
                    )
            lst.append(dfd)

        dlst = defer.DeferredList(lst, consumeErrors=False)
        dlst.addBoth(lambda _: self.item_completed(item, info))
        return dlst

    def _enqueue(self, request, info):
        result = self.media_to_download(request, info)
        if result is not None:
            return defer_result(result)

        fp = request.fingerprint()
        if fp in info.downloaded:
            return defer_result(info.downloaded[fp])

        if fp not in info.downloading:
            self._download(request, info, fp)

        wad = defer.Deferred()
        waiting = info.waiting.setdefault(fp, []).append(wad)
        return wad

    def _download(self, request, info, fp):
        dwld = mustbe_deferred(self.download(request, info))
        dwld.addCallbacks(
                callback=self.media_downloaded,
                callbackArgs=(request, info),
                errback=self.media_failure,
                errbackArgs=(request, info),
                )
        dwld.addBoth(self._downloaded, info, fp)
        info.downloading[fp] = (request, dwld)

    def _downloaded(self, result, info, fp):
        info.downloaded[fp] = result # cache result
        waiting = info.waiting[fp] # client list
        del info.waiting[fp]
        del info.downloading[fp]
        for wad in waiting:
            defer_result(result).chainDeferred(wad)


    ### Overradiable Interface
    def download(self, request, info):
        """ Defines how to request the download of media

        Default gives high priority to media requests and use scheduler,
        shouldn't be necessary to override.

        This methods is called only if result for request isn't cached,
        request fingerprint is used as cache key.

        """
        return scrapyengine.schedule(request, info.spider, priority=0)

    def media_to_download(self, request, info):
        """ Ongoing request hook pre-cache

        This method is called every time an item media is enqueue for download.

        returning a non-None value implies:
            - call `new_item_media` with this value as input unless value is Failure instance
            - call `failed_item_media` if value is Failure instance
            - prevent downloading, this means calling `download` method.
            - prevent taking the value from the cached result for this request.

        Take in count that this method doesn't cache returned value as request result.

        Override `download` method if you want to hook after checking for cached
        result, and if you want to store returned valued as result for request.

        """

    def get_urls_from_item(self, item, info):
        """ Return the urls or Request objects to download for this item

        Should return None or an iterable

        Defaults return None (no media to download)

        """

    def media_downloaded(self, response, request, info):
        """ Method called on success download of media request

        Return value is cached and used as input for `new_item_media` method.
        Default implementation returns None.

        WARNING: returning the response object can eat your memory.

        """

    def media_failure(self, failure, request, info):
        """ Method called when media request failed due to any kind of download error.

        Return value is cached and used as input for `failed_item_media` method.
        Default implementation returns same Failure object.
        """
        return failure

    def new_item_media(self, result, item, request, info):
        """ Method to handle result of requested media for item.

        result is the return value of `media_downloaded` hook, or the non-Failure instance
        returned by `media_failure` hook.

        return value of this method isn't important and is recommended to return None.
        """

    def failed_item_media(self, failure, item, request, info):
        """ Method to handle failed result of requested media for item.

        result is the returned Failure instance of `media_failure` hook, or Failure instance
        of an exception raised by `media_downloaded` hook.

        return value of this method isn't important and is recommended to return None.
        """

    def item_completed(self, item, info):
        """ Method called when all media requests for a single item has returned a result or failure.

        The return value of this method is used as output of pipeline stage.

        `item_completed` can return item itself or raise DropItem exception.

        Default returns item
        """
        return item

