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
:setting:`DOWNLOADER_MIDDLEWARES_BASE` setting defined in Scrapy (and not meant
to be overridden) and then sorted by order to get the final sorted list of
enabled middlewares: the first middleware is the one closer to the engine and
the last is the one closer to the downloader. In other words,
the :meth:`~scrapy.downloadermiddlewares.DownloaderMiddleware.process_request`
method of each middleware will be invoked in increasing
middleware order (100, 200, 300, ...) and the :meth:`~scrapy.downloadermiddlewares.DownloaderMiddleware.process_response` method
of each middleware will be invoked in decreasing order.

To decide which order to assign to your middleware see the
:setting:`DOWNLOADER_MIDDLEWARES_BASE` setting and pick a value according to
where you want to insert the middleware. The order does matter because each
middleware performs a different action and your middleware could depend on some
previous (or subsequent) middleware being applied.

If you want to disable a built-in middleware (the ones defined in
:setting:`DOWNLOADER_MIDDLEWARES_BASE` and enabled by default) you must define it
in your project's :setting:`DOWNLOADER_MIDDLEWARES` setting and assign `None`
as its value.  For example, if you want to disable the user-agent middleware::

    DOWNLOADER_MIDDLEWARES = {
        'myproject.middlewares.CustomDownloaderMiddleware': 543,
        'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
    }

Finally, keep in mind that some middlewares may need to be enabled through a
particular setting. See each middleware documentation for more info.

Writing your own downloader middleware
======================================

Each middleware component is a Python class that defines one or
more of the following methods:

.. interface:: IDownloaderMiddleware

   .. note::  Any of the downloader middleware methods may also return a deferred.

   .. method:: process_request(request, spider)

      This method is called for each request that goes through the download
      middleware.

      :meth:`process_request` should either: return ``None``, return a
      :class:`~scrapy.http.Response` object, return a :class:`~scrapy.http.Request`
      object, or raise :exc:`~scrapy.exceptions.IgnoreRequest`.

      If it returns ``None``, Scrapy will continue processing this request, executing all
      other middlewares until, finally, the appropriate downloader handler is called
      the request performed (and its response downloaded).

      If it returns a :class:`~scrapy.http.Response` object, Scrapy won't bother
      calling *any* other :meth:`process_request` or :meth:`process_exception` methods,
      or the appropriate download function; it'll return that response. The :meth:`process_response`
      methods of installed middleware is always called on every response.

      If it returns a :class:`~scrapy.http.Request` object, Scrapy will stop calling
      process_request methods and reschedule the returned request. Once the newly returned
      request is performed, the appropriate middleware chain will be called on
      the downloaded response.

      If it raises an :exc:`~scrapy.exceptions.IgnoreRequest` exception, the
      :meth:`process_exception` methods of installed downloader middleware will be called.
      If none of them handle the exception, the errback function of the request
      (``Request.errback``) is called. If no code handles the raised exception, it is
      ignored and not logged (unlike other exceptions).

      :param request: the request being processed
      :type request: :class:`~scrapy.http.Request` object

      :param spider: the spider for which this request is intended
      :type spider: :class:`~scrapy.spiders.Spider` object

   .. method:: process_response(request, response, spider)

      :meth:`process_response` should either: return a :class:`~scrapy.http.Response`
      object, return a :class:`~scrapy.http.Request` object or
      raise a :exc:`~scrapy.exceptions.IgnoreRequest` exception.

      If it returns a :class:`~scrapy.http.Response` (it could be the same given
      response, or a brand-new one), that response will continue to be processed
      with the :meth:`process_response` of the next middleware in the chain.

      If it returns a :class:`~scrapy.http.Request` object, the middleware chain is
      halted and the returned request is rescheduled to be downloaded in the future.
      This is the same behavior as if a request is returned from :meth:`process_request`.

      If it raises an :exc:`~scrapy.exceptions.IgnoreRequest` exception, the errback
      function of the request (``Request.errback``) is called. If no code handles the raised
      exception, it is ignored and not logged (unlike other exceptions).

      :param request: the request that originated the response
      :type request: is a :class:`~scrapy.http.Request` object

      :param response: the response being processed
      :type response: :class:`~scrapy.http.Response` object

      :param spider: the spider for which this response is intended
      :type spider: :class:`~scrapy.spiders.Spider` object

   .. method:: process_exception(request, exception, spider)

      Scrapy calls :meth:`process_exception` when a download handler
      or a :meth:`process_request` (from a downloader middleware) raises an
      exception (including an :exc:`~scrapy.exceptions.IgnoreRequest` exception)

      :meth:`process_exception` should return: either ``None``,
      a :class:`~scrapy.http.Response` object, or a :class:`~scrapy.http.Request` object.

      If it returns ``None``, Scrapy will continue processing this exception,
      executing any other :meth:`process_exception` methods of installed middleware,
      until no middleware is left and the default exception handling kicks in.

      If it returns a :class:`~scrapy.http.Response` object, the :meth:`process_response`
      method chain of installed middleware is started, and Scrapy won't bother calling
      any other :meth:`process_exception` methods of middleware.

      If it returns a :class:`~scrapy.http.Request` object, the returned request is
      rescheduled to be downloaded in the future. This stops the execution of
      :meth:`process_exception` methods of the middleware the same as returning a
      response would.

      :param request: the request that generated the exception
      :type request: is a :class:`~scrapy.http.Request` object

      :param exception: the raised exception
      :type exception: an ``Exception`` object

      :param spider: the spider for which this request is intended
      :type spider: :class:`~scrapy.spiders.Spider` object

   .. method:: from_crawler(cls, crawler)

      If present, this classmethod is called to create a middleware instance
      from a :class:`~scrapy.crawler.Crawler`. It must return a new instance
      of the middleware. Crawler object provides access to all Scrapy core
      components like settings and signals; it is a way for middleware to
      access them and hook its functionality into Scrapy.

      :param crawler: crawler that uses this middleware
      :type crawler: :class:`~scrapy.crawler.Crawler` object

