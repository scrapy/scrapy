from scrapy import signals
from scrapy.exceptions import NotConfigured, IgnoreRequest
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import load_object


class HttpCacheMiddleware(object):

    def __init__(self, settings, stats):
        if not settings.getbool('HTTPCACHE_ENABLED'):
            raise NotConfigured
        self.storage = load_object(settings['HTTPCACHE_STORAGE'])(settings)
        self.ignore_missing = settings.getbool('HTTPCACHE_IGNORE_MISSING')
        self.ignore_schemes = settings.getlist('HTTPCACHE_IGNORE_SCHEMES')
        self.ignore_http_codes = map(int, settings.getlist('HTTPCACHE_IGNORE_HTTP_CODES'))
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler):
        o = cls(crawler.settings, crawler.stats)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        return o

    def spider_opened(self, spider):
        self.storage.open_spider(spider)

    def spider_closed(self, spider):
        self.storage.close_spider(spider)

    def process_request(self, request, spider):
        if not self.is_cacheable(request):
            return
        response = self.storage.retrieve_response(spider, request)
        if response and self.is_cacheable_response(response):
            response.flags.append('cached')
            self.stats.inc_value('httpcache/hits', spider=spider)
            return response

        self.stats.inc_value('httpcache/misses', spider=spider)
        if self.ignore_missing:
            raise IgnoreRequest("Ignored request not in cache: %s" % request)

    def process_response(self, request, response, spider):
        if (self.is_cacheable(request)
            and self.is_cacheable_response(response)
            and 'cached' not in response.flags):
            self.storage.store_response(spider, request, response)
            self.stats.inc_value('httpcache/store', spider=spider)
        return response

    def is_cacheable_response(self, response):
        return response.status not in self.ignore_http_codes

    def is_cacheable(self, request):
        return urlparse_cached(request).scheme not in self.ignore_schemes


from scrapy.contrib.httpcache import FilesystemCacheStorage as _FilesystemCacheStorage


class FilesystemCacheStorage(_FilesystemCacheStorage):

    def __init__(self, *args, **kwargs):
        import warnings
        from scrapy.exceptions import ScrapyDeprecationWarning
        warnings.warn('Importing FilesystemCacheStorage from '
                      'scrapy.contrib.downloadermiddlware.httpcache is '
                      'deprecated, use scrapy.contrib.httpcache instead.',
                      category=ScrapyDeprecationWarning, stacklevel=1)
        super(_FilesystemCacheStorage, self).__init__(*args, **kwargs)
