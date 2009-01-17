"""
This module implements the Response class which is used to represent HTTP
esponses in Scrapy.

See documentation in docs/ref/request-response.rst
"""

import re
import copy
from types import NoneType

from twisted.web.http import RESPONSES
from BeautifulSoup import UnicodeDammit

from scrapy.http.url import Url
from scrapy.http.headers import Headers

class Response(object):

    _ENCODING_RE = re.compile(r'charset=([\w-]+)', re.I)

    def __init__(self, domain, url, status=200, headers=None, body=None, meta=None):
        self.domain = domain
        self.url = Url(url)
        self.headers = Headers(headers or {})
        self.status = status
        if body is not None:
            assert isinstance(body, basestring), \
                "body must be basestring, got %s" % type(body).__name__
            self.body = _ResponseBody(body, self.headers_encoding())
        else:
            self.body = None
        self.cached = False
        self.request = None
        self.meta = {} if meta is None else dict(meta)
        self.cache = {}

    def headers_encoding(self):
        content_type = self.headers.get('Content-Type')
        if content_type:
            encoding = self._ENCODING_RE.search(content_type[0])
            if encoding:
                return encoding.group(1)

    def __repr__(self):
        return "Response(domain=%s, url=%s, headers=%s, status=%s, body=%s)" % \
                (repr(self.domain), repr(self.url), repr(self.headers), repr(self.status), repr(self.body))

    def __str__(self):
        if self.status == 200:
            return "<%s>" % (self.url)
        else:
            return "<%d %s>" % (self.status, self.url)

    def copy(self):
        """Create a new Response based on the current one"""
        return self.replace()

    def replace(self, domain=None, url=None, status=None, headers=None, body=None):
        """Create a new Response with the same attributes except for those
        given new values.

        Example:

        >>> newresp = oldresp.replace(body="New body")
        """
        new = self.__class__(domain=domain or self.domain,
                             url=url or self.url,
                             status=status or self.status,
                             headers=headers or copy.deepcopy(self.headers),
                             body=body)
        if body is None:
            new.body = copy.deepcopy(self.body)
        new.meta = self.meta.copy()
        return new

    def httprepr(self):
        """
        Return raw HTTP response representation (as string). This is provided
        only for reference, since it's not the exact stream of bytes that was
        received (that's not exposed by Twisted).
        """

        s  = "HTTP/1.1 %s %s\r\n" % (self.status, RESPONSES[self.status])
        if self.headers:
            s += self.headers.to_string() + "\r\n"
        s += "\r\n"
        if self.body:
            s += self.body.to_string()
            s += "\r\n"
        return s

class _ResponseBody(object):
    """The body of an HTTP response. 
    
    WARNING: This is a private class and could be removed in the future without
    previous notice. Do not use it this class from outside this module, use
    the Response class instead.

    Currently, the main purpose of this class is to handle conversion to
    unicode and various character encodings.
    """

    _template = r'''%s\s*=\s*["']?\s*%s\s*["']?'''

    _httpequiv_re = _template % ('http-equiv', 'Content-Type')
    _content_re   = _template % ('content', r'(?P<mime>[^;]+);\s*charset=(?P<charset>[\w-]+)')
    _encoding_re  = _template % ('encoding', r'(?P<charset>[\w-]+)')

    XMLDECL_RE  = re.compile(r'<\?xml\s.*?%s' % _encoding_re, re.I)

    METATAG_RE  = re.compile(r'<meta\s+%s\s+%s' % (_httpequiv_re, _content_re), re.I)
    METATAG_RE2 = re.compile(r'<meta\s+%s\s+%s' % (_content_re, _httpequiv_re), re.I)

    def __init__(self, content, declared_encoding=None):
        self._content = content
        self._unicode_content = None
        self.declared_encoding = declared_encoding
        self._expected_encoding = None
        self._actual_encoding = None

    def to_string(self, encoding=None):
        """Get the body as a string. If an encoding is specified, the
        body will be encoded using that encoding.
        """
        if encoding in (None, self.declared_encoding, self._actual_encoding):
            return self._content
        # should we cache this decode?
        return self.to_unicode().encode(encoding)

    def to_unicode(self):
        """Return body as unicode string"""
        if self._unicode_content:
            return self._unicode_content
        proposed = self.get_expected_encoding()
        dammit = UnicodeDammit(self._content, [proposed])
        self._actual_encoding = dammit.originalEncoding
        # FIXME sometimes dammit.unicode fails, even when it recognizes the encoding correctly
        self._unicode_content = dammit.unicode
        return self._unicode_content

    def get_content(self):
        """Return original content bytes"""
        return self._content

    def get_declared_encoding(self):
        """Get the value of the declared encoding passed to the
        constructor.
        """
        return self.declared_encoding

    def get_real_encoding(self):
        """Get the real encoding, by trying first the expected and then the
        actual encoding.
        """
        if self.get_expected_encoding():
            result = self.get_expected_encoding()
        else:
            self.to_unicode()
            result = self._actual_encoding
        return result

    def get_expected_encoding(self):
        """Get the expected encoding for the page. This is the declared
        encoding, or the meta tag encoding.
        """
        if self._expected_encoding:
            return self._expected_encoding
        proposed = self.declared_encoding
        if not proposed:
            chunk = self._content[:5000]
            match = self.XMLDECL_RE.search(chunk) or self.METATAG_RE.search(chunk) or self.METATAG_RE2.search(chunk)
            if match:
                proposed = match.group("charset")
        self._expected_encoding = proposed
        return proposed

    def __repr__(self):
        return "_ResponseBody(content=%s, declared_encoding=%s)" % (repr(self._content), repr(self.declared_encoding))

    def __str__(self):
        return self.to_string()

    def __unicode__(self):
        return self.to_unicode()

    def __len__(self):
        return len(self._content)

