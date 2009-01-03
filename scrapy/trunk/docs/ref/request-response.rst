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

    A dict of the request headers.

.. attribute:: Request.body

    The body of the request as a string

Methods
-------

.. method:: Request.__init__(url, callback=None, context=None, method=None, body=None, headers=None, cookies=None, referer=None, url_encoding='utf-8', link_text='', http_user='', http_pass='', dont_filter=None)

    Instantiates a ``Request`` object with the given arguments:

    ``url`` is a string containing the URL for this request

    ``callback`` is a function that will be called with the response of this
    request (once its downloaded) as its first parameter

    ``context`` can be a dict which will be accesible in the callback function
    in ``response.request.context`` in the callback function

    ``body`` is a string containing the request body or None if the request doesn't contain a body (ex. GET requests)

    ``headers`` is a multi-valued dict containing the headers of this request

    ``cookies`` is dict of the request cookies

    ``referer`` is a string with the referer of this request

    ``url_encoding`` is a string with the encoding of the url of this request.
     Requests URLs will be percent encoded using this encoding before downloading 

    ``link_text`` is a string describing the URL of this requests. For example, in ``<a href="http://www.example.com/">Example site</a>`` the ``link_text`` would be ``"Example site"``

    ``http_user`` is a string containing the user name that will be used for
    HTTP authentication when performing this request. If None, HTTP auth will
    not be used

    ``http_user`` is a string containing the password that will be used for
    HTTP authentication when performing this request. If None, HTTP auth will
    not be used

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

    A dict of the response headers.

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

