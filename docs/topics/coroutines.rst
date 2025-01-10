.. _topics-coroutines:

==========
Coroutines
==========

.. versionadded:: 2.0

Scrapy has :ref:`partial support <coroutine-support>` for the
:ref:`coroutine syntax <async>`.

.. _coroutine-support:

Supported callables
===================

The following callables may be defined as coroutines using ``async def``, and
hence use coroutine syntax (e.g. ``await``, ``async for``, ``async with``):

-   :class:`~scrapy.Request` callbacks.

    If you are using any custom or third-party :ref:`spider middleware
    <topics-spider-middleware>`, see :ref:`sync-async-spider-middleware`.

    .. versionchanged:: 2.7
       Output of async callbacks is now processed asynchronously instead of
       collecting all of it first.

-   The :meth:`process_item` method of
    :ref:`item pipelines <topics-item-pipeline>`.

-   The
    :meth:`~scrapy.downloadermiddlewares.DownloaderMiddleware.process_request`,
    :meth:`~scrapy.downloadermiddlewares.DownloaderMiddleware.process_response`,
    and
    :meth:`~scrapy.downloadermiddlewares.DownloaderMiddleware.process_exception`
    methods of
    :ref:`downloader middlewares <topics-downloader-middleware-custom>`.

-   :ref:`Signal handlers that support deferreds <signal-deferred>`.

-   The
    :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_spider_output`
    method of :ref:`spider middlewares <topics-spider-middleware>`.

    It must be defined as an :term:`asynchronous generator`. The input
    ``result`` parameter is an :term:`asynchronous iterable`.

    See also :ref:`sync-async-spider-middleware` and
    :ref:`universal-spider-middleware`.

    .. versionadded:: 2.7

General usage
=============

There are several use cases for coroutines in Scrapy.

Code that would return Deferreds when written for previous Scrapy versions,
such as downloader middlewares and signal handlers, can be rewritten to be
shorter and cleaner:

.. code-block:: python

    from itemadapter import ItemAdapter


    class DbPipeline:
        def _update_item(self, data, item):
            adapter = ItemAdapter(item)
            adapter["field"] = data
            return item

        def process_item(self, item, spider):
            adapter = ItemAdapter(item)
            dfd = db.get_some_data(adapter["id"])
            dfd.addCallback(self._update_item, item)
            return dfd

becomes:

.. code-block:: python

    from itemadapter import ItemAdapter


    class DbPipeline:
        async def process_item(self, item, spider):
            adapter = ItemAdapter(item)
            adapter["field"] = await db.get_some_data(adapter["id"])
            return item

Coroutines may be used to call asynchronous code. This includes other
coroutines, functions that return Deferreds and functions that return
:term:`awaitable objects <awaitable>` such as :class:`~asyncio.Future`.
This means you can use many useful Python libraries providing such code:

.. skip: next
.. code-block:: python

    class MySpiderDeferred(Spider):
        # ...
        async def parse(self, response):
            additional_response = await treq.get("https://additional.url")
            additional_data = await treq.content(additional_response)
            # ... use response and additional_data to yield items and requests


    class MySpiderAsyncio(Spider):
        # ...
        async def parse(self, response):
            async with aiohttp.ClientSession() as session:
                async with session.get("https://additional.url") as additional_response:
                    additional_data = await additional_response.text()
            # ... use response and additional_data to yield items and requests

.. note:: Many libraries that use coroutines, such as `aio-libs`_, require the
          :mod:`asyncio` loop and to use them you need to
          :doc:`enable asyncio support in Scrapy<asyncio>`.

.. note:: If you want to ``await`` on Deferreds while using the asyncio reactor,
          you need to :ref:`wrap them<asyncio-await-dfd>`.

Common use cases for asynchronous code include:

* requesting data from websites, databases and other services (in callbacks,
  pipelines and middlewares);
* storing data in databases (in pipelines and middlewares);
* delaying the spider initialization until some external event (in the
  :signal:`spider_opened` handler);
* calling asynchronous Scrapy methods like :meth:`ExecutionEngine.download`
  (see :ref:`the screenshot pipeline example<ScreenshotPipeline>`).

.. _aio-libs: https://github.com/aio-libs


.. _inline-requests:

Inline requests
===============

The spider below shows how to send a request and await its response all from
within a spider callback:

.. code-block:: python

    from scrapy import Spider, Request
    from scrapy.utils.defer import maybe_deferred_to_future


    class SingleRequestSpider(Spider):
        name = "single"
        start_urls = ["https://example.org/product"]

        async def parse(self, response, **kwargs):
            additional_request = Request("https://example.org/price")
            deferred = self.crawler.engine.download(additional_request)
            additional_response = await maybe_deferred_to_future(deferred)
            yield {
                "h1": response.css("h1").get(),
                "price": additional_response.css("#price").get(),
            }

You can also send multiple requests in parallel:

.. code-block:: python

    from scrapy import Spider, Request
    from scrapy.utils.defer import maybe_deferred_to_future
    from twisted.internet.defer import DeferredList


    class MultipleRequestsSpider(Spider):
        name = "multiple"
        start_urls = ["https://example.com/product"]

        async def parse(self, response, **kwargs):
            additional_requests = [
                Request("https://example.com/price"),
                Request("https://example.com/color"),
            ]
            deferreds = []
            for r in additional_requests:
                deferred = self.crawler.engine.download(r)
                deferreds.append(deferred)
            responses = await maybe_deferred_to_future(DeferredList(deferreds))
            yield {
                "h1": response.css("h1::text").get(),
                "price": responses[0][1].css(".price::text").get(),
                "price2": responses[1][1].css(".color::text").get(),
            }


.. _sync-async-spider-middleware:

Mixing synchronous and asynchronous spider middlewares
======================================================

.. versionadded:: 2.7

The output of a :class:`~scrapy.Request` callback is passed as the ``result``
parameter to the
:meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_spider_output` method
of the first :ref:`spider middleware <topics-spider-middleware>` from the
:ref:`list of active spider middlewares <topics-spider-middleware-setting>`.
Then the output of that ``process_spider_output`` method is passed to the
``process_spider_output`` method of the next spider middleware, and so on for
every active spider middleware.

