"""
This module implements the Request class which is used to represent HTTP
requests in Scrapy.

See documentation in docs/topics/request-response.rst
"""

from __future__ import annotations

import inspect
from typing import (
    TYPE_CHECKING,
    Any,
    AnyStr,
    NoReturn,
    TypedDict,
    TypeVar,
    Union,
    overload,
)

from w3lib.url import safe_url_string

import scrapy
from scrapy.http.headers import Headers
from scrapy.utils.curl import curl_to_request_kwargs
from scrapy.utils.python import to_bytes
from scrapy.utils.trackref import object_ref
from scrapy.utils.url import escape_ajax

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from twisted.python.failure import Failure

    # typing.Concatenate requires Python 3.10
    # typing.NotRequired and typing.Self require Python 3.11
    from typing_extensions import Concatenate, NotRequired, Self

    from scrapy.http import Response

    CallbackT = Callable[Concatenate[Response, ...], Any]


class VerboseCookie(TypedDict):
    name: str
    value: str
    domain: NotRequired[str]
    path: NotRequired[str]
    secure: NotRequired[bool]


CookiesT = Union[dict[str, str], list[VerboseCookie]]


RequestTypeVar = TypeVar("RequestTypeVar", bound="Request")


def NO_CALLBACK(*args: Any, **kwargs: Any) -> NoReturn:
    """When assigned to the ``callback`` parameter of
    :class:`~scrapy.http.Request`, it indicates that the request is not meant
    to have a spider callback at all.

    For example:

    .. code-block:: python

       Request("https://example.com", callback=NO_CALLBACK)

    This value should be used by :ref:`components <topics-components>` that
    create and handle their own requests, e.g. through
    :meth:`scrapy.core.engine.ExecutionEngine.download`, so that downloader
    middlewares handling such requests can treat them differently from requests
    intended for the :meth:`~scrapy.Spider.parse` callback.
    """
    raise RuntimeError(
        "The NO_CALLBACK callback has been called. This is a special callback "
        "value intended for requests whose callback is never meant to be "
        "called."
    )


