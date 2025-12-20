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
      doesn't support non-default reactors and so the latter should be used
      with those.

-   :class:`scrapy.crawler.AsyncCrawlerRunner` and its subclass
    :class:`scrapy.crawler.AsyncCrawlerProcess` (coroutine-based) and
    :class:`scrapy.crawler.CrawlerRunner` and its subclass
    :class:`scrapy.crawler.CrawlerProcess` (Deferred-based): the former
    doesn't support non-default reactors and so the latter should be used
    with those.

The following user-supplied methods can return
:class:`~twisted.internet.defer.Deferred` objects (the methods that can also
return coroutines are listed in :ref:`coroutine-support`):

-   Custom download handlers (see :setting:`DOWNLOAD_HANDLERS`):

    - ``download_request()``

    - ``close()``

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

[UNCHANGED CONTENT CONTINUES BELOW]
