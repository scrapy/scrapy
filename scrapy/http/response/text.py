"""
This module implements the TextResponse class which adds encoding handling and
discovering (through HTTP headers) to base Response class.

See documentation in docs/topics/request-response.rst
"""

import re

from scrapy.xlib.BeautifulSoup import UnicodeDammit

from scrapy.http.response import Response
from scrapy.utils.python import memoizemethod_noargs

class TextResponse(Response):

    _ENCODING_RE = re.compile(r'charset=([\w-]+)', re.I)

    __slots__ = ['_encoding', '_body_inferred_encoding']

    def __init__(self, url, status=200, headers=None, body=None, meta=None, \
            flags=None, encoding=None):
        self._encoding = encoding
        self._body_inferred_encoding = None
        super(TextResponse, self).__init__(url, status, headers, body, meta, flags)

    def _get_url(self):
        return self._url

    def _set_url(self, url):
        if isinstance(url, unicode):
            if self.encoding is None:
                raise TypeError('Cannot convert unicode url - %s has no encoding' %
                    type(self).__name__)
            self._url = url.encode(self.encoding)
        else:
            super(TextResponse, self)._set_url(url)

    url = property(_get_url, _set_url)

    def _set_body(self, body):
        self._body = ''
        if isinstance(body, unicode):
            if self.encoding is None:
                raise TypeError('Cannot convert unicode body - %s has no encoding' %
                    type(self).__name__)
            self._body = body.encode(self._encoding)
        else:
            super(TextResponse, self)._set_body(body)

    def replace(self, *args, **kwargs):
        kwargs.setdefault('encoding', getattr(self, '_encoding', None))
        return Response.replace(self, *args, **kwargs)

    @property
    def encoding(self):
        return self._encoding or self.headers_encoding() or self.body_encoding()

    @memoizemethod_noargs
    def headers_encoding(self):
        content_type = self.headers.get('Content-Type')
        if content_type:
            encoding = self._ENCODING_RE.search(content_type)
            if encoding:
                return encoding.group(1)

    @memoizemethod_noargs
    def body_as_unicode(self):
        """Return body as unicode"""
        possible_encodings = (self._encoding, self.headers_encoding(), \
            self._body_declared_encoding())
        dammit = UnicodeDammit(self.body, possible_encodings)
        self._body_inferred_encoding = dammit.originalEncoding
        return dammit.unicode

    def body_encoding(self):
        if self._body_inferred_encoding is None:
            self.body_as_unicode()
        return self._body_inferred_encoding

    def _body_declared_encoding(self):
        # implemented in subclasses (XmlResponse, HtmlResponse)
        return None