.. _topics-downloader-middleware-ref:

Built-in downloader middleware reference
========================================

This page describes all downloader middleware components that come with
Scrapy. For information on how to use them and how to write your own downloader
middleware, see the :ref:`downloader middleware usage guide
<topics-downloader-middleware>`.

For a list of the components enabled by default (and their orders) see the
:setting:`DOWNLOADER_MIDDLEWARES_BASE` setting.

.. _cookies-mw:

CookiesMiddleware
-----------------

.. autoclass:: scrapy.downloadermiddlewares.cookies.CookiesMiddleware


DefaultHeadersMiddleware
------------------------

.. autoclass:: scrapy.downloadermiddlewares.defaultheaders.DefaultHeadersMiddleware


DownloadTimeoutMiddleware
-------------------------

.. autoclass:: scrapy.downloadermiddlewares.downloadtimeout.DownloadTimeoutMiddleware


HttpAuthMiddleware
------------------

.. autoclass:: scrapy.downloadermiddlewares.httpauth.HttpAuthMiddleware


HttpCacheMiddleware
-------------------

.. autoclass:: scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware


HttpCompressionMiddleware
-------------------------

.. autoclass:: scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware


HttpProxyMiddleware
-------------------

.. autoclass:: scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware


RedirectMiddleware
------------------

.. autoclass:: scrapy.downloadermiddlewares.redirect.RedirectMiddleware


MetaRefreshMiddleware
---------------------

.. autoclass:: scrapy.downloadermiddlewares.redirect.MetaRefreshMiddleware


RetryMiddleware
---------------

.. autoclass:: scrapy.downloadermiddlewares.retry.RetryMiddleware


.. _topics-dlmw-robots:

RobotsTxtMiddleware
-------------------

.. autoclass:: scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware


DownloaderStats
---------------

.. autoclass:: scrapy.downloadermiddlewares.stats.DownloaderStats


UserAgentMiddleware
-------------------

.. autoclass:: scrapy.downloadermiddlewares.useragent.UserAgentMiddleware


.. _ajaxcrawl-middleware:

AjaxCrawlMiddleware
-------------------

.. autoclass:: scrapy.downloadermiddlewares.ajaxcrawl.AjaxCrawlMiddleware


.. _DBM: https://en.wikipedia.org/wiki/Dbm
.. _anydbm: https://docs.python.org/2/library/anydbm.html
