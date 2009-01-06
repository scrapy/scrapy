.. _topics-downloader-middleware:

=====================
Downloader Middleware
=====================

The downloader middleware is a framework of hooks into Scrapy's
request/response processing.  It's a light, low-level system for globally
altering Scrapy's input and/or output.

Activating a downloader middleware
==================================

To activate a downloader middleware component, add it to the
:setting:`DOWNLOADER_MIDDLEWARES` list in your Scrapy settings.  In
:setting:`DOWNLOADER_MIDDLEWARES`, each middleware component is represented by
a string: the full Python path to the middleware's class name. For example::

    DOWNLOADER_MIDDLEWARES = [
            'scrapy.contrib.middleware.common.SpiderMiddleware',
            'scrapy.contrib.middleware.common.CommonMiddleware',
            'scrapy.contrib.middleware.redirect.RedirectMiddleware',
            'scrapy.contrib.middleware.cache.CacheMiddleware',
    ]

Writing your own downloader middleware
======================================

Writing your own downloader middleware is easy. Each middleware component is a
single Python class that defines one or more of the following methods:


.. method:: process_request(request, spider)

``request`` is a :class:`~scrapy.http.Request` object
``spider`` is a :class:`~scrapy.spider.BaseSpider` object

This method is called for each request that goes through the download
middleware.

``process_request()`` should return either ``None``, a
:class:`~scrapy.http.Response` object, or a :class:`~scrapy.http.Request`
object.

If returns ``None``, Scrapy will continue processing this request, executing all
other middlewares until, finally, the appropriate downloader handler is called
the request performed (and its response downloaded).

If returns a Response object, Scrapy won't bother calling ANY other request or
exception middleware, or the appropriate download function; it'll return that
Response. Response middleware is always called on every response.

If returns a :class:`~scrapy.http.Request` object, returned request is used to
instruct a redirection. Redirection is handled inside middleware scope, and
original request don't finish until redirected request is completed.


.. method:: process_response(request, response, spider)

``request`` is a :class:`~scrapy.http.Request` object
``response`` is a :class:`~scrapy.http.Response` object
``spider`` is a BaseSpider object

``process_response()`` should return a Response object or raise a
:exception:`IgnoreRequest` exception. 

If returns a Response (it could be the same given response, or a brand-new one)
that response will continue to be processed with the ``process_response()`` of
the next middleware in the pipeline.

If returns an :exception:`IgnoreRequest` exception, the response will be
dropped completely and its callback never called.

.. method:: process_download_exception(request, exception, spider)

``request`` is a :class:`~scrapy.http.Request` object.
``exception`` is an Exception object
``spider`` is a BaseSpider object

Scrapy calls ``process_download_exception()`` when a download handler or a
``process_request()`` (from a downloader middleware) raises an exception.

``process_download_exception()`` should return either ``None``,
:class:`~scrapy.http.Response` or :class:`~scrapy.http.Request` object.

If it returns ``None``, Scrapy will continue processing this exception,
executing any other exception middleware, until no middleware is left and
the default exception handling kicks in.

If it returns a :class:`~scrapy.http.Response` object, the response middleware
kicks in, and won't bother calling any other exception middleware.

If it returns a :class:`~scrapy.http.Request` object, returned request is used
to instruct a immediate redirection. Redirection is handled inside middleware
scope, and the original request won't finish until redirected request is
completed. This stop ``process_download_exception()`` middleware as returning Response
would do.

