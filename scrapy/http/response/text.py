"""
This module implements the TextResponse class which adds encoding handling and
discovering (through HTTP headers) to base Response class.

See documentation in docs/ref/request-response.rst
"""

import re

from scrapy.xlib.BeautifulSoup import UnicodeDammit

from scrapy.http.response import Response
from scrapy.utils.python import memoizemethod

class TextResponse(Response):

    _ENCODING_RE = re.compile(r'charset=([\w-]+)', re.I)

    __slots__ = ['_encoding']

    def __init__(self, url, status=200, headers=None, body=None, meta=None, flags=None, encoding=None):
        self._encoding = encoding
        if isinstance(body, unicode):
            if encoding is None:
                clsname = self.__class__.__name__
                raise TypeError("To instantiate a %s with unicode body you must specify the encoding" % clsname)
            body = body.encode(encoding)
        Response.__init__(self, url, status, headers, body, meta, flags)

    def set_body(self, body):
        if isinstance(body, str):
            self._body = body
        elif isinstance(body, unicode):
            self._body = body.encode(self._encoding)
        elif body is None:
            self._body = None
        else:
            raise TypeError("Request body must either str, unicode or None. Got: '%s'" % type(body).__name__)
    body = property(lambda x: x._body, set_body)

    def replace(self, *args, **kwargs):
        kwargs.setdefault('encoding', getattr(self, '_encoding', None))
        return Response.replace(self, *args, **kwargs)

    @property
    def encoding(self):
        return self._encoding or self.headers_encoding() or self.body_encoding()

    @memoizemethod('cache')
    def headers_encoding(self, headers=None):
        if headers is None:
            headers = self.headers
        content_type = headers.get('Content-Type')
        if content_type:
            encoding = self._ENCODING_RE.search(content_type)
            if encoding:
                return encoding.group(1)

    @memoizemethod('cache')
    def body_as_unicode(self):
        """Return body as unicode"""
        possible_encodings = (self._encoding, self.headers_encoding(), self._body_declared_encoding())
        dammit = UnicodeDammit(self.body, possible_encodings)
        self.cache['body_inferred_encoding'] = dammit.originalEncoding
        # XXX: sometimes dammit.unicode fails, even when it recognizes the encoding correctly
        return dammit.unicode

    def body_encoding(self):
        return self._body_inferred_encoding()

    def _body_inferred_encoding(self):
        if 'body_inferred_encoding' not in self.cache:
            self.body_as_unicode()
        return self.cache['body_inferred_encoding']

    def _body_declared_encoding(self):
        return None
