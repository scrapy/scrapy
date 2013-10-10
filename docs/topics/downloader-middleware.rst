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

If you want to disable a built-in middleware (the ones defined in
:setting:`DOWNLOADER_MIDDLEWARES_BASE` and enabled by default) you must define it
in your project's :setting:`DOWNLOADER_MIDDLEWARES` setting and assign `None`
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

.. module:: scrapy.contrib.downloadermiddleware

.. class:: DownloaderMiddleware

   .. method:: process_request(request, spider)

      This method is called for each request that goes through the download
      middleware.

      :meth:`process_request` should return either ``None``, a
      :class:`~scrapy.http.Response` object, or a :class:`~scrapy.http.Request`
      object.

      If it returns ``None``, Scrapy will continue processing this request, executing all
      other middlewares until, finally, the appropriate downloader handler is called
      the request performed (and its response downloaded).

      If it returns a :class:`~scrapy.http.Response` object, Scrapy won't bother
      calling ANY other request or exception middleware, or the appropriate
      download function; it'll return that Response. Response middleware is
      always called on every Response.

      If it raises an :exc:`~scrapy.exceptions.IgnoreRequest` exception, the
      entire request will be dropped completely and its callback never called.

      :param request: the request being processed
      :type request: :class:`~scrapy.http.Request` object

      :param spider: the spider for which this request is intended
      :type spider: :class:`~scrapy.spider.BaseSpider` object

   .. method:: process_response(request, response, spider)

      :meth:`process_response` should return either a :class:`~scrapy.http.Response`
      object, a :class:`~scrapy.http.Request` object or 
      raise a :exc:`~scrapy.exceptions.IgnoreRequest` exception.

      If it returns a :class:`~scrapy.http.Response` (it could be the same given
      response, or a brand-new one), that response will continue to be processed
      with the :meth:`process_response` of the next middleware in the pipeline.

      If it returns a :class:`~scrapy.http.Request` object, the returned request will be
      rescheduled to be downloaded in the future.

      If it raises an :exc:`~scrapy.exceptions.IgnoreRequest` exception, the
      response will be dropped completely and its callback never called.

      :param request: the request that originated the response
      :type request: is a :class:`~scrapy.http.Request` object

      :param response: the response being processed
      :type response: :class:`~scrapy.http.Response` object

      :param spider: the spider for which this response is intended
      :type spider: :class:`~scrapy.spider.BaseSpider` object

   .. method:: process_exception(request, exception, spider)

      Scrapy calls :meth:`process_exception` when a download handler
      or a :meth:`process_request` (from a downloader middleware) raises an
      exception.

      :meth:`process_exception` should return either ``None``,
      :class:`~scrapy.http.Response` or :class:`~scrapy.http.Request` object.

      If it returns ``None``, Scrapy will continue processing this exception,
      executing any other exception middleware, until no middleware is left and
      the default exception handling kicks in.

      If it returns a :class:`~scrapy.http.Response` object, the response middleware
      kicks in, and won't bother calling any other exception middleware.

      If it returns a :class:`~scrapy.http.Request` object, the returned request is
      used to instruct an immediate redirection.
      The original request won't finish until the redirected
      request is completed. This stops the :meth:`process_exception`
      middleware the same as returning Response would do.

      :param request: the request that generated the exception
      :type request: is a :class:`~scrapy.http.Request` object

      :param exception: the raised exception
      :type exception: an ``Exception`` object

      :param spider: the spider for which this request is intended
      :type spider: :class:`~scrapy.spider.BaseSpider` object

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

.. module:: scrapy.contrib.downloadermiddleware.cookies
   :synopsis: Cookies Downloader Middleware

.. class:: CookiesMiddleware

   This middleware enables working with sites that require cookies, such as
   those that use sessions. It keeps track of cookies sent by web servers, and
   send them back on subsequent requests (from that spider), just like web
   browsers do.

The following settings can be used to configure the cookie middleware:

* :setting:`COOKIES_ENABLED`
* :setting:`COOKIES_DEBUG`

.. reqmeta:: cookiejar

Multiple cookie sessions per spider
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 0.15

There is support for keeping multiple cookie sessions per spider by using the
:reqmeta:`cookiejar` Request meta key. By default it uses a single cookie jar
(session), but you can pass an identifier to use different ones.

For example::

    for i, url in enumerate(urls):
        yield Request("http://www.example.com", meta={'cookiejar': i},
            callback=self.parse_page)

