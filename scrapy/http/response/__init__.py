"""
This module implements the Response class which is used to represent HTTP
responses in Scrapy.

See documentation in docs/topics/request-response.rst
"""
from six.moves.urllib.parse import urljoin

from scrapy.http.request import Request
from scrapy.http.headers import Headers
from scrapy.link import Link
from scrapy.utils.trackref import object_ref
from scrapy.http.common import obsolete_setter
from scrapy.exceptions import NotSupported


class Response(object_ref):
    """A :class:`Response` object represents an HTTP response, which is usually
    downloaded (by the Downloader) and fed to the Spiders for processing.

    :param url: the URL of this response
    :type url: str

    :param status: the HTTP status of the response. Defaults to ``200``.
    :type status: int

    :param headers: the headers of this response. The dict values can be strings
       (for single valued headers) or lists (for multi-valued headers).
    :type headers: dict

    :param body: the response body. To access the decoded text as str (unicode
       in Python 2) you can use ``response.text`` from an encoding-aware
       :ref:`Response subclass <topics-request-response-ref-response-subclasses>`,
       such as :class:`TextResponse`.
    :type body: bytes

    :param flags: is a list containing the initial values for the
       :attr:`Response.flags` attribute. If given, the list will be shallow
       copied.
    :type flags: list

    :param request: the initial value of the :attr:`Response.request` attribute.
        This represents the :class:`Request` that generated this response.
    :type request: :class:`Request` object
    """

    def __init__(self, url, status=200, headers=None, body=b'', flags=None, request=None):
        #: A dictionary-like object which contains the response headers. Values
        #: can be accessed using :meth:`~scrapy.http.Headers.get` to return the
        #: first header value with the specified name or
        #: :meth:`~scrapy.http.Headers.getlist` to return all header values
        #: with the specified name. For example, this call will give you all
        #: cookies in the headers::
        #:
        #:     response.headers.getlist('Set-Cookie')
        self.headers = Headers(headers or {})

        #: An integer representing the HTTP status of the response. Example:
        #: ``200``, ``404``.
        self.status = int(status)

        self._set_body(body)
        self._set_url(url)

        #: The :class:`Request` object that generated this response. This attribute is
        #: assigned in the Scrapy engine, after the response and the request have passed
        #: through all :ref:`Downloader Middlewares <topics-downloader-middleware>`.
        #: In particular, this means that:
        #:
        #: - HTTP redirections will cause the original request (to the URL before
        #:   redirection) to be assigned to the redirected response (with the final
        #:   URL after redirection).
        #:
        #: - Response.request.url doesn't always equal Response.url
        #:
        #: - This attribute is only available in the spider code, and in the
        #:   :ref:`Spider Middlewares <topics-spider-middleware>`, but not in
        #:   Downloader Middlewares (although you have the Request available there by
        #:   other means) and handlers of the :signal:`response_downloaded` signal.
        self.request = request

        #: A list that contains flags for this response. Flags are labels used for
        #: tagging Responses. For example: `'cached'`, `'redirected`', etc. And
        #: they're shown on the string representation of the Response (`__str__`
        #: method) which is used by the engine for logging.
        self.flags = [] if flags is None else list(flags)

    @property
    def meta(self):
        """A shortcut to the :attr:`Request.meta <scrapy.Request.meta>`
        attribute of the :attr:`Response.request` object (i.e.
        ``self.request.meta``).

        Unlike the :attr:`Response.request` attribute, the
        :attr:`Response.meta` attribute is propagated along redirects and
        retries, so you will get the original :attr:`Request.meta
        <scrapy.Request.meta>` sent from your spider.

        .. seealso:: :attr:`Request.meta <scrapy.Request.meta>` attribute
        """
        try:
            return self.request.meta
        except AttributeError:
            raise AttributeError(
                "Response.meta not available, this response "
                "is not tied to any request"
            )

    def _get_url(self):
        return self._url

    def _set_url(self, url):
        if isinstance(url, str):
            self._url = url
        else:
            raise TypeError('%s url must be str, got %s:' % (type(self).__name__,
                type(url).__name__))

    #: A string containing the URL of the response.
    #:
    #: This attribute is read-only. To change the URL of a Response use
    #: :meth:`replace`.
    url = property(_get_url, obsolete_setter(_set_url, 'url'))

    def _get_body(self):
        return self._body

    def _set_body(self, body):
        if body is None:
            self._body = b''
        elif not isinstance(body, bytes):
            raise TypeError(
                "Response body must be bytes. "
                "If you want to pass unicode body use TextResponse "
                "or HtmlResponse.")
        else:
            self._body = body

    #: The body of this Response. Keep in mind that Response.body
    #: is always a bytes object. If you want the unicode version use
    #: :attr:`TextResponse.text` (only available in :class:`TextResponse`
    #: and subclasses).
    #:
    #: This attribute is read-only. To change the body of a Response use
    #: :meth:`replace`.
    body = property(_get_body, obsolete_setter(_set_body, 'body'))

    def __str__(self):
        return "<%d %s>" % (self.status, self.url)

    __repr__ = __str__

    def copy(self):
        """Returns a new Response which is a copy of this Response."""
        return self.replace()

    def replace(self, *args, **kwargs):
        """Returns a Response object with the same members, except for those members
       given new values by whichever keyword arguments are specified. The
       attribute :attr:`Response.meta` is copied by default."""
        for x in ['url', 'status', 'headers', 'body', 'request', 'flags']:
            kwargs.setdefault(x, getattr(self, x))
        cls = kwargs.pop('cls', self.__class__)
        return cls(*args, **kwargs)

    def urljoin(self, url):
        """Constructs an absolute url by combining the Response's :attr:`url`
        with a possible relative url.

        This is a wrapper over `urlparse.urljoin`_, it's merely an alias for
        making this call::

            urlparse.urljoin(response.url, url)
        """
        return urljoin(self.url, url)

    @property
    def text(self):
        """For subclasses of TextResponse, this will return the body
        as text (unicode object in Python 2 and str in Python 3)
        """
        raise AttributeError("Response content isn't text")

    def css(self, *a, **kw):
        """Shortcut method implemented only by responses whose content
        is text (subclasses of TextResponse).
        """
        raise NotSupported("Response content isn't text")

    def xpath(self, *a, **kw):
        """Shortcut method implemented only by responses whose content
        is text (subclasses of TextResponse).
        """
        raise NotSupported("Response content isn't text")

    def follow(self, url, callback=None, method='GET', headers=None, body=None,
               cookies=None, meta=None, encoding='utf-8', priority=0,
               dont_filter=False, errback=None):
        # type: (...) -> Request
        """
        Return a :class:`~.Request` instance to follow a link ``url``.
        It accepts the same arguments as ``Request.__init__`` method,
        but ``url`` can be a relative URL or a ``scrapy.link.Link`` object,
        not only an absolute URL.
        
        :class:`~.TextResponse` provides a :meth:`~.TextResponse.follow`
        method which supports selectors in addition to absolute/relative URLs
        and Link objects.
        """
        if isinstance(url, Link):
            url = url.url
        elif url is None:
            raise ValueError("url can't be None")
        url = self.urljoin(url)
        return Request(url, callback,
                       method=method,
                       headers=headers,
                       body=body,
                       cookies=cookies,
                       meta=meta,
                       encoding=encoding,
                       priority=priority,
                       dont_filter=dont_filter,
                       errback=errback)
