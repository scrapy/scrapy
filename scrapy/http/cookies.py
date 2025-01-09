from __future__ import annotations

import re
import time
from http.cookiejar import Cookie, CookiePolicy, DefaultCookiePolicy
from http.cookiejar import CookieJar as _CookieJar
from typing import TYPE_CHECKING, Any, cast

from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_unicode

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Request
    from scrapy.http import Response


# Defined in the http.cookiejar module, but undocumented:
# https://github.com/python/cpython/blob/v3.9.0/Lib/http/cookiejar.py#L527
IPV4_RE = re.compile(r"\.\d+$", re.ASCII)


class CookieJar:
    def __init__(
        self,
        policy: CookiePolicy | None = None,
        check_expired_frequency: int = 10000,
    ):
        self.policy: CookiePolicy = policy or DefaultCookiePolicy()
        self.jar: _CookieJar = _CookieJar(self.policy)
        self.jar._cookies_lock = _DummyLock()  # type: ignore[attr-defined]
        self.check_expired_frequency: int = check_expired_frequency
        self.processed: int = 0

    def extract_cookies(self, response: Response, request: Request) -> None:
        wreq = WrappedRequest(request)
        wrsp = WrappedResponse(response)
        self.jar.extract_cookies(wrsp, wreq)  # type: ignore[arg-type]

    def add_cookie_header(self, request: Request) -> None:
        wreq = WrappedRequest(request)
        self.policy._now = self.jar._now = int(time.time())  # type: ignore[attr-defined]

        # the cookiejar implementation iterates through all domains
        # instead we restrict to potential matches on the domain
        req_host = urlparse_cached(request).hostname
        if not req_host:
            return

        if not IPV4_RE.search(req_host):
            hosts = potential_domain_matches(req_host)
            if "." not in req_host:
                hosts += [req_host + ".local"]
        else:
            hosts = [req_host]

        cookies = []
        for host in hosts:
            if host in self.jar._cookies:  # type: ignore[attr-defined]
                cookies += self.jar._cookies_for_domain(host, wreq)  # type: ignore[attr-defined]

        attrs = self.jar._cookie_attrs(cookies)  # type: ignore[attr-defined]
        if attrs and not wreq.has_header("Cookie"):
            wreq.add_unredirected_header("Cookie", "; ".join(attrs))

        self.processed += 1
        if self.processed % self.check_expired_frequency == 0:
            # This is still quite inefficient for large number of cookies
            self.jar.clear_expired_cookies()

    @property
    def _cookies(self) -> dict[str, dict[str, dict[str, Cookie]]]:
        return self.jar._cookies  # type: ignore[attr-defined,no-any-return]

    def clear_session_cookies(self) -> None:
        return self.jar.clear_session_cookies()

    def clear(
        self,
        domain: str | None = None,
        path: str | None = None,
        name: str | None = None,
    ) -> None:
        self.jar.clear(domain, path, name)

    def __iter__(self) -> Iterator[Cookie]:
        return iter(self.jar)

    def __len__(self) -> int:
        return len(self.jar)

    def set_policy(self, pol: CookiePolicy) -> None:
        self.jar.set_policy(pol)

    def make_cookies(self, response: Response, request: Request) -> Sequence[Cookie]:
        wreq = WrappedRequest(request)
        wrsp = WrappedResponse(response)
        return self.jar.make_cookies(wrsp, wreq)  # type: ignore[arg-type]

    def set_cookie(self, cookie: Cookie) -> None:
        self.jar.set_cookie(cookie)

    def set_cookie_if_ok(self, cookie: Cookie, request: Request) -> None:
        self.jar.set_cookie_if_ok(cookie, WrappedRequest(request))  # type: ignore[arg-type]


def potential_domain_matches(domain: str) -> list[str]:
    """Potential domain matches for a cookie

    >>> potential_domain_matches('www.example.com')
    ['www.example.com', 'example.com', '.www.example.com', '.example.com']

    """
    matches = [domain]
    try:
        start = domain.index(".") + 1
        end = domain.rindex(".")
        while start < end:
            matches.append(domain[start:])
            start = domain.index(".", start) + 1
    except ValueError:
        pass
    return matches + ["." + d for d in matches]


class _DummyLock:
    def acquire(self) -> None:
        pass

    def release(self) -> None:
        pass


class WrappedRequest:
    """Wraps a scrapy Request class with methods defined by urllib2.Request class to interact with CookieJar class

    see http://docs.python.org/library/urllib2.html#urllib2.Request
    """

    def __init__(self, request: Request):
        self.request = request

    def get_full_url(self) -> str:
        return self.request.url

    def get_host(self) -> str:
        return urlparse_cached(self.request).netloc

    def get_type(self) -> str:
        return urlparse_cached(self.request).scheme

    def is_unverifiable(self) -> bool:
        """Unverifiable should indicate whether the request is unverifiable, as defined by RFC 2965.

        It defaults to False. An unverifiable request is one whose URL the user did not have the
        option to approve. For example, if the request is for an image in an
        HTML document, and the user had no option to approve the automatic
        fetching of the image, this should be true.
        """
        return cast(bool, self.request.meta.get("is_unverifiable", False))

    @property
    def full_url(self) -> str:
        return self.get_full_url()

    @property
    def host(self) -> str:
        return self.get_host()

    @property
    def type(self) -> str:
        return self.get_type()

    @property
    def unverifiable(self) -> bool:
        return self.is_unverifiable()

    @property
    def origin_req_host(self) -> str:
        return cast(str, urlparse_cached(self.request).hostname)

    def has_header(self, name: str) -> bool:
        return name in self.request.headers

    def get_header(self, name: str, default: str | None = None) -> str | None:
        value = self.request.headers.get(name, default)
        return to_unicode(value, errors="replace") if value is not None else None

    def header_items(self) -> list[tuple[str, list[str]]]:
        return [
            (
                to_unicode(k, errors="replace"),
                [to_unicode(x, errors="replace") for x in v],
            )
            for k, v in self.request.headers.items()
        ]

    def add_unredirected_header(self, name: str, value: str) -> None:
        self.request.headers.appendlist(name, value)


class WrappedResponse:
    def __init__(self, response: Response):
        self.response = response

    def info(self) -> Self:
        return self

    def get_all(self, name: str, default: Any = None) -> list[str]:
        return [
            to_unicode(v, errors="replace") for v in self.response.headers.getlist(name)
        ]
