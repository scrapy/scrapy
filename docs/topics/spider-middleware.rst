.. _topics-spider-middleware:

=================
Spider Middleware
=================

The spider middleware is a framework of hooks into Scrapy's spider processing
mechanism where you can plug custom functionality to process the responses that
are sent to :ref:`topics-spiders` for processing and to process the requests
and items that are generated from spiders.

.. _topics-spider-middleware-setting:

Activating a spider middleware
==============================

To activate a spider middleware component, add it to the
:setting:`SPIDER_MIDDLEWARES` setting, which is a dict whose keys are the
middleware class path and their values are the middleware orders.

Here's an example::

    SPIDER_MIDDLEWARES = {
        'myproject.middlewares.CustomSpiderMiddleware': 543,
    }

The :setting:`SPIDER_MIDDLEWARES` setting is merged with the
:setting:`SPIDER_MIDDLEWARES_BASE` setting defined in Scrapy (and not meant to
be overridden) and then sorted by order to get the final sorted list of enabled
middlewares: the first middleware is the one closer to the engine and the last
is the one closer to the spider. In other words,
the :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_spider_input`
method of each middleware will be invoked in increasing
middleware order (100, 200, 300, ...), and the
:meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_spider_output` method
of each middleware will be invoked in decreasing order.

To decide which order to assign to your middleware see the
:setting:`SPIDER_MIDDLEWARES_BASE` setting and pick a value according to where
you want to insert the middleware. The order does matter because each
middleware performs a different action and your middleware could depend on some
previous (or subsequent) middleware being applied.

If you want to disable a builtin middleware (the ones defined in
:setting:`SPIDER_MIDDLEWARES_BASE`, and enabled by default) you must define it
in your project :setting:`SPIDER_MIDDLEWARES` setting and assign `None` as its
value.  For example, if you want to disable the off-site middleware::

    SPIDER_MIDDLEWARES = {
        'myproject.middlewares.CustomSpiderMiddleware': 543,
        'scrapy.spidermiddlewares.offsite.OffsiteMiddleware': None,
    }

Finally, keep in mind that some middlewares may need to be enabled through a
particular setting. See each middleware documentation for more info.

Writing your own spider middleware
==================================

Each middleware component is a Python class that defines one or more of the
following methods:

.. module:: scrapy.spidermiddlewares