Keep in mind that the :reqmeta:`cookiejar` meta key is not "sticky". You need to keep
passing it along on subsequent requests. For example::

    def parse_page(self, response):
        # do some processing
        return Request("http://www.example.com/otherpage",
            meta={'cookiejar': response.meta['cookiejar']},
            callback=self.parse_other_page)

.. setting:: COOKIES_ENABLED

COOKIES_ENABLED
~~~~~~~~~~~~~~~

Default: ``True``

Whether to enable the cookies middleware. If disabled, no cookies will be sent
to web servers.

.. setting:: COOKIES_DEBUG

COOKIES_DEBUG
~~~~~~~~~~~~~

Default: ``False``

If enabled, Scrapy will log all cookies sent in requests (ie. ``Cookie``
header) and all cookies received in responses (ie. ``Set-Cookie`` header).

Here's an example of a log with :setting:`COOKIES_DEBUG` enabled::

    2011-04-06 14:35:10-0300 [diningcity] INFO: Spider opened
    2011-04-06 14:35:10-0300 [diningcity] DEBUG: Sending cookies to: <GET http://www.diningcity.com/netherlands/index.html>
            Cookie: clientlanguage_nl=en_EN
    2011-04-06 14:35:14-0300 [diningcity] DEBUG: Received cookies from: <200 http://www.diningcity.com/netherlands/index.html>
            Set-Cookie: JSESSIONID=B~FA4DC0C496C8762AE4F1A620EAB34F38; Path=/
            Set-Cookie: ip_isocode=US
            Set-Cookie: clientlanguage_nl=en_EN; Expires=Thu, 07-Apr-2011 21:21:34 GMT; Path=/
    2011-04-06 14:49:50-0300 [diningcity] DEBUG: Crawled (200) <GET http://www.diningcity.com/netherlands/index.html> (referer: None)
    [...]


DefaultHeadersMiddleware
------------------------

.. module:: scrapy.contrib.downloadermiddleware.defaultheaders
   :synopsis: Default Headers Downloader Middleware

.. class:: DefaultHeadersMiddleware

    This middleware sets all default requests headers specified in the
    :setting:`DEFAULT_REQUEST_HEADERS` setting.

DownloadTimeoutMiddleware
-------------------------

.. module:: scrapy.contrib.downloadermiddleware.downloadtimeout
   :synopsis: Download timeout middleware

.. class:: DownloadTimeoutMiddleware

    This middleware sets the download timeout for requests specified in the
    :setting:`DOWNLOAD_TIMEOUT` setting.

HttpAuthMiddleware
------------------

.. module:: scrapy.contrib.downloadermiddleware.httpauth
   :synopsis: HTTP Auth downloader middleware

.. class:: HttpAuthMiddleware

    This middleware authenticates all requests generated from certain spiders
    using `Basic access authentication`_ (aka. HTTP auth).

    To enable HTTP authentication from certain spiders, set the ``http_user``
    and ``http_pass`` attributes of those spiders.

    Example::

        class SomeIntranetSiteSpider(CrawlSpider):

            http_user = 'someuser'
            http_pass = 'somepass'
            name = 'intranet.example.com'

            # .. rest of the spider code omitted ...

.. _Basic access authentication: http://en.wikipedia.org/wiki/Basic_access_authentication


HttpCacheMiddleware
-------------------

.. module:: scrapy.contrib.downloadermiddleware.httpcache
   :synopsis: HTTP Cache downloader middleware

.. class:: HttpCacheMiddleware

    This middleware provides low-level cache to all HTTP requests and responses.
    It has to be combined with a cache storage backend as well as a cache policy.

    Scrapy ships with two HTTP cache storage backends:

        * :ref:`httpcache-storage-dbm`
        * :ref:`httpcache-storage-fs`

    You can change the HTTP cache storage backend with the :setting:`HTTPCACHE_STORAGE`
    setting. Or you can also implement your own storage backend.

    Scrapy ships with two HTTP cache policies:

        * :ref:`httpcache-policy-rfc2616`
        * :ref:`httpcache-policy-dummy`

    You can change the HTTP cache policy with the :setting:`HTTPCACHE_POLICY`
    setting. Or you can also implement your own policy.


.. _httpcache-policy-dummy:

Dummy policy (default)
~~~~~~~~~~~~~~~~~~~~~~

This policy has no awareness of any HTTP Cache-Control directives.
Every request and its corresponding response are cached.  When the same
request is seen again, the response is returned without transferring
anything from the Internet.

