"""
This module implements the TextResponse class which adds encoding handling and
discovering (through HTTP headers) to base Response class.

See documentation in docs/topics/request-response.rst
"""

import six
from six.moves.urllib.parse import urljoin

import parsel
from w3lib.encoding import html_to_unicode, resolve_encoding, \
    html_body_declared_encoding, http_content_type_encoding
from w3lib.html import strip_html5_whitespace

from scrapy.http.request import Request
from scrapy.http.response import Response
from scrapy.utils.response import get_base_url
from scrapy.utils.python import memoizemethod_noargs, to_native_str


class TextResponse(Response):

    _DEFAULT_ENCODING = 'ascii'

    def __init__(self, *args, **kwargs):
        self._encoding = kwargs.pop('encoding', None)
        self._cached_benc = None
        self._cached_ubody = None
        self._cached_selector = None
        super(TextResponse, self).__init__(*args, **kwargs)

    def _set_url(self, url):
        if isinstance(url, six.text_type):
            if six.PY2 and self.encoding is None:
                raise TypeError("Cannot convert unicode url - %s "
                                "has no encoding" % type(self).__name__)
            self._url = to_native_str(url, self.encoding)
        else:
            super(TextResponse, self)._set_url(url)

    def _set_body(self, body):
        self._body = b''  # used by encoding detection
        if isinstance(body, six.text_type):
            if self._encoding is None:
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
        return self.text

    @property
    def text(self):
        """ Body as unicode """
        # access self.encoding before _cached_ubody to make sure
        # _body_inferred_encoding is called
        benc = self.encoding
        if self._cached_ubody is None:
            charset = 'charset=%s' % benc
            self._cached_ubody = html_to_unicode(charset, self.body)[1]
        return self._cached_ubody

    def urljoin(self, url):
        """Join this Response's url with a possible relative url to form an
        absolute interpretation of the latter."""
        return urljoin(get_base_url(self), url)

    @memoizemethod_noargs
    def _headers_encoding(self):
        content_type = self.headers.get(b'Content-Type', b'')
        return http_content_type_encoding(to_native_str(content_type))

    def _body_inferred_encoding(self):
        if self._cached_benc is None:
            content_type = to_native_str(self.headers.get(b'Content-Type', b''))
            benc, ubody = html_to_unicode(content_type, self.body,
                    auto_detect_fun=self._auto_detect_fun,
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

    def xpath(self, query, **kwargs):
        return self.selector.xpath(query, **kwargs)

    def css(self, query):
        return self.selector.css(query)

    def follow(self, url, callback=None, method='GET', headers=None, body=None,
               cookies=None, meta=None, encoding=None, priority=0,
               dont_filter=False, errback=None):
        # type: (...) -> Request
        """
        Return a :class:`~.Request` instance to follow a link ``url``.
        It accepts the same arguments as ``Request.__init__`` method,
        but ``url`` can be not only an absolute URL, but also
        
        * a relative URL;
        * a scrapy.link.Link object (e.g. a link extractor result);
        * an attribute Selector (not SelectorList) - e.g.
          ``response.css('a::attr(href)')[0]`` or
          ``response.xpath('//img/@src')[0]``.
        * a Selector for ``<a>`` or ``<link>`` element, e.g.
          ``response.css('a.my_link')[0]``.
          
        See :ref:`response-follow-example` for usage examples.
        """
        if isinstance(url, parsel.Selector):
            url = _url_from_selector(url)
        elif isinstance(url, parsel.SelectorList):
            raise ValueError("SelectorList is not supported")
        encoding = self.encoding if encoding is None else encoding
        return super(TextResponse, self).follow(url, callback,
            method=method,
            headers=headers,
            body=body,
            cookies=cookies,
            meta=meta,
            encoding=encoding,
            priority=priority,
            dont_filter=dont_filter,
            errback=errback
        )


def _url_from_selector(sel):
    # type: (parsel.Selector) -> str
    if isinstance(sel.root, six.string_types):
        # e.g. ::attr(href) result
        return strip_html5_whitespace(sel.root)
    if not hasattr(sel.root, 'tag'):
        raise ValueError("Unsupported selector: %s" % sel)
    if sel.root.tag not in ('a', 'link'):
        raise ValueError("Only <a> and <link> elements are supported; got <%s>" %
                         sel.root.tag)
    href = sel.root.get('href')
    if href is None:
        raise ValueError("<%s> element has no href attribute: %s" %
                         (sel.root.tag, sel))
    return strip_html5_whitespace(href)
