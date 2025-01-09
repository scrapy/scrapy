"""
This module implements the TextResponse class which adds encoding handling and
discovering (through HTTP headers) to base Response class.

See documentation in docs/topics/request-response.rst
"""

from __future__ import annotations

import json
from contextlib import suppress
from typing import TYPE_CHECKING, Any, AnyStr, cast
from urllib.parse import urljoin

import parsel
from w3lib.encoding import (
    html_body_declared_encoding,
    html_to_unicode,
    http_content_type_encoding,
    read_bom,
    resolve_encoding,
)
from w3lib.html import strip_html5_whitespace

from scrapy.http.response import Response
from scrapy.utils.python import memoizemethod_noargs, to_unicode
from scrapy.utils.response import get_base_url

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from twisted.python.failure import Failure

    from scrapy.http.request import CallbackT, CookiesT, Request
    from scrapy.link import Link
    from scrapy.selector import Selector, SelectorList


_NONE = object()


class TextResponse(Response):
    _DEFAULT_ENCODING = "ascii"
    _cached_decoded_json = _NONE

    attributes: tuple[str, ...] = (*Response.attributes, "encoding")

    def __init__(self, *args: Any, **kwargs: Any):
        self._encoding: str | None = kwargs.pop("encoding", None)
        self._cached_benc: str | None = None
        self._cached_ubody: str | None = None
        self._cached_selector: Selector | None = None
        super().__init__(*args, **kwargs)

    def _set_body(self, body: str | bytes | None) -> None:
        self._body: bytes = b""  # used by encoding detection
        if isinstance(body, str):
            if self._encoding is None:
                raise TypeError(
                    "Cannot convert unicode body - "
                    f"{type(self).__name__} has no encoding"
                )
            self._body = body.encode(self._encoding)
        else:
            super()._set_body(body)

    @property
    def encoding(self) -> str:
        return self._declared_encoding() or self._body_inferred_encoding()

    def _declared_encoding(self) -> str | None:
        return (
            self._encoding
            or self._bom_encoding()
            or self._headers_encoding()
            or self._body_declared_encoding()
        )

    def json(self) -> Any:
        """
        .. versionadded:: 2.2

        Deserialize a JSON document to a Python object.
        """
        if self._cached_decoded_json is _NONE:
            self._cached_decoded_json = json.loads(self.body)
        return self._cached_decoded_json

    @property
    def text(self) -> str:
        """Body as unicode"""
        # access self.encoding before _cached_ubody to make sure
        # _body_inferred_encoding is called
        benc = self.encoding
        if self._cached_ubody is None:
            charset = f"charset={benc}"
            self._cached_ubody = html_to_unicode(charset, self.body)[1]
        return self._cached_ubody

    def urljoin(self, url: str) -> str:
        """Join this Response's url with a possible relative url to form an
        absolute interpretation of the latter."""
        return urljoin(get_base_url(self), url)

    @memoizemethod_noargs
    def _headers_encoding(self) -> str | None:
        content_type = cast(bytes, self.headers.get(b"Content-Type", b""))
        return http_content_type_encoding(to_unicode(content_type, encoding="latin-1"))

    def _body_inferred_encoding(self) -> str:
        if self._cached_benc is None:
            content_type = to_unicode(
                cast(bytes, self.headers.get(b"Content-Type", b"")), encoding="latin-1"
            )
            benc, ubody = html_to_unicode(
                content_type,
                self.body,
                auto_detect_fun=self._auto_detect_fun,
                default_encoding=self._DEFAULT_ENCODING,
            )
            self._cached_benc = benc
            self._cached_ubody = ubody
        return self._cached_benc

    def _auto_detect_fun(self, text: bytes) -> str | None:
        for enc in (self._DEFAULT_ENCODING, "utf-8", "cp1252"):
            try:
                text.decode(enc)
            except UnicodeError:
                continue
            return resolve_encoding(enc)
        return None

    @memoizemethod_noargs
    def _body_declared_encoding(self) -> str | None:
        return html_body_declared_encoding(self.body)

    @memoizemethod_noargs
    def _bom_encoding(self) -> str | None:
        return read_bom(self.body)[0]

    @property
    def selector(self) -> Selector:
        from scrapy.selector import Selector

        if self._cached_selector is None:
            self._cached_selector = Selector(self)
        return self._cached_selector

    def jmespath(self, query: str, **kwargs: Any) -> SelectorList:
        from scrapy.selector import SelectorList

        if not hasattr(self.selector, "jmespath"):
            raise AttributeError(
                "Please install parsel >= 1.8.1 to get jmespath support"
            )

        return cast(SelectorList, self.selector.jmespath(query, **kwargs))

    def xpath(self, query: str, **kwargs: Any) -> SelectorList:
        from scrapy.selector import SelectorList

        return cast(SelectorList, self.selector.xpath(query, **kwargs))

    def css(self, query: str) -> SelectorList:
        from scrapy.selector import SelectorList

        return cast(SelectorList, self.selector.css(query))

    def follow(
        self,
        url: str | Link | parsel.Selector,
        callback: CallbackT | None = None,
        method: str = "GET",
        headers: Mapping[AnyStr, Any] | Iterable[tuple[AnyStr, Any]] | None = None,
        body: bytes | str | None = None,
        cookies: CookiesT | None = None,
        meta: dict[str, Any] | None = None,
        encoding: str | None = None,
        priority: int = 0,
        dont_filter: bool = False,
        errback: Callable[[Failure], Any] | None = None,
        cb_kwargs: dict[str, Any] | None = None,
        flags: list[str] | None = None,
    ) -> Request:
        """
        Return a :class:`~.Request` instance to follow a link ``url``.
        It accepts the same arguments as ``Request.__init__()`` method,
        but ``url`` can be not only an absolute URL, but also

        * a relative URL
        * a :class:`~scrapy.link.Link` object, e.g. the result of
          :ref:`topics-link-extractors`
        * a :class:`~scrapy.Selector` object for a ``<link>`` or ``<a>`` element, e.g.
          ``response.css('a.my_link')[0]``
        * an attribute :class:`~scrapy.Selector` (not SelectorList), e.g.
          ``response.css('a::attr(href)')[0]`` or
          ``response.xpath('//img/@src')[0]``

        See :ref:`response-follow-example` for usage examples.
        """
        if isinstance(url, parsel.Selector):
            url = _url_from_selector(url)
        elif isinstance(url, parsel.SelectorList):
            raise ValueError("SelectorList is not supported")
        encoding = self.encoding if encoding is None else encoding
        return super().follow(
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
        urls: Iterable[str | Link] | parsel.SelectorList | None = None,
        callback: CallbackT | None = None,
        method: str = "GET",
        headers: Mapping[AnyStr, Any] | Iterable[tuple[AnyStr, Any]] | None = None,
        body: bytes | str | None = None,
        cookies: CookiesT | None = None,
        meta: dict[str, Any] | None = None,
        encoding: str | None = None,
        priority: int = 0,
        dont_filter: bool = False,
        errback: Callable[[Failure], Any] | None = None,
        cb_kwargs: dict[str, Any] | None = None,
        flags: list[str] | None = None,
        css: str | None = None,
        xpath: str | None = None,
    ) -> Iterable[Request]:
        """
        A generator that produces :class:`~.Request` instances to follow all
        links in ``urls``. It accepts the same arguments as the :class:`~.Request`'s
        ``__init__()`` method, except that each ``urls`` element does not need to be
        an absolute URL, it can be any of the following:

        * a relative URL
        * a :class:`~scrapy.link.Link` object, e.g. the result of
          :ref:`topics-link-extractors`
        * a :class:`~scrapy.Selector` object for a ``<link>`` or ``<a>`` element, e.g.
          ``response.css('a.my_link')[0]``
        * an attribute :class:`~scrapy.Selector` (not SelectorList), e.g.
          ``response.css('a::attr(href)')[0]`` or
          ``response.xpath('//img/@src')[0]``

        In addition, ``css`` and ``xpath`` arguments are accepted to perform the link extraction
        within the ``follow_all()`` method (only one of ``urls``, ``css`` and ``xpath`` is accepted).

        Note that when passing a ``SelectorList`` as argument for the ``urls`` parameter or
        using the ``css`` or ``xpath`` parameters, this method will not produce requests for
        selectors from which links cannot be obtained (for instance, anchor tags without an
        ``href`` attribute)
        """
        arguments = [x for x in (urls, css, xpath) if x is not None]
        if len(arguments) != 1:
            raise ValueError(
                "Please supply exactly one of the following arguments: urls, css, xpath"
            )
        if not urls:
            if css:
                urls = self.css(css)
            if xpath:
                urls = self.xpath(xpath)
        if isinstance(urls, parsel.SelectorList):
            selectors = urls
            urls = []
            for sel in selectors:
                with suppress(_InvalidSelector):
                    urls.append(_url_from_selector(sel))
        return super().follow_all(
            urls=cast("Iterable[str | Link]", urls),
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


class _InvalidSelector(ValueError):
    """
    Raised when a URL cannot be obtained from a Selector
    """


def _url_from_selector(sel: parsel.Selector) -> str:
    if isinstance(sel.root, str):
        # e.g. ::attr(href) result
        return strip_html5_whitespace(sel.root)
    if not hasattr(sel.root, "tag"):
        raise _InvalidSelector(f"Unsupported selector: {sel}")
    if sel.root.tag not in ("a", "link"):
        raise _InvalidSelector(
            f"Only <a> and <link> elements are supported; got <{sel.root.tag}>"
        )
    href = sel.root.get("href")
    if href is None:
        raise _InvalidSelector(f"<{sel.root.tag}> element has no href attribute: {sel}")
    return strip_html5_whitespace(href)
