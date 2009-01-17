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

    def __init__(self, url, callback=None, method='GET',
        body=None, headers=None, cookies=None,
        url_encoding='utf-8', dont_filter=None, domain=None):

        self.encoding = url_encoding  # this one has to be set first
        self.set_url(url)

        self.method = method.upper()

        # body
        if isinstance(body, dict):
            body = urllib.urlencode(body)
        self.body = body

        # callback / deferred
        if callable(callback):
            callback = defer.Deferred().addCallback(callback)
        self.deferred = callback or defer.Deferred()

        # request cookies
        self.cookies = cookies or {}
        # request headers
        self.headers = Headers(headers or {}, encoding=url_encoding)
        # dont_filter be filtered by scheduler
        self.dont_filter = dont_filter
        #allows to directly specify the spider for the request
        self.domain = domain

        self.meta = {}
        self.cache = {}
        
    def append_callback(self, callback, *args, **kwargs):
        if isinstance(callback, defer.Deferred):
            return chain_deferred(self.deferred, callback)
        return self.deferred.addCallback(callback, *args, **kwargs)

    def set_url(self, url):
        assert isinstance(url, basestring), \
            'Request url argument must be str or unicode, got %s:' % type(url).__name__
        decoded_url = url if isinstance(url, unicode) else url.decode(self.encoding)
        self._url = Url(safe_url_string(decoded_url, self.encoding))
    url = property(lambda x: x._url, set_url)

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
            'cookies': self.cookies,
            'body': self.body,
            }
        return "%s(%s)" % (self.__class__.__name__, repr(d))

    def copy(self):
        """Return a new request cloned from this one"""
        new = copy.copy(self)
        new.cache = {}
        for att in self.__dict__:
            if att not in ['cache', 'url', 'deferred']:
                value = getattr(self, att)
                setattr(new, att, copy.copy(value))
        new.deferred = defer.Deferred()
        return new

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
