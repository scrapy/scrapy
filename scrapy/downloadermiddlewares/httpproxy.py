from __future__ import annotations

import base64
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlunparse
from urllib.request import (  # type: ignore[attr-defined]
    _parse_proxy,
    getproxies,
    proxy_bypass,
)

from scrapy.exceptions import NotConfigured
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_bytes

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Request, Spider
    from scrapy.crawler import Crawler
    from scrapy.http import Response


class HttpProxyMiddleware:
    def __init__(self, auth_encoding: str | None = "latin-1"):
        self.auth_encoding: str | None = auth_encoding
        self.proxies: dict[str, tuple[bytes | None, str]] = {}
        for type_, url in getproxies().items():
            try:
                self.proxies[type_] = self._get_proxy(url, type_)
            # some values such as '/var/run/docker.sock' can't be parsed
            # by _parse_proxy and as such should be skipped
            except ValueError:
                continue

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        if not crawler.settings.getbool("HTTPPROXY_ENABLED"):
            raise NotConfigured
        auth_encoding: str | None = crawler.settings.get("HTTPPROXY_AUTH_ENCODING")
        return cls(auth_encoding)

    def _basic_auth_header(self, username: str, password: str) -> bytes:
        user_pass = to_bytes(
            f"{unquote(username)}:{unquote(password)}", encoding=self.auth_encoding
        )
        return base64.b64encode(user_pass)

    def _get_proxy(self, url: str, orig_type: str) -> tuple[bytes | None, str]:
        proxy_type, user, password, hostport = _parse_proxy(url)
        proxy_url = urlunparse((proxy_type or orig_type, hostport, "", "", "", ""))

        if user:
            creds = self._basic_auth_header(user, password)
        else:
            creds = None

        return creds, proxy_url

    def process_request(
        self, request: Request, spider: Spider
    ) -> Request | Response | None:
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
                or (parsed.hostname and not proxy_bypass(parsed.hostname))
            ) and _scheme in self.proxies:
                scheme = _scheme
                creds, proxy_url = self.proxies[scheme]

        self._set_proxy_and_creds(request, proxy_url, creds, scheme)
        return None

    def _set_proxy_and_creds(
        self,
        request: Request,
        proxy_url: str | None,
        creds: bytes | None,
        scheme: str | None,
    ) -> None:
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
