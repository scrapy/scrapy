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

    The following are known caveats of the current implementation that we aim
    to address in future versions of Scrapy:

    -   The callback output is not processed until the whole callback finishes.

        As a side effect, if the callback raises an exception, none of its
        output is processed.

    -   Because `asynchronous generators were introduced in Python 3.6`_, you
        can only use ``yield`` if you are using Python 3.6 or later.

        If you need to output multiple items or requests and you are using
        Python 3.5, return an iterable (e.g. a list) instead.

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
    :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_start_requests`
    method of :ref:`spider middlewares <custom-spider-middleware>`. See
    :ref:`async-start_requests` below for details.

-   :ref:`Signal handlers that support deferreds <signal-deferred>`.

-   The :meth:`~scrapy.spiders.Spider.start_requests` spider method.

.. _asynchronous generators were introduced in Python 3.6: https://www.python.org/dev/peps/pep-0525/

.. _async-start_requests:

Asynchronous start_requests and spider middlewares
==================================================

.. versionadded:: 2.2

The :meth:`~scrapy.spiders.Spider.start_requests` spider method can be an
asynchronous generator::

    async def start_requests():
        # ...
        yield scrapy.Request(...)
        # ...

In this case all spider middlewares used with this spider that have the
:meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_start_requests`
method must support this: if they receive an asynchronous iterable, they must
return one as well. On the other hand, if they receive a normal iterable, they
shouldn't break and ideally should return a normal iterable too. There can be
several possible implementations of this.

First, such universal :meth:`process_start_requests` can be an asynchronous
generator itself, and so it will always convert a normal iterable to an
asynchronous one. Because a result of a middleware method is passed to the same
method of the next middleware, it's only possible to mix middlewares with
synchronous and asynchronous :meth:`process_start_requests` if all synchronous
ones are called first.

.. autofunction:: scrapy.utils.asyncgen.as_async_generator

Here is an example of a universal middleware using this approach::

    from scrapy.utils.asyncgen import as_async_generator

    class ProcessStartRequestsAsyncGenMiddleware:
        async def process_start_requests(self, start_requests, spider):
            async for req in as_async_generator(start_requests):
                # ... do something with req
                yield req

If this method includes asynchronous code, that code will work even with
synchronous :meth:`~scrapy.spiders.Spider.start_requests`.

Another option is to make separate methods for normal and asynchronous
iterables and choose one at run time::

    from inspect import isasyncgen

    class ProcessStartRequestsAsyncGenMiddleware:
        def _normal_process_start_requests(self, start_requests, spider):
            # ... do something with normal start_requests

        async def _async_process_start_requests(self, start_requests, spider):
            # ... do something with async start_requests

        def process_start_requests(self, start_requests, spider):
            if isasyncgen(start_requests):
                return self._async_process_start_requests(start_requests, spider)
            else:
                return self._normal_process_start_requests(start_requests, spider)


Usage
=====

There are several use cases for coroutines in Scrapy. Code that would
return Deferreds when written for previous Scrapy versions, such as downloader
middlewares and signal handlers, can be rewritten to be shorter and cleaner::

    class DbPipeline:
        def _update_item(self, data, item):
            item['field'] = data
            return item

        def process_item(self, item, spider):
            dfd = db.get_some_data(item['id'])
            dfd.addCallback(self._update_item, item)
            return dfd

becomes::

    class DbPipeline:
        async def process_item(self, item, spider):
            item['field'] = await db.get_some_data(item['id'])
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
                    additional_data = await additional_response.text()
            # ... use response and additional_data to yield items and requests

.. note:: Many libraries that use coroutines, such as `aio-libs`_, require the
          :mod:`asyncio` loop and to use them you need to
          :doc:`enable asyncio support in Scrapy<asyncio>`.

Common use cases for asynchronous code include:

* requesting data from websites, databases and other services (in
  :meth:`~scrapy.spiders.Spider.start_requests`, callbacks, pipelines and middlewares);
* storing data in databases (in pipelines and middlewares);
* delaying the spider initialization until some external event (in the
  :signal:`spider_opened` handler);
* calling asynchronous Scrapy methods like ``ExecutionEngine.download`` (see
  :ref:`the screenshot pipeline example<ScreenshotPipeline>`).

.. _aio-libs: https://github.com/aio-libs
