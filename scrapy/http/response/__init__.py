"""
This module implements the Response class which is used to represent HTTP
responses in Scrapy.

See documentation in docs/topics/request-response.rst
"""

import copy

from scrapy.http.headers import Headers
from scrapy.utils.trackref import object_ref
from scrapy.http.common import deprecated_setter

class Response(object_ref):

    __slots__ = ['_url', 'headers', 'status', '_body', 'request', \
        'flags', '__weakref__']

    def __init__(self, url, status=200, headers=None, body='', flags=None, request=None):
        self.headers = Headers(headers or {})
        self.status = int(status)
        self._set_body(body)
        self._set_url(url)
        self.request = request
        self.flags = [] if flags is None else list(flags)

    @property
    def meta(self):
        try:
            return self.request.meta
        except AttributeError:
            raise AttributeError("Response.meta not available, this response " \
                "is not tied to any request")

    def _get_url(self):
        return self._url

    def _set_url(self, url):
        if isinstance(url, str):
            self._url = url
        else:
            raise TypeError('%s url must be str, got %s:' % (type(self).__name__, \
                type(url).__name__))

    url = property(_get_url, deprecated_setter(_set_url, 'url'))

    def _get_body(self):
        return self._body

    def _set_body(self, body):
        if isinstance(body, str):
            self._body = body
        elif isinstance(body, unicode):
            raise TypeError("Cannot assign a unicode body to a raw Response. " \
                "Use TextResponse, HtmlResponse, etc")
        elif body is None:
            self._body = ''
        else:
            raise TypeError("Response body must either str or unicode. Got: '%s'" \
                % type(body).__name__)

    body = property(_get_body, deprecated_setter(_set_body, 'body'))

    def __repr__(self):
        attrs = ['url', 'status', 'body', 'headers', 'request', 'flags']
        args = ", ".join(["%s=%r" % (a, getattr(self, a)) for a in attrs])
        return "%s(%s)" % (self.__class__.__name__, args)

    def __str__(self):
        return "<%d %s>" % (self.status, self.url)

    def copy(self):
        """Return a copy of this Response"""
        return self.replace()

    def replace(self, *args, **kwargs):
        """Create a new Response with the same attributes except for those
        given new values.
        """
        for x in ['url', 'status', 'headers', 'body', 'request', 'flags']:
            kwargs.setdefault(x, getattr(self, x))
        cls = kwargs.pop('cls', self.__class__)
        return cls(*args, **kwargs)
