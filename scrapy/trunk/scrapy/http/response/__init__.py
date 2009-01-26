"""
This module implements the Response class which is used to represent HTTP
responses in Scrapy.

See documentation in docs/ref/request-response.rst
"""

import copy

from twisted.web.http import RESPONSES

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
        new = cls(url=url or self.url,
                  status=status or self.status,
                  headers=headers or copy.deepcopy(self.headers),
                  body=body or self.body,
                  meta=meta or self.meta,
                  flags=flags or self.flags,
                  **kwargs)
        return new

    def httprepr(self):
        """
        Return raw HTTP response representation (as string). This is provided
        only for reference, since it's not the exact stream of bytes that was
        received (that's not exposed by Twisted).
        """

        s  = "HTTP/1.1 %d %s\r\n" % (self.status, RESPONSES[self.status])
        if self.headers:
            s += self.headers.to_string() + "\r\n"
        s += "\r\n"
        s += self.body
        return s
