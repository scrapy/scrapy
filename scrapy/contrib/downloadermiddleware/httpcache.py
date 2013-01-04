from time import time
from email.utils import formatdate
from weakref import WeakKeyDictionary
from scrapy import signals
from scrapy.exceptions import NotConfigured, IgnoreRequest
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import load_object
from scrapy.contrib.httpcache import rfc1123_to_epoch, parse_cachecontrol


class DummyPolicy(object):

    def __init__(self, settings):
        self.ignore_schemes = settings.getlist('HTTPCACHE_IGNORE_SCHEMES')
        self.ignore_http_codes = map(int, settings.getlist('HTTPCACHE_IGNORE_HTTP_CODES'))

    def should_cache_request(self, request):
        return urlparse_cached(request).scheme not in self.ignore_schemes

    def should_cache_response(self, response, request):
        return response.status not in self.ignore_http_codes

    def is_cached_response_fresh(self, response, request):
        return True

    def is_cached_response_valid(self, cachedresponse, response, request):
        return True


class RFC2616Policy(object):

    MAXAGE = 3600 * 24 * 365  # one year

    def __init__(self, settings):
        self.ignore_schemes = settings.getlist('HTTPCACHE_IGNORE_SCHEMES')
        self._cc_parsed = WeakKeyDictionary()

    def _parse_cachecontrol(self, r):
        if r not in self._cc_parsed:
            cch = r.headers.get('Cache-Control', '')
            self._cc_parsed[r] = parse_cachecontrol(cch)
        return self._cc_parsed[r]

    def should_cache_request(self, request):
        if urlparse_cached(request).scheme in self.ignore_schemes:
            return False
        cc = self._parse_cachecontrol(request)
        # obey user-agent directive "Cache-Control: no-store"
        if 'no-store' in cc:
            return False
        # Any other is eligible for caching
        return True

    def should_cache_response(self, response, request):
        # What is cacheable - http://www.w3.org/Protocols/rfc2616/rfc2616-sec13.html#sec14.9.1
        # Response cacheability - http://www.w3.org/Protocols/rfc2616/rfc2616-sec13.html#sec13.4
        # Status code 206 is not included because cache can not deal with partial contents
        cc = self._parse_cachecontrol(response)
        # obey directive "Cache-Control: no-store"
        if 'no-store' in cc:
            return False
        # Never cache 304 (Not Modified) responses
        elif response.status == 304:
            return False
        # Any hint on response expiration is good
        elif 'max-age' in cc or 'Expires' in response.headers:
            return True
        # Firefox fallbacks this statuses to one year expiration if none is set
        elif response.status in (300, 301, 308):
            return True
        # Other statuses without expiration requires at least one validator
        elif response.status in (200, 203, 401):
            return 'Last-Modified' in response.headers or 'ETag' in response.headers
        # Any other is probably not eligible for caching
        # Makes no sense to cache responses that does not contain expiration
        # info and can not be revalidated
        else:
            return False

    def is_cached_response_fresh(self, cachedresponse, request):
        cc = self._parse_cachecontrol(cachedresponse)
        if 'no-cache' in cc:
            return False

        now = time()
        freshnesslifetime = self._compute_freshness_lifetime(cachedresponse, request, now)
        currentage = self._compute_current_age(cachedresponse, request, now)
        if currentage < freshnesslifetime:
            return True
        # Cached response is stale, try to set validators if any
        self._set_conditional_validators(request, cachedresponse)
        return False

    def is_cached_response_valid(self, cachedresponse, response, request):
        return response.status == 304

    def _set_conditional_validators(self, request, cachedresponse):
        if 'Last-Modified' in cachedresponse.headers:
            request.headers['If-Modified-Since'] = cachedresponse.headers['Last-Modified']

        if 'ETag' in cachedresponse.headers:
            request.headers['If-None-Match'] = cachedresponse.headers['ETag']

    def _compute_freshness_lifetime(self, response, request, now):
        # Reference nsHttpResponseHead::ComputeFresshnessLifetime
        # http://dxr.mozilla.org/mozilla-central/netwerk/protocol/http/nsHttpResponseHead.cpp.html#l259
        cc = self._parse_cachecontrol(response)
        if 'max-age' in cc:
            try:
                return max(0, int(cc['max-age']))
            except ValueError:
                pass

        # Parse date header or synthesize it if none exists
        date = rfc1123_to_epoch(response.headers.get('Date')) or now

        # Try HTTP/1.0 Expires header
        if 'Expires' in response.headers:
            expires = rfc1123_to_epoch(response.headers['Expires'])
            # When parsing Expires header fails RFC 2616 section 14.21 says we
            # should treat this as an expiration time in the past.
            return max(0, expires - date) if expires else 0

        # Fallback to heuristic using last-modified header
        # This is not in RFC but on Firefox caching implementation
        lastmodified = rfc1123_to_epoch(response.headers.get('Last-Modified'))
        if lastmodified and lastmodified <= date:
            return (date - lastmodified) / 10

        # This request can be cached indefinitely
        if response.status in (300, 301, 308):
            return self.MAXAGE

        # Insufficient information to compute fresshness lifetime
        return 0

    def _compute_current_age(self, response, request, now):
        # Reference nsHttpResponseHead::ComputeCurrentAge
        # http://dxr.mozilla.org/mozilla-central/netwerk/protocol/http/nsHttpResponseHead.cpp.html
        currentage = 0
        # If Date header is not set we assume it is a fast connection, and
        # clock is in sync with the server
        date = rfc1123_to_epoch(response.headers.get('Date')) or now
        if now > date:
            currentage = now - date

        if 'Age' in response.headers:
            try:
                age = int(response.headers['Age'])
                currentage = max(currentage, age)
            except ValueError:
                pass

        return currentage


