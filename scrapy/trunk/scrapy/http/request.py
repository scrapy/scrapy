import urllib
import hashlib
from copy import copy
from base64 import urlsafe_b64encode

from twisted.internet import defer

from scrapy.http.url import Url
from scrapy.http.headers import Headers
from scrapy.utils.url import safe_url_string
from scrapy.utils.c14n import canonicalize
from scrapy.utils.defer import chain_deferred

class Request(object):
    def __init__(self, url, callback=None, context=None, method=None, body=None, headers=None, cookies=None,
            referer=None, url_encoding='utf-8', link_text='', http_user='', http_pass='', dont_filter=None, 
            fingerprint_params=None, domain=None):

        self.encoding = url_encoding  # this one has to be set first
        self.set_url(url)

        # method
        if method is None and body is not None:
            method = 'POST' # backwards compatibility
        self.method = method.upper() if method else 'GET'
        assert isinstance(self.method, basestring), 'Request method argument must be str or unicode, got %s: %s' % (type(method), method)

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
        # fingerprint parameters
        self.fingerprint_params = fingerprint_params or {}
        self._fingerprint = None
        # shortcut for setting referer
        if referer is not None:
            self.headers['referer'] = referer
        # http auth
        if http_user or http_pass:
            self.httpauth(http_user, http_pass)
        self.depth = 0
        self.link_text = link_text
        #allows to directly specify the spider for the request
        self.domain = domain
        
    def append_callback(self, callback, *args, **kwargs):
        if isinstance(callback, defer.Deferred):
            return chain_deferred(self.deferred, callback)
        return self.deferred.addCallback(callback, *args, **kwargs)

    def prepend_callback(self, func, *args, **kwargs):
        if callable(func):
            func = defer.Deferred().addCallback(func, *args, **kwargs)
        assert isinstance(func, defer.Deferred), 'prepend_callback expects a callable or defer.Deferred instance, got %s' % type(func)
        self.deferred = chain_deferred(func, self.deferred)
        return self.deferred

    def set_url(self, url):
        assert isinstance(url, basestring), 'Request url argument must be str or unicode, got %s:' % type(url).__name__
        decoded_url = url if isinstance(url, unicode) else url.decode(self.encoding)
        self._url = Url(safe_url_string(decoded_url, self.encoding))
        self._fingerprint = None # invalidate cached fingerprint
    url = property(lambda x: x._url, set_url)

    def httpauth(self, http_user, http_pass):
        if not http_user:
            http_user = ''
        if not http_pass:
            http_pass = ''
        self.headers['Authorization'] = 'Basic ' + urlsafe_b64encode("%s:%s" % (http_user, http_pass))

    def __str__(self):
        if self.method != 'GET':
            return "<(%s) %s>" % (self.method, self.url)
        return "<%s>" % self.url

    def __len__(self):
        """Return raw HTTP request size"""
        return len(self.to_string())

    def traceinfo(self):
        fp = self.fingerprint()
        version = '%s..%s' % (fp[:4], fp[-4:])
        return "<Request: %s %s (%s)>" % (self.method, self.url, version)

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
        for att in self.__dict__:
            if att not in ['context', 'url', 'deferred', '_fingerprint']:
                value = getattr(self, att)
                setattr(new, att, copy(value))
        new.deferred = defer.Deferred()
        new.context = self.context # requests shares same context dictionary
        new._fingerprint = None # reset fingerprint
        return new

    def fingerprint(self):
        """Returns unique resource fingerprint with caching support"""
        if not self._fingerprint or self.fingerprint_params:
            self.update_fingerprint()
        return self._fingerprint

    def update_fingerprint(self):
        """Update request fingerprint, based on its current data. A request
        fingerprint is a hash which uniquely identifies the HTTP resource"""

        headers = {}
        if self.fingerprint_params:
            if 'tamperfunc' in self.fingerprint_params:
                tamperfunc = self.fingerprint_params['tamperfunc']
                assert callable(tamperfunc)
                req = tamperfunc(self.copy())
                assert isinstance(req, Request)
                try:
                    del req.fingerprint_params['tamperfunc']
                except KeyError:
                    pass
                return req.fingerprint()

            if self.headers:
                if 'include_headers' in self.fingerprint_params:
                    keys = [k.lower() for k in self.fingerprint_params['include_headers']]
                    headers = dict([(k, v) for k, v in self.headers.items() if k.lower() in keys])
                elif 'exclude_headers' in self.fingerprint_params:
                    keys = [k.lower() for k in self.fingerprint_params['exclude_headers']]
                    headers = dict([(k, v) for k, v in self.headers.items() if k.lower() not in keys])

        # fingerprint generation
        fp = hashlib.sha1()
        fp.update(canonicalize(self.url))
        fp.update(self.method)

        if self.body and self.method in ['POST', 'PUT']:
            fp.update(self.body)

        if headers:
            for k, v in sorted([(k.lower(), v) for k, v in headers.items()]):
                fp.update(k)
                fp.update(v)

        self._fingerprint = fp.hexdigest()

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
