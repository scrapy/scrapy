.. _topics-spider-middleware:

=================
Spider Middleware
=================

The spider middleware is a framework of hooks into Scrapy's spider processing
mechanism where you can plug custom functionality to process the requests that
are sent to :ref:`topics-spiders` for processing and to process the responses
and item that are generated from spiders. 

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
is the one closer to the spider.

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
        'scrapy.contrib.spidermiddleware.offsite.OffsiteMiddleware': None,
    }

Finally, keep in mind that some middlewares may need to be enabled through a
particular setting. See each middleware documentation for more info.

Writing your own spider middleware
==================================

Writing your own spider middleware is easy. Each middleware component is a
single Python class that defines one or more of the following methods:


.. method:: process_spider_input(response, spider)

``response`` is a :class:`~scrapy.http.Response` object
``spider`` is a :class:`~scrapy.spider.BaseSpider` object

This method is called for each request that goes through the spider middleware.

``process_spider_input()`` should return either ``None`` or an iterable of
:class:`~scrapy.http.Response` or :class:`~scrapy.http.ScrapedItem` objects.

If returns ``None``, Scrapy will continue processing this response, executing all
other middlewares until, finally, the response is handled to the spider for
processing.

If returns an iterable, Scrapy won't bother calling ANY other spider middleware
``process_spider_input()`` and will return the iterable back in the other direction
for the ``process_spider_exception()`` and ``process_spider_output()`` methods to hook it.

.. method:: process_spider_output(response, result, spider)

``response`` is a :class:`~scrapy.http.Response` object
``result`` is an iterable of :class:`~scrapy.http.Request` or :class:`~scrapy.item.ScrapedItem` objects
``spider`` is a :class:`~scrapy.item.BaseSpider` object

This method is called with the results that are returned from the Spider, after
it has processed the response.

``process_spider_output()`` must return an iterable of :class:`~scrapy.http.Request`
or :class:`~scrapy.item.ScrapedItem` objects.

.. method:: process_spider_exception(request, exception, spider)

``request`` is a :class:`~scrapy.http.Request` object.
``exception`` is an Exception object
``spider`` is a BaseSpider object

Scrapy calls ``process_spider_exception()`` when a spider or ``process_spider_input()``
(from a spider middleware) raises an exception.

``process_spider_exception()`` should return either ``None`` or an iterable of
:class:`~scrapy.http.Response` or :class:`~scrapy.item.ScrapedItem` objects.

If it returns ``None``, Scrapy will continue processing this exception,
executing any other ``process_spider_exception()`` in the middleware pipeline, until
no middleware is left and the default exception handling kicks in.

If it returns an iterable the ``process_spider_output()`` pipeline kicks in, and no
other ``process_spider_exception()`` will be called.

