from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from tldextract import TLDExtract

from scrapy.exceptions import NotConfigured
from scrapy.http import Response
from scrapy.http.cookies import CookieJar
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_unicode

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from http.cookiejar import Cookie

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Request, Spider
    from scrapy.crawler import Crawler
    from scrapy.http.request import VerboseCookie


logger = logging.getLogger(__name__)


_split_domain = TLDExtract(include_psl_private_domains=True)
_UNSET = object()


def _is_public_domain(domain: str) -> bool:
    parts = _split_domain(domain)
    return not parts.domain


class CookiesMiddleware:
    """This middleware enables working with sites that need cookies"""

    def __init__(self, debug: bool = False):
        self.jars: defaultdict[Any, CookieJar] = defaultdict(CookieJar)
        self.debug: bool = debug

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        if not crawler.settings.getbool("COOKIES_ENABLED"):
            raise NotConfigured
        return cls(crawler.settings.getbool("COOKIES_DEBUG"))

    def _process_cookies(
        self, cookies: Iterable[Cookie], *, jar: CookieJar, request: Request
    ) -> None:
        for cookie in cookies:
            cookie_domain = cookie.domain
            cookie_domain = cookie_domain.removeprefix(".")

            hostname = urlparse_cached(request).hostname
            assert hostname is not None
            request_domain = hostname.lower()

            if cookie_domain and _is_public_domain(cookie_domain):
                if cookie_domain != request_domain:
                    continue
                cookie.domain = request_domain

            jar.set_cookie_if_ok(cookie, request)

    def process_request(
        self, request: Request, spider: Spider
    ) -> Request | Response | None:
        if request.meta.get("dont_merge_cookies", False):
            return None

        cookiejarkey = request.meta.get("cookiejar")
        jar = self.jars[cookiejarkey]
        cookies = self._get_request_cookies(jar, request)
        self._process_cookies(cookies, jar=jar, request=request)

        # set Cookie header
        request.headers.pop("Cookie", None)
        jar.add_cookie_header(request)
        self._debug_cookie(request, spider)
        return None

    def process_response(
        self, request: Request, response: Response, spider: Spider
    ) -> Request | Response:
        if request.meta.get("dont_merge_cookies", False):
            return response

        # extract cookies from Set-Cookie and drop invalid/expired cookies
        cookiejarkey = request.meta.get("cookiejar")
        jar = self.jars[cookiejarkey]
        cookies = jar.make_cookies(response, request)
        self._process_cookies(cookies, jar=jar, request=request)

        self._debug_set_cookie(response, spider)

        return response

    def _debug_cookie(self, request: Request, spider: Spider) -> None:
        if self.debug:
            cl = [
                to_unicode(c, errors="replace")
                for c in request.headers.getlist("Cookie")
            ]
            if cl:
                cookies = "\n".join(f"Cookie: {c}\n" for c in cl)
                msg = f"Sending cookies to: {request}\n{cookies}"
                logger.debug(msg, extra={"spider": spider})

    def _debug_set_cookie(self, response: Response, spider: Spider) -> None:
        if self.debug:
            cl = [
                to_unicode(c, errors="replace")
                for c in response.headers.getlist("Set-Cookie")
            ]
            if cl:
                cookies = "\n".join(f"Set-Cookie: {c}\n" for c in cl)
                msg = f"Received cookies from: {response}\n{cookies}"
                logger.debug(msg, extra={"spider": spider})

    def _format_cookie(self, cookie: VerboseCookie, request: Request) -> str | None:
        """
        Given a dict consisting of cookie components, return its string representation.
        Decode from bytes if necessary.
        """
        decoded = {}
        flags = set()
        for key in ("name", "value", "path", "domain"):
            value = cookie.get(key)
            if value is None:
                if key in ("name", "value"):
                    msg = f"Invalid cookie found in request {request}: {cookie} ('{key}' is missing)"
                    logger.warning(msg)
                    return None
                continue
            if isinstance(value, (bool, float, int, str)):
                decoded[key] = str(value)
            else:
                assert isinstance(value, bytes)
                try:
                    decoded[key] = value.decode("utf8")
                except UnicodeDecodeError:
                    logger.warning(
                        "Non UTF-8 encoded cookie found in request %s: %s",
                        request,
                        cookie,
                    )
                    decoded[key] = value.decode("latin1", errors="replace")
        for flag in ("secure",):
            value = cookie.get(flag, _UNSET)
            if value is _UNSET or not value:
                continue
            flags.add(flag)
        cookie_str = f"{decoded.pop('name')}={decoded.pop('value')}"
        for key, value in decoded.items():  # path, domain
            cookie_str += f"; {key.capitalize()}={value}"
        for flag in flags:  # secure
            cookie_str += f"; {flag.capitalize()}"
        return cookie_str

    def _get_request_cookies(
        self, jar: CookieJar, request: Request
    ) -> Sequence[Cookie]:
        """
        Extract cookies from the Request.cookies attribute
        """
        if not request.cookies:
            return []
        cookies: Iterable[VerboseCookie]
        if isinstance(request.cookies, dict):
            cookies = tuple({"name": k, "value": v} for k, v in request.cookies.items())
        else:
            cookies = request.cookies
        for cookie in cookies:
            cookie.setdefault("secure", urlparse_cached(request).scheme == "https")
        formatted = filter(None, (self._format_cookie(c, request) for c in cookies))
        response = Response(request.url, headers={"Set-Cookie": formatted})
        return jar.make_cookies(response, request)
