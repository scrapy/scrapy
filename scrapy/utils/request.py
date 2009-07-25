"""
This module provides some useful functions for working with
scrapy.http.Request objects
"""

import hashlib
from base64 import urlsafe_b64encode

from scrapy.utils.url import canonicalize_url

def request_fingerprint(request, include_headers=()):
    """
    Return the request fingerprint.
    
    The request fingerprint is a hash that uniquely identifies the resource the
    request points to. For example, take the following two urls:
    
    http://www.example.com/query?id=111&cat=222
    http://www.example.com/query?cat=222&id=111

    Even though those are two different URLs both point to the same resource
    and are equivalent (ie. they should return the same response).

    Another example are cookies used to store session ids. Suppose the
    following page is only accesible to authenticated users:
    
    http://www.example.com/members/offers.html

    Lot of sites use a cookie to store the session id, which adds a random
    component to the HTTP Request and thus should be ignored when calculating
    the fingerprint. 
    
    For this reason, request headers are ignored by default when calculating
    the fingeprint. If you want to include specific headers use the
    include_headers argument, which is a list of Request headers to include.

    """

    if include_headers:
        include_headers = [h.lower() for h in sorted(include_headers)]
        cachekey = 'fingerprint' + '_'.join(include_headers)
    else:
        cachekey = 'fingerprint'

    try:
        return request.cache[cachekey]
    except KeyError:
        fp = hashlib.sha1()
        fp.update(request.method)
        fp.update(canonicalize_url(request.url))
        fp.update(request.body or '')
        for hdr in include_headers:
            if hdr in request.headers:
                fp.update(hdr)
                for v in request.headers.getlist(hdr):
                    fp.update(v)
        fphash = fp.hexdigest()
        request.cache[cachekey] = fphash
        return fphash

def request_authenticate(request, username, password):
    """Autenticate the given request (in place) using the HTTP basic access
    authentication mechanism (RFC 2617) and the given username and password
    """
    b64userpass = urlsafe_b64encode("%s:%s" % (username, password))
    request.headers['Authorization'] = 'Basic ' + b64userpass

def request_info(request):
    """Return a short string with request info including method, url and
    fingeprint. Mainly used for debugging
    """
    fp = request_fingerprint(request)
    return "<Request: %s %s (%s..)>" % (request.method, request.url, fp[:8])

def request_httprepr(request):
    """Return the raw HTTP representation (as string) of the given request.
    This is provided only for reference since it's not the actual stream of
    bytes that will be send when performing the request (that's controlled
    by Twisted).
    """

    s  = "%s %s HTTP/1.1\r\n" % (request.method, request.url)
    s += "Host: %s\r\n" % request.url.hostname
    if request.headers:
        s += request.headers.to_string() + "\r\n"
    s += "\r\n"
    s += request.body
    return s