The Dummy policy is useful for testing spiders faster (without having
to wait for downloads every time) and for trying your spider offline,
when an Internet connection is not available. The goal is to be able to
"replay" a spider run *exactly as it ran before*.

In order to use this policy, set:

* :setting:`HTTPCACHE_POLICY` to ``scrapy.contrib.httpcache.DummyPolicy``


.. _httpcache-policy-rfc2616:

RFC2616 policy
~~~~~~~~~~~~~~

This policy provides a RFC2616 compliant HTTP cache, i.e. with HTTP
Cache-Control awareness, aimed at production and used in continuous
runs to avoid downloading unmodified data (to save bandwidth and speed up crawls).

what is implemented:

* Do not attempt to store responses/requests with `no-store` cache-control directive set
* Do not serve responses from cache if `no-cache` cache-control directive is set even for fresh responses
* Compute freshness lifetime from `max-age` cache-control directive
* Compute freshness lifetime from `Expires` response header
* Compute freshness lifetime from `Last-Modified` response header (heuristic used by Firefox)
* Compute current age from `Age` response header
* Compute current age from `Date` header
* Revalidate stale responses based on `Last-Modified` response header
* Revalidate stale responses based on `ETag` response header
* Set `Date` header for any received response missing it

what is missing:

* `Pragma: no-cache` support http://www.mnot.net/cache_docs/#PRAGMA
* `Vary` header support http://www.w3.org/Protocols/rfc2616/rfc2616-sec13.html#sec13.6
* Invalidation after updates or deletes http://www.w3.org/Protocols/rfc2616/rfc2616-sec13.html#sec13.10
* ... probably others ..

In order to use this policy, set:

* :setting:`HTTPCACHE_POLICY` to ``scrapy.contrib.httpcache.RFC2616Policy``


.. _httpcache-storage-dbm:

DBM storage backend (default)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 0.13

A DBM_ storage backend is available for the HTTP cache middleware.

By default, it uses the anydbm_ module, but you can change it with the
:setting:`HTTPCACHE_DBM_MODULE` setting.

In order to use this storage backend, set:

* :setting:`HTTPCACHE_STORAGE` to ``scrapy.contrib.httpcache.DbmCacheStorage``


.. _httpcache-storage-fs:

Filesystem storage backend
~~~~~~~~~~~~~~~~~~~~~~~~~~

A file system storage backend is also available for the HTTP cache middleware.

In order to use this storage backend, set:

* :setting:`HTTPCACHE_STORAGE` to ``scrapy.contrib.httpcache.FilesystemCacheStorage``

Each request/response pair is stored in a different directory containing
the following files:

 * ``request_body`` - the plain request body
 * ``request_headers`` - the request headers (in raw HTTP format)
 * ``response_body`` - the plain response body
 * ``response_headers`` - the request headers (in raw HTTP format)
 * ``meta`` - some metadata of this cache resource in Python ``repr()`` format
   (grep-friendly format)
 * ``pickled_meta`` - the same metadata in ``meta`` but pickled for more
   efficient deserialization

The directory name is made from the request fingerprint (see
``scrapy.utils.request.fingerprint``), and one level of subdirectories is
used to avoid creating too many files into the same directory (which is
inefficient in many file systems). An example directory could be::

   /path/to/cache/dir/example.com/72/72811f648e718090f041317756c03adb0ada46c7


HTTPCache middleware settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The :class:`HttpCacheMiddleware` can be configured through the following
settings:

.. setting:: HTTPCACHE_ENABLED

HTTPCACHE_ENABLED
^^^^^^^^^^^^^^^^^

.. versionadded:: 0.11

Default: ``False``

Whether the HTTP cache will be enabled.

.. versionchanged:: 0.11
   Before 0.11, :setting:`HTTPCACHE_DIR` was used to enable cache.

.. setting:: HTTPCACHE_EXPIRATION_SECS

HTTPCACHE_EXPIRATION_SECS
^^^^^^^^^^^^^^^^^^^^^^^^^

Default: ``0``

Expiration time for cached requests, in seconds.

Cached requests older than this time will be re-downloaded. If zero, cached
requests will never expire.

.. versionchanged:: 0.11
   Before 0.11, zero meant cached requests always expire.

.. setting:: HTTPCACHE_DIR

HTTPCACHE_DIR
^^^^^^^^^^^^^

Default: ``'httpcache'``

The directory to use for storing the (low-level) HTTP cache. If empty, the HTTP
cache will be disabled. If a relative path is given, is taken relative to the
project data dir. For more info see: :ref:`topics-project-structure`.

