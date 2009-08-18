.. _topics-downloader-middleware:

=====================
Downloader Middleware
=====================

The downloader middleware is a framework of hooks into Scrapy's
request/response processing.  It's a light, low-level system for globally
altering Scrapy's requests and responses.

.. _topics-downloader-middleware-setting:

Activating a downloader middleware
==================================

To activate a downloader middleware component, add it to the
:setting:`DOWNLOADER_MIDDLEWARES` setting, which is a dict whose keys are the
middleware class paths and their values are the middleware orders.

Here's an example::

    DOWNLOADER_MIDDLEWARES = {
        'myproject.middlewares.CustomDownloaderMiddleware': 543,
    }

The :setting:`DOWNLOADER_MIDDLEWARES` setting is merged with the
:setting:`DOWNLOADER_MIDDLEWARES_BASE` setting defined in Scrapy (and not meant to
be overridden) and then sorted by order to get the final sorted list of enabled
middlewares: the first middleware is the one closer to the engine and the last
is the one closer to the downloader.

To decide which order to assign to your middleware see the
:setting:`DOWNLOADER_MIDDLEWARES_BASE` setting and pick a value according to
where you want to insert the middleware. The order does matter because each
middleware performs a different action and your middleware could depend on some
previous (or subsequent) middleware being applied.

If you want to disable a builtin middleware (the ones defined in
:setting:`DOWNLOADER_MIDDLEWARES_BASE` and enabled by default) you must define it
in your project :setting:`DOWNLOADER_MIDDLEWARES` setting and assign `None`
as its value.  For example, if you want to disable the off-site middleware::

    DOWNLOADER_MIDDLEWARES = {
        'myproject.middlewares.CustomDownloaderMiddleware': 543,
        'scrapy.contrib.downloadermiddleware.useragent.UserAgentMiddleware': None,
    }

Finally, keep in mind that some middlewares may need to be enabled through a
particular setting. See each middleware documentation for more info.

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

If returns a :class:`~scrapy.http.Request` object, the returned request will be
re-scheduled (in the Scheduler) to be downloaded in the future. The callback of
the original request will always be called. If the new request has a callback
it will be called with the response downloaded, and the output of that callback
will then be passed to the original callback. If the new request doesn't have a
callback, the response downloaded will be just passed to the original request
callback.

If returns an :exception:`IgnoreRequest` exception, the entire request will be
dropped completely and its callback never called.


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


.. _topics-downloader-middleware-ref:

Built-in downloader middleware reference
========================================

This page describes all downloader middleware components that come with
Scrapy. For information on how to use them and how to write your own downloader
middleware, see the :ref:`downloader middleware usage guide
<topics-downloader-middleware>`.

For a list of the components enabled by default (and their orders) see the
:setting:`DOWNLOADER_MIDDLEWARES_BASE` setting.

DefaultHeadersMiddleware
------------------------

.. module:: scrapy.contrib.downloadermiddleware.defaultheaders
   :synopsis: Default Headers Downloader Middleware

.. class:: DefaultHeadersMiddleware

    This middleware sets all default requests headers specified in the
    :setting:`DEFAULT_REQUEST_HEADERS` setting.

DebugMiddleware
---------------

.. module:: scrapy.contrib.downloadermiddleware.debug
   :synopsis: Downloader middlewares for debugging

.. class:: DebugMiddleware

    This is a convenient middleware to inspect what's passing through the
    downloader middleware. It logs all requests and responses catched by the
    middleware component methods. This middleware does not use any settings and
    does not come enabled by default. Instead, it's meant to be inserted at the
    point of the middleware that you want to inspect.

HttpCacheMiddleware
-------------------

.. module:: scrapy.contrib.downloadermiddleware.httpcache
   :synopsis: HTTP Cache downloader middleware

.. class:: HttpCacheMiddleware

    This middleware provides low-level cache to all HTTP requests and responses.
    Every request and its corresponding response are cached and then, when that
    same request is seen again, the response is returned without transferring
    anything from the Internet.

    The HTTP cache is useful for testing spiders faster (without having to wait for
    downloads every time) and for trying your spider off-line when you don't have
    an Internet connection.

    The :class:`HttpCacheMiddleware` can be configured through the following
    settings (see the settings documentation for more info):

        * :setting:`HTTPCACHE_DIR` - this one actually enables the cache besides
          settings the cache dir
        * :setting:`HTTPCACHE_IGNORE_MISSING` - ignoring missing requests instead
          of downloading them
        * :setting:`HTTPCACHE_SECTORIZE` - split HTTP cache in several directories
          (for performance reasons)
        * :setting:`HTTPCACHE_EXPIRATION_SECS` - how many secs until the cache is
          considered out of date

RobotsTxtMiddleware
-------------------

.. module:: scrapy.contrib.downloadermiddleware.robotstxt
   :synopsis: robots.txt middleware

.. class:: RobotsTxtMiddleware:

    This middleware filters out requests forbidden by the robots.txt exclusion
    standard.

    To make sure Scrapy respects robots.txt make sure the middleware is enabled
    amd the :setting:`ROBOTSTXT_OBEY` setting is enabled.

    .. warning:: Keep in mind that, if you crawl using multiple concurrent
       requests per domain, Scrapy could still  download some forbidden pages
       if they were requested before the robots.txt file was downloaded. This
       is a known limitation of the current robots.txt middleware and will
       be fixed in the future.
