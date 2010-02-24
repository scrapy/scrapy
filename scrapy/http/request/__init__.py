"""
This module implements the Request class which is used to represent HTTP
requests in Scrapy.

See documentation in docs/topics/request-response.rst
"""

import copy

from twisted.internet import defer

from scrapy.http.headers import Headers
from scrapy.utils.url import safe_url_string
from scrapy.utils.trackref import object_ref

class Request(object_ref):

    __slots__ = ['_encoding', 'method', '_url', '_body', '_meta', \
        'dont_filter', 'headers', 'cookies', 'deferred', 'priority', \
        '__weakref__']

    def __init__(self, url, callback=None, method='GET', headers=None, body=None, 
                 cookies=None, meta=None, encoding='utf-8', priority=0.0,
                 dont_filter=False, errback=None):

        self._encoding = encoding  # this one has to be set first
        self.method = method.upper()
        self._set_url(url)
        self._set_body(body)
        self.priority = priority

        if callable(callback):
            callback = defer.Deferred().addCallbacks(callback, errback)
        self.deferred = callback or defer.Deferred()

        self.cookies = cookies or {}
        self.headers = Headers(headers or {}, encoding=encoding)
        self.dont_filter = dont_filter

        self._meta = dict(meta) if meta else None

    @property
    def meta(self):
        if self._meta is None:
            self._meta = {}
        return self._meta

    def _get_url(self):
        return self._url

    def _set_url(self, url):
        if isinstance(url, str):
            self._url = safe_url_string(url)
        elif isinstance(url, unicode):
            if self.encoding is None:
                raise TypeError('Cannot convert unicode url - %s has no encoding' %
                    type(self).__name__)
            unicode_url = url if isinstance(url, unicode) else url.decode(self.encoding)
            self._url = safe_url_string(unicode_url, self.encoding)
        else:
            raise TypeError('Request url must be str or unicode, got %s:' % type(url).__name__)

    url = property(_get_url, _set_url)

    def _get_body(self):
        return self._body

    def _set_body(self, body):
        if isinstance(body, str):
            self._body = body
        elif isinstance(body, unicode):
            if self.encoding is None:
                raise TypeError('Cannot convert unicode body - %s has no encoding' %
                    type(self).__name__)
            self._body = body.encode(self.encoding)
        elif body is None:
            self._body = ''
        else:
            raise TypeError("Request body must either str or unicode. Got: '%s'" % type(body).__name__)

    body = property(_get_body, _set_body)

    @property
    def encoding(self):
        return self._encoding

    def __str__(self):
        return "<%s %s>" % (self.method, self.url)

    def __repr__(self):
        attrs = ['url', 'method', 'body', 'headers', 'cookies', 'meta']
        args = ", ".join(["%s=%r" % (a, getattr(self, a)) for a in attrs])
        return "%s(%s)" % (self.__class__.__name__, args)

    def copy(self):
        """Return a copy of this Request"""
        return self.replace()

    def replace(self, url=None, callback=None, method=None, headers=None, body=None, \
                cookies=None, meta=None, encoding=None, priority=None, \
                dont_filter=None, errback=None):
        """Create a new Request with the same attributes except for those
        given new values.
        """
        return self.__class__(url=self.url if url is None else url,
                              callback=callback,
                              method=self.method if method is None else method,
                              headers=copy.deepcopy(self.headers) if headers is None else headers,
                              body=self.body if body is None else body,
                              cookies=self.cookies if cookies is None else cookies,
                              meta=self.meta if meta is None else meta,
                              encoding=self.encoding if encoding is None else encoding,
                              priority=self.priority if priority is None else priority,
                              dont_filter=self.dont_filter if dont_filter is None else dont_filter,
                              errback=errback)
