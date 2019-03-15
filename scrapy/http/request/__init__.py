"""
This module implements the Request class which is used to represent HTTP
requests in Scrapy.

See documentation in docs/topics/request-response.rst
"""
import six
from w3lib.url import safe_url_string

from scrapy.http.headers import Headers
from scrapy.utils.python import to_bytes
from scrapy.utils.trackref import object_ref
from scrapy.utils.url import escape_ajax
from scrapy.http.common import obsolete_setter


class Request(object_ref):

    def __init__(self, url, callback=None, method='GET', headers=None, body=None,
                 cookies=None, meta=None, encoding='utf-8', priority=0,
                 dont_filter=False, errback=None, flags=None):

        self._encoding = encoding  # this one has to be set first
        self.method = str(method).upper()
        self._set_url(url)
        self._set_body(body)
        assert isinstance(priority, int), "Request priority not an integer: %r" % priority
        self.priority = priority

        if callback is not None and not callable(callback):
            raise TypeError('callback must be a callable, got %s' % type(callback).__name__)
        if errback is not None and not callable(errback):
            raise TypeError('errback must be a callable, got %s' % type(errback).__name__)
        assert callback or not errback, "Cannot use errback without a callback"
        self.callback = callback
        self.errback = errback

        self.cookies = cookies or {}
        self.headers = Headers(headers or {}, encoding=encoding)
        self.dont_filter = dont_filter

        self._meta = dict(meta) if meta else None
        self.flags = [] if flags is None else list(flags)

    @property
    def meta(self):
        if self._meta is None:
            self._meta = {}
        return self._meta

    def _get_url(self):
        return self._url

    def _set_url(self, url):
        if not isinstance(url, six.string_types):
            raise TypeError('Request url must be str or unicode, got %s:' % type(url).__name__)

        s = safe_url_string(url, self.encoding)
        self._url = escape_ajax(s)

        if ':' not in self._url:
            raise ValueError('Missing scheme in request url: %s' % self._url)

    url = property(_get_url, obsolete_setter(_set_url, 'url'))

    def _get_body(self):
        return self._body

    def _set_body(self, body):
        if body is None:
            self._body = b''
        else:
            self._body = to_bytes(body, self.encoding)

    body = property(_get_body, obsolete_setter(_set_body, 'body'))

    @property
    def encoding(self):
        return self._encoding

    def __str__(self):
        return "<%s %s>" % (self.method, self.url)

    __repr__ = __str__

    def copy(self):
        """Return a copy of this Request"""
        return self.replace()

    def replace(self, *args, **kwargs):
        """Create a new Request with the same attributes except for those
        given new values.
        """
        for x in ['url', 'method', 'headers', 'body', 'cookies', 'meta', 'flags',
                  'encoding', 'priority', 'dont_filter', 'callback', 'errback']:
            kwargs.setdefault(x, getattr(self, x))
        cls = kwargs.pop('cls', self.__class__)
        return cls(*args, **kwargs)

    def mark_for_retry(self, reason=None, **kwargs):
        """Return a new instance that is marked as to be retried.
        New request is same as this request except attributes provided as keyword arguments.

        :param reason: Reason for retrying. Optional, defaults to None.
        :type reason: str"""
        new_req = self.replace(**kwargs)
        new_req.meta['_retry_requested'] = True
        new_req.meta['_retry_request_reason'] = reason
        return new_req

    def unmark_as_retry(self):
        """Unmark this request as to be retried"""
        self.meta.pop('_retry_requested', None)
        self.meta.pop('_retry_request_reason', None)

    def is_marked_for_retry(self):
        """Return whether this request is marked as to be retried."""
        return self.meta.get('_retry_requested') is True

    def get_retry_reason(self):
        """Return reason for retry if this request is marked for retry"""
        return self.is_marked_for_retry() and self.meta.get('_retry_request_reason') or None

    def is_retrying_enabled(self):
        """Return whether retrying is enabled on this request"""
        return not bool(self.meta.get('dont_retry', False))
