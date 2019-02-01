import base64
from six.moves.urllib.parse import unquote, urlunparse
from six.moves.urllib.request import getproxies, proxy_bypass
try:
    from urllib2 import _parse_proxy
except ImportError:
    from urllib.request import _parse_proxy

from scrapy.exceptions import NotConfigured
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_bytes


class HttpProxyMiddleware(object):
    """This middleware sets the HTTP proxy to use for requests, by setting the
    ``proxy`` meta value for :class:`~scrapy.http.Request` objects.

    .. versionadded:: 0.8

    .. reqmeta:: proxy

    Like the Python standard library modules `urllib`_ and `urllib2`_, it obeys
    the following environment variables:

    * ``http_proxy``
    * ``https_proxy``
    * ``no_proxy``

    You can also set the meta key ``proxy`` per-request, to a value like
    ``http://some_proxy_server:port`` or ``http://username:password@some_proxy_server:port``.
    Keep in mind this value will take precedence over ``http_proxy``/``https_proxy``
    environment variables, and it will also ignore ``no_proxy`` environment variable.

    .. rubric:: HttpProxyMiddleware settings

    .. setting:: HTTPPROXY_ENABLED

    .. rubric:: HTTPPROXY_ENABLED

    Default: ``True``

    Whether or not to enable the :class:`HttpProxyMiddleware`.

    .. setting:: HTTPPROXY_AUTH_ENCODING

    .. rubric:: HTTPPROXY_AUTH_ENCODING

    Default: ``"latin-1"``

    The default encoding for proxy authentication on :class:`HttpProxyMiddleware`.

    .. _urllib: https://docs.python.org/2/library/urllib.html
    .. _urllib2: https://docs.python.org/2/library/urllib2.html
    """

    def __init__(self, auth_encoding='latin-1'):
        self.auth_encoding = auth_encoding
        self.proxies = {}
        for type_, url in getproxies().items():
            self.proxies[type_] = self._get_proxy(url, type_)

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('HTTPPROXY_ENABLED'):
            raise NotConfigured
        auth_encoding = crawler.settings.get('HTTPPROXY_AUTH_ENCODING')
        return cls(auth_encoding)

    def _basic_auth_header(self, username, password):
        user_pass = to_bytes(
            '%s:%s' % (unquote(username), unquote(password)),
            encoding=self.auth_encoding)
        return base64.b64encode(user_pass)

    def _get_proxy(self, url, orig_type):
        proxy_type, user, password, hostport = _parse_proxy(url)
        proxy_url = urlunparse((proxy_type or orig_type, hostport, '', '', '', ''))

        if user:
            creds = self._basic_auth_header(user, password)
        else:
            creds = None

        return creds, proxy_url

    def process_request(self, request, spider):
        # ignore if proxy is already set
        if 'proxy' in request.meta:
            if request.meta['proxy'] is None:
                return
            # extract credentials if present
            creds, proxy_url = self._get_proxy(request.meta['proxy'], '')
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
