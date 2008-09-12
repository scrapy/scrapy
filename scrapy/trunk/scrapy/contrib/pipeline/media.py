from __future__ import with_statement

from twisted.internet import defer
from twisted.python import failure
from pprint import pprint

from scrapy.core import log
from scrapy.http import Request
from scrapy.core.engine import scrapyengine
from scrapy.spider import spiders
from scrapy.core.exceptions import DropItem, NotConfigured
from scrapy.core.exceptions import HttpException
from scrapy.stats import stats
from scrapy.utils.misc import chain_deferred, mustbe_deferred
from scrapy.conf import settings

class DomainInfo(object):
    def __init__(self, domain):
        self.domain = domain
        self.spider = spiders.fromdomain(domain)
        self.downloading = {}
        self.downloaded = {}
        self.waiting = {}


class MediaPipeline(object):
    def __init__(self):
        self.cache = {}

    def process_item(self, domain, response, item):
        urls = self.get_urls_from_item(item)
        info = self.cache[domain]

        ulist = []
        for url in urls:
            dfd = self._enqueue(url, info)
            dfd.addCallbacks(
                    callback=self.new_item_media,
                    callbackArgs=(item,),
                    errback=self.failed_item_media,
                    errbackArgs=(item,),
                    )
            ulist.append(dfd)

        dlist = defer.DeferredList(ulist, consumeErrors=False)
        dlist.addBoth(self._item_completed, item)
        return dlist

    def _enqueue(self, url, info):
        wad = defer.Deferred()
        wad.addBoth(lambda _: pprint(_))

        request = Request(url=url)
        fp = request.fingerprint()
        waiting = info.waiting.setdefault(fp, []).append(wad)

        if fp in info.downloading:
            return

        dwld = scrapyengine.schedule(request, info.spider, priority=0)
        dwld.addCallbacks(self.media_downloaded, self.media_failure)
        dwld.addBoth(self._download_finished, info, fp)
        info.downloading[fp] = (request, dwld)
        return wad

    def _download_finished(self, result, info, fp):
        del info.downloading[fp]
        info.downloaded[fp] = result # cache result
        waiting = info.waiting[fp]

        isfail = isinstance(result, failure.Failure)
        for wad in waiting:
            tocall = wad.errback if isfail else wad.callback
            pprint(tocall)
            tocall(result)
        return result

    def _item_completed(self, result, item):
        return self.item_completed(item) #dummy as hell

    def open_domain(self, domain):
        self.cache[domain] = DomainInfo(domain)

    def close_domain(self, domain):
        print '##### closing'
        del self.cache[domain]

    ### Overradiable Interface

    def get_urls_from_item(self, item):
        print '##### get_urls_from_item'
        return item.image_urls

    def media_to_download(self, url):
        print '##### media_to_download'
        pass

    def media_downloaded(self, response):
        print '##### media_downloaded'
        pass

    def media_failure(self, _failure):
        print '##### media_failure'
        return _failure

    def new_item_media(self, result, item):
        print '##### new_item_media'
        pass

    def failed_item_media(self, _failure, item):
        print '##### failed_item_media'
        pass

    def item_completed(self, item):
        print '##### item_completed'
        return item



