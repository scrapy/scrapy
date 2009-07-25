"""
This module provides some useful functions for working with
scrapy.http.Response objects
"""

import re

from twisted.web import http
from twisted.web.http import RESPONSES

from scrapy.http.response import Response

def body_or_str(obj, unicode=True):
    assert isinstance(obj, (Response, basestring)), "obj must be Response or basestring, not %s" % type(obj).__name__
    if isinstance(obj, Response):
        return obj.body_as_unicode() if unicode else obj.body
    elif isinstance(obj, str):
        return obj.decode('utf-8') if unicode else obj
    else:
        return obj if unicode else obj.encode('utf-8')

BASEURL_RE = re.compile(r'<base\s+href\s*=\s*[\"\']\s*([^\"\'\s]+)\s*[\"\']', re.I)
def get_base_url(response):
    """ Return the base url of the given response used to resolve relative links. """
    # re is used instead of xpath for eficiency reasons. In a quick
    # benchmark using timeit we got (for 50 repetitions) 0.0017 seconds
    # using re and 0.7452 using xpath
    if 'base_url' not in response.cache:
        match = BASEURL_RE.search(response.body[0:4096])
        response.cache['base_url'] = match.group(1) if match else response.url
    return response.cache['base_url']

META_REFRESH_RE = re.compile(r'<meta[^>]*http-equiv[^>]*refresh[^>].*?(\d+);\s*url=([^"\']+)', re.IGNORECASE)
def get_meta_refresh(response):
    """ Return a tuple of two strings containing the interval and url included
    in the http-equiv parameter of the HTML meta element. If no url is included
    (None, None) is returned [instead of (interval, None)]
    """
    if 'meta_refresh_url' not in response.cache:
        match = META_REFRESH_RE.search(response.body[0:4096])
        response.cache['meta_refresh_url'] = match.groups() if match else (None, None)
    return response.cache['meta_refresh_url']

def response_status_message(status):
    """Return status code plus status text descriptive message

    >>> response_status_message(200)
    200 OK

    >>> response_status_message(404)
    404 Not Found
    """
    return '%s %s' % (status, http.responses.get(int(status)))

def response_httprepr(response):
    """Return raw HTTP representation (as string) of the given response. This
    is provided only for reference, since it's not the exact stream of bytes
    that was received (that's not exposed by Twisted).
    """

    s  = "HTTP/1.1 %d %s\r\n" % (response.status, RESPONSES[response.status])
    if response.headers:
        s += response.headers.to_string() + "\r\n"
    s += "\r\n"
    s += response.body
    return s
