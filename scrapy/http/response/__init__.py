"""
This module implements the Response class which is used to represent HTTP
responses in Scrapy.

See documentation in docs/ref/request-response.rst
"""

import copy

from scrapy.http.url import Url
from scrapy.http.headers import Headers

class Response(object):

    def __init__(self, url, status=200, headers=None, body='', meta=None, flags=None):
        self.url = Url(url)
        self.headers = Headers(headers or {})
        self.status = int(status)
        self.set_body(body)
        self.cached = False
        self.request = None
        self.meta = {} if meta is None else dict(meta)
        self.flags = [] if flags is None else list(flags)
        self.cache = {}

    def set_body(self, body):
        if isinstance(body, str):
            self._body = body
        elif isinstance(body, unicode):
            raise TypeError("Cannot assign a unicode body to a raw Response. Use TextResponse, HtmlResponse, etc")
        elif body is None:
            self._body = ''
        else:
            raise TypeError("Response body must either str or unicode. Got: '%s'" % type(body).__name__)
    body = property(lambda x: x._body, set_body)

    def __repr__(self):
        return "%s(url=%s, headers=%s, status=%s, body=%s)" % \
                (type(self).__name__, repr(self.url), repr(self.headers), repr(self.status), repr(self.body))

    def __str__(self):
        flags = "(%s) " % ",".join(self.flags) if self.flags else ""
        status = "%d " % self.status + " " if self.status != 200 else ""
        return "%s<%s%s>" % (flags, status, self.url)

    def copy(self):
        """Return a copy of this Response"""
        return self.replace()

    def replace(self, url=None, status=None, headers=None, body=None, meta=None, flags=None, cls=None, **kwargs):
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
