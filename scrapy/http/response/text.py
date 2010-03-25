"""
This module implements the TextResponse class which adds encoding handling and
discovering (through HTTP headers) to base Response class.

See documentation in docs/topics/request-response.rst
"""

import re

from scrapy.xlib.BeautifulSoup import UnicodeDammit

from scrapy.http.response import Response
from scrapy.utils.python import memoizemethod_noargs
from scrapy.utils.encoding import encoding_exists, resolve_encoding
from scrapy.conf import settings

class TextResponse(Response):

    _DEFAULT_ENCODING = settings['DEFAULT_RESPONSE_ENCODING']
    _ENCODING_RE = re.compile(r'charset=([\w-]+)', re.I)

    __slots__ = ['_encoding', '_cached_benc']

    def __init__(self, url, status=200, headers=None, body=None, meta=None, \
            flags=None, encoding=None):
        self._encoding = encoding
        self._cached_benc = None
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
        enc = self._declared_encoding()
        if not (enc and encoding_exists(enc)):
            enc = self._body_inferred_encoding() or self._DEFAULT_ENCODING
        return resolve_encoding(enc)

    def _declared_encoding(self):
        return self._encoding or self._headers_encoding() \
            or self._body_declared_encoding()

    @memoizemethod_noargs
    def body_as_unicode(self):
        """Return body as unicode"""
        denc = self._declared_encoding()
        dencs = [resolve_encoding(denc)] if denc else []
        dammit = UnicodeDammit(self.body, dencs)
        benc = dammit.originalEncoding
        self._cached_benc = benc if benc != 'ascii' else None
        return self.body.decode(benc) if benc == 'utf-16' else dammit.unicode

    @memoizemethod_noargs
    def _headers_encoding(self):
        content_type = self.headers.get('Content-Type')
        if content_type:
            m = self._ENCODING_RE.search(content_type)
            if m:
                encoding = m.group(1)
                if encoding_exists(encoding):
                    return encoding

    def _body_inferred_encoding(self):
        if self._cached_benc is None:
            self.body_as_unicode()
        return self._cached_benc

    def _body_declared_encoding(self):
        # implemented in subclasses (XmlResponse, HtmlResponse)
        return None
