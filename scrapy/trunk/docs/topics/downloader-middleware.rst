=====================
Downloader Middleware
=====================

The downloader middleware is a framework of hooks into Scrapy's
request/response processing.  It's a light, low-level system for globally
altering Scrapy's input and/or output.

Activating a middleware
=======================

To activate a middleware component, add it to the
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


.. method:: process_request(self, request, spider)

``request`` is a Request object.
``spider`` is a BaseSpider object

This method is called in each request until scrapy decides which
download function to use.

process_request() should return either None, Response or Request.

If returns None, Scrapy will continue processing this request,
executing any other middleware and, then, the appropiate download
function.

If returns a Response object, Scrapy won't bother calling ANY other
request or exception middleware, or the appropiate download function;
it'll return that Response. Response middleware is always called on
every response.

If returns a Request object, returned request is used to instruct a
redirection. Redirection is handled inside middleware scope, and
original request don't finish until redirected request is completed.


.. method:: process_response(self, request, response, spider)

``request`` is a Request object
``response`` is a Response object
``spider`` is a BaseSpider object

process_response MUST return a Response object. It could alter the given
response, or it could create a brand-new Response.
To drop the response entirely an IgnoreRequest exception must be raised.

.. method:: process_exception(self, request, exception, spider)

``request`` is a Request object.
``exception`` is an Exception object
``spider`` is a BaseSpider object

Scrapy calls process_exception() when a download handler or
process_request middleware raises an exception.

process_exception() should return either None, Response or Request object.

if it returns None, Scrapy will continue processing this exception,
executing any other exception middleware, until no middleware left and
default exception handling kicks in.

If it returns a Response object, the response middleware kicks in, and
won't bother calling ANY other exception middleware.

If it returns a Request object, returned request is used to instruct a
immediate redirection. Redirection is handled inside middleware scope,
and original request don't finish until redirected request is
completed. This stop process_exception middleware as returning
Response does.

