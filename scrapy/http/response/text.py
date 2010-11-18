"""
This module implements the TextResponse class which adds encoding handling and
discovering (through HTTP headers) to base Response class.

See documentation in docs/topics/request-response.rst
"""

import re
import codecs
from scrapy.xlib.BeautifulSoup import UnicodeDammit
from scrapy.http.response import Response
from scrapy.utils.python import memoizemethod_noargs
from scrapy.utils.encoding import encoding_exists, resolve_encoding
from scrapy.conf import settings


# Python decoder doesn't follow unicode standard when handling
# bad utf-8 encoded strings. see http://bugs.python.org/issue8271
codecs.register_error('scrapy_replace', lambda exc: (u'\ufffd', exc.start+1))


class TextResponse(Response):

    _DEFAULT_ENCODING = settings['DEFAULT_RESPONSE_ENCODING']
    _ENCODING_RE = re.compile(r'charset=([\w-]+)', re.I)

    __slots__ = ['_encoding', '_cached_benc', '_cached_ubody']

    def __init__(self, *args, **kwargs):
        self._encoding = kwargs.pop('encoding', None)
        self._cached_benc = None
        self._cached_ubody = None
        super(TextResponse, self).__init__(*args, **kwargs)

    def _set_url(self, url):
        if isinstance(url, unicode):
            if self.encoding is None:
                raise TypeError('Cannot convert unicode url - %s has no encoding' %
                    type(self).__name__)
            self._url = url.encode(self.encoding)
        else:
            super(TextResponse, self)._set_url(url)

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
        kwargs.setdefault('encoding', self.encoding)
        return Response.replace(self, *args, **kwargs)

    @property
    def encoding(self):
        return self._get_encoding(infer=True)

    def _get_encoding(self, infer=False):
        enc = self._declared_encoding()
        if enc and not encoding_exists(enc):
            enc = None
        if not enc and infer:
            enc = self._body_inferred_encoding()
        if not enc:
            enc = self._DEFAULT_ENCODING
        return resolve_encoding(enc)

    def _declared_encoding(self):
        return self._encoding or self._headers_encoding() \
            or self._body_declared_encoding()

    def body_as_unicode(self):
        """Return body as unicode"""
        if self._cached_ubody is None:
            self._cached_ubody = self.body.decode(self.encoding, 'scrapy_replace')
        return self._cached_ubody

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
            enc = self._get_encoding()
            dammit = UnicodeDammit(self.body, [enc])
            benc = dammit.originalEncoding
            self._cached_benc = benc
            # UnicodeDammit is buggy decoding utf-16
            if self._cached_ubody is None and benc != 'utf-16':
                self._cached_ubody = dammit.unicode
        return self._cached_benc

    def _body_declared_encoding(self):
        # implemented in subclasses (XmlResponse, HtmlResponse)
        return None
