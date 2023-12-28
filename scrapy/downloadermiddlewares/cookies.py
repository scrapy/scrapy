from __future__ import annotations

import logging
from collections import defaultdict
from http.cookiejar import Cookie
from typing import (
    TYPE_CHECKING,
    Any,
    DefaultDict,
    Dict,
    Iterable,
    Optional,
    Sequence,
    Union,
)

from tldextract import TLDExtract

from scrapy import Request, Spider
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.http import Response
from scrapy.http.cookies import CookieJar
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_unicode

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self


logger = logging.getLogger(__name__)


_split_domain = TLDExtract(include_psl_private_domains=True)


def _is_public_domain(domain: str) -> bool:
    parts = _split_domain(domain)
    return not parts.domain


class CookiesMiddleware:
    """This middleware enables working with sites that need cookies"""

    def __init__(self, debug: bool = False):
        self.jars: DefaultDict[Any, CookieJar] = defaultdict(CookieJar)
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
            if cookie_domain.startswith("."):
                cookie_domain = cookie_domain[1:]

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
    ) -> Union[Request, Response, None]:
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
    ) -> Union[Request, Response]:
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

    def _format_cookie(self, cookie: Dict[str, Any], request: Request) -> Optional[str]:
        """
        Given a dict consisting of cookie components, return its string representation.
        Decode from bytes if necessary.
        """
        decoded = {}
        for key in ("name", "value", "path", "domain"):
            if cookie.get(key) is None:
                if key in ("name", "value"):
                    msg = f"Invalid cookie found in request {request}: {cookie} ('{key}' is missing)"
                    logger.warning(msg)
                    return None
                continue
            if isinstance(cookie[key], (bool, float, int, str)):
                decoded[key] = str(cookie[key])
            else:
                try:
                    decoded[key] = cookie[key].decode("utf8")
                except UnicodeDecodeError:
                    logger.warning(
                        "Non UTF-8 encoded cookie found in request %s: %s",
                        request,
                        cookie,
                    )
                    decoded[key] = cookie[key].decode("latin1", errors="replace")

        cookie_str = f"{decoded.pop('name')}={decoded.pop('value')}"
        for key, value in decoded.items():  # path, domain
            cookie_str += f"; {key.capitalize()}={value}"
        return cookie_str

    def _get_request_cookies(
        self, jar: CookieJar, request: Request
    ) -> Sequence[Cookie]:
        """
        Extract cookies from the Request.cookies attribute
        """
        if not request.cookies:
            return []
        cookies: Iterable[Dict[str, Any]]
        if isinstance(request.cookies, dict):
            cookies = ({"name": k, "value": v} for k, v in request.cookies.items())
        else:
            cookies = request.cookies
        formatted = filter(None, (self._format_cookie(c, request) for c in cookies))
        response = Response(request.url, headers={"Set-Cookie": formatted})
        return jar.make_cookies(response, request)