.. setting:: HTTPCACHE_IGNORE_HTTP_CODES

HTTPCACHE_IGNORE_HTTP_CODES
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. versionadded:: 0.10

Default: ``[]``

Don't cache response with these HTTP codes.

.. setting:: HTTPCACHE_IGNORE_MISSING

HTTPCACHE_IGNORE_MISSING
^^^^^^^^^^^^^^^^^^^^^^^^

Default: ``False``

If enabled, requests not found in the cache will be ignored instead of downloaded.

.. setting:: HTTPCACHE_IGNORE_SCHEMES

HTTPCACHE_IGNORE_SCHEMES
^^^^^^^^^^^^^^^^^^^^^^^^

.. versionadded:: 0.10

Default: ``['file']``

Don't cache responses with these URI schemes.

.. setting:: HTTPCACHE_STORAGE

HTTPCACHE_STORAGE
^^^^^^^^^^^^^^^^^

Default: ``'scrapy.contrib.httpcache.DbmCacheStorage'``

The class which implements the cache storage backend.

.. setting:: HTTPCACHE_DBM_MODULE

HTTPCACHE_DBM_MODULE
^^^^^^^^^^^^^^^^^^^^

.. versionadded:: 0.13

Default: ``'anydbm'``

The database module to use in the :ref:`DBM storage backend
<httpcache-storage-dbm>`. This setting is specific to the DBM backend.

.. setting:: HTTPCACHE_POLICY

HTTPCACHE_POLICY
^^^^^^^^^^^^^^^^

.. versionadded:: 0.18

Default: ``'scrapy.contrib.httpcache.DummyPolicy'``

The class which implements the cache policy.


HttpCompressionMiddleware
-------------------------

.. module:: scrapy.contrib.downloadermiddleware.httpcompression
   :synopsis: Http Compression Middleware

.. class:: HttpCompressionMiddleware

   This middleware allows compressed (gzip, deflate) traffic to be
   sent/received from web sites.

HttpCompressionMiddleware Settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. setting:: COMPRESSION_ENABLED

COMPRESSION_ENABLED
^^^^^^^^^^^^^^^^^^^

Default: ``True``

Whether the Compression middleware will be enabled.


ChunkedTransferMiddleware
-------------------------

.. module:: scrapy.contrib.downloadermiddleware.chunked
   :synopsis: Chunked Transfer Middleware

.. class:: ChunkedTransferMiddleware

   This middleware adds support for `chunked transfer encoding`_

HttpProxyMiddleware
-------------------

.. module:: scrapy.contrib.downloadermiddleware.httpproxy
   :synopsis: Http Proxy Middleware

.. versionadded:: 0.8

.. class:: HttpProxyMiddleware

   This middleware sets the HTTP proxy to use for requests, by setting the
   ``proxy`` meta value to :class:`~scrapy.http.Request` objects.

   Like the Python standard library modules `urllib`_ and `urllib2`_, it obeys
   the following environment variables:

   * ``http_proxy``
   * ``https_proxy``
   * ``no_proxy``

.. _urllib: http://docs.python.org/library/urllib.html
.. _urllib2: http://docs.python.org/library/urllib2.html

RedirectMiddleware
------------------

.. module:: scrapy.contrib.downloadermiddleware.redirect
   :synopsis: Redirection Middleware

.. class:: RedirectMiddleware

   This middleware handles redirection of requests based on response status.

.. reqmeta:: redirect_urls

The urls which the request goes through (while being redirected) can be found
in the ``redirect_urls`` :attr:`Request.meta <scrapy.http.Request.meta>` key.

The :class:`RedirectMiddleware` can be configured through the following
settings (see the settings documentation for more info):

* :setting:`REDIRECT_ENABLED`
* :setting:`REDIRECT_MAX_TIMES`

.. reqmeta:: dont_redirect

If :attr:`Request.meta <scrapy.http.Request.meta>` contains the
``dont_redirect`` key, the request will be ignored by this middleware.


RedirectMiddleware settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. setting:: REDIRECT_ENABLED

REDIRECT_ENABLED
^^^^^^^^^^^^^^^^

.. versionadded:: 0.13

Default: ``True``

Whether the Redirect middleware will be enabled.

.. setting:: REDIRECT_MAX_TIMES

REDIRECT_MAX_TIMES
^^^^^^^^^^^^^^^^^^

Default: ``20``

The maximum number of redirections that will be follow for a single request.

MetaRefreshMiddleware
---------------------

.. class:: MetaRefreshMiddleware

   This middleware handles redirection of requests based on meta-refresh html tag.

