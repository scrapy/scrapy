from __future__ import annotations

import logging
import warnings
from typing import TYPE_CHECKING, Any, ClassVar

from tldextract import TLDExtract

from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.http import Response
from scrapy.http.cookies import CookieJar
from scrapy.sessions import _MAIN_ID
from scrapy.utils.datatypes import LocalCache
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_unicode
from scrapy.utils.request import _decode_cookie, _to_verbose_cookies

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from http.cookiejar import Cookie

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Request, Spider
    from scrapy.crawler import Crawler
    from scrapy.http.request import VerboseCookie
    from scrapy.sessions import Session


logger = logging.getLogger(__name__)


_split_domain = TLDExtract(include_psl_private_domains=True)
_UNSET = object()


def _is_public_domain(domain: str) -> bool:
    parts = _split_domain(domain)
    return not parts.domain


class CookiesMiddleware:
    """This middleware enables working with sites that need cookies"""

    crawler: Crawler

    _DEPRECATED_KEYS: ClassVar[dict[str, str]] = {
        "cookiejar": "Use the session request meta key instead.",
        "dont_merge_cookies": "Set the session request meta key to None instead.",
    }

    def __init__(self, debug: bool = False):
        self.debug: bool = debug
        # Session ID of every cookiejar meta key seen so far, for self.jars.
        self._session_ids: LocalCache[Any, str] = LocalCache()

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        if not crawler.settings.getbool("COOKIES_ENABLED"):
            raise NotConfigured
        o = cls(crawler.settings.getbool("COOKIES_DEBUG"))
        o.crawler = crawler
        o._session_ids.limit = crawler.settings.getint("SESSIONS_MAX")
        return o

    @property
    def jars(self) -> dict[Any, CookieJar]:
        """Cookie jars of the :reqmeta:`cookiejar` request meta keys seen so
        far."""
        warnings.warn(
            "CookiesMiddleware.jars is deprecated, use Crawler.sessions instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        sessions = self.crawler.sessions
        return {key: sessions[id_].cookies for key, id_ in self._session_ids.items()}

    def _session(self, request: Request) -> Session | None:
        """Return the session of *request*, or ``None`` if it has none."""
        has_session = "session" in request.meta
        for key in self._DEPRECATED_KEYS:
            if key in request.meta:
                self._warn_deprecated_key(key, ignored=has_session)
        if has_session:
            session_id = request.meta["session"]
            return None if session_id is None else self.crawler.sessions[session_id]
        if request.meta.get("dont_merge_cookies", False):
            return None
        jar_key = request.meta.get("cookiejar")
        jar_id = _MAIN_ID if jar_key is None else f"cookiejar:{jar_key!r}"
        self._session_ids[jar_key] = jar_id
        return self.crawler.sessions[jar_id]

    def _warn_deprecated_key(self, key: str, *, ignored: bool) -> None:
        if ignored:
            message = (
                f"The {key} request meta key is deprecated, and it is being "
                f"ignored because the session request meta key is set on the "
                f"same request. Remove {key}."
            )
        else:
            message = (
                f"The {key} request meta key is deprecated. "
                f"{self._DEPRECATED_KEYS[key]} Note that, unlike {key}, session "
                f"is inherited by the follow-up requests that a spider callback "
                f"yields."
            )
        warnings.warn(message, category=ScrapyDeprecationWarning, stacklevel=3)

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

    @_warn_spider_arg
    def process_request(
        self, request: Request, spider: Spider | None = None
    ) -> Request | Response | None:
        session = self._session(request)
        if session is None:
            # The cookies of the request are its own, so they are sent even with
            # no session to merge them into; a jar that no one keeps turns them
            # into a Cookie header. dont_merge_cookies drops them instead.
            if request.cookies and not request.meta.get("dont_merge_cookies", False):
                self._set_cookie_header(CookieJar(), request)
            return None
        self._set_cookie_header(session.cookies, request)
        return None

    def _set_cookie_header(self, jar: CookieJar, request: Request) -> None:
        cookies = self._get_request_cookies(jar, request)
        self._process_cookies(cookies, jar=jar, request=request)
        request.headers.pop("Cookie", None)
        jar.add_cookie_header(request)
        self._debug_cookie(request)

    @_warn_spider_arg
    def process_response(
        self, request: Request, response: Response, spider: Spider | None = None
    ) -> Request | Response:
        session = self._session(request)
        if session is None:
            return response

        # extract cookies from Set-Cookie and drop invalid/expired cookies
        jar = session.cookies
        cookies = jar.make_cookies(response, request)
        self._process_cookies(cookies, jar=jar, request=request)

        self._debug_set_cookie(response)

        return response

    def _debug_cookie(self, request: Request) -> None:
        if self.debug:
            cl = [
                to_unicode(c, errors="replace")
                for c in request.headers.getlist("Cookie")
            ]
            if cl:
                cookies = "\n".join(f"Cookie: {c}\n" for c in cl)
                msg = f"Sending cookies to: {request}\n{cookies}"
                logger.debug(msg, extra={"spider": self.crawler.spider})

    def _debug_set_cookie(self, response: Response) -> None:
        if self.debug:
            cl = [
                to_unicode(c, errors="replace")
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
