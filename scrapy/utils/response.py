"""
This module provides some useful functions for working with
scrapy.http.Response objects
"""

import os
import re
import weakref
import webbrowser
import tempfile

from twisted.web import http
from twisted.web.http import RESPONSES
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
        text = response.body_as_unicode()[0:4096]
        _baseurl_cache[response] = html.get_base_url(text, response.url, \
            response.encoding)
    return _baseurl_cache[response]

_noscript_re = re.compile(u'<noscript>.*?</noscript>', re.IGNORECASE | re.DOTALL)
_script_re = re.compile(u'<script.*?>.*?</script>', re.IGNORECASE | re.DOTALL)
_metaref_cache = weakref.WeakKeyDictionary()
def get_meta_refresh(response):
    """Parse the http-equiv refrsh parameter from the given response"""
    if response not in _metaref_cache:
        text = response.body_as_unicode()[0:4096]
        text = _noscript_re.sub(u'', text)
        text = _script_re.sub(u'', text)
        _metaref_cache[response] = html.get_meta_refresh(text, response.url, \
            response.encoding)
    return _metaref_cache[response]

def response_status_message(status):
    """Return status code plus status text descriptive message

    >>> response_status_message(200)
    '200 OK'

    >>> response_status_message(404)
    '404 Not Found'
    """
    # Implicit decode/encode is on purpose to force native strings
    # This is properly fixed in Scrapy >=1.1 at revision faf9265
    reason = http.RESPONSES.get(int(status)).decode('utf8', errors='replace')
    return '{} {}'.format(status, reason)

def response_httprepr(response):
    """Return raw HTTP representation (as string) of the given response. This
    is provided only for reference, since it's not the exact stream of bytes
    that was received (that's not exposed by Twisted).
    """

    s = "HTTP/1.1 %d %s\r\n" % (response.status, RESPONSES.get(response.status, ''))
    if response.headers:
        s += response.headers.to_string() + "\r\n"
    s += "\r\n"
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
        if '<base' not in body:
            body = body.replace('<head>', '<head><base href="%s">' % response.url)
        ext = '.html'
    elif isinstance(response, TextResponse):
        ext = '.txt'
    else:
        raise TypeError("Unsupported response type: %s" % \
            response.__class__.__name__)
    fd, fname = tempfile.mkstemp(ext)
    os.write(fd, body)
    os.close(fd)
    return _openfunc("file://%s" % fname)
