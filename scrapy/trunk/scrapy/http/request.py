import urllib
from copy import copy

from twisted.internet import defer

from scrapy.http.url import Url
from scrapy.http.headers import Headers
from scrapy.utils.url import safe_url_string
from scrapy.utils.defer import chain_deferred

class Request(object):

    def __init__(self, url, callback=None, context=None, method=None,
        body=None, headers=None, cookies=None, referer=None,
        url_encoding='utf-8', link_text='', dont_filter=None, domain=None):

        self.encoding = url_encoding  # this one has to be set first
        self.set_url(url)

        # method
        if method is None and body is not None:
            method = 'POST' # backwards compatibility
        self.method = method.upper() if method else 'GET'
        assert isinstance(self.method, basestring), \
             'Request method argument must be str or unicode, got %s: %s' % (type(method), method)

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
        # persistent context across requests
        self.context = context or {}
        # dont_filter be filtered by scheduler
        self.dont_filter = dont_filter
        # shortcut for setting referer
        if referer is not None:
            self.headers['referer'] = referer
        self.depth = 0
        self.link_text = link_text
        #allows to directly specify the spider for the request
        self.domain = domain

        # bucket to store cached data such as fingerprint and others
        self._cache = {}
        
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
        if self.method != 'GET':
            return "<(%s) %s>" % (self.method, self.url)
        return "<%s>" % self.url

    def __len__(self):
        """Return raw HTTP request size"""
        return len(self.to_string())

    def __repr__(self):
        d = {
            'method': self.method,
            'url': self.url,
            'headers': self.headers,
            'cookies': self.cookies,
            'body': self.body,
            'context': self.context
            }
        return "%s(%s)" % (self.__class__.__name__, repr(d))

    def copy(self):
        """Clone request except `context` attribute"""
        new = copy(self)
        new._cache = {}
        for att in self.__dict__:
            if att not in ['_cache', 'context', 'url', 'deferred']:
                value = getattr(self, att)
                setattr(new, att, copy(value))
        new.deferred = defer.Deferred()
        new.context = self.context # requests shares same context dictionary
        return new

    def to_string(self):
        """ Return raw HTTP request representation (as string). This is
        provided only for reference since it's not the actual stream of bytes
        that will be send when performing the request (that's controlled by
        Twisted).
        """

        s  = "%s %s HTTP/1.1\r\n" % (self.method, self.url)
        s += "Host: %s\r\n" % self.url.hostname
        s += self.headers.to_string() + "\r\n"
        s += "\r\n"
        if self.body:
            s += self.body
            s += "\r\n"
        return s
