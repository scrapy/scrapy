"""
This module implements the TextResponse class which adds encoding handling and
discovering (through HTTP headers) to base Response class.

See documentation in docs/topics/request-response.rst
"""

from w3lib.encoding import html_to_unicode, resolve_encoding, \
    html_body_declared_encoding, http_content_type_encoding
from scrapy.http.response import Response
from scrapy.utils.python import memoizemethod_noargs


class TextResponse(Response):

    _DEFAULT_ENCODING = 'ascii'

    def __init__(self, *args, **kwargs):
        self._encoding = kwargs.pop('encoding', None)
        self._cached_benc = None
        self._cached_ubody = None
        self._cached_selector = None
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
        return self._declared_encoding() or self._body_inferred_encoding()

    def _declared_encoding(self):
        return self._encoding or self._headers_encoding() \
            or self._body_declared_encoding()

    def body_as_unicode(self):
        """Return body as unicode"""
        # check for self.encoding before _cached_ubody just in
        # _body_inferred_encoding is called
        benc = self.encoding
        if self._cached_ubody is None:
            charset = 'charset=%s' % benc
            self._cached_ubody = html_to_unicode(charset, self.body)[1]
        return self._cached_ubody

    @memoizemethod_noargs
    def _headers_encoding(self):
        content_type = self.headers.get('Content-Type')
        return http_content_type_encoding(content_type)

    def _body_inferred_encoding(self):
        if self._cached_benc is None:
            content_type = self.headers.get('Content-Type')
            benc, ubody = html_to_unicode(content_type, self.body, \
                    auto_detect_fun=self._auto_detect_fun, \
                    default_encoding=self._DEFAULT_ENCODING)
            self._cached_benc = benc
            self._cached_ubody = ubody
        return self._cached_benc

    def _auto_detect_fun(self, text):
        for enc in (self._DEFAULT_ENCODING, 'utf-8', 'cp1252'):
            try:
                text.decode(enc)
            except UnicodeError:
                continue
            return resolve_encoding(enc)

    @memoizemethod_noargs
    def _body_declared_encoding(self):
        return html_body_declared_encoding(self.body)

    @property
    def selector(self):
        from scrapy.selector import Selector
        if self._cached_selector is None:
            self._cached_selector = Selector(self)
        return self._cached_selector

    def xpath(self, query):
        return self.selector.xpath(query)

    def css(self, query):
        return self.selector.css(query)
