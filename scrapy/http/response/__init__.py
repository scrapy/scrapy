"""
This module implements the Response class which is used to represent HTTP
responses in Scrapy.

See documentation in docs/topics/request-response.rst
"""
from typing import Any, Generator, List, Tuple
from urllib.parse import urljoin

from scrapy.exceptions import NotSupported
from scrapy.http.common import obsolete_setter
from scrapy.http.headers import Headers
from scrapy.http.request import Request
from scrapy.link import Link
from scrapy.utils.trackref import object_ref


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
        status=200,
        headers=None,
        body=b"",
        flags=None,
        request=None,
        certificate=None,
        ip_address=None,
        protocol=None,
    ):
        self.headers = Headers(headers or {})
        self.status = int(status)
        self._set_body(body)
        self._set_url(url)
        self.request = request
        self.flags = [] if flags is None else list(flags)
        self.certificate = certificate
        self.ip_address = ip_address
        self.protocol = protocol

    @property
    def cb_kwargs(self):
        try:
            return self.request.cb_kwargs
        except AttributeError:
            raise AttributeError(
                "Response.cb_kwargs not available, this response "
                "is not tied to any request"
            )

    @property
    def meta(self):
        try:
            return self.request.meta
        except AttributeError:
            raise AttributeError(
                "Response.meta not available, this response "
                "is not tied to any request"
            )

    def _get_url(self):
        return self._url

    def _set_url(self, url: str):
        if isinstance(url, str):
            self._url = url
        else:
            raise TypeError(
                f"{type(self).__name__} url must be str, " f"got {type(url).__name__}"
            )

    url = property(_get_url, obsolete_setter(_set_url, "url"))

    def _get_body(self):
        return self._body

    def _set_body(self, body):
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

    body = property(_get_body, obsolete_setter(_set_body, "body"))

    def __repr__(self):
        return f"<{self.status} {self.url}>"

    def copy(self):
        """Return a copy of this Response"""
        return self.replace()

    def replace(self, *args, **kwargs):
        """Create a new Response with the same attributes except for those given new values"""
        for x in self.attributes:
            kwargs.setdefault(x, getattr(self, x))
        cls = kwargs.pop("cls", self.__class__)
        return cls(*args, **kwargs)

    def urljoin(self, url):
        """Join this Response's url with a possible relative url to form an
        absolute interpretation of the latter."""
        return urljoin(self.url, url)

    @property
    def text(self):
        """For subclasses of TextResponse, this will return the body
        as str
        """
        raise AttributeError("Response content isn't text")

    def css(self, *a, **kw):
        """Shortcut method implemented only by responses whose content
        is text (subclasses of TextResponse).
        """
        raise NotSupported("Response content isn't text")

    def jmespath(self, *a, **kw):
        """Shortcut method implemented only by responses whose content
        is text (subclasses of TextResponse).
        """
        raise NotSupported("Response content isn't text")

    def xpath(self, *a, **kw):
        """Shortcut method implemented only by responses whose content
        is text (subclasses of TextResponse).
        """
        raise NotSupported("Response content isn't text")

    def follow(
        self,
        url,
        callback=None,
        method="GET",
        headers=None,
        body=None,
        cookies=None,
        meta=None,
        encoding="utf-8",
        priority=0,
        dont_filter=False,
        errback=None,
        cb_kwargs=None,
        flags=None,
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
        urls,
        callback=None,
        method="GET",
        headers=None,
        body=None,
        cookies=None,
        meta=None,
        encoding="utf-8",
        priority=0,
        dont_filter=False,
        errback=None,
        cb_kwargs=None,
        flags=None,
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


class ResponseBuilder:
    response: Response

    def __init__(self):
        pass

    def set_url(self, url: str):
        self.response._set_url(url)
        return self

    def set_status(self, status: int):
        self.response.status = int(status)
        return self

    def set_headers(self, headers: Headers):
        self.response.headers = headers
        return self

    def set_body(self, body: bytes | str):
        self.response._set_body(body)
        return self

    def set_flags(self, flags: List[str]):
        self.response.flags = flags
        return self

    def set_request(self, request: Any):
        self.response.request = request
        return self

    def set_certificate(self, certificate: Any):
        self.response.certificate = certificate
        return self

    def set_ip_address(self, ip_address: Any):
        self.response.ip_address = ip_address
        return self

    def set_protocol(self, protocol: Any):
        self.response.protocol = protocol
        return self

    def build(self) -> Response:
        return self.response