.. class:: SpiderMiddleware

    .. method:: process_spider_input(response, spider)

        This method is called for each response that goes through the spider
        middleware and into the spider, for processing.

        :meth:`process_spider_input` should return ``None`` or raise an
        exception.

        If it returns ``None``, Scrapy will continue processing this response,
        executing all other middlewares until, finally, the response is handed
        to the spider for processing.

        If it raises an exception, Scrapy won't bother calling any other spider
        middleware :meth:`process_spider_input` and will call the request
        errback.  The output of the errback is chained back in the other
        direction for :meth:`process_spider_output` to process it, or
        :meth:`process_spider_exception` if it raised an exception.

        :param response: the response being processed
        :type response: :class:`~scrapy.http.Response` object

        :param spider: the spider for which this response is intended
        :type spider: :class:`~scrapy.spiders.Spider` object


    .. method:: process_spider_output(response, result, spider)

        This method is called with the results returned from the Spider, after
        it has processed the response.

        :meth:`process_spider_output` must return an iterable of
        :class:`~scrapy.http.Request`, dict or :class:`~scrapy.item.Item`
        objects.

        :param response: the response which generated this output from the
          spider
        :type response: :class:`~scrapy.http.Response` object

        :param result: the result returned by the spider
        :type result: an iterable of :class:`~scrapy.http.Request`, dict
          or :class:`~scrapy.item.Item` objects

        :param spider: the spider whose result is being processed
        :type spider: :class:`~scrapy.spiders.Spider` object


    .. method:: process_spider_exception(response, exception, spider)

        This method is called when a spider or :meth:`process_spider_input`
        method (from other spider middleware) raises an exception.

        :meth:`process_spider_exception` should return either ``None`` or an
        iterable of :class:`~scrapy.http.Response`, dict or
        :class:`~scrapy.item.Item` objects.

        If it returns ``None``, Scrapy will continue processing this exception,
        executing any other :meth:`process_spider_exception` in the following
        middleware components, until no middleware components are left and the
        exception reaches the engine (where it's logged and discarded).

        If it returns an iterable the :meth:`process_spider_output` pipeline
        kicks in, and no other :meth:`process_spider_exception` will be called.

        :param response: the response being processed when the exception was
          raised
        :type response: :class:`~scrapy.http.Response` object

        :param exception: the exception raised
        :type exception: `Exception`_ object

        :param spider: the spider which raised the exception
        :type spider: :class:`~scrapy.spiders.Spider` object

    .. method:: process_start_requests(start_requests, spider)

        .. versionadded:: 0.15

        This method is called with the start requests of the spider, and works
        similarly to the :meth:`process_spider_output` method, except that it
        doesn't have a response associated and must return only requests (not
        items).

        It receives an iterable (in the ``start_requests`` parameter) and must
        return another iterable of :class:`~scrapy.http.Request` objects.

        .. note:: When implementing this method in your spider middleware, you
           should always return an iterable (that follows the input one) and
           not consume all ``start_requests`` iterator because it can be very
           large (or even unbounded) and cause a memory overflow. The Scrapy
           engine is designed to pull start requests while it has capacity to
           process them, so the start requests iterator can be effectively
           endless where there is some other condition for stopping the spider
           (like a time limit or item/page count).

        :param start_requests: the start requests
        :type start_requests: an iterable of :class:`~scrapy.http.Request`

        :param spider: the spider to whom the start requests belong
        :type spider: :class:`~scrapy.spiders.Spider` object


.. _Exception: https://docs.python.org/2/library/exceptions.html#exceptions.Exception


.. _topics-spider-middleware-ref:

Built-in spider middleware reference
====================================

This page describes all spider middleware components that come with Scrapy. For
information on how to use them and how to write your own spider middleware, see
the :ref:`spider middleware usage guide <topics-spider-middleware>`.

For a list of the components enabled by default (and their orders) see the
:setting:`SPIDER_MIDDLEWARES_BASE` setting.

DepthMiddleware
---------------

.. module:: scrapy.spidermiddlewares.depth
   :synopsis: Depth Spider Middleware

.. class:: DepthMiddleware

   DepthMiddleware is a scrape middleware used for tracking the depth of each
   Request inside the site being scraped. It can be used to limit the maximum
   depth to scrape or things like that.

   The :class:`DepthMiddleware` can be configured through the following
   settings (see the settings documentation for more info):

      * :setting:`DEPTH_LIMIT` - The maximum depth that will be allowed to
        crawl for any site. If zero, no limit will be imposed.
      * :setting:`DEPTH_STATS` - Whether to collect depth stats.
      * :setting:`DEPTH_PRIORITY` - Whether to prioritize the requests based on
        their depth.

HttpErrorMiddleware
-------------------

.. module:: scrapy.spidermiddlewares.httperror
   :synopsis: HTTP Error Spider Middleware

.. class:: HttpErrorMiddleware

    Filter out unsuccessful (erroneous) HTTP responses so that spiders don't
    have to deal with them, which (most of the time) imposes an overhead,
    consumes more resources, and makes the spider logic more complex.

According to the `HTTP standard`_, successful responses are those whose
status codes are in the 200-300 range.

.. _HTTP standard: https://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html

If you still want to process response codes outside that range, you can
specify which response codes the spider is able to handle using the
``handle_httpstatus_list`` spider attribute or
:setting:`HTTPERROR_ALLOWED_CODES` setting.

For example, if you want your spider to handle 404 responses you can do
this::

    class MySpider(CrawlSpider):
        handle_httpstatus_list = [404]

