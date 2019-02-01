from email.utils import formatdate
from twisted.internet import defer
from twisted.internet.error import TimeoutError, DNSLookupError, \
        ConnectionRefusedError, ConnectionDone, ConnectError, \
        ConnectionLost, TCPTimedOutError
from twisted.web.client import ResponseFailed
from scrapy import signals
from scrapy.exceptions import NotConfigured, IgnoreRequest
from scrapy.utils.misc import load_object


class HttpCacheMiddleware(object):
    """This middleware provides low-level cache to all HTTP requests and responses.
    It has to be combined with a cache storage backend as well as a cache policy.

    Scrapy ships with three HTTP cache storage backends:

        * :ref:`httpcache-storage-fs`
        * :ref:`httpcache-storage-dbm`
        * :ref:`httpcache-storage-leveldb`

    You can change the HTTP cache storage backend with the :setting:`HTTPCACHE_STORAGE`
    setting. Or you can also implement your own storage backend.

    Scrapy ships with two HTTP cache policies:

        * :ref:`httpcache-policy-rfc2616`
        * :ref:`httpcache-policy-dummy`

    You can change the HTTP cache policy with the :setting:`HTTPCACHE_POLICY`
    setting. Or you can also implement your own policy.

    .. reqmeta:: dont_cache

    You can also avoid caching a response on every policy using :reqmeta:`dont_cache` meta key equals `True`.

    .. _httpcache-policy-dummy:

    .. rubric:: Dummy policy (default)

    This policy has no awareness of any HTTP Cache-Control directives.
    Every request and its corresponding response are cached.  When the same
    request is seen again, the response is returned without transferring
    anything from the Internet.

    The Dummy policy is useful for testing spiders faster (without having
    to wait for downloads every time) and for trying your spider offline,
    when an Internet connection is not available. The goal is to be able to
    "replay" a spider run *exactly as it ran before*.

    In order to use this policy, set:

    * :setting:`HTTPCACHE_POLICY` to ``scrapy.extensions.httpcache.DummyPolicy``


    .. _httpcache-policy-rfc2616:

    .. rubric:: RFC2616 policy

    This policy provides a RFC2616 compliant HTTP cache, i.e. with HTTP
    Cache-Control awareness, aimed at production and used in continuous
    runs to avoid downloading unmodified data (to save bandwidth and speed up crawls).

    what is implemented:

    * Do not attempt to store responses/requests with `no-store` cache-control directive set
    * Do not serve responses from cache if `no-cache` cache-control directive is set even for fresh responses
    * Compute freshness lifetime from `max-age` cache-control directive
    * Compute freshness lifetime from `Expires` response header
    * Compute freshness lifetime from `Last-Modified` response header (heuristic used by Firefox)
    * Compute current age from `Age` response header
    * Compute current age from `Date` header
    * Revalidate stale responses based on `Last-Modified` response header
    * Revalidate stale responses based on `ETag` response header
    * Set `Date` header for any received response missing it
    * Support `max-stale` cache-control directive in requests

    This allows spiders to be configured with the full RFC2616 cache policy,
    but avoid revalidation on a request-by-request basis, while remaining
    conformant with the HTTP spec.

    Example:

    Add `Cache-Control: max-stale=600` to Request headers to accept responses that
    have exceeded their expiration time by no more than 600 seconds.

    See also: RFC2616, 14.9.3

    what is missing:

    * `Pragma: no-cache` support https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.9.1
    * `Vary` header support https://www.w3.org/Protocols/rfc2616/rfc2616-sec13.html#sec13.6
    * Invalidation after updates or deletes https://www.w3.org/Protocols/rfc2616/rfc2616-sec13.html#sec13.10
    * ... probably others ..

    In order to use this policy, set:

    * :setting:`HTTPCACHE_POLICY` to ``scrapy.extensions.httpcache.RFC2616Policy``


    .. _httpcache-storage-fs:

    .. rubric:: Filesystem storage backend (default)

    File system storage backend is available for the HTTP cache middleware.

    In order to use this storage backend, set:

    * :setting:`HTTPCACHE_STORAGE` to ``scrapy.extensions.httpcache.FilesystemCacheStorage``

    Each request/response pair is stored in a different directory containing
    the following files:

    * ``request_body`` - the plain request body
    * ``request_headers`` - the request headers (in raw HTTP format)
    * ``response_body`` - the plain response body
    * ``response_headers`` - the request headers (in raw HTTP format)
    * ``meta`` - some metadata of this cache resource in Python ``repr()`` format
      (grep-friendly format)
    * ``pickled_meta`` - the same metadata in ``meta`` but pickled for more
      efficient deserialization

    The directory name is made from the request fingerprint (see
    ``scrapy.utils.request.fingerprint``), and one level of subdirectories is
    used to avoid creating too many files into the same directory (which is
    inefficient in many file systems). An example directory could be::

    /path/to/cache/dir/example.com/72/72811f648e718090f041317756c03adb0ada46c7

    .. _httpcache-storage-dbm:

    .. rubric:: DBM storage backend

    .. versionadded:: 0.13

    A DBM_ storage backend is also available for the HTTP cache middleware.

    By default, it uses the anydbm_ module, but you can change it with the
    :setting:`HTTPCACHE_DBM_MODULE` setting.

    In order to use this storage backend, set:

    * :setting:`HTTPCACHE_STORAGE` to ``scrapy.extensions.httpcache.DbmCacheStorage``

    .. _httpcache-storage-leveldb:

    .. rubric:: LevelDB storage backend

    .. versionadded:: 0.23

    A LevelDB_ storage backend is also available for the HTTP cache middleware.

    This backend is not recommended for development because only one process can
    access LevelDB databases at the same time, so you can't run a crawl and open
    the scrapy shell in parallel for the same spider.

    In order to use this storage backend:

    * set :setting:`HTTPCACHE_STORAGE` to ``scrapy.extensions.httpcache.LeveldbCacheStorage``
    * install `LevelDB python bindings`_ like ``pip install leveldb``

    .. _LevelDB: https://github.com/google/leveldb
    .. _leveldb python bindings: https://pypi.python.org/pypi/leveldb


    .. rubric:: HTTPCache middleware settings

    The :class:`HttpCacheMiddleware` can be configured through the following
    settings:

    .. setting:: HTTPCACHE_ENABLED

    .. rubric:: HTTPCACHE_ENABLED

    .. versionadded:: 0.11

    Default: ``False``

    Whether the HTTP cache will be enabled.

    .. versionchanged:: 0.11

    Before 0.11, :setting:`HTTPCACHE_DIR` was used to enable cache.

    .. setting:: HTTPCACHE_EXPIRATION_SECS

    .. rubric:: HTTPCACHE_EXPIRATION_SECS

    Default: ``0``

    Expiration time for cached requests, in seconds.

    Cached requests older than this time will be re-downloaded. If zero, cached
    requests will never expire.

    .. versionchanged:: 0.11

    Before 0.11, zero meant cached requests always expire.

    .. setting:: HTTPCACHE_DIR

    .. rubric:: HTTPCACHE_DIR

    Default: ``'httpcache'``

    The directory to use for storing the (low-level) HTTP cache. If empty, the HTTP
    cache will be disabled. If a relative path is given, is taken relative to the
    project data dir. For more info see: :ref:`topics-project-structure`.

    .. setting:: HTTPCACHE_IGNORE_HTTP_CODES

    .. rubric:: HTTPCACHE_IGNORE_HTTP_CODES

    .. versionadded:: 0.10

    Default: ``[]``

    Don't cache response with these HTTP codes.

    .. setting:: HTTPCACHE_IGNORE_MISSING

    .. rubric:: HTTPCACHE_IGNORE_MISSING

    Default: ``False``

    If enabled, requests not found in the cache will be ignored instead of downloaded.

    .. setting:: HTTPCACHE_IGNORE_SCHEMES

    .. rubric:: HTTPCACHE_IGNORE_SCHEMES

    .. versionadded:: 0.10

    Default: ``['file']``

    Don't cache responses with these URI schemes.

    .. setting:: HTTPCACHE_STORAGE

    .. rubric:: HTTPCACHE_STORAGE

    Default: ``'scrapy.extensions.httpcache.FilesystemCacheStorage'``

    The class which implements the cache storage backend.

    .. setting:: HTTPCACHE_DBM_MODULE

    .. rubric:: HTTPCACHE_DBM_MODULE

    .. versionadded:: 0.13

    Default: ``'anydbm'``

    The database module to use in the :ref:`DBM storage backend
    <httpcache-storage-dbm>`. This setting is specific to the DBM backend.

    .. setting:: HTTPCACHE_POLICY

    .. rubric:: HTTPCACHE_POLICY

    .. versionadded:: 0.18

    Default: ``'scrapy.extensions.httpcache.DummyPolicy'``

    The class which implements the cache policy.

    .. setting:: HTTPCACHE_GZIP

    .. rubric:: HTTPCACHE_GZIP

    .. versionadded:: 1.0

    Default: ``False``

    If enabled, will compress all cached data with gzip.
    This setting is specific to the Filesystem backend.

    .. setting:: HTTPCACHE_ALWAYS_STORE

    .. rubric:: HTTPCACHE_ALWAYS_STORE

    .. versionadded:: 1.1

    Default: ``False``

    If enabled, will cache pages unconditionally.

    A spider may wish to have all responses available in the cache, for
    future use with `Cache-Control: max-stale`, for instance. The
    DummyPolicy caches all responses but never revalidates them, and
    sometimes a more nuanced policy is desirable.

    This setting still respects `Cache-Control: no-store` directives in responses.
    If you don't want that, filter `no-store` out of the Cache-Control headers in
    responses you feedto the cache middleware.

    .. setting:: HTTPCACHE_IGNORE_RESPONSE_CACHE_CONTROLS

    .. rubric:: HTTPCACHE_IGNORE_RESPONSE_CACHE_CONTROLS

    .. versionadded:: 1.1

    Default: ``[]``

    List of Cache-Control directives in responses to be ignored.

    Sites often set "no-store", "no-cache", "must-revalidate", etc., but get
    upset at the traffic a spider can generate if it respects those
    directives. This allows to selectively ignore Cache-Control directives
    that are known to be unimportant for the sites being crawled.

    We assume that the spider will not issue Cache-Control directives
    in requests unless it actually needs them, so directives in requests are
    not filtered.
    """

    DOWNLOAD_EXCEPTIONS = (defer.TimeoutError, TimeoutError, DNSLookupError,
                           ConnectionRefusedError, ConnectionDone, ConnectError,
                           ConnectionLost, TCPTimedOutError, ResponseFailed,
                           IOError)

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
        if request.meta.get('dont_cache', False):
            return

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
        if request.meta.get('dont_cache', False):
            return response

        # Skip cached responses and uncacheable requests
        if 'cached' in response.flags or '_dont_cache' in request.meta:
            request.meta.pop('_dont_cache', None)
            return response

        # RFC2616 requires origin server to set Date header,
        # https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.18
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

    def process_exception(self, request, exception, spider):
        cachedresponse = request.meta.pop('cached_response', None)
        if cachedresponse is not None and isinstance(exception, self.DOWNLOAD_EXCEPTIONS):
            self.stats.inc_value('httpcache/errorrecovery', spider=spider)
            return cachedresponse

    def _cache_response(self, spider, response, request, cachedresponse):
        if self.policy.should_cache_response(response, request):
            self.stats.inc_value('httpcache/store', spider=spider)
            self.storage.store_response(spider, request, response)
        else:
            self.stats.inc_value('httpcache/uncacheable', spider=spider)
