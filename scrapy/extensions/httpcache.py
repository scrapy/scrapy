import gzip
import logging
import os
import pickle
from email.utils import mktime_tz, parsedate_tz
from importlib import import_module
from time import time
from weakref import WeakKeyDictionary

from w3lib.http import headers_raw_to_dict, headers_dict_to_raw

from scrapy.http import Headers, Response
from scrapy.responsetypes import responsetypes
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.project import data_path
from scrapy.utils.python import to_bytes, to_unicode
from scrapy.utils.request import request_fingerprint


logger = logging.getLogger(__name__)


class DummyPolicy:

    def __init__(self, settings):
        self.ignore_schemes = settings.getlist('HTTPCACHE_IGNORE_SCHEMES')
        self.ignore_http_codes = [int(x) for x in settings.getlist('HTTPCACHE_IGNORE_HTTP_CODES')]

    def should_cache_request(self, request):
        return urlparse_cached(request).scheme not in self.ignore_schemes

    def should_cache_response(self, response, request):
        return response.status not in self.ignore_http_codes

    def is_cached_response_fresh(self, cachedresponse, request):
        return True

    def is_cached_response_valid(self, cachedresponse, response, request):
        return True


class RFC2616Policy:

    MAXAGE = 3600 * 24 * 365  # one year

    def __init__(self, settings):
        self.always_store = settings.getbool('HTTPCACHE_ALWAYS_STORE')
        self.ignore_schemes = settings.getlist('HTTPCACHE_IGNORE_SCHEMES')
        self._cc_parsed = WeakKeyDictionary()
        self.ignore_response_cache_controls = [
            to_bytes(cc) for cc in settings.getlist('HTTPCACHE_IGNORE_RESPONSE_CACHE_CONTROLS')
        ]

    def _parse_cachecontrol(self, r):
        if r not in self._cc_parsed:
            cch = r.headers.get(b'Cache-Control', b'')
            parsed = parse_cachecontrol(cch)
            if isinstance(r, Response):
                for key in self.ignore_response_cache_controls:
                    parsed.pop(key, None)
            self._cc_parsed[r] = parsed
        return self._cc_parsed[r]

    def should_cache_request(self, request):
        if urlparse_cached(request).scheme in self.ignore_schemes:
            return False
        cc = self._parse_cachecontrol(request)
        # obey user-agent directive "Cache-Control: no-store"
        if b'no-store' in cc:
            return False
        # Any other is eligible for caching
        return True

    def should_cache_response(self, response, request):
        # What is cacheable - https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.9.1
        # Response cacheability - https://www.w3.org/Protocols/rfc2616/rfc2616-sec13.html#sec13.4
        # Status code 206 is not included because cache can not deal with partial contents
        cc = self._parse_cachecontrol(response)
        # obey directive "Cache-Control: no-store"
        if b'no-store' in cc:
            return False
        # Never cache 304 (Not Modified) responses
        elif response.status == 304:
            return False
        # Cache unconditionally if configured to do so
        elif self.always_store:
            return True
        # Any hint on response expiration is good
        elif b'max-age' in cc or b'Expires' in response.headers:
            return True
        # Firefox fallbacks this statuses to one year expiration if none is set
        elif response.status in (300, 301, 308):
            return True
        # Other statuses without expiration requires at least one validator
        elif response.status in (200, 203, 401):
            return b'Last-Modified' in response.headers or b'ETag' in response.headers
        # Any other is probably not eligible for caching
        # Makes no sense to cache responses that does not contain expiration
        # info and can not be revalidated
        else:
            return False

    def is_cached_response_fresh(self, cachedresponse, request):
        cc = self._parse_cachecontrol(cachedresponse)
        ccreq = self._parse_cachecontrol(request)
        if b'no-cache' in cc or b'no-cache' in ccreq:
            return False

        now = time()
        freshnesslifetime = self._compute_freshness_lifetime(cachedresponse, request, now)
        currentage = self._compute_current_age(cachedresponse, request, now)

        reqmaxage = self._get_max_age(ccreq)
        if reqmaxage is not None:
            freshnesslifetime = min(freshnesslifetime, reqmaxage)

        if currentage < freshnesslifetime:
            return True

        if b'max-stale' in ccreq and b'must-revalidate' not in cc:
            # From RFC2616: "Indicates that the client is willing to
            # accept a response that has exceeded its expiration time.
            # If max-stale is assigned a value, then the client is
            # willing to accept a response that has exceeded its
            # expiration time by no more than the specified number of
            # seconds. If no value is assigned to max-stale, then the
            # client is willing to accept a stale response of any age."
            staleage = ccreq[b'max-stale']
            if staleage is None:
                return True

            try:
                if currentage < freshnesslifetime + max(0, int(staleage)):
                    return True
            except ValueError:
                pass

        # Cached response is stale, try to set validators if any
        self._set_conditional_validators(request, cachedresponse)
        return False

    def is_cached_response_valid(self, cachedresponse, response, request):
        # Use the cached response if the new response is a server error,
        # as long as the old response didn't specify must-revalidate.
        if response.status >= 500:
            cc = self._parse_cachecontrol(cachedresponse)
            if b'must-revalidate' not in cc:
                return True

        # Use the cached response if the server says it hasn't changed.
        return response.status == 304

    def _set_conditional_validators(self, request, cachedresponse):
        if b'Last-Modified' in cachedresponse.headers:
            request.headers[b'If-Modified-Since'] = cachedresponse.headers[b'Last-Modified']

        if b'ETag' in cachedresponse.headers:
            request.headers[b'If-None-Match'] = cachedresponse.headers[b'ETag']

    def _get_max_age(self, cc):
        try:
            return max(0, int(cc[b'max-age']))
        except (KeyError, ValueError):
            return None

    def _compute_freshness_lifetime(self, response, request, now):
        # Reference nsHttpResponseHead::ComputeFreshnessLifetime
        # https://dxr.mozilla.org/mozilla-central/source/netwerk/protocol/http/nsHttpResponseHead.cpp#706
        cc = self._parse_cachecontrol(response)
        maxage = self._get_max_age(cc)
        if maxage is not None:
            return maxage

        # Parse date header or synthesize it if none exists
        date = rfc1123_to_epoch(response.headers.get(b'Date')) or now

        # Try HTTP/1.0 Expires header
        if b'Expires' in response.headers:
            expires = rfc1123_to_epoch(response.headers[b'Expires'])
            # When parsing Expires header fails RFC 2616 section 14.21 says we
            # should treat this as an expiration time in the past.
            return max(0, expires - date) if expires else 0

        # Fallback to heuristic using last-modified header
        # This is not in RFC but on Firefox caching implementation
        lastmodified = rfc1123_to_epoch(response.headers.get(b'Last-Modified'))
        if lastmodified and lastmodified <= date:
            return (date - lastmodified) / 10

        # This request can be cached indefinitely
        if response.status in (300, 301, 308):
            return self.MAXAGE

        # Insufficient information to compute fresshness lifetime
        return 0

    def _compute_current_age(self, response, request, now):
        # Reference nsHttpResponseHead::ComputeCurrentAge
        # https://dxr.mozilla.org/mozilla-central/source/netwerk/protocol/http/nsHttpResponseHead.cpp#658
        currentage = 0
        # If Date header is not set we assume it is a fast connection, and
        # clock is in sync with the server
        date = rfc1123_to_epoch(response.headers.get(b'Date')) or now
        if now > date:
            currentage = now - date

        if b'Age' in response.headers:
            try:
                age = int(response.headers[b'Age'])
                currentage = max(currentage, age)
            except ValueError:
                pass

        return currentage


