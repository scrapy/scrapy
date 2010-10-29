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

from scrapy.utils.markup import remove_entities, remove_comments
from scrapy.utils.url import safe_url_string, urljoin_rfc
from scrapy.xlib.BeautifulSoup import BeautifulSoup
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

BASEURL_RE = re.compile(ur'<base\s+href\s*=\s*[\"\']\s*([^\"\'\s]+)\s*[\"\']', re.I)
_baseurl_cache = weakref.WeakKeyDictionary()
def get_base_url(response):
    """ Return the base url of the given response used to resolve relative links. """
    if response not in _baseurl_cache:
        match = BASEURL_RE.search(response.body_as_unicode()[0:4096])
        _baseurl_cache[response] = urljoin_rfc(response.url, match.group(1)) if match else response.url
    return _baseurl_cache[response]

META_REFRESH_RE = re.compile(ur'<meta[^>]*http-equiv[^>]*refresh[^>]*content\s*=\s*(?P<quote>["\'])(?P<int>(\d*\.)?\d+)\s*;\s*url=(?P<url>.*?)(?P=quote)', \
    re.DOTALL | re.IGNORECASE)
_metaref_cache = weakref.WeakKeyDictionary()
def get_meta_refresh(response):
    """Parse the http-equiv parameter of the HTML meta element from the given
    response and return a tuple (interval, url) where interval is an integer
    containing the delay in seconds (or zero if not present) and url is a
    string with the absolute url to redirect.

    If no meta redirect is found, (None, None) is returned.
    """
    if response not in _metaref_cache:
        body_chunk = remove_comments(remove_entities(response.body_as_unicode()[0:4096]))
        match = META_REFRESH_RE.search(body_chunk)
        if match:
            interval = float(match.group('int'))
            url = safe_url_string(match.group('url').strip(' "\''))
            url = urljoin_rfc(response.url, url)
            _metaref_cache[response] = (interval, url)
        else:
            _metaref_cache[response] = (None, None)
        #_metaref_cache[response] = match.groups() if match else (None, None)
    return _metaref_cache[response]

_beautifulsoup_cache = weakref.WeakKeyDictionary()
def get_cached_beautifulsoup(response):
    """Return BeautifulSoup object of the given response, with caching
    support"""
    if response not in _beautifulsoup_cache:
        _beautifulsoup_cache[response] = BeautifulSoup(response.body)
    return _beautifulsoup_cache[response]

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
