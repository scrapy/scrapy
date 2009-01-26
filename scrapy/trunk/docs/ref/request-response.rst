.. _ref-request-response:

============================
Request and Response objects
============================

.. module:: scrapy.http
   :synopsis: Classes dealing with HTTP requests and responses.

Quick overview
==============

Scrapy uses :class:`Request` and :class:`Response` objects for crawling web
sites. 

Typically, :class:`Request` objects are generated in the spiders and pass
across the system until they reach the Downloader, which executes the request
and returns a :class:`Response` object which goes back to the spider that
generated the request.

Both Request and Response classes contains subclasses which adds additional
functionality not required in the base classes. See
:ref:`ref-request-subclasses` and :ref:`ref-response-subclasses` below.

Request objects
===============

.. class:: Request(url, callback=None, method='GET', body=None, headers=None, cookies=None, meta=None, encoding='utf-8', dont_filter=None)

    A :class:`Request` object represents an HTTP request, which is usually
    generated in the Spider and executed by the Downloader, and thus generating
    a :class:`Response`.
    
    ``url`` is a string containing the URL for this request

    ``callback`` is a function that will be called with the response of this
    request (once its downloaded) as its first parameter

    ``method`` is a string with the HTTP method of this request

    ``meta`` is a dict containing the initial values for the
    :attr:`Request.meta` attribute. If passed, the dict will be shallow copied.

    ``body`` is a str or unicode containing the request body. If ``body`` is
    a `unicode` it's encoded to str using the `encoding` passed.

    ``headers`` is a multi-valued dict containing the headers of this request

    ``cookies`` is a dict containing the request cookies

    ``encoding`` is a string with the encoding of this request. This encoding
    will be used to percent-encode the URL and to convert the body to str (when
    given as unicode).

    ``dont_filter`` is a boolean which indicates that this request should not
    be filtered by the scheduler. This is used when you want to perform an
    identical request multiple times, for whatever reason

Request Attributes
------------------

.. attribute:: Request.url

    A string containing the URL of this request. Keep in mind that this
    attribute contains the escaped URL, so it can differ from the URL passed in
    the constructor.

.. attribute:: Request.method

    A string representing the HTTP method in the request. This is guaranteed to
    be uppercase. Example: ``"GET"``, ``"POST"``, ``"PUT"``, etc

.. attribute:: Request.headers

    A dictionary-like object which contains the request headers.

.. attribute:: Request.body

    A str that contains the request body

.. attribute:: Request.meta

    A dict that contains arbitrary metadata for this request. This dict is
    empty for new Requests, and is usually  populated by different Scrapy
    components (extensions, middlewares, etc). So the data contained in this
    dict depends on the extensions you have enabled.

    This dict is `shallow copied`_ when the request is cloned using the
    ``copy()`` or ``replace()`` methods.

.. _shallow copied: http://docs.python.org/library/copy.html

.. attribute:: Request.cache

    A dict that contains arbitrary cached data for this request. This dict is
    empty for new Requests, and is usually populated by different Scrapy
    components (extensions, middlewares, etc) to avoid duplicate processing. So
    the data contained in this dict depends on the extensions you have enabled.

    Unlike the ``meta`` attribute, this dict is not copied at all when the
    request is cloned using the ``copy()`` or ``replace()`` methods.

Request Methods
---------------

.. method:: Request.copy()

   Return a new Request which is a copy of this Request. The attribute
   :attr:`Request.meta` is copied, while :attr:`Request.cache` is not.

.. method:: Request.replace()

   Return a Request object with the same members, except for those members
   given new values by whichever keyword arguments are specified. The attribute
   :attr:`Request.meta` is copied, while :attr:`Request.cache` is not.

.. method:: Request.httprepr()

   Return a string with the raw HTTP representation of this response.

.. _ref-request-subclasses:

Request subclasses
==================

Here is the list of built-in Request subclasses. You can also subclass the
Request class to implement your own functionality.

FormRequest objects
-------------------

.. class:: FormRequest

The FormRequest class adds a new parameter to the constructor:

  `formdata` - a dictionary or list of (key, value) tuples (typically
      containing HTML Form data) which will be urlencoded and assigned to the body
      of the request.

Response objects
================

.. class:: Response(url, status=200, headers=None, body=None, meta=None, flags=None)

    A :class:`Response` object represents an HTTP response, which is usually
    downloaded (by the Downloader) and fed to the Spiders for processing.
    
    ``url`` is a string containing the URL for this response

    ``headers`` is a multivalued dict of the response headers

    ``status`` is an integer with the HTTP status of the response

    ``body`` is a str with the response body. It must be str, not unicode,
    unless you're using a Response sublcass such as :class:`TextResponse`.

    ``meta`` is a dict containing the initial values for the
    :attr:`Response.meta` attribute. If passed, the dict will be shallow copied.

    ``flags`` is a list containing the initial values for the
    :attr:`Response.flags` attribute. If passed, the list will be shallow copied.


Response Attributes
-------------------

.. attribute:: Response.url

    A string containing the URL of the response. 

