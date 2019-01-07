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
    """A :class:`Request` object represents an HTTP request, which is usually
    generated in the Spider and executed by the Downloader, and thus generating
    a :class:`~scrapy.http.Response`.

    :param url: the URL of this request as a string

    :param callback: the function that will be called with the response of this
       request (once its downloaded) as its first parameter. For more information
       see :ref:`topics-request-response-ref-request-callback-arguments` below.
       If a Request doesn't specify a callback, the spider's
       :meth:`~scrapy.Spider.parse` method will be used.
       Note that if exceptions are raised during processing, errback is called instead.

    :param method: the HTTP method of this request as a string. Defaults to
        ``'GET'``.

    :param meta: the initial values for the :attr:`Request.meta` attribute. If
       given, the dict passed in this parameter will be shallow copied.
    :type meta: dict

    :param body: the request body. If a ``unicode`` is passed, then it's encoded to
      ``str`` using the `encoding` passed (which defaults to ``utf-8``). If
      ``body`` is not given, an empty string is stored. Regardless of the
      type of this argument, the final value stored will be a ``str`` (never
      ``unicode`` or ``None``).
    :type body: str

    :param headers: the headers of this request. The dict values can be strings
       (for single valued headers) or lists (for multi-valued headers). If
       ``None`` is passed as value, the HTTP header will not be sent at all.
    :type headers: dict

    :param cookies: the request cookies. These can be sent in two forms.

        1. Using a dict::

            request_with_cookies = Request(url="http://www.example.com",
                                           cookies={'currency': 'USD', 'country': 'UY'})

        2. Using a list of dicts::

            request_with_cookies = Request(url="http://www.example.com",
                                           cookies=[{'name': 'currency',
                                                    'value': 'USD',
                                                    'domain': 'example.com',
                                                    'path': '/currency'}])

        The latter form allows for customizing the ``domain`` and ``path``
        attributes of the cookie. This is only useful if the cookies are saved
        for later requests.

        .. reqmeta:: dont_merge_cookies

        When some site returns cookies (in a response) those are stored in the
        cookies for that domain and will be sent again in future requests. That's
        the typical behaviour of any regular web browser. However, if, for some
        reason, you want to avoid merging with existing cookies you can instruct
        Scrapy to do so by setting the ``dont_merge_cookies`` key to True in the
        :attr:`Request.meta`.

        Example of request without merging cookies::

            request_with_cookies = Request(url="http://www.example.com",
                                           cookies={'currency': 'USD', 'country': 'UY'},
                                           meta={'dont_merge_cookies': True})

        For more info see :ref:`cookies-mw`.
    :type cookies: dict or list

    :param encoding: the encoding of this request as a string (defaults to
        ``'utf-8'``). This encoding will be used to percent-encode the URL and
        to convert the body to ``str`` (if given as ``unicode``).

    :param priority: the priority of this request (defaults to ``0``).
       The priority is used by the scheduler to define the order used to process
       requests.  Requests with a higher priority value will execute earlier.
       Negative values are allowed in order to indicate relatively low-priority.
    :type priority: int

    :param dont_filter: indicates that this request should not be filtered by
       the scheduler. This is used when you want to perform an identical
       request multiple times, to ignore the duplicates filter. Use it with
       care, or you will get into crawling loops. Default to ``False``.
    :type dont_filter: bool

    :param errback: a function that will be called if any exception was
       raised while processing the request. This includes pages that failed
       with 404 HTTP errors and such. It receives a `Twisted Failure`_ instance
       as first parameter.
       For more information,
       see :ref:`topics-request-response-ref-errbacks` below.

    :param flags:  Flags sent to the request, can be used for logging or similar purposes.
    :type flags: list
    """

    def __init__(self, url, callback=None, method='GET', headers=None, body=None,
                 cookies=None, meta=None, encoding='utf-8', priority=0,
                 dont_filter=False, errback=None, flags=None):

        self._encoding = encoding  # this one has to be set first

        #: A string representing the HTTP method in the request. This is
        #: guaranteed to be uppercase. Example: ``"GET"``, ``"POST"``,
        #: ``"PUT"``, etc
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

        #: A dictionary-like object which contains the request headers.
        self.headers = Headers(headers or {}, encoding=encoding)

        #: If true, the request will be schedule even if it is a duplicate of a
        #: request already scheduled during the current crawl.
        self.dont_filter = dont_filter

        self._meta = dict(meta) if meta else None
        self.flags = [] if flags is None else list(flags)

    @property
    def meta(self):
        """A dict that contains arbitrary metadata for this request. This dict is
        empty for new Requests, and is usually  populated by different Scrapy
        components (extensions, middlewares, etc). So the data contained in this
        dict depends on the extensions you have enabled.

        See :ref:`topics-request-meta` for a list of special meta keys
        recognized by Scrapy.

        This dict is `shallow copied`_ when the request is cloned using the
        ``copy()`` or ``replace()`` methods, and can also be accessed, in your
        spider, from the ``response.meta`` attribute.

        .. _shallow copied: https://docs.python.org/2/library/copy.html
        """
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

    #: A string containing the URL of this request. Keep in mind that this
    #: attribute contains the escaped URL, so it can differ from the URL passed
    #: in the constructor.
    #:
    #: This attribute is read-only. To change the URL of a Request use
    #: :meth:`replace`.
    url = property(_get_url, obsolete_setter(_set_url, 'url'))

    def _get_body(self):
        return self._body

    def _set_body(self, body):
        if body is None:
            self._body = b''
        else:
            self._body = to_bytes(body, self.encoding)

    #: A str that contains the request body.
    #:
    #: This attribute is read-only. To change the body of a Request use
    #: :meth:`replace`.
    body = property(_get_body, obsolete_setter(_set_body, 'body'))

    @property
    def encoding(self):
        return self._encoding

    def __str__(self):
        return "<%s %s>" % (self.method, self.url)

    __repr__ = __str__

    def copy(self):
        """Return a new Request which is a copy of this Request. See also:
       :ref:`topics-request-response-ref-request-callback-arguments`."""
        return self.replace()

    def replace(self, *args, **kwargs):
        """Return a Request object with the same members, except for those members
       given new values by whichever keyword arguments are specified. The
       attribute :attr:`Request.meta` is copied by default (unless a new value
       is given in the ``meta`` argument). See also
       :ref:`topics-request-response-ref-request-callback-arguments`.
        """
        for x in ['url', 'method', 'headers', 'body', 'cookies', 'meta', 'flags',
                  'encoding', 'priority', 'dont_filter', 'callback', 'errback']:
            kwargs.setdefault(x, getattr(self, x))
        cls = kwargs.pop('cls', self.__class__)
        return cls(*args, **kwargs)
