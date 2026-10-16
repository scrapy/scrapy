from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Self

from tldextract import TLDExtract

from scrapy.exceptions import NotConfigured
from scrapy.http import Response
from scrapy.http.cookies import CookieJar
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.request import _decode_cookie, _to_verbose_cookies

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from http.cookiejar import Cookie

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

    crawler: Crawler

    def __init__(self, debug: bool = False):
        self.jars: defaultdict[Any, CookieJar] = defaultdict(CookieJar)
        self.debug: bool = debug

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        if not crawler.settings.getbool("COOKIES_ENABLED"):
            raise NotConfigured
        o = cls(crawler.settings.getbool("COOKIES_DEBUG"))
        o.crawler = crawler
        return o

    def _process_cookies(
        self, cookies: Iterable[Cookie], *, jar: CookieJar, request: Request
    ) -> None:
        for cookie in cookies:
            cookie_domain = cookie.domain
            cookie_domain = cookie_domain.removeprefix(".")

            hostname = urlparse_cached(request).hostname
            if hostname is None:
                continue
            request_domain = hostname.lower()

            if cookie_domain and _is_public_domain(cookie_domain):
                if cookie_domain != request_domain:
                    continue
                cookie.domain = request_domain

            jar.set_cookie_if_ok(cookie, request)

    @_warn_spider_arg
    def process_request(
        self, request: Request, spider: Spider | None = None
    ) -> Request | Response | None:
        if request.meta.get("dont_merge_cookies", False):
            return None

        cookiejarkey = request.meta.get("cookiejar")
        jar = self.jars[cookiejarkey]
        cookies = self._get_request_cookies(jar, request)
        self._process_cookies(cookies, jar=jar, request=request)

        header_cookies = self._get_header_cookies(request)

        # set Cookie header
        request.headers.pop("Cookie", None)
        jar.add_cookie_header(request)
        if header_cookies:
            self._merge_header_cookies(request, header_cookies)
        self._debug_cookie(request)
        return None

    def _get_header_cookies(self, request: Request) -> list[tuple[str, str]]:
        """Return the cookies set in the ``Cookie`` header of *request* as
        ``(name, value)`` pairs, in header order.

        If a name appears more than once, only its last value is kept.
        """
        cookies: dict[str, str] = {}
        for header in request.headers.getlist("Cookie"):
            for segment in header.split(b";"):
                name, _, value = segment.strip().partition(b"=")
                if not name:
                    continue
                cookies[self._decode_header_part(name)] = self._decode_header_part(
                    value.strip()
                )
        return list(cookies.items())

    @staticmethod
    def _decode_header_part(part: bytes) -> str:
        try:
            return part.decode("utf-8")
        except UnicodeDecodeError:
            return part.decode("latin-1")

    def _merge_header_cookies(
        self, request: Request, header_cookies: list[tuple[str, str]]
    ) -> None:
        """Add *header_cookies* to the ``Cookie`` header of *request*.

        Cookies already in the header, which come from the cookie jar, take
        precedence over header cookies with the same name. Header cookies are
        not stored in the cookie jar, so a stale header copied onto a new
        request (e.g. by a redirect) cannot overwrite fresher cookies set
        through a ``Set-Cookie`` response header.
        """
        pairs: list[tuple[str, str]] = []
        current = request.headers.get("Cookie")
        if current is not None:
            for segment in current.split(b";"):
                name, _, value = segment.strip().partition(b"=")
                if name:
                    pairs.append(
                        (
                            self._decode_header_part(name),
                            self._decode_header_part(value.strip()),
                        )
                    )
        jar_names = {name for name, _ in pairs}
        pairs.extend(
            (name, value) for name, value in header_cookies if name not in jar_names
        )
        if pairs:
            request.headers["Cookie"] = "; ".join(
                f"{name}={value}" for name, value in pairs
            ).encode("utf-8")

    @_warn_spider_arg
    def process_response(
        self, request: Request, response: Response, spider: Spider | None = None
    ) -> Request | Response:
        if request.meta.get("dont_merge_cookies", False):
            return response

        # extract cookies from Set-Cookie and drop invalid/expired cookies
        cookiejarkey = request.meta.get("cookiejar")
        jar = self.jars[cookiejarkey]
        cookies = jar.make_cookies(response, request)
        self._process_cookies(cookies, jar=jar, request=request)

        self._debug_set_cookie(response)

        return response

    def _debug_cookie(self, request: Request) -> None:
        if self.debug:
            cl = [c.decode(errors="replace") for c in request.headers.getlist("Cookie")]
            if cl:
                cookies = "\n".join(f"Cookie: {c}\n" for c in cl)
                msg = f"Sending cookies to: {request}\n{cookies}"
                logger.debug(msg, extra={"spider": self.crawler.spider})

    def _debug_set_cookie(self, response: Response) -> None:
        if self.debug:
            cl = [
                c.decode(errors="replace")
                for c in response.headers.getlist("Set-Cookie")
            ]
            if cl:
                cookies = "\n".join(f"Set-Cookie: {c}\n" for c in cl)
                msg = f"Received cookies from: {response}\n{cookies}"
                logger.debug(msg, extra={"spider": self.crawler.spider})

    def _format_cookie(self, cookie: VerboseCookie, request: Request) -> str | None:
        """
        Given a dict consisting of cookie components, return its string representation.
        Decode from bytes if necessary.
        """
        decoded = _decode_cookie(cookie, request)
        if decoded is None:
            return None
        flags = set()
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
            return ()
        cookies: Iterable[VerboseCookie] = _to_verbose_cookies(request.cookies)
        for cookie in cookies:
            cookie.setdefault("secure", urlparse_cached(request).scheme == "https")
        formatted = filter(None, (self._format_cookie(c, request) for c in cookies))
        response = Response(request.url, headers={"Set-Cookie": formatted})
        return jar.make_cookies(response, request)
