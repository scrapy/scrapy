import base64
from urllib.parse import unquote, urlunparse
from urllib.request import _parse_proxy, getproxies, proxy_bypass

from scrapy.exceptions import NotConfigured
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_bytes


class HttpProxyMiddleware:
    def __init__(self, auth_encoding="latin-1"):
        self.auth_encoding = auth_encoding
        self.proxies = {}
        for type_, url in getproxies().items():
            try:
                self.proxies[type_] = self._get_proxy(url, type_)
            # some values such as '/var/run/docker.sock' can't be parsed
            # by _parse_proxy and as such should be skipped
            except ValueError:
                continue

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool("HTTPPROXY_ENABLED"):
            raise NotConfigured
        auth_encoding = crawler.settings.get("HTTPPROXY_AUTH_ENCODING")
        return cls(auth_encoding)

    def _basic_auth_header(self, username, password):
        user_pass = to_bytes(
            f"{unquote(username)}:{unquote(password)}", encoding=self.auth_encoding
        )
        return base64.b64encode(user_pass)

    def _get_proxy(self, url, orig_type):
        proxy_type, user, password, hostport = _parse_proxy(url)
        proxy_url = urlunparse((proxy_type or orig_type, hostport, "", "", "", ""))

        if user:
            creds = self._basic_auth_header(user, password)
        else:
            creds = None

        return creds, proxy_url

    def process_request(self, request, spider):
        creds, proxy_url, scheme = None, None, None
        if "proxy" in request.meta:
            if request.meta["proxy"] is not None:
                creds, proxy_url = self._get_proxy(request.meta["proxy"], "")
        elif self.proxies:
            parsed = urlparse_cached(request)
            _scheme = parsed.scheme
            if (
                # 'no_proxy' is only supported by http schemes
                _scheme not in ("http", "https")
                or not proxy_bypass(parsed.hostname)
            ) and _scheme in self.proxies:
                scheme = _scheme
                creds, proxy_url = self.proxies[scheme]

        self._set_proxy_and_creds(request, proxy_url, creds, scheme)

    def _set_proxy_and_creds(self, request, proxy_url, creds, scheme):
        if scheme:
            request.meta["_scheme_proxy"] = True
        if proxy_url:
            request.meta["proxy"] = proxy_url
        elif request.meta.get("proxy") is not None:
            request.meta["proxy"] = None
        if creds:
            request.headers[b"Proxy-Authorization"] = b"Basic " + creds
            request.meta["_auth_proxy"] = proxy_url
        elif "_auth_proxy" in request.meta:
            if proxy_url != request.meta["_auth_proxy"]:
                if b"Proxy-Authorization" in request.headers:
                    del request.headers[b"Proxy-Authorization"]
                del request.meta["_auth_proxy"]
        elif b"Proxy-Authorization" in request.headers:
            if proxy_url:
                request.meta["_auth_proxy"] = proxy_url
            else:
                del request.headers[b"Proxy-Authorization"]
