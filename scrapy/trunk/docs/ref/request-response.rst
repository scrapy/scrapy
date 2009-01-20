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

    ``body`` is a string containing the request body or None if the request
    doesn't contain a body (ex. GET requests)

    ``headers`` is a multi-valued dict containing the headers of this request

    ``cookies`` is a dict containing the request cookies

    ``encoding`` is a string with the encoding of this request. This encoding
    will be used to percent-encode the URL and to convert the body to str (when
    given as unicode).

    ``dont_filter`` is a boolean which indicates that this request should not
    be filtered by the scheduler. This is used when you want to perform an
    identical request multiple times, for whatever reason

Attributes
----------

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

    A string that contains the request body

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

Methods
-------

.. method:: Request.copy()

   Return a new Request which is a copy of this Request. The attribute
   :attr:`Request.meta` is copied, while :attr:`Request.cache` is not.

.. method:: Request.replace()

   Return a Request object with the same members, except for those members
   given new values by whichever keyword arguments are specified. The attribute
   :attr:`Request.meta` is copied, while :attr:`Request.cache` is not.

.. method:: Request.httprepr()

   Return a string with the raw HTTP representation of this response.

Response objects
================

.. class:: Response(url, status=200, headers=None, body=None)

    A :class:`Response` object represents an HTTP response, which is usually
    downloaded (by the Downloader) and fed to the Spiders for processing.
    
    ``url`` is a string containing the URL for this response

    ``headers`` is a multivalued dict of the response headers

    ``status`` is an integer with the HTTP status of the response

    ``body`` is a string (or unicode) containing the response body

    ``meta`` is a dict containing the initial values for the
    :attr:`Response.meta` attribute. If passed, the dict will be shallow copied.


Attributes
----------

.. attribute:: Response.url

    A string containing the URL of the response. 

.. attribute:: Response.status

    An integer representing the HTTP status of the response. Example: ``200``,
    ``404``.

.. attribute:: Response.headers

    A dictionary-like object which contains the response headers.

.. attribute:: Response.body

    The body of this Response.

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

.. attribute:: Response.cache

    A dict that contains arbitrary cached data for this response, similar to
    the :attr:`Request.cache` attribute. See the :attr:`Request.cache`
    attribute for more info.

Methods
-------

.. method:: Response.copy()

   Return a new Response which is a copy of this Response. The attribute
   :attr:`Response.meta` is copied, while :attr:`Response.cache` is not.

.. method:: Response.replace(url=None, status=None, headers=None, body=None)

   Return a Response object with the same members, except for those members
   given new values by whichever keyword arguments are specified. The attribute
   :attr:`Response.meta` is copied, while :attr:`Response.cache` is not.

.. method:: Response.httprepr()

   Return a string with the raw HTTP representation of this response.