The :class:`MetaRefreshMiddleware` can be configured through the following
settings (see the settings documentation for more info):

* :setting:`METAREFRESH_ENABLED`
* :setting:`METAREFRESH_MAXDELAY`

This middleware obey :setting:`REDIRECT_MAX_TIMES` setting, :reqmeta:`dont_redirect`
and :reqmeta:`redirect_urls` request meta keys as described for :class:`RedirectMiddleware`


MetaRefreshMiddleware settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. setting:: METAREFRESH_ENABLED

METAREFRESH_ENABLED
^^^^^^^^^^^^^^^^^^^

.. versionadded:: 0.17

Default: ``True``

Whether the Meta Refresh middleware will be enabled.

.. setting:: REDIRECT_MAX_METAREFRESH_DELAY

REDIRECT_MAX_METAREFRESH_DELAY
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Default: ``100``

The maximum meta-refresh delay (in seconds) to follow the redirection.

RetryMiddleware
---------------

.. module:: scrapy.contrib.downloadermiddleware.retry
   :synopsis: Retry Middleware

.. class:: RetryMiddleware

   A middlware to retry failed requests that are potentially caused by
   temporary problems such as a connection timeout or HTTP 500 error.

Failed pages are collected on the scraping process and rescheduled at the
end, once the spider has finished crawling all regular (non failed) pages.
Once there are no more failed pages to retry, this middleware sends a signal
(retry_complete), so other extensions could connect to that signal.

The :class:`RetryMiddleware` can be configured through the following
settings (see the settings documentation for more info):

* :setting:`RETRY_ENABLED`
* :setting:`RETRY_TIMES`
* :setting:`RETRY_HTTP_CODES`

About HTTP errors to consider:

You may want to remove 400 from :setting:`RETRY_HTTP_CODES`, if you stick to the
HTTP protocol. It's included by default because it's a common code used
to indicate server overload, which would be something we want to retry.

.. reqmeta:: dont_retry

If :attr:`Request.meta <scrapy.http.Request.meta>` contains the ``dont_retry``
key, the request will be ignored by this middleware.

RetryMiddleware Settings
~~~~~~~~~~~~~~~~~~~~~~~~

.. setting:: RETRY_ENABLED

RETRY_ENABLED
^^^^^^^^^^^^^

.. versionadded:: 0.13

Default: ``True``

Whether the Retry middleware will be enabled.

.. setting:: RETRY_TIMES

RETRY_TIMES
^^^^^^^^^^^

Default: ``2``

Maximum number of times to retry, in addition to the first download.

.. setting:: RETRY_HTTP_CODES

RETRY_HTTP_CODES
^^^^^^^^^^^^^^^^

Default: ``[500, 502, 503, 504, 400, 408]``

Which HTTP response codes to retry. Other errors (DNS lookup issues,
connections lost, etc) are always retried.

.. _topics-dlmw-robots:

RobotsTxtMiddleware
-------------------

.. module:: scrapy.contrib.downloadermiddleware.robotstxt
   :synopsis: robots.txt middleware

.. class:: RobotsTxtMiddleware

    This middleware filters out requests forbidden by the robots.txt exclusion
    standard.

    To make sure Scrapy respects robots.txt make sure the middleware is enabled
    and the :setting:`ROBOTSTXT_OBEY` setting is enabled.

    .. warning:: Keep in mind that, if you crawl using multiple concurrent
       requests per domain, Scrapy could still  download some forbidden pages
       if they were requested before the robots.txt file was downloaded. This
       is a known limitation of the current robots.txt middleware and will
       be fixed in the future.

DownloaderStats
---------------

.. module:: scrapy.contrib.downloadermiddleware.stats
   :synopsis: Downloader Stats Middleware

.. class:: DownloaderStats

   Middleware that stores stats of all requests, responses and exceptions that
   pass through it.

   To use this middleware you must enable the :setting:`DOWNLOADER_STATS`
   setting.

UserAgentMiddleware
-------------------

.. module:: scrapy.contrib.downloadermiddleware.useragent
   :synopsis: User Agent Middleware

.. class:: UserAgentMiddleware

   Middleware that allows spiders to override the default user agent.

   In order for a spider to override the default user agent, its `user_agent`
   attribute must be set.


.. _DBM: http://en.wikipedia.org/wiki/Dbm
.. _anydbm: http://docs.python.org/library/anydbm.html
.. _chunked transfer encoding: http://en.wikipedia.org/wiki/Chunked_transfer_encoding
