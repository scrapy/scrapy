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

    If you are using any custom or third-party :ref:`spider middleware
    <topics-spider-middleware>`, see :ref:`sync-async-spider-middleware`.

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
    method of :ref:`spider middlewares <topics-spider-middleware>`.

    If defined as a coroutine, it must be an :term:`asynchronous generator`.
    The input ``result`` parameter is an :term:`asynchronous iterable`.

    See also :ref:`sync-async-spider-middleware` and
    :ref:`universal-spider-middleware`.

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

These APIs don't have a coroutine-based counterpart:

-   :class:`~scrapy.mail.MailSender`

    - :meth:`~scrapy.mail.MailSender.send`

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

For example:

-   The :meth:`MailSender.send() <scrapy.mail.MailSender.send>` method returns
    a :class:`~twisted.internet.defer.Deferred` object that fires when the
    email is sent. You can use this object directly in Deferred-based code or
    convert it into a :class:`~asyncio.Future` object with
    :func:`~scrapy.utils.defer.maybe_deferred_to_future`.
-   A custom scheduler needs to define an ``open()`` method that can return a
    :class:`~twisted.internet.defer.Deferred` object. You can write a method
    that works with Deferreds and returns one directly, or you can write a
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


.. _sync-async-spider-middleware:

Mixing synchronous and asynchronous spider middlewares
======================================================

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

.. _sync-async-spider-middleware-users:

For middleware users
--------------------

If you have asynchronous callbacks or use asynchronous-only spider middlewares
you should make sure the asynchronous-to-synchronous conversions
:ref:`described above <sync-async-spider-middleware>` don't happen. To do this,
make sure all spider middlewares you use support asynchronous spider output.
Even if you don't have asynchronous callbacks and don't use asynchronous-only
spider middlewares in your project, it's still a good idea to make sure all
middlewares you use support asynchronous spider output, so that it will be easy
to start using asynchronous callbacks in the future. Because of this, Scrapy
logs a warning when it detects a synchronous-only spider middleware.

If you want to update middlewares you wrote, see the :ref:`following section
<sync-async-spider-middleware-authors>`. If you have 3rd-party middlewares that
aren't yet updated by their authors, you can :ref:`subclass <tut-inheritance>`
them to make them :ref:`universal <universal-spider-middleware>` and use the
subclasses in your projects.

.. _sync-async-spider-middleware-authors:

For middleware authors
----------------------

If you have a spider middleware that defines a synchronous
``process_spider_output`` method, you should update it to support asynchronous
spider output for :ref:`better compatibility <sync-async-spider-middleware>`,
even if you don't yet use it with asynchronous callbacks, especially if you
publish this middleware for other people to use. You have two options for this:

1. Make the middleware asynchronous, by making the ``process_spider_output``
   method an :term:`asynchronous generator`.
2. Make the middleware universal, as described in the :ref:`next section
   <universal-spider-middleware>`.

If your middleware won't be used in projects with synchronous-only middlewares,
e.g. because it's an internal middleware and you know that all other
middlewares in your projects are already updated, it's safe to choose the first
option. Otherwise, it's better to choose the second option.

.. _universal-spider-middleware:

Universal spider middlewares
----------------------------

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
        def process_spider_output(self, response, result):
            for r in result:
                # ... do something with r
                yield r

        async def process_spider_output_async(self, response, result):
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

Since 2.13.0, Scrapy provides a base class,
:class:`~scrapy.spidermiddlewares.base.BaseSpiderMiddleware`, which implements
the ``process_spider_output()`` and ``process_spider_output_async()`` methods,
so instead of duplicating the processing code you can override the
``get_processed_request()`` and/or the ``get_processed_item()`` method.