.. reqmeta:: handle_httpstatus_list

.. reqmeta:: handle_httpstatus_all

The ``handle_httpstatus_list`` key of :attr:`Request.meta
<scrapy.http.Request.meta>` can also be used to specify which response codes to
allow on a per-request basis. You can also set the meta key ``handle_httpstatus_all``
to ``True`` if you want to allow any response code for a request.

Keep in mind, however, that it's usually a bad idea to handle non-200
responses, unless you really know what you're doing.

For more information see: `HTTP Status Code Definitions`_.

.. _HTTP Status Code Definitions: https://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html

HttpErrorMiddleware settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. setting:: HTTPERROR_ALLOWED_CODES

HTTPERROR_ALLOWED_CODES
^^^^^^^^^^^^^^^^^^^^^^^

Default: ``[]``

Pass all responses with non-200 status codes contained in this list.

.. setting:: HTTPERROR_ALLOW_ALL

HTTPERROR_ALLOW_ALL
^^^^^^^^^^^^^^^^^^^

Default: ``False``

Pass all responses, regardless of its status code.

OffsiteMiddleware
-----------------

.. module:: scrapy.spidermiddlewares.offsite
   :synopsis: Offsite Spider Middleware

.. class:: OffsiteMiddleware

   Filters out Requests for URLs outside the domains covered by the spider.

   This middleware filters out every request whose host names aren't in the
   spider's :attr:`~scrapy.spiders.Spider.allowed_domains` attribute.
   All subdomains of any domain in the list are also allowed.
   E.g. the rule ``www.example.org`` will also allow ``bob.www.example.org``
   but not ``www2.example.com`` nor ``example.com``.

   When your spider returns a request for a domain not belonging to those
   covered by the spider, this middleware will log a debug message similar to
   this one::

      DEBUG: Filtered offsite request to 'www.othersite.com': <GET http://www.othersite.com/some/page.html>

   To avoid filling the log with too much noise, it will only print one of
   these messages for each new domain filtered. So, for example, if another
   request for ``www.othersite.com`` is filtered, no log message will be
   printed. But if a request for ``someothersite.com`` is filtered, a message
   will be printed (but only for the first request filtered).

   If the spider doesn't define an
   :attr:`~scrapy.spiders.Spider.allowed_domains` attribute, or the
   attribute is empty, the offsite middleware will allow all requests.

   If the request has the :attr:`~scrapy.http.Request.dont_filter` attribute
   set, the offsite middleware will allow the request even if its domain is not
   listed in allowed domains.


RefererMiddleware
-----------------

.. module:: scrapy.spidermiddlewares.referer
   :synopsis: Referer Spider Middleware

.. class:: RefererMiddleware

   Populates Request ``Referer`` header, based on the URL of the Response which
   generated it.

RefererMiddleware settings
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. setting:: REFERER_ENABLED

REFERER_ENABLED
^^^^^^^^^^^^^^^

.. versionadded:: 0.15

Default: ``True``

Whether to enable referer middleware.

.. setting:: REFERRER_POLICY

REFERRER_POLICY
^^^^^^^^^^^^^^^

.. versionadded:: 1.4

Default: ``'scrapy.spidermiddlewares.referer.DefaultReferrerPolicy'``

.. reqmeta:: referrer_policy

`Referrer Policy`_ to apply when populating Request "Referer" header.

.. note::
    You can also set the Referrer Policy per request,
    using the special ``"referrer_policy"`` :ref:`Request.meta <topics-request-meta>` key,
    with the same acceptable values as for the ``REFERRER_POLICY`` setting.

Acceptable values for REFERRER_POLICY
*************************************

- either a path to a ``scrapy.spidermiddlewares.referer.ReferrerPolicy``
  subclass — a custom policy or one of the built-in ones (see classes below),
- or one of the standard W3C-defined string values,
- or the special ``"scrapy-default"``.

