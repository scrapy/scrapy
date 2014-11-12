import base64
from urllib import getproxies, unquote, proxy_bypass
from urllib2 import _parse_proxy
from six.moves.urllib.parse import urlunparse

from scrapy.utils.httpobj import urlparse_cached
from scrapy.exceptions import NotConfigured


class HttpProxyMiddleware(object):

    def __init__(self):
        self.proxies = {}
        for type, url in getproxies().items():
            self.proxies[type] = self._get_proxy(url, type)

        if not self.proxies:
            raise NotConfigured

    def _get_proxy(self, url, orig_type):
        proxy_type, user, password, hostport = _parse_proxy(url)
        proxy_url = urlunparse((proxy_type or orig_type, hostport, '', '', '', ''))

        if user and password:
            user_pass = '%s:%s' % (unquote(user), unquote(password))
            creds = base64.b64encode(user_pass).strip()
        else:
            creds = None

        return creds, proxy_url

    def process_request(self, request, spider):
        # ignore if proxy is already seted
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
            request.headers['Proxy-Authorization'] = 'Basic ' + creds
