"""
This module implements the Response class which is used to represent HTTP
responses in Scrapy.

See documentation in docs/topics/request-response.rst
"""

import copy

from scrapy.http.headers import Headers
from scrapy.utils.trackref import object_ref

class Response(object_ref):

    __slots__ = ['_url', 'headers', 'status', '_body', 'request', '_meta', \
        'flags', '__weakref__']

    def __init__(self, url, status=200, headers=None, body='', meta=None, flags=None):
        self.headers = Headers(headers or {})
        self.status = int(status)
        self._set_body(body)
        self._set_url(url)
        self.request = None
        self.flags = [] if flags is None else list(flags)
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
            self._url = url
        else:
            raise TypeError('%s url must be str, got %s:' % (type(self).__name__, \
                type(url).__name__))

    url = property(_get_url, _set_url)

    def _get_body(self):
        return self._body

    def _set_body(self, body):
        if isinstance(body, str):
            self._body = body
        elif isinstance(body, unicode):
            raise TypeError("Cannot assign a unicode body to a raw Response. " \
                "Use TextResponse, HtmlResponse, etc")
        elif body is None:
            self._body = ''
        else:
            raise TypeError("Response body must either str or unicode. Got: '%s'" \
                % type(body).__name__)

    body = property(_get_body, _set_body)

    def __repr__(self):
        d = {
            'status': self.status,
            'url': self.url,
            'headers': self.headers,
            'body': self.body,
            'meta': self.meta,
            'flags': self.flags,
        }
        return "%s(%s)" % (self.__class__.__name__, repr(d))

    def __str__(self):
        flags = "(%s) " % ",".join(self.flags) if self.flags else ""
        status = "%d " % self.status + " " if self.status != 200 else ""
        return "%s<%s%s>" % (flags, status, self.url)

    def copy(self):
        """Return a copy of this Response"""
        return self.replace()

    def replace(self, url=None, status=None, headers=None, body=None, meta=None, \
            flags=None, cls=None, **kwargs):
        """Create a new Response with the same attributes except for those
        given new values.
        """
        if cls is None:
            cls = self.__class__
        new = cls(url=self.url if url is None else url,
                  status=self.status if status is None else status,
                  headers=copy.deepcopy(self.headers) if headers is None else headers,
                  body=self.body if body is None else body,
                  meta=self.meta if meta is None else meta,
                  flags=self.flags if flags is None else flags,
                  **kwargs)
        return new