Scrapy supports mixing :ref:`coroutine methods <async>` and synchronous methods
in this chain of calls.

However, if any of the ``process_spider_output`` methods is defined as a
synchronous method, and the previous ``Request`` callback or
``process_spider_output`` method is a coroutine, there are some drawbacks to
the asynchronous-to-synchronous conversion that Scrapy does so that the
synchronous ``process_spider_output`` method gets a synchronous iterable as its
``result`` parameter:

-   The whole output of the previous ``Request`` callback or
    ``process_spider_output`` method is awaited at this point.

-   If an exception raises while awaiting the output of the previous
    ``Request`` callback or ``process_spider_output`` method, none of that
    output will be processed.

    This contrasts with the regular behavior, where all items yielded before
    an exception raises are processed.

Asynchronous-to-synchronous conversions are supported for backward
compatibility, but they are deprecated and will stop working in a future
version of Scrapy.

To avoid asynchronous-to-synchronous conversions, when defining ``Request``
callbacks as coroutine methods or when using spider middlewares whose
``process_spider_output`` method is an :term:`asynchronous generator`, all
active spider middlewares must either have their ``process_spider_output``
method defined as an asynchronous generator or :ref:`define a
process_spider_output_async method <universal-spider-middleware>`.

.. note:: When using third-party spider middlewares that only define a
          synchronous ``process_spider_output`` method, consider
          :ref:`making them universal <universal-spider-middleware>` through
          :ref:`subclassing <tut-inheritance>`.


.. _universal-spider-middleware:

Universal spider middlewares
============================

.. versionadded:: 2.7

To allow writing a spider middleware that supports asynchronous execution of
its ``process_spider_output`` method in Scrapy 2.7 and later (avoiding
:ref:`asynchronous-to-synchronous conversions <sync-async-spider-middleware>`)
while maintaining support for older Scrapy versions, you may define
``process_spider_output`` as a synchronous method and define an
:term:`asynchronous generator` version of that method with an alternative name:
``process_spider_output_async``.

For example:

.. code-block:: python

    class UniversalSpiderMiddleware:
        def process_spider_output(self, response, result, spider):
            for r in result:
                # ... do something with r
                yield r

        async def process_spider_output_async(self, response, result, spider):
            async for r in result:
                # ... do something with r
                yield r

.. note:: This is an interim measure to allow, for a time, to write code that
          works in Scrapy 2.7 and later without requiring
          asynchronous-to-synchronous conversions, and works in earlier Scrapy
          versions as well.

          In some future version of Scrapy, however, this feature will be
          deprecated and, eventually, in a later version of Scrapy, this
          feature will be removed, and all spider middlewares will be expected
          to define their ``process_spider_output`` method as an asynchronous
          generator.
