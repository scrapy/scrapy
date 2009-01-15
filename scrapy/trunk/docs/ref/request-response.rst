.. _ref-request-response:

============================
Request and Response objects
============================

.. module:: scrapy.http
   :synopsis: Classes dealing with HTTP requests and responses.

Quick overview
==============

Scrapy uses requests and response objects for crawling web sites. 

Typically, :class:`Request` objects are generated is the spiders and pass
across the system until they reach the downloader which ends up performing the
requests and downloading a HTTP url, to finally generate a :class:`Response`
object that returns to the spider which generated the request.

Request objects
===============

.. class:: Request

Attributes
----------

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

.. method:: Request.__init__(url, callback=None, context=None, method='GET', body=None, headers=None, cookies=None, url_encoding='utf-8', dont_filter=None)

    Instantiates a ``Request`` object with the given arguments:

    ``url`` is a string containing the URL for this request

    ``callback`` is a function that will be called with the response of this
    request (once its downloaded) as its first parameter

    ``context`` can be a dict which will be accessible in the callback function
    in ``response.request.context`` in the callback function

    ``method`` is a string with the HTTP method of this request

    ``body`` is a string containing the request body or None if the request
    doesn't contain a body (ex. GET requests)

    ``headers`` is a multi-valued dict containing the headers of this request

    ``cookies`` is dict of the request cookies

    ``url_encoding`` is a string with the encoding of the url of this request.
    The request URL will be percent encoded using this encoding before
    downloading 

    ``dont_filter`` is a boolean which indicates that this request should not
    be filtered by the scheduler. This is used when you want to perform an
    identical request multiple times, for whatever reason

.. class:: Response

Response objects
================

Attributes
----------

.. attribute:: Response.status

    An integer representing the HTTP status in the response. Example: ``200``,
    ``404``, etc

.. attribute:: Response.headers

    A dictionary-like object which contains the response headers.

.. attribute:: Response.meta

    A dict that contains arbitrary metadata fro this response. It works like
    :attr:`Request.meta` for Request objects. See that attribute help for more
    info.

.. attribute:: Response.cache

    A dict that contains arbitrary cached data for this response. It works like
    :attr:`Request.cache` for Request objects. See that attribute help for more
    info.

Methods
-------

.. method:: __init__(domain, url, original_url=None, headers=None, status=200, body=None)

    Instantiates a ``Response`` object with the given arguments:

    ``url`` is a string containing the URL for this response

    ``original_url`` is a string containing the url from which this response
    was redirected (only for redirected responses)

    ``headers`` is a multivalued dict of the response headers

    ``status`` is an integer with the HTTP status of the response

    ``body`` is a string (or unicode) containing the response body

