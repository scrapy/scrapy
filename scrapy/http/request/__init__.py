"""
This module implements the Request class which is used to represent HTTP
requests in Scrapy.

See documentation in docs/topics/request-response.rst
"""
from typing import Callable, List, Optional, Type, TypeVar
from w3lib.url import safe_url_string

import scrapy
from scrapy.http.common import obsolete_setter
from scrapy.http.headers import Headers
from scrapy.utils.curl import curl_to_request_kwargs
from scrapy.utils.python import to_bytes
from scrapy.utils.reqser import request_from_dict, request_to_dict, _find_method, _get_method
from scrapy.utils.trackref import object_ref
from scrapy.utils.url import escape_ajax


class Request(object_ref):

    def __init__(self, url, callback=None, method='GET', headers=None, body=None,
                 cookies=None, meta=None, encoding='utf-8', priority=0,
                 dont_filter=False, errback=None, flags=None, cb_kwargs=None):

        self._encoding = encoding  # this one has to be set first
        self.method = str(method).upper()
        self._set_url(url)
        self._set_body(body)
        if not isinstance(priority, int):
            raise TypeError(f"Request priority not an integer: {priority!r}")
        self.priority = priority

        if callback is not None and not callable(callback):
            raise TypeError(f'callback must be a callable, got {type(callback).__name__}')
        if errback is not None and not callable(errback):
            raise TypeError(f'errback must be a callable, got {type(errback).__name__}')
        self.callback = callback
        self.errback = errback

        self.cookies = cookies or {}
        self.headers = Headers(headers or {}, encoding=encoding)
        self.dont_filter = dont_filter

        self._meta = dict(meta) if meta else None
        self._cb_kwargs = dict(cb_kwargs) if cb_kwargs else None
        self.flags = [] if flags is None else list(flags)

    @property
    def cb_kwargs(self):
        if self._cb_kwargs is None:
            self._cb_kwargs = {}
        return self._cb_kwargs

    @property
    def meta(self):
        if self._meta is None:
            self._meta = {}
        return self._meta

    def _get_url(self):
        return self._url

    def _set_url(self, url):
        if not isinstance(url, str):
            raise TypeError(f'Request url must be str or unicode, got {type(url).__name__}')

        s = safe_url_string(url, self.encoding)
        self._url = escape_ajax(s)

        if (
            '://' not in self._url
            and not self._url.startswith('about:')
            and not self._url.startswith('data:')
        ):
            raise ValueError(f'Missing scheme in request url: {self._url}')

    url = property(_get_url, obsolete_setter(_set_url, 'url'))

    def _get_body(self):
        return self._body

    def _set_body(self, body):
        if body is None:
            self._body = b''
        else:
            self._body = to_bytes(body, self.encoding)

    body = property(_get_body, obsolete_setter(_set_body, 'body'))

    @property
    def encoding(self):
        return self._encoding

    def __str__(self):
        return f"<{self.method} {self.url}>"

    __repr__ = __str__

    def copy(self):
        """Return a copy of this Request"""
        return self.replace()

    def replace(self, *args, **kwargs):
        """Create a new Request with the same attributes except for those
        given new values.
        """
        for x in ['url', 'method', 'headers', 'body', 'cookies', 'meta', 'flags',
                  'encoding', 'priority', 'dont_filter', 'callback', 'errback', 'cb_kwargs']:
            kwargs.setdefault(x, getattr(self, x))
        cls = kwargs.pop('cls', self.__class__)
        return cls(*args, **kwargs)

    @classmethod
    def from_curl(cls, curl_command, ignore_unknown_options=True, **kwargs):
        """Create a Request object from a string containing a `cURL
        <https://curl.haxx.se/>`_ command. It populates the HTTP method, the
        URL, the headers, the cookies and the body. It accepts the same
        arguments as the :class:`Request` class, taking preference and
        overriding the values of the same arguments contained in the cURL
        command.

        Unrecognized options are ignored by default. To raise an error when
        finding unknown options call this method by passing
        ``ignore_unknown_options=False``.

        .. caution:: Using :meth:`from_curl` from :class:`~scrapy.http.Request`
                     subclasses, such as :class:`~scrapy.http.JSONRequest`, or
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


RequestListTypeVar = TypeVar("RequestListTypeVar", bound="RequestList")


class RequestList(object_ref):
    def __init__(
        self,
        *requests,
        callback: Optional[Callable] = None,
        errback: Optional[Callable] = None,
        priority: int = 0,
        cb_kwargs: Optional[dict] = None,
        meta: Optional[dict] = None,
    ) -> None:
        self.requests: List[Request] = list(requests)
        self.callback = callback
        self.errback = errback
        self.priority = priority
        self.cb_kwargs = cb_kwargs or {}
        self.meta = meta or {}
        for req in self.requests:
            req.meta["request_list"] = self

    @classmethod
    def from_dict(
        cls: Type[RequestListTypeVar], d: dict, spider: Optional["scrapy.spiders.Spider"] = None
    ) -> RequestListTypeVar:
        callback = d["callback"]
        if callback and spider:
            callback = _get_method(spider, callback)
        errback = d["errback"]
        if errback and spider:
            errback = _get_method(spider, errback)
        requests = [request_from_dict(req, spider) for req in d["requests"]]
        return cls(
            *requests,
            callback=callback,
            errback=errback,
            priority=d["priority"],
            cb_kwargs=d["cb_kwargs"],
            meta=d["meta"],
        )

    def to_dict(self, spider: Optional["scrapy.spiders.Spider"] = None) -> dict:
        callback = self.callback
        if callable(callback):
            callback = _find_method(spider, callback)
        errback = self.errback
        if callable(errback):
            errback = _find_method(spider, errback)
        requests = []
        for req in self.requests:
            req_dict = request_to_dict(req, spider)
            req_dict["meta"].pop("request_list", None)
            requests.append(req_dict)
        return {
            "requests": requests,
            "callback": callback,
            "errback": errback,
            "priority": self.priority,
            "cb_kwargs": self.cb_kwargs,
            "meta": self.meta,
        }
