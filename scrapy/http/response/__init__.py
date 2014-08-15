"""
This module implements the Response class which is used to represent HTTP
responses in Scrapy.

See documentation in docs/topics/request-response.rst
"""
from scrapy.http.headers import Headers
from scrapy.utils.trackref import object_ref
from scrapy.http.common import obsolete_setter


class Response(object_ref):

    def __init__(self, url, status=200, headers=None, body=b'', flags=None, request=None):
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
            raise AttributeError("Response.meta not available, this response "
                                 "is not tied to any request")

    def _get_url(self):
        return self._url

    def _set_url(self, url):
        if isinstance(url, bytes):
            self._url = url
        else:
            raise TypeError('{0} url must be bytes, got {1}:'
                            .format(type(self).__name__, type(url).__name__))

    url = property(_get_url, obsolete_setter(_set_url, 'url'))

    def _get_body(self):
        return self._body

    def _set_body(self, body):
        if body is None:
            self._body = b''
        elif isinstance(body, bytes):
            self._body = body
        else:
            raise TypeError("Response body must be bytes. Got: '{0}'"
                            .format(type(body).__name__))

    body = property(_get_body, obsolete_setter(_set_body, 'body'))

    def __str__(self):
        return "<%d %s>" % (self.status, self.url)

    __repr__ = __str__

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
