.. _topics-coroutines:

==========
Coroutines
==========

Scrapy :ref:`supports <coroutine-support>` the :ref:`coroutine syntax <async>`
(i.e. ``async def``).


.. _coroutine-support:

Supported callables
===================

The following callables may be defined as coroutines using ``async def``, and
hence use coroutine syntax (e.g. ``await``, ``async for``, ``async with``):

-   The :meth:`~scrapy.spiders.Spider.start` spider method, which *must* be
    defined as an :term:`asynchronous generator`.

    .. versionadded:: 2.13

-   :class:`~scrapy.Request` callbacks.

-   The :meth:`process_item` method of
    :ref:`item pipelines <topics-item-pipeline>`.

-   The
    :meth:`~scrapy.downloadermiddlewares.DownloaderMiddleware.process_request`,
    :meth:`~scrapy.downloadermiddlewares.DownloaderMiddleware.process_response`,
    and
    :meth:`~scrapy.downloadermiddlewares.DownloaderMiddleware.process_exception`
    methods of
    :ref:`downloader middlewares <topics-downloader-middleware-custom>`.

-   The
    :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_spider_output`
    method of :ref:`spider middlewares <topics-spider-middleware>`, which
    *must* be defined as an :term:`asynchronous generator` except in
    :ref:`universal spider middlewares <universal-spider-middleware>`.

-   The :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_start` method
    of :ref:`spider middlewares <custom-spider-middleware>`, which *must* be
    defined as an :term:`asynchronous generator`.

    .. versionadded:: 2.13

-   :ref:`Signal handlers that support deferreds <signal-deferred>`.

-   Methods of :ref:`download handlers <topics-download-handlers>`.

    .. versionadded:: 2.14


.. _coroutine-deferred-apis:

Using Deferred-based APIs
=========================

In addition to native coroutine APIs Scrapy has some APIs that return a
:class:`~twisted.internet.defer.Deferred` object or take a user-supplied
function that returns a :class:`~twisted.internet.defer.Deferred` object. These
APIs are also asynchronous but don't yet support native ``async def`` syntax.
In the future we plan to add support for the ``async def`` syntax to these APIs
or replace them with other APIs where changing the existing ones isn't
possible.

These APIs have a coroutine-based implementation and a Deferred-based one:

-   :class:`scrapy.crawler.Crawler`:

    - :meth:`~scrapy.crawler.Crawler.crawl_async` (coroutine-based) and
      :meth:`~scrapy.crawler.Crawler.crawl` (Deferred-based): the former
      may be inconvenient to use in Deferred-based code so both are available,
      this may change in a future Scrapy version.

-   :class:`scrapy.crawler.AsyncCrawlerRunner` and its subclass
    :class:`scrapy.crawler.AsyncCrawlerProcess` (coroutine-based) and
    :class:`scrapy.crawler.CrawlerRunner` and its subclass
    :class:`scrapy.crawler.CrawlerProcess` (Deferred-based): the former
    doesn't support non-default reactors and so the latter should be used
    with those.

The following user-supplied methods can return
:class:`~twisted.internet.defer.Deferred` objects (the methods that can also
return coroutines are listed in :ref:`coroutine-support`):

-   Custom downloader implementations (see :setting:`DOWNLOADER`):

    - ``fetch()``

-   Custom scheduler implementations (see :setting:`SCHEDULER`):

    - :meth:`~scrapy.core.scheduler.BaseScheduler.open`

    - :meth:`~scrapy.core.scheduler.BaseScheduler.close`

-   Custom dupefilters (see :setting:`DUPEFILTER_CLASS`):

    - ``open()``

    - ``close()``

-   Custom feed storages (see :setting:`FEED_STORAGES`):

    - ``store()``

-   Subclasses of :class:`scrapy.pipelines.media.MediaPipeline`:

    - ``media_to_download()``

    - ``item_completed()``

-   Custom storages used by subclasses of
    :class:`scrapy.pipelines.files.FilesPipeline`:

    - ``persist_file()``

    - ``stat_file()``

In most cases you can use these APIs in code that otherwise uses coroutines, by
wrapping a :class:`~twisted.internet.defer.Deferred` object into a
:class:`~asyncio.Future` object or vice versa. See :ref:`asyncio-await-dfd` for
more information about this.

For example: a custom scheduler needs to define an ``open()`` method that can
return a :class:`~twisted.internet.defer.Deferred` object. You can write a
method that works with Deferreds and returns one directly, or you can write a
coroutine and convert it into a function that returns a Deferred with
:func:`~scrapy.utils.defer.deferred_f_from_coro_f`.


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

        def process_item(self, item):
            adapter = ItemAdapter(item)
            dfd = db.get_some_data(adapter["id"])
            dfd.addCallback(self._update_item, item)
            return dfd

becomes:

.. code-block:: python

    from itemadapter import ItemAdapter


    class DbPipeline:
        async def process_item(self, item):
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

* requesting data from websites, databases and other services (in
  :meth:`~scrapy.spiders.Spider.start`, callbacks, pipelines and
  middlewares);
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


    class SingleRequestSpider(Spider):
        name = "single"
        start_urls = ["https://example.org/product"]

        async def parse(self, response, **kwargs):
            additional_request = Request("https://example.org/price")
            additional_response = await self.crawler.engine.download_async(
                additional_request
            )
            yield {
                "h1": response.css("h1").get(),
                "price": additional_response.css("#price").get(),
            }

You can also send multiple requests in parallel:

.. code-block:: python

    import asyncio

    from scrapy import Spider, Request


    class MultipleRequestsSpider(Spider):
        name = "multiple"
        start_urls = ["https://example.com/product"]

        async def parse(self, response, **kwargs):
            additional_requests = [
                Request("https://example.com/price"),
                Request("https://example.com/color"),
            ]
            tasks = []
            for r in additional_requests:
                task = self.crawler.engine.download_async(r)
                tasks.append(task)
            responses = await asyncio.gather(*tasks)
            yield {
                "h1": response.css("h1::text").get(),
                "price": responses[0][1].css(".price::text").get(),
                "price2": responses[1][1].css(".color::text").get(),
            }