class DbmCacheStorage:

    def __init__(self, settings):
        self.cachedir = data_path(settings['HTTPCACHE_DIR'], createdir=True)
        self.expiration_secs = settings.getint('HTTPCACHE_EXPIRATION_SECS')
        self.dbmodule = import_module(settings['HTTPCACHE_DBM_MODULE'])
        self.db = None

    def open_spider(self, spider):
        dbpath = os.path.join(self.cachedir, f'{spider.name}.db')
        self.db = self.dbmodule.open(dbpath, 'c')

        logger.debug("Using DBM cache storage in %(cachepath)s" % {'cachepath': dbpath}, extra={'spider': spider})

    def close_spider(self, spider):
        self.db.close()

    def retrieve_response(self, spider, request):
        data = self._read_data(spider, request)
        if data is None:
            return  # not cached
        url = data['url']
        status = data['status']
        headers = Headers(data['headers'])
        body = data['body']
        respcls = responsetypes.from_args(headers=headers, url=url)
        response = respcls(url=url, headers=headers, status=status, body=body)
        return response

    def store_response(self, spider, request, response):
        key = self._request_key(request)
        data = {
            'status': response.status,
            'url': response.url,
            'headers': dict(response.headers),
            'body': response.body,
        }
        self.db[f'{key}_data'] = pickle.dumps(data, protocol=4)
        self.db[f'{key}_time'] = str(time())

    def _read_data(self, spider, request):
        key = self._request_key(request)
        db = self.db
        tkey = f'{key}_time'
        if tkey not in db:
            return  # not found

        ts = db[tkey]
        if 0 < self.expiration_secs < time() - float(ts):
            return  # expired

        return pickle.loads(db[f'{key}_data'])

    def _request_key(self, request):
        return request_fingerprint(request)


