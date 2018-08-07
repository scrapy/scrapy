"""
This module provides some useful functions for working with
scrapy.http.Response objects
"""
import os
import weakref
import webbrowser
import tempfile

from twisted.web import http
from scrapy.utils.python import to_bytes, to_native_str
from w3lib import html

from scrapy.utils.decorators import deprecated


@deprecated
def body_or_str(*a, **kw):
    from scrapy.utils.iterators import _body_or_str
    return _body_or_str(*a, **kw)


_baseurl_cache = weakref.WeakKeyDictionary()
def get_base_url(response):
    """Return the base url of the given response, joined with the response url"""
    if response not in _baseurl_cache:
        text = response.text[0:4096]
        _baseurl_cache[response] = html.get_base_url(text, response.url,
            response.encoding)
    return _baseurl_cache[response]


_metaref_cache = weakref.WeakKeyDictionary()
def get_meta_refresh(response):
    """Parse the http-equiv refrsh parameter from the given response"""
    if response not in _metaref_cache:
        text = response.text[0:4096]
        _metaref_cache[response] = html.get_meta_refresh(text, response.url,
            response.encoding, ignore_tags=('script', 'noscript'))
    return _metaref_cache[response]


def response_status_message(status):
    """Return status code plus status text descriptive message
    """
    message = http.RESPONSES.get(int(status), "Unknown Status")
    return '%s %s' % (status, to_native_str(message))


def response_httprepr(response):
    """Return raw HTTP representation (as bytes) of the given response. This
    is provided only for reference, since it's not the exact stream of bytes
    that was received (that's not exposed by Twisted).
    """
    s = b"HTTP/1.1 " + to_bytes(str(response.status)) + b" " + \
        to_bytes(http.RESPONSES.get(response.status, b'')) + b"\r\n"
    if response.headers:
        s += response.headers.to_string() + b"\r\n"
    s += b"\r\n"
    s += response.body
    return s


def open_in_browser(response, _openfunc=webbrowser.open):
    """Open the given response in a local web browser, populating the <base>
    tag for external links to work
    """
    from scrapy.http import HtmlResponse, TextResponse
    # XXX: this implementation is a bit dirty and could be improved
    body = response.body
    if isinstance(response, HtmlResponse):
        if b'<base' not in body:
            repl = '<head><base href="%s">' % response.url
            body = body.replace(b'<head>', to_bytes(repl))
        ext = '.html'
    elif isinstance(response, TextResponse):
        ext = '.txt'
    else:
        raise TypeError("Unsupported response type: %s" %
                        response.__class__.__name__)
    fd, fname = tempfile.mkstemp(ext)
    os.write(fd, body)
    os.close(fd)
    return _openfunc("file://%s" % fname)
