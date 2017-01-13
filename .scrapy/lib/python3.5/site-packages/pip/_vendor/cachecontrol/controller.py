"""
The httplib2 algorithms ported for use with requests.
"""
import re
import calendar
import time
from email.utils import parsedate_tz

from pip._vendor.requests.structures import CaseInsensitiveDict

from .cache import DictCache
from .serialize import Serializer


URI = re.compile(r"^(([^:/?#]+):)?(//([^/?#]*))?([^?#]*)(\?([^#]*))?(#(.*))?")


def parse_uri(uri):
    """Parses a URI using the regex given in Appendix B of RFC 3986.

        (scheme, authority, path, query, fragment) = parse_uri(uri)
    """
    groups = URI.match(uri).groups()
    return (groups[1], groups[3], groups[4], groups[6], groups[8])


class CacheController(object):
    """An interface to see if request should cached or not.
    """
    def __init__(self, cache=None, cache_etags=True, serializer=None):
        self.cache = cache or DictCache()
        self.cache_etags = cache_etags
        self.serializer = serializer or Serializer()

    @classmethod
    def _urlnorm(cls, uri):
        """Normalize the URL to create a safe key for the cache"""
        (scheme, authority, path, query, fragment) = parse_uri(uri)
        if not scheme or not authority:
            raise Exception("Only absolute URIs are allowed. uri = %s" % uri)

        scheme = scheme.lower()
        authority = authority.lower()

        if not path:
            path = "/"

        # Could do syntax based normalization of the URI before
        # computing the digest. See Section 6.2.2 of Std 66.
        request_uri = query and "?".join([path, query]) or path
        defrag_uri = scheme + "://" + authority + request_uri

        return defrag_uri

    @classmethod
    def cache_url(cls, uri):
        return cls._urlnorm(uri)

    def parse_cache_control(self, headers):
        """
        Parse the cache control headers returning a dictionary with values
        for the different directives.
        """
        retval = {}

        cc_header = 'cache-control'
        if 'Cache-Control' in headers:
            cc_header = 'Cache-Control'

        if cc_header in headers:
            parts = headers[cc_header].split(',')
            parts_with_args = [
                tuple([x.strip().lower() for x in part.split("=", 1)])
                for part in parts if -1 != part.find("=")
            ]
            parts_wo_args = [
                (name.strip().lower(), 1)
                for name in parts if -1 == name.find("=")
            ]
            retval = dict(parts_with_args + parts_wo_args)
        return retval

    def cached_request(self, request):
        """
        Return a cached response if it exists in the cache, otherwise
        return False.
        """
        cache_url = self.cache_url(request.url)
        cc = self.parse_cache_control(request.headers)

        # non-caching states
        no_cache = True if 'no-cache' in cc else False
        if 'max-age' in cc and cc['max-age'] == 0:
            no_cache = True

        # Bail out if no-cache was set
        if no_cache:
            return False

        # It is in the cache, so lets see if it is going to be
        # fresh enough
        resp = self.serializer.loads(request, self.cache.get(cache_url))

        # Check to see if we have a cached object
        if not resp:
            return False

        # If we have a cached 301, return it immediately. We don't
        # need to test our response for other headers b/c it is
        # intrinsically "cacheable" as it is Permanent.
        # See:
        #   https://tools.ietf.org/html/rfc7231#section-6.4.2
        #
        # Client can try to refresh the value by repeating the request
        # with cache busting headers as usual (ie no-cache).
        if resp.status == 301:
            return resp

        headers = CaseInsensitiveDict(resp.headers)
        if not headers or 'date' not in headers:
            # With date or etag, the cached response can never be used
            # and should be deleted.
            if 'etag' not in headers:
                self.cache.delete(cache_url)
            return False

        now = time.time()
        date = calendar.timegm(
            parsedate_tz(headers['date'])
        )
        current_age = max(0, now - date)

        # TODO: There is an assumption that the result will be a
        #       urllib3 response object. This may not be best since we
        #       could probably avoid instantiating or constructing the
        #       response until we know we need it.
        resp_cc = self.parse_cache_control(headers)

        # determine freshness
        freshness_lifetime = 0

        # Check the max-age pragma in the cache control header
        if 'max-age' in resp_cc and resp_cc['max-age'].isdigit():
            freshness_lifetime = int(resp_cc['max-age'])

        # If there isn't a max-age, check for an expires header
        elif 'expires' in headers:
            expires = parsedate_tz(headers['expires'])
            if expires is not None:
                expire_time = calendar.timegm(expires) - date
                freshness_lifetime = max(0, expire_time)

        # determine if we are setting freshness limit in the req
        if 'max-age' in cc:
            try:
                freshness_lifetime = int(cc['max-age'])
            except ValueError:
                freshness_lifetime = 0

        if 'min-fresh' in cc:
            try:
                min_fresh = int(cc['min-fresh'])
            except ValueError:
                min_fresh = 0
            # adjust our current age by our min fresh
            current_age += min_fresh

        # see how fresh we actually are
        fresh = (freshness_lifetime > current_age)

        if fresh:
            return resp

        # we're not fresh. If we don't have an Etag, clear it out
        if 'etag' not in headers:
            self.cache.delete(cache_url)

        # return the original handler
        return False

    def conditional_headers(self, request):
        cache_url = self.cache_url(request.url)
        resp = self.serializer.loads(request, self.cache.get(cache_url))
        new_headers = {}

        if resp:
            headers = CaseInsensitiveDict(resp.headers)

            if 'etag' in headers:
                new_headers['If-None-Match'] = headers['ETag']

            if 'last-modified' in headers:
                new_headers['If-Modified-Since'] = headers['Last-Modified']

        return new_headers

    def cache_response(self, request, response, body=None):
        """
        Algorithm for caching requests.

        This assumes a requests Response object.
        """
        # From httplib2: Don't cache 206's since we aren't going to
        #                handle byte range requests
        if response.status not in [200, 203, 300, 301]:
            return

        response_headers = CaseInsensitiveDict(response.headers)

        cc_req = self.parse_cache_control(request.headers)
        cc = self.parse_cache_control(response_headers)

        cache_url = self.cache_url(request.url)

        # Delete it from the cache if we happen to have it stored there
        no_store = cc.get('no-store') or cc_req.get('no-store')
        if no_store and self.cache.get(cache_url):
            self.cache.delete(cache_url)

        # If we've been given an etag, then keep the response
        if self.cache_etags and 'etag' in response_headers:
            self.cache.set(
                cache_url,
                self.serializer.dumps(request, response, body=body),
            )

        # Add to the cache any 301s. We do this before looking that
        # the Date headers.
        elif response.status == 301:
            self.cache.set(
                cache_url,
                self.serializer.dumps(request, response)
            )

        # Add to the cache if the response headers demand it. If there
        # is no date header then we can't do anything about expiring
        # the cache.
        elif 'date' in response_headers:
            # cache when there is a max-age > 0
            if cc and cc.get('max-age'):
                if int(cc['max-age']) > 0:
                    self.cache.set(
                        cache_url,
                        self.serializer.dumps(request, response, body=body),
                    )

            # If the request can expire, it means we should cache it
            # in the meantime.
            elif 'expires' in response_headers:
                if response_headers['expires']:
                    self.cache.set(
                        cache_url,
                        self.serializer.dumps(request, response, body=body),
                    )

    def update_cached_response(self, request, response):
        """On a 304 we will get a new set of headers that we want to
        update our cached value with, assuming we have one.

        This should only ever be called when we've sent an ETag and
        gotten a 304 as the response.
        """
        cache_url = self.cache_url(request.url)

        cached_response = self.serializer.loads(
            request,
            self.cache.get(cache_url)
        )

        if not cached_response:
            # we didn't have a cached response
            return response

        # Lets update our headers with the headers from the new request:
        # http://tools.ietf.org/html/draft-ietf-httpbis-p4-conditional-26#section-4.1
        #
        # The server isn't supposed to send headers that would make
        # the cached body invalid. But... just in case, we'll be sure
        # to strip out ones we know that might be problmatic due to
        # typical assumptions.
        excluded_headers = [
            "content-length",
        ]

        cached_response.headers.update(
            dict((k, v) for k, v in response.headers.items()
                 if k.lower() not in excluded_headers)
        )

        # we want a 200 b/c we have content via the cache
        cached_response.status = 200

        # update our cache
        self.cache.set(
            cache_url,
            self.serializer.dumps(request, cached_response),
        )

        return cached_response