class HttpCacheMiddleware(object):

    def __init__(self, settings, stats):
        if not settings.getbool('HTTPCACHE_ENABLED'):
            raise NotConfigured
        self.policy = load_object(settings['HTTPCACHE_POLICY'])(settings)
        self.storage = load_object(settings['HTTPCACHE_STORAGE'])(settings)
        self.ignore_missing = settings.getbool('HTTPCACHE_IGNORE_MISSING')
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
        # Skip uncacheable requests
        if not self.policy.should_cache_request(request):
            request.meta['_dont_cache'] = True  # flag as uncacheable
            return

        # Look for cached response and check if expired
        cachedresponse = self.storage.retrieve_response(spider, request)
        if cachedresponse is None:
            self.stats.inc_value('httpcache/miss', spider=spider)
            if self.ignore_missing:
                self.stats.inc_value('httpcache/ignore', spider=spider)
                raise IgnoreRequest("Ignored request not in cache: %s" % request)
            return  # first time request

        # Return cached response only if not expired
        cachedresponse.flags.append('cached')
        if self.policy.is_cached_response_fresh(cachedresponse, request):
            self.stats.inc_value('httpcache/hit', spider=spider)
            return cachedresponse

        # Keep a reference to cached response to avoid a second cache lookup on
        # process_response hook
        request.meta['cached_response'] = cachedresponse

    def process_response(self, request, response, spider):
        # Skip cached responses and uncacheable requests
        if 'cached' in response.flags or '_dont_cache' in request.meta:
            request.meta.pop('_dont_cache', None)
            return response

        # RFC2616 requires origin server to set Date header,
        # http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.18
        if 'Date' not in response.headers:
            response.headers['Date'] = formatdate(usegmt=1)

        # Do not validate first-hand responses
        cachedresponse = request.meta.pop('cached_response', None)
        if cachedresponse is None:
            self.stats.inc_value('httpcache/firsthand', spider=spider)
            self._cache_response(spider, response, request, cachedresponse)
            return response

        if self.policy.is_cached_response_valid(cachedresponse, response, request):
            self.stats.inc_value('httpcache/revalidate', spider=spider)
            return cachedresponse

        self.stats.inc_value('httpcache/invalidate', spider=spider)
        self._cache_response(spider, response, request, cachedresponse)
        return response

    def _cache_response(self, spider, response, request, cachedresponse):
        if self.policy.should_cache_response(response, request):
            self.stats.inc_value('httpcache/store', spider=spider)
            self.storage.store_response(spider, request, response)
        else:
            self.stats.inc_value('httpcache/uncacheable', spider=spider)


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
