.. _topics-spider-middleware:

=================
Spider Middleware
=================

The spider middleware is a framework of hooks into Scrapy's spider processing
mechanism where you can plug custom functionality to process the requests that
are sent to :ref:`topics-spiders` for processing and to process the responses
and item that are generated from spiders. 

Activating a spider middleware
==============================

To activate a middleware component, add it to the :setting:`SPIDER_MIDDLEWARES`
list in your Scrapy settings.  In :setting:`SPIDER_MIDDLEWARES`, each
middleware component is represented by a string: the full Python path to the
middleware's class name. For example::

    SPIDER_MIDDLEWARES = [
        'scrapy.contrib.spidermiddleware.limit.RequestLimitMiddleware',
        'scrapy.contrib.spidermiddleware.restrict.RestrictMiddleware',
        'scrapy.contrib.spidermiddleware.offsite.OffsiteMiddleware',
        'scrapy.contrib.spidermiddleware.referer.RefererMiddleware',
        'scrapy.contrib.spidermiddleware.urllength.UrlLengthMiddleware',
        'scrapy.contrib.spidermiddleware.depth.DepthMiddleware',
    ]

The first (top) middleware is the one closer to the engine, the last (bottom)
middleware is the one closer to the spider.

Writing your own spider middleware
======================================

Writing your own spider middleware is easy. Each middleware component is a
single Python class that defines one or more of the following methods:


.. method:: process_scrape(response, spider)

``response`` is a :class:`~scrapy.http.Response` object
``spider`` is a :class:`~scrapy.spider.BaseSpider` object

This method is called for each request that goes through the spider middleware.

``process_scrape()`` should return either ``None`` or an iterable of
:class:`~scrapy.http.Response` or :class:`~scrapy.http.ScrapedItem` objects.

If returns ``None``, Scrapy will continue processing this response, executing all
other middlewares until, finally, the response is handled to the spider for
processing.

If returns an iterable, Scrapy won't bother calling ANY other spider middleware
``process_scrape()`` and will return the iterable back in the other direction
for the ``process_exception()`` and ``process_result`` methods to hook it.

.. method:: process_result(response, result, spider)

``response`` is a :class:`~scrapy.http.Response` object
``result`` is an iterable of :class:`~scrapy.http.Request` or :class:`~scrapy.item.ScrapedItem` objects
``spider`` is a :class:`~scrapy.item.BaseSpider` object

This method is called with the results that are returned from the Spider, after
it has processed the response.

``process_result()`` must return an iterable of :class:`~scrapy.http.Request`
or :class:`~scrapy.item.ScrapedItem` objects.

.. method:: process_exception(request, exception, spider)

``request`` is a :class:`~scrapy.http.Request` object.
``exception`` is an Exception object
``spider`` is a BaseSpider object

Scrapy calls ``process_exception()`` when a spider or ``process_scrape()``
(from a spider middleware) raises an exception.

process_exception() should return either ``None`` or an iterable of
:class:`~scrapy.http.Response` or :class:`~scrapy.item.ScrapedItem` objects.

If it returns ``None``, Scrapy will continue processing this exception,
executing any other ``process_exception()`` in the middleware pipeline, until
no middleware is left and the default exception handling kicks in.

If it returns an iterable the ``process_result()`` pipeline kicks in, and no
other ``process_exception()`` will be called.

