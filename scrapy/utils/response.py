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

from scrapy.http import HtmlResponse, TextResponse
from scrapy.utils.decorator import deprecated
from scrapy.utils.python import unicode_to_str


@deprecated
def body_or_str(*a, **kw):
    from scrapy.utils.iterators import _body_or_str
    return _body_or_str(*a, **kw)


def get_base_url(response):
    """Return the base url of the given response, joined with the response url"""
    if response not in _baseurl_cache:
        text = response.body_as_unicode()[0:4096]
        _baseurl_cache[response] = html.get_base_url(text, response.url,
                                                     response.encoding)
    return _baseurl_cache[response]
_baseurl_cache = weakref.WeakKeyDictionary()


def get_meta_refresh(response):
    """Parse the http-equiv refrsh parameter from the given response"""
    if response not in _metaref_cache:
        text = response.body_as_unicode()[0:4096]
        text = _noscript_re.sub(u'', text)
        text = _script_re.sub(u'', text)
        _metaref_cache[response] = html.get_meta_refresh(text, response.url,
                                                         response.encoding)
    return _metaref_cache[response]
_noscript_re = re.compile(u'<noscript>.*?</noscript>', re.IGNORECASE | re.DOTALL)
_script_re = re.compile(u'<script.*?>.*?</script>', re.IGNORECASE | re.DOTALL)
_metaref_cache = weakref.WeakKeyDictionary()


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
    headers = response.headers.to_string()
    return b''.join((
        b'HTTP/1.1 ',
        str(response.status).encode('ascii'),
        b' ',
        unicode_to_str(RESPONSES.get(response.status, '')),
        b'\r\n',
        headers + b'\r\n' if headers else b'',
        b'\r\n',
        response.body
    ))


def open_in_browser(response, _openfunc=webbrowser.open):
    """Open the given response in a local web browser, populating the <base>
    tag for external links to work
    """
    # XXX: this implementation is a bit dirty and could be improved
    body = response.body
    if isinstance(response, HtmlResponse):
        if '<base' not in body:
            body = body.replace('<head>', '<head><base href="%s">' % response.url)
        ext = '.html'
    elif isinstance(response, TextResponse):
        ext = '.txt'
    else:
        raise TypeError("Unsupported response type: {0}"
                        .format(response.__class__.__name__))
    fd, fname = tempfile.mkstemp(ext)
    os.write(fd, body)
    os.close(fd)
    return _openfunc("file://%s" % fname)