.. attribute:: Response.status

    An integer representing the HTTP status of the response. Example: ``200``,
    ``404``.

.. attribute:: Response.headers

    A dictionary-like object which contains the response headers.

.. attribute:: Response.body

    A str containing the body of this Response. Keep in mind that Reponse.body
    is always a str. If you want the unicode version use
    :meth:`TextResponse.body_as_unicode` (only available in
    :class:`TextResponse` and subclasses).

.. attribute:: Response.request

    The :class:`Request` object that generated this response. This attribute is
    assigned in the Scrapy engine, after the response and request has passed
    through all :ref:`Downloader Middlewares <topics-downloader-middleware>`.
    In particular, this means that:

    - HTTP redirections will cause the original request (to the URL before
      redirection) to be assigned to the redirected response (with the final
      URL after redirection).

    - Response.request.url doesn't always equals Response.url

    - This attribute is only available in the spider code, and in the 
      :ref:`Spider Middlewares <topics-spider-middleware>`, but not in
      Downloader Middlewares (although you have the Request available there by
      other means) and handlers of the :signal:`response_downloaded` signal.

.. attribute:: Response.meta

    A dict that contains arbitrary metadata for this response, similar to the
    :attr:`Request.meta` attribute. See the :attr:`Request.meta` attribute for
    more info.

.. attribute:: Response.flags

    A list that contains flags for this response. Flags are labels used for
    tagging Responses. For example: `'cached'`, `'redirected`', etc. And
    they're shown on the string representation of the Response (`__str__`
    method) which is used by the engine for logging.

.. attribute:: Response.cache

    A dict that contains arbitrary cached data for this response, similar to
    the :attr:`Request.cache` attribute. See the :attr:`Request.cache`
    attribute for more info.

Response Methods
----------------

.. method:: Response.copy()

   Return a new Response which is a copy of this Response. The attribute
   :attr:`Response.meta` is copied, while :attr:`Response.cache` is not.

.. method:: Response.replace(url=None, status=None, headers=None, body=None)

   Return a Response object with the same members, except for those members
   given new values by whichever keyword arguments are specified. The attribute
   :attr:`Response.meta` is copied, while :attr:`Response.cache` is not.

.. method:: Response.httprepr()

   Return a string with the raw HTTP representation of this response.

.. _ref-response-subclasses:

Response subclasses
===================

Here is the list of available built-in Response subclasses. You can also
subclass the Response class to implement your own functionality.

.. class:: TextResponse

The TextResponse class adds encoding capabilities to the base Response class.
The base Response class is intended for binary data such as images or media
files.

:class:`TextResponse` supports the following constructor arguments, attributes
nd methods in addition to the base Request ones. The remaining functionality is
the same as for the :class:`Response` class and is not documented here.

TextResponse
------------

TextResponse constructor arguments
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    - `encoding` - a string which contains the encoding to use for this
       TextResponse. If you create a TextResponse with a unicode body it will be
       encoded using this encoding (remember the body attribute is always a
       string). 

       If encoding is `None` the encoding will be looked up in the headers anb
       body instead.

       It defaults to `None`.

TextResponse attributes
~~~~~~~~~~~~~~~~~~~~~~~

.. attribute:: TextResponse.encoding

   A string with the encoding of this Response. The encoding is resolved in the
   following order: 

   1. the encoding passed in the constructor `encoding` argument
   2. the encoding declared in the Content-Type HTTP header
   3. the encoding declared in the response body. The TextResponse class
      doesn't provide any special functionality for this. However, the
      :class:`HtmlResponse` and :class:`XmlResponse` classes do.
   4. the encoding inferred by looking at the response body. This is the more
      fragile method but also the last one tried.

TextResponse methods
~~~~~~~~~~~~~~~~~~~~

.. method:: TextResponse.headers_encoding()

    Returns a string with the encoding declared in the headers (ie. the
    Content-Type HTTP header).

.. method:: TextResponse.body_encoding()

    Returns a string with the encoding of the body, either declared or inferred
    from its contents. The body encoding declaration is implemented in
    :class:`TextResponse` subclasses such as: :class:`HtmlResponse` or
    :class:`XmlResponse`.

.. method:: TextResponse.body_as_unicode()

    Returns the body of the response as unicode. This is equivalent to::

        response.body.encode(response.encoding)

    But keep in mind that this is not equivalent to::
    
        unicode(response.body)
    
    Since in the latter case you would be using you system default encoding
    (typically `ascii`) to convert the body to uniode instead of the response
    encoding.

HtmlResponse objects
--------------------

.. class:: HtmlResponse

The HtmlResponse class is a subclass of :class:`TextResponse` which adds
encoding auto-discovering by looking into the HTML meta http-equiv attribute.
See :attr:`TextResponse.encoding`.

XmlResponse objects
-------------------

.. class:: HtmlResponse

The XmlResponse class is a subclass of :class:`TextResponse` which adds
encoding auto-discovering by looking into the XML declaration line.
See :attr:`TextResponse.encoding`.

