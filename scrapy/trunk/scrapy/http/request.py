"""
This module implements the Request class which is used to represent HTTP
requests in Scrapy.

See documentation in docs/ref/request-response.rst
"""

import urllib
import copy

from twisted.internet import defer

from scrapy.http.url import Url
from scrapy.http.headers import Headers
from scrapy.utils.url import safe_url_string
from scrapy.utils.defer import chain_deferred

class Request(object):

    def __init__(self, url, callback=None, method='GET', headers=None, body=None, 
                 cookies=None, meta=None, encoding='utf-8', dont_filter=None):

        self.encoding = encoding  # this one has to be set first
        self.method = method.upper()
        self.set_url(url)
        self.set_body(body)

        if callable(callback):
            callback = defer.Deferred().addCallback(callback)
        self.deferred = callback or defer.Deferred()

        self.cookies = cookies or {}
        self.headers = Headers(headers or {}, encoding=encoding)
        self.dont_filter = dont_filter

        self.meta = {} if meta is None else dict(meta)
        self.cache = {}
        
    def set_url(self, url):
        assert isinstance(url, basestring), \
            'Request url argument must be str or unicode, got %s:' % type(url).__name__
        decoded_url = url if isinstance(url, unicode) else url.decode(self.encoding)
        self._url = Url(safe_url_string(decoded_url, self.encoding))
    url = property(lambda x: x._url, set_url)

    def set_body(self, body):
        # TODO: move dict constructor to another Request class
        if isinstance(body, dict):
            self._body = urllib.urlencode(body)
        elif body is None:
            self._body = None
        elif isinstance(body, str):
            self._body = body
        elif isinstance(body, unicode):
            self._body = body.encode(self.encoding)
        else:
            raise TypeError("Request body must either str, unicode or None. Got: '%s'" % type(body).__name__)
    body = property(lambda x: x._body, set_body)

    def __str__(self):
        if self.method == 'GET':
            return "<%s>" % self.url
        else:
            return "<%s %s>" % (self.method, self.url)

    def __repr__(self):
        d = {
            'method': self.method,
            'url': self.url,
            'headers': self.headers,
            'body': self.body,
            'cookies': self.cookies,
            'meta': self.meta,
            }
        return "%s(%s)" % (self.__class__.__name__, repr(d))

    def copy(self):
        """Return a copy a of this Request"""
        new = copy.copy(self)
        new.cache = {}
        for att in self.__dict__:
            if att not in ['cache', 'url', 'deferred']:
                value = getattr(self, att)
                setattr(new, att, copy.copy(value))
        new.deferred = defer.Deferred()
        return new

    def replace(self, url=None, method=None, headers=None, body=None, cookies=None, meta=None):
        """Create a new Request with the same attributes except for those
        given new values.
        """
        return self.__class__(url=url or self.url,
                              method=method or self.method,
                              headers=headers or copy.deepcopy(self.headers),
                              body=body or self.body,
                              cookies=cookies or self.cookies,
                              meta=meta or self.meta)

    def httprepr(self):
        """ Return raw HTTP request representation (as string). This is
        provided only for reference since it's not the actual stream of bytes
        that will be send when performing the request (that's controlled by
        Twisted).
        """

        s  = "%s %s HTTP/1.1\r\n" % (self.method, self.url)
        s += "Host: %s\r\n" % self.url.hostname
        if self.headers:
            s += self.headers.to_string() + "\r\n"
        s += "\r\n"
        if self.body:
            s += self.body
            s += "\r\n"
        return s
