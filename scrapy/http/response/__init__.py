"""
This module implements the Response class which is used to represent HTTP
responses in Scrapy.

See documentation in docs/topics/request-response.rst
"""
from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address
from typing import (
    TYPE_CHECKING,
    Any,
    AnyStr,
    Callable,
    Dict,
    Generator,
    Iterable,
    List,
    Mapping,
    Optional,
    Tuple,
    Union,
    cast,
)
from urllib.parse import urljoin

from twisted.internet.ssl import Certificate

from scrapy.exceptions import NotSupported
from scrapy.http.headers import Headers
from scrapy.http.request import Request
from scrapy.link import Link
from scrapy.utils.trackref import object_ref

if TYPE_CHECKING:
    from scrapy.selector import SelectorList


class Response(object_ref):
    """An object that represents an HTTP response, which is usually
    downloaded (by the Downloader) and fed to the Spiders for processing.
    """

    attributes: Tuple[str, ...] = (
        "url",
        "status",
        "headers",
        "body",
        "flags",
        "request",
        "certificate",
        "ip_address",
        "protocol",
    )
    """A tuple of :class:`str` objects containing the name of all public
    attributes of the class that are also keyword parameters of the
    ``__init__`` method.

    Currently used by :meth:`Response.replace`.
    """

    def __init__(
        self,
        url: str,
        status: int = 200,
        headers: Union[Mapping[AnyStr, Any], Iterable[Tuple[AnyStr, Any]], None] = None,
        body: bytes = b"",
        flags: Optional[List[str]] = None,
        request: Optional[Request] = None,
        certificate: Optional[Certificate] = None,
        ip_address: Union[IPv4Address, IPv6Address, None] = None,
        protocol: Optional[str] = None,
    ):
        self.headers: Headers = Headers(headers or {})
        self.status: int = int(status)
        self._set_body(body)
        self._set_url(url)
        self.request: Optional[Request] = request
        self.flags: List[str] = [] if flags is None else list(flags)
        self.certificate: Optional[Certificate] = certificate
        self.ip_address: Union[IPv4Address, IPv6Address, None] = ip_address
        self.protocol: Optional[str] = protocol

    @property
    def cb_kwargs(self) -> Dict[str, Any]:
        try:
            return self.request.cb_kwargs  # type: ignore[union-attr]
        except AttributeError:
            raise AttributeError(
                "Response.cb_kwargs not available, this response "
                "is not tied to any request"
            )

    @property
    def meta(self) -> Dict[str, Any]:
        try:
            return self.request.meta  # type: ignore[union-attr]
        except AttributeError:
            raise AttributeError(
                "Response.meta not available, this response "
                "is not tied to any request"
            )

    @property
    def url(self) -> str:
        return self._url

    def _set_url(self, url: str) -> None:
        if isinstance(url, str):
            self._url: str = url
        else:
            raise TypeError(
                f"{type(self).__name__} url must be str, " f"got {type(url).__name__}"
            )

    @property
    def body(self) -> bytes:
        return self._body

    def _set_body(self, body: Optional[bytes]) -> None:
        if body is None:
            self._body = b""
        elif not isinstance(body, bytes):
            raise TypeError(
                "Response body must be bytes. "
                "If you want to pass unicode body use TextResponse "
                "or HtmlResponse."
            )
        else:
            self._body = body

    def __repr__(self) -> str:
        return f"<{self.status} {self.url}>"

    def copy(self) -> Response:
        """Return a copy of this Response"""
        return self.replace()

    def replace(self, *args: Any, **kwargs: Any) -> Response:
        """Create a new Response with the same attributes except for those given new values"""
        for x in self.attributes:
            kwargs.setdefault(x, getattr(self, x))
        cls = kwargs.pop("cls", self.__class__)
        return cast(Response, cls(*args, **kwargs))

    def urljoin(self, url: str) -> str:
        """Join this Response's url with a possible relative url to form an
        absolute interpretation of the latter."""
        return urljoin(self.url, url)

    @property
    def text(self) -> str:
        """For subclasses of TextResponse, this will return the body
        as str
        """
        raise AttributeError("Response content isn't text")

    def css(self, *a: Any, **kw: Any) -> SelectorList:
        """Shortcut method implemented only by responses whose content
        is text (subclasses of TextResponse).
        """
        raise NotSupported("Response content isn't text")

    def jmespath(self, *a: Any, **kw: Any) -> SelectorList:
        """Shortcut method implemented only by responses whose content
        is text (subclasses of TextResponse).
        """
        raise NotSupported("Response content isn't text")

    def xpath(self, *a: Any, **kw: Any) -> SelectorList:
        """Shortcut method implemented only by responses whose content
        is text (subclasses of TextResponse).
        """
        raise NotSupported("Response content isn't text")

    def follow(
        self,
        url: Union[str, Link],
        callback: Optional[Callable] = None,
        method: str = "GET",
        headers: Union[Mapping[AnyStr, Any], Iterable[Tuple[AnyStr, Any]], None] = None,
        body: Optional[Union[bytes, str]] = None,
        cookies: Optional[Union[dict, List[dict]]] = None,
        meta: Optional[Dict[str, Any]] = None,
        encoding: Optional[str] = "utf-8",
        priority: int = 0,
        dont_filter: bool = False,
        errback: Optional[Callable] = None,
        cb_kwargs: Optional[Dict[str, Any]] = None,
        flags: Optional[List[str]] = None,
    ) -> Request:
        """
        Return a :class:`~.Request` instance to follow a link ``url``.
        It accepts the same arguments as ``Request.__init__`` method,
        but ``url`` can be a relative URL or a ``scrapy.link.Link`` object,
        not only an absolute URL.

        :class:`~.TextResponse` provides a :meth:`~.TextResponse.follow`
        method which supports selectors in addition to absolute/relative URLs
        and Link objects.

        .. versionadded:: 2.0
           The *flags* parameter.
        """
        if encoding is None:
            raise ValueError("encoding can't be None")
        if isinstance(url, Link):
            url = url.url
        elif url is None:
            raise ValueError("url can't be None")
        url = self.urljoin(url)

        return Request(
            url=url,
            callback=callback,
            method=method,
            headers=headers,
            body=body,
            cookies=cookies,
            meta=meta,
            encoding=encoding,
            priority=priority,
            dont_filter=dont_filter,
            errback=errback,
            cb_kwargs=cb_kwargs,
            flags=flags,
        )

    def follow_all(
        self,
        urls: Iterable[Union[str, Link]],
        callback: Optional[Callable] = None,
        method: str = "GET",
        headers: Union[Mapping[AnyStr, Any], Iterable[Tuple[AnyStr, Any]], None] = None,
        body: Optional[Union[bytes, str]] = None,
        cookies: Optional[Union[dict, List[dict]]] = None,
        meta: Optional[Dict[str, Any]] = None,
        encoding: Optional[str] = "utf-8",
        priority: int = 0,
        dont_filter: bool = False,
        errback: Optional[Callable] = None,
        cb_kwargs: Optional[Dict[str, Any]] = None,
        flags: Optional[List[str]] = None,
    ) -> Generator[Request, None, None]:
        """
        .. versionadded:: 2.0

        Return an iterable of :class:`~.Request` instances to follow all links
        in ``urls``. It accepts the same arguments as ``Request.__init__`` method,
        but elements of ``urls`` can be relative URLs or :class:`~scrapy.link.Link` objects,
        not only absolute URLs.

        :class:`~.TextResponse` provides a :meth:`~.TextResponse.follow_all`
        method which supports selectors in addition to absolute/relative URLs
        and Link objects.
        """
        if not hasattr(urls, "__iter__"):
            raise TypeError("'urls' argument must be an iterable")
        return (
            self.follow(
                url=url,
                callback=callback,
                method=method,
                headers=headers,
                body=body,
                cookies=cookies,
                meta=meta,
                encoding=encoding,
                priority=priority,
                dont_filter=dont_filter,
                errback=errback,
                cb_kwargs=cb_kwargs,
                flags=flags,
            )
            for url in urls
        )
