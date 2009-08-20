"""
This module implements the HtmlResponse class which adds encoding
discovering through HTML encoding declarations to the TextResponse class.

See documentation in docs/topics/request-response.rst
"""

import re

from scrapy.http.response.text import TextResponse
from scrapy.utils.python import memoizemethod

class HtmlResponse(TextResponse):

    __slots__ = ()

    _template = r'''%s\s*=\s*["']?\s*%s\s*["']?'''

    _httpequiv_re = _template % ('http-equiv', 'Content-Type')
    _content_re   = _template % ('content', r'(?P<mime>[^;]+);\s*charset=(?P<charset>[\w-]+)')
    _encoding_re  = _template % ('encoding', r'(?P<charset>[\w-]+)')

    METATAG_RE  = re.compile(r'<meta\s+%s\s+%s' % (_httpequiv_re, _content_re), re.I)
    METATAG_RE2 = re.compile(r'<meta\s+%s\s+%s' % (_content_re, _httpequiv_re), re.I)

    def body_encoding(self):
        return self._body_declared_encoding() or self._body_inferred_encoding()

    @memoizemethod('cache')
    def _body_declared_encoding(self):
        chunk = self.body[:5000]
        match = self.METATAG_RE.search(chunk) or self.METATAG_RE2.search(chunk)
        return match.group('charset') if match else None