class FilesystemCacheStorage:

    def __init__(self, settings):
        self.cachedir = data_path(settings['HTTPCACHE_DIR'])
        self.expiration_secs = settings.getint('HTTPCACHE_EXPIRATION_SECS')
        self.use_gzip = settings.getbool('HTTPCACHE_GZIP')
        self._open = gzip.open if self.use_gzip else open

    def open_spider(self, spider):
        logger.debug("Using filesystem cache storage in %(cachedir)s" % {'cachedir': self.cachedir},
                     extra={'spider': spider})

    def close_spider(self, spider):
        pass

    def retrieve_response(self, spider, request):
        """Return response if present in cache, or None otherwise."""
        metadata = self._read_meta(spider, request)
        if metadata is None:
            return  # not cached
        rpath = self._get_request_path(spider, request)
        with self._open(os.path.join(rpath, 'response_body'), 'rb') as f:
            body = f.read()
        with self._open(os.path.join(rpath, 'response_headers'), 'rb') as f:
            rawheaders = f.read()
        url = metadata.get('response_url')
        status = metadata['status']
        headers = Headers(headers_raw_to_dict(rawheaders))
        respcls = responsetypes.from_args(headers=headers, url=url)
        response = respcls(url=url, headers=headers, status=status, body=body)
        return response

    def store_response(self, spider, request, response):
        """Store the given response in the cache."""
        rpath = self._get_request_path(spider, request)
        if not os.path.exists(rpath):
            os.makedirs(rpath)
        metadata = {
            'url': request.url,
            'method': request.method,
            'status': response.status,
            'response_url': response.url,
            'timestamp': time(),
        }
        with self._open(os.path.join(rpath, 'meta'), 'wb') as f:
            f.write(to_bytes(repr(metadata)))
        with self._open(os.path.join(rpath, 'pickled_meta'), 'wb') as f:
            pickle.dump(metadata, f, protocol=4)
        with self._open(os.path.join(rpath, 'response_headers'), 'wb') as f:
            f.write(headers_dict_to_raw(response.headers))
        with self._open(os.path.join(rpath, 'response_body'), 'wb') as f:
            f.write(response.body)
        with self._open(os.path.join(rpath, 'request_headers'), 'wb') as f:
            f.write(headers_dict_to_raw(request.headers))
        with self._open(os.path.join(rpath, 'request_body'), 'wb') as f:
            f.write(request.body)

    def _get_request_path(self, spider, request):
        key = request_fingerprint(request)
        return os.path.join(self.cachedir, spider.name, key[0:2], key)

    def _read_meta(self, spider, request):
        rpath = self._get_request_path(spider, request)
        metapath = os.path.join(rpath, 'pickled_meta')
        if not os.path.exists(metapath):
            return  # not found
        mtime = os.stat(metapath).st_mtime
        if 0 < self.expiration_secs < time() - mtime:
            return  # expired
        with self._open(metapath, 'rb') as f:
            return pickle.load(f)


def parse_cachecontrol(header):
    """Parse Cache-Control header

    https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.9

    >>> parse_cachecontrol(b'public, max-age=3600') == {b'public': None,
    ...                                                 b'max-age': b'3600'}
    True
    >>> parse_cachecontrol(b'') == {}
    True

    """
    directives = {}
    for directive in header.split(b','):
        key, sep, val = directive.strip().partition(b'=')
        if key:
            directives[key.lower()] = val if sep else None
    return directives


def rfc1123_to_epoch(date_str):
    try:
        date_str = to_unicode(date_str, encoding='ascii')
        return mktime_tz(parsedate_tz(date_str))
    except Exception:
        return None
