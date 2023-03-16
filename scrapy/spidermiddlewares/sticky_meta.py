from scrapy.exceptions import NotConfigured
from scrapy.http import Request


class StickyMetaParamsMiddleware(object):
    """Forward a configurable list of meta keys through subsequent requests"""

    @classmethod
    def from_crawler(cls, crawler):
        keys_to_sticky = getattr(crawler.spider, "sticky_meta_keys", [])
        if not keys_to_sticky:
            raise NotConfigured
        return cls(keys_to_sticky)

    def __init__(self, keys_to_sticky):
        self.keys_to_sticky = keys_to_sticky

    def process_spider_output(self, response, result, spider):
        sticky_meta = {
            k: response.meta[k] for k in self.keys_to_sticky if k in response.meta
        }
        for r in result:
            if not isinstance(r, Request):
                yield r
                continue
            for k, v in sticky_meta.items():
                if k not in r.meta:
                    r.meta[k] = v
            yield r
