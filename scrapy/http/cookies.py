from __future__ import annotations

import re
import time
from http.cookiejar import Cookie
from http.cookiejar import CookieJar as _CookieJar
from http.cookiejar import CookiePolicy, DefaultCookiePolicy
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
    cast,
)

from scrapy import Request
from scrapy.http import Response
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_unicode

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

# Defined in the http.cookiejar module, but undocumented:
# https://github.com/python/cpython/blob/v3.9.0/Lib/http/cookiejar.py#L527
IPV4_RE = re.compile(r"\.\d+$", re.ASCII)


class CookieJar:
    """
    A class that represents a cookie jar. It manages cookies and provides methods to extract, add, and manipulate cookies.
    """

    def __init__(
        self,
        policy: Optional[CookiePolicy] = None,
        check_expired_frequency: int = 10000,
    ):
        """
        Initialize a CookieJar object with a policy and a check_expired_frequency.
        """
        self.policy: CookiePolicy = policy or DefaultCookiePolicy()
        self.jar: _CookieJar = _CookieJar(self.policy)
        self.jar._cookies_lock = _DummyLock()  # type: ignore[attr-defined]
        self.check_expired_frequency: int = check_expired_frequency
        self.processed: int = 0

    def extract_cookies(self, response: Response, request: Request) -> None:
        """
        Extract cookies from the response and request.
        """
        wreq = WrappedRequest(request)
        wrsp = WrappedResponse(response)
        self.jar.extract_cookies(wrsp, wreq)  # type: ignore[arg-type]

    def add_cookie_header(self, request: Request) -> None:
        """
        Add cookie header to the request.
        """
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
        if attrs:
            if not wreq.has_header("Cookie"):
                wreq.add_unredirected_header("Cookie", "; ".join(attrs))

        self.processed += 1
        if self.processed % self.check_expired_frequency == 0:
            # This is still quite inefficient for large number of cookies
            self.jar.clear_expired_cookies()

    @property
    def _cookies(self) -> Dict[str, Dict[str, Dict[str, Cookie]]]:
        """
        Return the cookies in the jar.
        """
        return self.jar._cookies  # type: ignore[attr-defined,no-any-return]

    def clear_session_cookies(self) -> None:
        """
        Clear all session cookies.
        """
        return self.jar.clear_session_cookies()

    def clear(
        self,
        domain: Optional[str] = None,
        path: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        """
        Clear cookies, optionally filtered by domain, path, and name.
        """
        self.jar.clear(domain, path, name)

    def __iter__(self) -> Iterator[Cookie]:
        """
        Return an iterator over the cookies in the jar.
        """
        return iter(self.jar)

    def __len__(self) -> int:
        """
        Return the number of cookies in the jar.
        """
        return len(self.jar)

    def set_policy(self, pol: CookiePolicy) -> None:
        """
        Set the policy for the cookie jar.
        """
        self.jar.set_policy(pol)

    def make_cookies(self, response: Response, request: Request) -> Sequence[Cookie]:
        """
        Make cookies from the response and request.
        """
        wreq = WrappedRequest(request)
        wrsp = WrappedResponse(response)
        return self.jar.make_cookies(wrsp, wreq)  # type: ignore[arg-type]

    def set_cookie(self, cookie: Cookie) -> None:
        """
        Set a cookie in the jar.
        """
        self.jar.set_cookie(cookie)

    def set_cookie_if_ok(self, cookie: Cookie, request: Request) -> None:
        """
        Set a cookie in the jar if it's OK according to the policy.
        """
        self.jar.set_cookie_if_ok(cookie, WrappedRequest(request))  # type: ignore[arg-type]


def potential_domain_matches(domain: str) -> List[str]:
    """
    Potential domain matches for a cookie

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
    """
    A dummy lock class for use with the cookie jar.
    """

    def acquire(self) -> None:
        """
        Acquire the lock.
        """
        pass

    def release(self) -> None:
        """
        Release the lock.
        """
        pass


class WrappedRequest:
    """
    Wraps a scrapy Request class with methods defined by urllib2.Request class to interact with CookieJar class

    see http://docs.python.org/library/urllib2.html#urllib2.Request
    """

    def __init__(self, request: Request):
        """
        Initialize a WrappedRequest object with a request.
        """
        self.request = request

    def get_full_url(self) -> str:
        """
        Return the full URL of the request.
        """
        return self.request.url

    def get_host(self) -> str:
        """
        Return the host of the request.
        """
        return urlparse_cached(self.request).netloc

    def get_type(self) -> str:
        """
        Return the type (scheme) of the request.
        """
        return urlparse_cached(self.request).scheme

    def is_unverifiable(self) -> bool:
        """
        Return whether the request is unverifiable, as defined by RFC 2965.
        """
        return cast(bool, self.request.meta.get("is_unverifiable", False))

    @property
    def full_url(self) -> str:
        """
        Return the full URL of the request.
        """
        return self.get_full_url()

    @property
    def host(self) -> str:
        """
        Return the host of the request.
        """
        return self.get_host()

    @property
    def type(self) -> str:
        """
        Return the type (scheme) of the request.
        """
        return self.get_type()

    @property
    def unverifiable(self) -> bool:
        """
        Return whether the request is unverifiable.
        """
        return self.is_unverifiable()

    @property
    def origin_req_host(self) -> str:
        """
        Return the origin host of the request.
        """
        return cast(str, urlparse_cached(self.request).hostname)

    def has_header(self, name: str) -> bool:
        """
        Return whether the request has a header with the given name.
        """
        return name in self.request.headers

    def get_header(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """
        Return the value of the header with the given name, or the default value if the header is not present.
        """
        value = self.request.headers.get(name, default)
        return to_unicode(value, errors="replace") if value is not None else None

    def header_items(self) -> List[Tuple[str, List[str]]]:
        """
        Return a list of all headers, each represented by a tuple of the name and a list of values.
        """
        return [
            (
                to_unicode(k, errors="replace"),
                [to_unicode(x, errors="replace") for x in v],
            )
            for k, v in self.request.headers.items()
        ]

    def add_unredirected_header(self, name: str, value: str) -> None:
        """
        Add a header that will not be redirected.
        """
        self.request.headers.appendlist(name, value)


class WrappedResponse:
    """
    Wraps a scrapy Response class to interact with CookieJar class.
    """

    def __init__(self, response: Response):
        """
        Initialize a WrappedResponse object with a response.
        """
        self.response = response

    def info(self) -> Self:
        """
        Return self for compatibility with urllib2.Response.
        """
        return self

    def get_all(self, name: str, default: Any = None) -> List[str]:
        """
        Return all headers with the given name, or the default value if no such headers are present.
        """
        return [
            to_unicode(v, errors="replace") for v in self.response.headers.getlist(name)
        ]