=======================================  ========================================================================
String value                             Class name (as a string)
=======================================  ========================================================================
``"scrapy-default"`` (default)           :class:`scrapy.spidermiddlewares.referer.DefaultReferrerPolicy`
`"no-referrer"`_                         :class:`scrapy.spidermiddlewares.referer.NoReferrerPolicy`
`"no-referrer-when-downgrade"`_          :class:`scrapy.spidermiddlewares.referer.NoReferrerWhenDowngradePolicy`
`"same-origin"`_                         :class:`scrapy.spidermiddlewares.referer.SameOriginPolicy`
`"origin"`_                              :class:`scrapy.spidermiddlewares.referer.OriginPolicy`
`"strict-origin"`_                       :class:`scrapy.spidermiddlewares.referer.StrictOriginPolicy`
`"origin-when-cross-origin"`_            :class:`scrapy.spidermiddlewares.referer.OriginWhenCrossOriginPolicy`
`"strict-origin-when-cross-origin"`_     :class:`scrapy.spidermiddlewares.referer.StrictOriginWhenCrossOriginPolicy`
`"unsafe-url"`_                          :class:`scrapy.spidermiddlewares.referer.UnsafeUrlPolicy`
=======================================  ========================================================================

.. autoclass:: DefaultReferrerPolicy
.. warning::
    Scrapy's default referrer policy — just like `"no-referrer-when-downgrade"`_,
    the W3C-recommended value for browsers — will send a non-empty
    "Referer" header from any ``http(s)://`` to any ``https://`` URL,
    even if the domain is different.

    `"same-origin"`_ may be a better choice if you want to remove referrer
    information for cross-domain requests.

.. autoclass:: NoReferrerPolicy

.. autoclass:: NoReferrerWhenDowngradePolicy
.. note::
    "no-referrer-when-downgrade" policy is the W3C-recommended default,
    and is used by major web browsers.

    However, it is NOT Scrapy's default referrer policy (see :class:`DefaultReferrerPolicy`).

.. autoclass:: SameOriginPolicy

.. autoclass:: OriginPolicy

.. autoclass:: StrictOriginPolicy

.. autoclass:: OriginWhenCrossOriginPolicy

.. autoclass:: StrictOriginWhenCrossOriginPolicy

.. autoclass:: UnsafeUrlPolicy
.. warning::
    "unsafe-url" policy is NOT recommended.

.. _Referrer Policy: https://www.w3.org/TR/referrer-policy
.. _"no-referrer": https://www.w3.org/TR/referrer-policy/#referrer-policy-no-referrer
.. _"no-referrer-when-downgrade": https://www.w3.org/TR/referrer-policy/#referrer-policy-no-referrer-when-downgrade
.. _"same-origin": https://www.w3.org/TR/referrer-policy/#referrer-policy-same-origin
.. _"origin": https://www.w3.org/TR/referrer-policy/#referrer-policy-origin
.. _"strict-origin": https://www.w3.org/TR/referrer-policy/#referrer-policy-strict-origin
.. _"origin-when-cross-origin": https://www.w3.org/TR/referrer-policy/#referrer-policy-origin-when-cross-origin
.. _"strict-origin-when-cross-origin": https://www.w3.org/TR/referrer-policy/#referrer-policy-strict-origin-when-cross-origin
.. _"unsafe-url": https://www.w3.org/TR/referrer-policy/#referrer-policy-unsafe-url


UrlLengthMiddleware
-------------------

.. module:: scrapy.spidermiddlewares.urllength
   :synopsis: URL Length Spider Middleware

.. class:: UrlLengthMiddleware

   Filters out requests with URLs longer than URLLENGTH_LIMIT

   The :class:`UrlLengthMiddleware` can be configured through the following
   settings (see the settings documentation for more info):

      * :setting:`URLLENGTH_LIMIT` - The maximum URL length to allow for crawled URLs.

