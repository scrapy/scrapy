import re
import hashlib
import copy

from BeautifulSoup import UnicodeDammit

from scrapy.http.url import Url
from scrapy.http.headers import Headers

from twisted.web import http
reason_phrases = http.RESPONSES 

class Response(object) :
    """HTTP responses

    Arguments:
        * Domain - the spider domain for the page
        * url - the final url for the resource
        * original_url - the url requested
        * headers - HTTP headers
        * status - HTTP status code
        * body - Body object containing the content of the response
    """
    _ENCODING_RE = re.compile(r'charset=([\w-]+)', re.I)

    def __init__(self, domain, url, original_url=None, headers=None, status=200, body=None):
        self.domain = domain
        self.url = Url(url)
        self.original_url = Url(original_url) if original_url else url # different if redirected or escaped
        self.headers = Headers(headers or {})
        self.status = status
        # ResponseBody is not meant to be used directly (use .replace instead)
        assert(isinstance(body, basestring) or body is None)
        self.body = ResponseBody(body, self.headers_encoding())
        self.cached = False
        self.request = None # request which originated this response

    def version(self):
        """A hash of the contents of this response"""
        if not hasattr(self, '_version'):
            self._version = hashlib.sha1(self.body.to_string()).hexdigest()
        return self._version

    def headers_encoding(self):
        content_type = self.headers.get('Content-Type')
        if content_type:
            encoding = self._ENCODING_RE.search(content_type[0])
            if encoding:
                return encoding.group(1)

    def __repr__(self):
        return "Response(domain=%s, url=%s, original_url=%s, headers=%s, status=%s, body=%s)" % \
                (repr(self.domain), repr(self.url), repr(self.original_url), repr(self.headers), repr(self.status), repr(self.body))

    def __str__(self):
        version = '%s..%s' % (self.version()[:4], self.version()[-4:])
        return "<Response: %s %s (%s)>" % (self.status, self.url, version)

    def __len__(self):
        """Return raw HTTP response size"""
        return len(self.to_string())

    def info(self):
        return "<Response status=%s domain=%s url=%s headers=%s" % (self.status, self.domain, self.url, self.headers)

    def copy(self):
        """Create a new Response based on the current one"""
        return self.replace()

    def replace(self, **kw):
        """Create a new Response with the same attributes except for those given new values.

        Example: newresp = oldresp.replace(body="New body")
        """
        def sameheaders():
            return copy.deepcopy(self.headers)
        def samebody():
            return copy.deepcopy(self.body)
        newresp = Response(kw.get('domain', self.domain),
                           kw.get('url', self.url),
                           original_url=kw.get('original_url', self.original_url),
                           headers=kw.get('headers', sameheaders()),
                           status=kw.get('status', self.status))
        newresp.body = kw.get('body', samebody())
        return newresp

    def to_string(self):
        """
        Return raw HTTP response representation (as string). This is provided
        only for reference, since it's not the exact stream of bytes that was
        received (that's not exposed by Twisted).
        """

        s  = "HTTP/1.1 %s %s\r\n" % (self.status, reason_phrases[int(self.status)])
        s += self.headers.to_string() + "\r\n"
        s += "\r\n"
        if self.body:
            s += self.body.to_string()
            s += "\r\n"
        return s

class ResponseBody(object):
    """The body of an HTTP response

    This handles conversion to unicode and various character encodings.
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
        return "ResponseBody(content=%s, declared_encoding=%s)" % (repr(self._content), repr(self.declared_encoding))

    def __str__(self):
        return self.to_string()

    def __unicode__(self):
        return self.to_unicode()

    def __len__(self):
        return len(self._content)

