import warnings
try:
    from functools import lru_cache
except ImportError:
    from functools32 import lru_cache
from six.moves.urllib.parse import urlunparse
from six.moves.urllib.request import getproxies, proxy_bypass
try:
    from urllib2 import _parse_proxy
except ImportError:
    from urllib.request import _parse_proxy

from w3lib.http import basic_auth_header

from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.utils.httpobj import urlparse_cached


def get_proxy(url, orig_type, auth_encoding):
    proxy_type, user, password, hostport = _parse_proxy(url)
    proxy_url = urlunparse((proxy_type or orig_type, hostport, '', '', '', ''))

    if user:
        creds = basic_auth_header(user, password, auth_encoding)
    else:
        creds = None

    return creds, proxy_url


cached_proxy_bypass = lru_cache(maxsize=1024)(proxy_bypass)


class HttpProxyMiddleware(object):

    def __init__(self, auth_encoding='latin-1'):
        self.auth_encoding = auth_encoding
        self.proxies = {}
        for type_, url in getproxies().items():
            self.proxies[type_] = get_proxy(url, type_, self.auth_encoding)

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('HTTPPROXY_ENABLED'):
            raise NotConfigured
        auth_encoding = crawler.settings.get('HTTPPROXY_AUTH_ENCODING')
        return cls(auth_encoding)

    def _basic_auth_header(self, username, password):
        warnings.warn(
            "Method `scrapy.downloadermiddleware.httpproxy.HttpProxyMiddleware._basic_auth_header` "
            "is deprecated and will be removed in future releases. Please use "
            "`w3lib.http.basic_auth_header` instead",
            ScrapyDeprecationWarning, stacklevel=2,
        )
        return basic_auth_header(username, password, self.auth_encoding)

    def _get_proxy(self, url, orig_type):
        warnings.warn(
            "Method 'scrapy.downloadermiddleware.httpproxy.HttpProxyMiddleware._get_proxy "
            "is deprecated and will be removed in future releases. Please use "
            "`scrapy.downloadermiddleware.httpproxy.HttpProxyMiddleware.get_proxy` "
            "instead",
            ScrapyDeprecationWarning, stacklevel=2,
        )
        return get_proxy(url, orig_type, self.auth_encoding)

    def process_request(self, request, spider):
        # ignore if proxy is already set
        if 'proxy' in request.meta:
            if request.meta['proxy'] is None:
                return
            # extract credentials if present
            creds, proxy_url = get_proxy(request.meta['proxy'], '', self.auth_encoding)
            request.meta['proxy'] = proxy_url
            if creds and not request.headers.get('Proxy-Authorization'):
                request.headers['Proxy-Authorization'] = creds
            return
        elif not self.proxies:
            return

        parsed = urlparse_cached(request)
        scheme = parsed.scheme

        # 'no_proxy' is only supported by http schemes
        if scheme in ('http', 'https') and cached_proxy_bypass(parsed.hostname):
            return

        if scheme in self.proxies:
            self._set_proxy(request, scheme)

    def _set_proxy(self, request, scheme):
        creds, proxy = self.proxies[scheme]
        request.meta['proxy'] = proxy
        if creds:
            request.headers['Proxy-Authorization'] = creds
