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
    method of :ref:`spider middlewares <custom-spider-middleware>`. See
    :ref:`async-spider-middlewares`.

    .. versionadded:: VERSION

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
* calling asynchronous Scrapy methods like :meth:`ExecutionEngine.download`
  (see :ref:`the screenshot pipeline example<ScreenshotPipeline>`).

.. _aio-libs: https://github.com/aio-libs

.. _async-spider-middlewares:

Asynchronous spider middlewares
===============================

.. versionadded:: VERSION
.. note:: This currently applies to
          :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_spider_output`.
          In the future it will also apply to
          :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_start_requests`.

Middleware methods discussed here can take and return async iterables. They can
return the same type of iterable or they can take a normal one and return an
async one. If such method needs to return an async iterable it must be an async
generator, not just a coroutine that returns an iterable.

As the result of a middleware method is passed to the same method of the next
middleware, it needs to be adapted if the second method expects a different
type. Scrapy will do this transparently:

* A normal iterable is wrapped into an async one which shouldn't cause any side
  effects.
* An async iterable is downgraded to a normal one by waiting until all results
  are available and wrapping them in a normal iterable. This is problematic
  because it pauses the normal middleware processing for this iterable and
  because all results can be skipped if exceptions are raised during
  processing. This case emits a warning and will be deprecated and then removed
  in a later Scrapy version.
* Async iterables returned from
  :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_spider_exception`
  won't be downgraded, an exception will be raised if that is needed.

As downgrading is undesirable, here is the proposed way to avoid it. If all
middlewares, including 3rd-party ones, support async iterables as input, no
downgrading will happen. But removing normal iterable support (making the
method a coroutine) from a middleware published as a separate project or used
internally in projects for older Scrapy versions breaks backwards
compatibility. So, as an interim measure (it will be deprecated and then
removed in a later Scrapy version), a middleware can provide both sync and
async methods in the following form::

    class UniversalSpiderMiddleware:
        def process_spider_output(self, response, result, spider):
            for r in result:
                # ... do something with r
                yield r

        async def process_spider_output_async(self, response, result, spider):
            async for r in result:
                # ... do something with r
                yield r

In this case normal and async iterables will be passed to the respective
methods without any wrapping or downgrading, and in older versions of Scrapy
the coroutine method will just be ignored. When the backwards compatibility is
no longer needed the non-coroutine method can be dropped and the coroutine one
renamed to the normal name. It may be possible to extract common code from both
methods to reduce code duplication, as in the simplest case the only difference
between them will be ``for`` vs ``async for``.

So, to recap:

* If you don't intend to use async callbacks or middlewares containing async
  code in your project, nothing should change for you yet. At some point in the
  future some of the 3rd-party middlewares you use may drop backwards
  compatibility, which shouldn't lead to immediate problems but may be a sign
  to start converting your code to ``async def`` too.
* If you maintain a middleware that can be used with projects you can't control
  (e.g. one you published for other people to use, or one that needs to support
  some old project that can't be modernized), we recommend adding a
  ``process_spider_output_async`` method so that the amount of unnecessary
  iterable conversions is reduced but no compatibility is broken.
* If you use async callbacks, try to make sure all middlewares support them.
  Note that you can modernize 3rd-party middlewares by subclassing them.
* If you want to write and publish a middleware that requires async code, you
  should write in the docs that the minimum support Scrapy version is VERSION
  (maybe even check this at the run time, using :attr:`scrapy.__version__`).
