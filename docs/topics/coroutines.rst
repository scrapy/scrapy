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

    .. versionchanged:: VERSION
       Output of async callbacks is now processed asynchronously instead of collecting
       all of it first.

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

-   The :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_spider_output`
    method of :ref:`spider middlewares <custom-spider-middleware>`.

    .. versionadded:: VERSION
    .. note:: This method needs to be an async generator, not just a coroutine that
              returns an iterable.

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

    class MySpiderDeferred(Spider):
        # ...
        async def parse(self, response):
            additional_response = await treq.get('https://additional.url')
            additional_data = await treq.content(additional_response)
            # ... use response and additional_data to yield items and requests

    class MySpiderAsyncio(Spider):
        # ...
        async def parse(self, response):
            async with aiohttp.ClientSession() as session:
                async with session.get('https://additional.url') as additional_response:
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
* calling asynchronous Scrapy methods like ``ExecutionEngine.download`` (see
  :ref:`the screenshot pipeline example<ScreenshotPipeline>`).

.. _aio-libs: https://github.com/aio-libs

.. _async-spider-middlewares:

Asynchronous spider middlewares
===============================

.. versionadded:: VERSION
.. note:: This currently applies to
          :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_spider_output`.

Middleware methods discussed here can take and return async iterables. They can
return the same type of iterable or they can take a normal one and return an
async one. If such method needs to return an async iterable it must be an async
generator, not just a coroutine that returns an iterable.

.. autofunction:: scrapy.utils.asyncgen.as_async_generator

In the simplest form that supports both sync and async input it can be written
like this::

    from scrapy.utils.asyncgen import as_async_generator

    class ProcessSpiderOutputAsyncGenMiddleware:
        async def process_spider_output(self, response, result, spider):
            async for r in as_async_generator(result):
                # ... do something with r
                yield r

If the middleware input (the callback result for ``process_spider_output``) is
an async iterable, all middlewares that process it must support it. The
built-in ones do, but the ones in your project and 3rd-party ones will need to
be updated to support it, as the code that expects a normal iterable will break
on an async one. If these middlewares receive an async iterable, they must
return one as well. On the other hand, if they receive a normal iterable, they
shouldn't break and ideally should return a normal iterable too. There can be
several possible implementations of this.

The simplest one, always converting normal iterables to async ones, is provided
above. Because a result of a middleware method is passed to the same method of
the next middleware, it's only possible to mix middlewares with synchronous and
asynchronous implementations of the same method if all synchronous ones are
called first (which isn't always possible).

Another option is to make separate methods for normal and async iterables and
choose one at run time::

    from inspect import isasyncgen

    class ProcessSpiderOutputAsyncGenMiddleware:
        def _normal_process_spider_output(self, response, result, spider):
            # ... do something with normal result

        async def _async_process_spider_output(self, response, result, spider):
            # ... do the same with async result

        def process_spider_output(self, response, result, spider):
            if isasyncgen(result):
                return self._async_process_spider_output(self, response, result, spider)
            else:
                return self._normal_process_spider_output(self, response, result, spider)

If you are writing a middleware that you intend to publish or to use in many
projects, this is likely the best way to implement it. It may be possible to
extract common code from both methods to reduce code duplication, as in the
simplest case the only difference between them will be ``for`` vs ``async for``.
