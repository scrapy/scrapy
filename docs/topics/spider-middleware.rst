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

.. interface:: SpiderMiddleware

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
        iterable of :class:`~scrapy.http.Request`, dict or
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

    .. method:: from_crawler(cls, crawler)
    
       If present, this classmethod is called to create a middleware instance
       from a :class:`~scrapy.crawler.Crawler`. It must return a new instance
       of the middleware. Crawler object provides access to all Scrapy core
       components like settings and signals; it is a way for middleware to
       access them and hook its functionality into Scrapy.
    
       :param crawler: crawler that uses this middleware
       :type crawler: :class:`~scrapy.crawler.Crawler` object


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

.. autoclass:: DepthMiddleware


HttpErrorMiddleware
-------------------

.. module:: scrapy.spidermiddlewares.httperror
   :synopsis: HTTP Error Spider Middleware

.. autoclass:: HttpErrorMiddleware


OffsiteMiddleware
-----------------

.. module:: scrapy.spidermiddlewares.offsite
   :synopsis: Offsite Spider Middleware

.. autoclass:: OffsiteMiddleware


RefererMiddleware
-----------------

.. module:: scrapy.spidermiddlewares.referer
   :synopsis: Referer Spider Middleware

.. autoclass:: RefererMiddleware

.. autoclass:: DefaultReferrerPolicy

.. autoclass:: NoReferrerPolicy

.. autoclass:: NoReferrerWhenDowngradePolicy

.. autoclass:: SameOriginPolicy

.. autoclass:: OriginPolicy

.. autoclass:: StrictOriginPolicy

.. autoclass:: OriginWhenCrossOriginPolicy

.. autoclass:: StrictOriginWhenCrossOriginPolicy

.. autoclass:: UnsafeUrlPolicy

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

.. autoclass:: UrlLengthMiddleware
