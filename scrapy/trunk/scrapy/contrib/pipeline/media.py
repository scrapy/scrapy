from twisted.internet import defer
from twisted.python import failure

from scrapy.core import log
from scrapy.http import Request
from scrapy.core.engine import scrapyengine
from scrapy.spider import spiders
from scrapy.core.exceptions import DropItem, NotConfigured
from scrapy.core.exceptions import HttpException
from scrapy.stats import stats
from scrapy.utils.misc import chain_deferred, mustbe_deferred, defer_result
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

    def process_item(self, domain, response, item):
        urls = self.get_urls_from_item(item)
        info = self.cache[domain]

        lst = []
        for url in urls or ():
            dfd = self._enqueue(url, info)
            dfd.addCallbacks(
                    callback=self.new_item_media,
                    callbackArgs=(item, url),
                    errback=self.failed_item_media,
                    errbackArgs=(item, url),
                    )
            lst.append(dfd)

        dlst = defer.DeferredList(lst, consumeErrors=False)
        dlst.addBoth(lambda _: self.item_completed(item))
        return dlst

    def _enqueue(self, url, info):
        request = self.media_to_download(url, info)
        if not isinstance(request, Request):
            return defer_result(request)

        fp = request.fingerprint()
        if fp in info.downloaded:
            return defer_result(info.downloaded[fp])

        if fp not in info.downloading:
            self._download(request, info, fp)

        wad = defer.Deferred()
        waiting = info.waiting.setdefault(fp, []).append(wad)
        return wad

    def _download(self, request, info, fp):
        dwld = mustbe_deferred(self.request(request, info))
        dwld.addCallbacks(self.media_downloaded, self.media_failure)
        dwld.addBoth(self._download_finished, info, fp)
        info.downloading[fp] = (request, dwld)

    def _download_finished(self, result, info, fp):
        info.downloaded[fp] = result # cache result
        del info.downloading[fp]

        waiting = info.waiting[fp] # client list
        del info.waiting[fp]

        for wad in waiting:
            defer_result(result).chainDeferred(wad)

    def request(self, request, info):
        return scrapyengine.schedule(request, info.spider, priority=0)

    def open_domain(self, domain):
        self.cache[domain] = DomainInfo(domain)

    def close_domain(self, domain):
        del self.cache[domain]

    ### Overradiable Interface
    def get_urls_from_item(self, item):
        return item.image_urls

    def media_to_download(self, url, info):
        return Request(url=url)

    def media_downloaded(self, response):
        pass

    def media_failure(self, _failure):
        return _failure

    def new_item_media(self, result, item, url):
        pass

    def failed_item_media(self, _failure, item, url):
        pass

    def item_completed(self, item):
        return item




