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

from scrapy.http import Response, HtmlResponse

def body_or_str(obj, unicode=True):
    assert isinstance(obj, (Response, basestring)), \
        "obj must be Response or basestring, not %s" % type(obj).__name__
    if isinstance(obj, Response):
        return obj.body_as_unicode() if unicode else obj.body
    elif isinstance(obj, str):
        return obj.decode('utf-8') if unicode else obj
    else:
        return obj if unicode else obj.encode('utf-8')

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
    return '%s %s' % (status, http.responses.get(int(status)))

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
    # XXX: this implementation is a bit dirty and could be improved
    if not isinstance(response, HtmlResponse):
        raise TypeError("Unsupported response type: %s" % \
            response.__class__.__name__)
    body = response.body
    if '<base' not in body:
        body = body.replace('<head>', '<head><base href="%s">' % response.url)
    fd, fname = tempfile.mkstemp('.html')
    os.write(fd, body)
    os.close(fd)
    return _openfunc("file://%s" % fname)
