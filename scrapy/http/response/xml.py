"""
This module implements the XmlResponse class which adds encoding
discovering through XML encoding declarations to the TextResponse class.

See documentation in docs/topics/request-response.rst
"""

import re

from scrapy.http.response.text import TextResponse
from scrapy.utils.python import memoizemethod_noargs

class XmlResponse(TextResponse):

    _template = r'''%s\s*=\s*["']?\s*%s\s*["']?'''
    _encoding_re  = _template % ('encoding', r'(?P<charset>[\w-]+)')
    XMLDECL_RE  = re.compile(r'<\?xml\s.*?%s' % _encoding_re, re.I)

    @memoizemethod_noargs
    def _body_declared_encoding(self):
        chunk = self.body[:5000]
        match = self.XMLDECL_RE.search(chunk)
        return match.group('charset') if match else None

