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

-   :class:`~scrapy.http.Request` callbacks.

    .. note:: The callback output is not processed until the whole callback
        finishes.

        As a side effect, if the callback raises an exception, none of its
        output is processed.

        This is a known caveat of the current implementation that we aim to
        address in a future version of Scrapy.

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

Usage
=====

There are several use cases for coroutines in Scrapy. Code that would
return Deferreds when written for previous Scrapy versions, such as downloader
middlewares and signal handlers, can be rewritten to be shorter and cleaner::

    from itemadapter import ItemAdapter

    class DbPipeline:
        def _update_item(self, data, item):
            adapter = ItemAdapter(item)
            adapter['field'] = data
            return item

        def process_item(self, item, spider):
            adapter = ItemAdapter(item)
            dfd = db.get_some_data(adapter['id'])
            dfd.addCallback(self._update_item, item)
            return dfd

becomes::

    from itemadapter import ItemAdapter

    class DbPipeline:
        async def process_item(self, item, spider):
            adapter = ItemAdapter(item)
            adapter['field'] = await db.get_some_data(adapter['id'])
            return item

Coroutines may be used to call asynchronous code. This includes other
coroutines, functions that return Deferreds and functions that return
:term:`awaitable objects <awaitable>` such as :class:`~asyncio.Future`.
This means you can use many useful Python libraries providing such code::

    class MySpider(Spider):
        # ...
        async def parse_with_deferred(self, response):
            additional_response = await treq.get('https://additional.url')
            additional_data = await treq.content(additional_response)
            # ... use response and additional_data to yield items and requests

        async def parse_with_asyncio(self, response):
            async with aiohttp.ClientSession() as session:
                async with session.get('https://additional.url') as additional_response:
                    additional_data = await r.text()
            # ... use response and additional_data to yield items and requests

.. note:: Many libraries that use coroutines, such as `aio-libs`_, require the
          :mod:`asyncio` loop and to use them you need to
          :doc:`enable asyncio support in Scrapy<asyncio>`.

Common use cases for asynchronous code include:

* requesting data from websites, databases and other services (in callbacks,
  pipelines and middlewares);
* storing data in databases (in pipelines and middlewares);
* delaying the spider initialization until some external event (in the
  :signal:`spider_opened` handler);
* calling asynchronous Scrapy methods like ``ExecutionEngine.download`` (see
  :ref:`the screenshot pipeline example<ScreenshotPipeline>`).

.. _aio-libs: https://github.com/aio-libs
