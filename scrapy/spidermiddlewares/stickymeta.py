"""
StickyMeta middleware transfers specified meta keys to further
requests in spider request chain.

Sticky meta keys can be configured either by:
* Setting STICKY_META_KEYS eg:
    STICKY_META_KEYS = ['key1', 'key2']
* Spider attribute sticky_meta eg:
    spider.sticky_meta = ['key1','key2']
* Meta attribute "sticky" eg:
    Request(meta={'sticky': ['foo'], 'foo': 'bar'})
resolve priority is meta > spider attribute > setting
"""
from scrapy import Request


class StickyMeta:
    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def __init__(self, settings):
        self.settings_sticky_meta = settings.getlist('STICKY_META')

    def process_spider_output(self, response, result, spider):
        # without attached request response will not have meta to pass on
        if not response.request:
            for value in result:
                yield value
            return

        spider_sticky_meta = getattr(spider, 'sticky_meta', None)
        for request in result:
            if not isinstance(request, Request):
                yield request
                continue
            # priority: meta > spider attribute > setting
            sticky = response.meta.get(
                'sticky',
                spider_sticky_meta if spider_sticky_meta is not None else self.settings_sticky_meta
            )
            for k, v in response.meta.items():
                if k in sticky and k not in request.meta:
                    request.meta[k] = v
            yield request
