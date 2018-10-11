import base64
<<<<<<< HEAD
try:
    from functools import lru_cache
except:
    from functools32 import lru_cache
=======
from six.moves.urllib.parse import unquote, urlunparse
from six.moves.urllib.request import getproxies, proxy_bypass
>>>>>>> upstream/master
try:
    from urllib2 import _parse_proxy
except ImportError:
    from urllib.request import _parse_proxy

<<<<<<< HEAD
from six.moves.urllib.parse import urlunparse, unquote
from six.moves.urllib.request import getproxies, proxy_bypass

=======
>>>>>>> upstream/master
from scrapy.exceptions import NotConfigured
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_bytes


@lru_cache(maxsize=128)
def basic_auth_header(auth_encoding, username, password):
    user_pass = to_bytes(
        '%s:%s' % (unquote(username), unquote(password)),
        encoding=auth_encoding)
    return base64.b64encode(user_pass).strip()


@lru_cache(maxsize=128)
def get_proxy(auth_encoding, url, orig_type):
    proxy_type, user, password, hostport = _parse_proxy(url)
    proxy_url = urlunparse((proxy_type or orig_type, hostport, '', '', '', ''))

    if user:
        creds = basic_auth_header(auth_encoding, user, password)
    else:
        creds = None

    return creds, proxy_url


class HttpProxyMiddleware(object):

    def __init__(self, auth_encoding='latin-1'):
        self.auth_encoding = auth_encoding
        self.proxies = {}
        for type_, url in getproxies().items():
<<<<<<< HEAD
            self.proxies[type_] = get_proxy(self.auth_encoding, url, type_)
=======
            self.proxies[type_] = self._get_proxy(url, type_)
>>>>>>> upstream/master

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('HTTPPROXY_ENABLED'):
            raise NotConfigured
        auth_encoding = crawler.settings.get('HTTPPROXY_AUTH_ENCODING')
        return cls(auth_encoding)

    def process_request(self, request, spider):
        # ignore if proxy is already set
        if 'proxy' in request.meta:
            if request.meta['proxy'] is None:
                return
            # extract credentials if present
            creds, proxy_url = get_proxy(self.auth_encoding, request.meta['proxy'], '')
            request.meta['proxy'] = proxy_url
            if creds and not request.headers.get('Proxy-Authorization'):
                request.headers['Proxy-Authorization'] = b'Basic ' + creds
            return
        elif not self.proxies:
            return

        parsed = urlparse_cached(request)
        scheme = parsed.scheme

        # 'no_proxy' is only supported by http schemes
        if scheme in ('http', 'https') and proxy_bypass(parsed.hostname):
            return

        if scheme in self.proxies:
            self._set_proxy(request, scheme)

    def _set_proxy(self, request, scheme):
        creds, proxy = self.proxies[scheme]
        request.meta['proxy'] = proxy
        if creds:
            request.headers['Proxy-Authorization'] = b'Basic ' + creds
