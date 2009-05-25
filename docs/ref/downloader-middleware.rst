.. _ref-downloader-middleware:

========================================
Built-in downloader middleware reference
========================================

This document explains all downloader middleware components that come with
Scrapy. For information on how to use them and how to write your own downloader
middleware, see the :ref:`downloader middleware usage guide
<topics-downloader-middleware>`.

Available downloader middlewares
================================

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

