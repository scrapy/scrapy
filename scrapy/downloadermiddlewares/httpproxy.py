import base64

from six.moves.urllib.parse import unquote, urlunparse
from six.moves.urllib.request import getproxies, proxy_bypass

from scrapy.exceptions import NotConfigured
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_bytes

try:
    from urllib2 import _parse_proxy
except ImportError:
    from urllib.request import _parse_proxy



class HttpProxyMiddleware(object):

    def __init__(self, auth_encoding='latin-1'):
        self.auth_encoding = auth_encoding
        self.proxies = {}
        for type, url in getproxies().items():
            self.proxies[type] = self._get_proxy(url, type)

        if not self.proxies:
            raise NotConfigured

    @classmethod
    def from_crawler(cls, crawler):
        auth_encoding = crawler.settings.get('HTTPPROXY_AUTH_ENCODING')
        return cls(auth_encoding)

    def _get_proxy(self, url, orig_type):
        proxy_type, user, password, hostport = _parse_proxy(url)
        proxy_url = urlunparse((proxy_type or orig_type, hostport, '', '', '', ''))

        if user:
            user_pass = to_bytes(
                '%s:%s' % (unquote(user), unquote(password)),
                encoding=self.auth_encoding)
            creds = base64.b64encode(user_pass).strip()
        else:
            creds = None

        return creds, proxy_url

    def process_request(self, request, spider):
        # ignore if proxy is already set
        if 'proxy' in request.meta:
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
