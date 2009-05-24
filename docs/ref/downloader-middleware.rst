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

.. _ref-downloader-middleware-common:

"Common" downloader middleware
------------------------------

.. module:: scrapy.contrib.downloadermiddleware.common
   :synopsis: Downloader middleware for performing basic required tasks

.. class:: scrapy.contrib.downloadermiddleware.common.CommonMiddleware

This middleware performs some commonly required tasks over all requests, and
thus it's recommended to leave it always enabled. Those tasks are:

    * If the ``Accept`` request header is not already set, then set it to
      :setting:`REQUEST_HEADER_ACCEPT`
    
    * If the ``Accept-Language`` request header is not already set, then set it
      to :setting:`REQUEST_HEADER_ACCEPT_LANGUAGE` 

    * If the request method is ``POST`` and the ``Content-Type`` header is not
      set, then set it to ``'application/x-www-form-urlencoded'``, the `default
      Form content type`_.

    * If the request contains a body and the ``Content-Length`` headers it not
      set, then set it to the ``len(body)``.
    
.. _default Form content type: http://www.w3.org/TR/html401/interact/forms.html#h-17.13.4.1

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