class Request(object_ref):
    """Represents an HTTP request, which is usually generated in a Spider and
    executed by the Downloader, thus generating a :class:`Response`.
    """

    attributes: tuple[str, ...] = (
        "url",
        "callback",
        "method",
        "headers",
        "body",
        "cookies",
        "meta",
        "encoding",
        "priority",
        "dont_filter",
        "errback",
        "flags",
        "cb_kwargs",
    )
    """A tuple of :class:`str` objects containing the name of all public
    attributes of the class that are also keyword parameters of the
    ``__init__`` method.

    Currently used by :meth:`Request.replace`, :meth:`Request.to_dict` and
    :func:`~scrapy.utils.request.request_from_dict`.
    """

    def __init__(
        self,
        url: str,
        callback: CallbackT | None = None,
        method: str = "GET",
        headers: Mapping[AnyStr, Any] | Iterable[tuple[AnyStr, Any]] | None = None,
        body: bytes | str | None = None,
        cookies: CookiesT | None = None,
        meta: dict[str, Any] | None = None,
        encoding: str = "utf-8",
        priority: int = 0,
        dont_filter: bool = False,
        errback: Callable[[Failure], Any] | None = None,
        flags: list[str] | None = None,
        cb_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self._encoding: str = encoding  # this one has to be set first
        self.method: str = str(method).upper()
        self._set_url(url)
        self._set_body(body)
        if not isinstance(priority, int):
            raise TypeError(f"Request priority not an integer: {priority!r}")
        self.priority: int = priority

        if not (callable(callback) or callback is None):
            raise TypeError(
                f"callback must be a callable, got {type(callback).__name__}"
            )
        if not (callable(errback) or errback is None):
            raise TypeError(f"errback must be a callable, got {type(errback).__name__}")
        self.callback: CallbackT | None = callback
        self.errback: Callable[[Failure], Any] | None = errback

        self.cookies: CookiesT = cookies or {}
        self.headers: Headers = Headers(headers or {}, encoding=encoding)
        self.dont_filter: bool = dont_filter

        self._meta: dict[str, Any] | None = dict(meta) if meta else None
        self._cb_kwargs: dict[str, Any] | None = dict(cb_kwargs) if cb_kwargs else None
        self.flags: list[str] = [] if flags is None else list(flags)

    @property
    def cb_kwargs(self) -> dict[str, Any]:
        if self._cb_kwargs is None:
            self._cb_kwargs = {}
        return self._cb_kwargs

    @property
    def meta(self) -> dict[str, Any]:
        if self._meta is None:
            self._meta = {}
        return self._meta

    @property
    def url(self) -> str:
        return self._url

    def _set_url(self, url: str) -> None:
        if not isinstance(url, str):
            raise TypeError(f"Request url must be str, got {type(url).__name__}")

        s = safe_url_string(url, self.encoding)
        self._url = escape_ajax(s)

        if (
            "://" not in self._url
            and not self._url.startswith("about:")
            and not self._url.startswith("data:")
        ):
            raise ValueError(f"Missing scheme in request url: {self._url}")

    @property
    def body(self) -> bytes:
        return self._body

    def _set_body(self, body: str | bytes | None) -> None:
        self._body = b"" if body is None else to_bytes(body, self.encoding)

    @property
    def encoding(self) -> str:
        return self._encoding

    def __repr__(self) -> str:
        return f"<{self.method} {self.url}>"

    def copy(self) -> Self:
        return self.replace()

    @overload
    def replace(
        self, *args: Any, cls: type[RequestTypeVar], **kwargs: Any
    ) -> RequestTypeVar: ...

    @overload
    def replace(self, *args: Any, cls: None = None, **kwargs: Any) -> Self: ...

    def replace(
        self, *args: Any, cls: type[Request] | None = None, **kwargs: Any
    ) -> Request:
        """Create a new Request with the same attributes except for those given new values"""
        for x in self.attributes:
            kwargs.setdefault(x, getattr(self, x))
        if cls is None:
            cls = self.__class__
        return cls(*args, **kwargs)

    @classmethod
    def from_curl(
        cls,
        curl_command: str,
        ignore_unknown_options: bool = True,
        **kwargs: Any,
    ) -> Self:
        """Create a Request object from a string containing a `cURL
        <https://curl.se/>`_ command. It populates the HTTP method, the
        URL, the headers, the cookies and the body. It accepts the same
        arguments as the :class:`Request` class, taking preference and
        overriding the values of the same arguments contained in the cURL
        command.

        Unrecognized options are ignored by default. To raise an error when
        finding unknown options call this method by passing
        ``ignore_unknown_options=False``.

        .. caution:: Using :meth:`from_curl` from :class:`~scrapy.http.Request`
                     subclasses, such as :class:`~scrapy.http.JsonRequest`, or
                     :class:`~scrapy.http.XmlRpcRequest`, as well as having
                     :ref:`downloader middlewares <topics-downloader-middleware>`
                     and
                     :ref:`spider middlewares <topics-spider-middleware>`
                     enabled, such as
                     :class:`~scrapy.downloadermiddlewares.defaultheaders.DefaultHeadersMiddleware`,
                     :class:`~scrapy.downloadermiddlewares.useragent.UserAgentMiddleware`,
                     or
                     :class:`~scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware`,
                     may modify the :class:`~scrapy.http.Request` object.

        To translate a cURL command into a Scrapy request,
        you may use `curl2scrapy <https://michael-shub.github.io/curl2scrapy/>`_.
        """
        request_kwargs = curl_to_request_kwargs(curl_command, ignore_unknown_options)
        request_kwargs.update(kwargs)
        return cls(**request_kwargs)

    def to_dict(self, *, spider: scrapy.Spider | None = None) -> dict[str, Any]:
        """Return a dictionary containing the Request's data.

        Use :func:`~scrapy.utils.request.request_from_dict` to convert back into a :class:`~scrapy.Request` object.

        If a spider is given, this method will try to find out the name of the spider methods used as callback
        and errback and include them in the output dict, raising an exception if they cannot be found.
        """
        d = {
            "url": self.url,  # urls are safe (safe_string_url)
            "callback": (
                _find_method(spider, self.callback)
                if callable(self.callback)
                else self.callback
            ),
            "errback": (
                _find_method(spider, self.errback)
                if callable(self.errback)
                else self.errback
            ),
            "headers": dict(self.headers),
        }
        for attr in self.attributes:
            d.setdefault(attr, getattr(self, attr))
        if type(self) is not Request:  # pylint: disable=unidiomatic-typecheck
            d["_class"] = self.__module__ + "." + self.__class__.__name__
        return d


def _find_method(obj: Any, func: Callable[..., Any]) -> str:
    """Helper function for Request.to_dict"""
    # Only instance methods contain ``__func__``
    if obj and hasattr(func, "__func__"):
        members = inspect.getmembers(obj, predicate=inspect.ismethod)
        for name, obj_func in members:
            # We need to use __func__ to access the original function object because instance
            # method objects are generated each time attribute is retrieved from instance.
            #
            # Reference: The standard type hierarchy
            # https://docs.python.org/3/reference/datamodel.html
            if obj_func.__func__ is func.__func__:
                return name
    raise ValueError(f"Function {func} is not an instance method in: {obj}")
