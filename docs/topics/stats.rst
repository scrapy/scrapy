.. _topics-stats:

================
Stats Collection
================

Scrapy provides a convenient facility for collecting stats in the form of
key/values, where values are often counters. The facility is called the Stats
Collector, and can be accessed through the :attr:`~scrapy.crawler.Crawler.stats`
attribute of the :ref:`topics-api-crawler`, as illustrated by the examples in
the :ref:`topics-stats-usecases` section below.

The Stats Collector API is always available, so you can always use it (to
increment or set new stat keys), regardless
of whether the stats collection is enabled or not. If it's disabled, the API
will still work but it won't collect anything. This is aimed at simplifying the
stats collector usage: you should spend no more than one line of code for
collecting stats in your spider, Scrapy extension, or whatever code you're
using the Stats Collector from.

Another feature of the Stats Collector is that it's very efficient (when
enabled) and extremely efficient (almost unnoticeable) when disabled.

See :ref:`topics-stats-reference` below for the stats that Scrapy sets.

.. _topics-stats-usecases:

Common Stats Collector uses
===========================

Access the stats collector through the :attr:`~scrapy.crawler.Crawler.stats`
attribute. Here is an example of an extension that access stats:

.. code-block:: python

    class ExtensionThatAccessStats:
        def __init__(self, stats):
            self.stats = stats

        @classmethod
        def from_crawler(cls, crawler):
            return cls(crawler.stats)

.. skip: start

Set stat value:

.. code-block:: python

    stats.set_value("hostname", socket.gethostname())

Increment stat value:

.. code-block:: python

    stats.inc_value("custom_count")

Set stat value only if greater than previous:

.. code-block:: python

    stats.max_value("max_items_scraped", value)

Set stat value only if lower than previous:

.. code-block:: python

    stats.min_value("min_free_memory_percent", value)

Get stat value:

.. code-block:: pycon

    >>> stats.get_value("custom_count")
    1

Get all stats:

.. code-block:: pycon

    >>> stats.get_stats()
    {'custom_count': 1, 'start_time': datetime.datetime(2009, 7, 14, 21, 47, 28, 977139)}

.. skip: end

Available Stats Collectors
==========================

.. currentmodule:: scrapy.statscollectors

Besides the basic :class:`StatsCollector` there are other Stats Collectors
available in Scrapy which extend the basic Stats Collector. You can select
which Stats Collector to use through the :setting:`STATS_CLASS` setting. The
default Stats Collector used is the :class:`MemoryStatsCollector`.

StatsCollector
--------------

.. autoclass:: StatsCollector
   :members:

MemoryStatsCollector
--------------------

.. autoclass:: MemoryStatsCollector
   :members:

DummyStatsCollector
-------------------

.. autoclass:: DummyStatsCollector

.. _topics-stats-reference:

Built-in stats reference
========================

Scrapy sets the following :ref:`stats <topics-stats>`. Components other than
those built into Scrapy may set additional stats; see their documentation.

Stat keys that contain a ``{placeholder}`` below stand for a family of stats,
one per actual value of the placeholder.

.. note:: Most stats are set by a specific :ref:`component
    <topics-components>`, and are only present if that component is enabled and
    its code path is reached. A stat that is missing from
    :meth:`~scrapy.statscollectors.StatsCollector.get_stats` output is
    equivalent to a counter of 0.

.. stat:: depth/request_ignored_count

``depth/request_ignored_count``
    Number of requests dropped for exceeding :setting:`DEPTH_LIMIT`.

    Set by :class:`~scrapy.spidermiddlewares.depth.DepthMiddleware`.

.. stat:: downloader/exception_count

``downloader/exception_count``
    Number of exceptions raised while downloading requests.

    Set by :class:`~scrapy.downloadermiddlewares.stats.DownloaderStats`.

.. stat:: downloader/exception_type_count/{exception_type}

``downloader/exception_type_count/{exception_type}``
    Number of exceptions raised while downloading requests, per exception type,
    where ``{exception_type}`` is the import path of the exception class, e.g.
    ``twisted.internet.error.DNSLookupError``.

    Set by :class:`~scrapy.downloadermiddlewares.stats.DownloaderStats`.

.. stat:: downloader/request_bytes

``downloader/request_bytes``
    Total size, in bytes, of the requests sent, counting the request line, the
    headers and the body. As with :stat:`downloader/request_count`, requests
    served from the cache are also counted.

    It is an approximation, reconstructed from each :class:`~scrapy.Request`
    object instead of measured on the wire, so it does not account for the
    actual bytes that the :ref:`download handler
    <topics-download-handlers>` sends, e.g. transport-level overhead.

    Set by :class:`~scrapy.downloadermiddlewares.stats.DownloaderStats`.

.. stat:: downloader/request_count

``downloader/request_count``
    Number of requests sent.

    Requests that :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`
    serves from the cache are also counted, even though they are never sent,
    because it handles requests after
    :class:`~scrapy.downloadermiddlewares.stats.DownloaderStats`.

    Set by :class:`~scrapy.downloadermiddlewares.stats.DownloaderStats`.

.. stat:: downloader/request_method_count/{method}

``downloader/request_method_count/{method}``
    Number of requests sent, per HTTP method, e.g. ``GET`` or ``POST``. As with
    :stat:`downloader/request_count`, requests served from the cache are also
    counted.

    Set by :class:`~scrapy.downloadermiddlewares.stats.DownloaderStats`.

.. stat:: downloader/response_bytes

``downloader/response_bytes``
    Total size, in bytes, of the responses received, counting the status line,
    the headers and the body. It covers the same responses as
    :stat:`downloader/response_count`.

    The body is counted as received, i.e. still compressed for responses that
    used ``Content-Encoding``, because
    :class:`~scrapy.downloadermiddlewares.stats.DownloaderStats` handles
    responses before
    :class:`~scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware`
    decompresses them. See :stat:`httpcompression/response_bytes` for
    decompressed sizes.

    Set by :class:`~scrapy.downloadermiddlewares.stats.DownloaderStats`.

.. stat:: downloader/response_count

``downloader/response_count``
    Number of responses received.

    It counts responses that :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`
    serves from the cache, even though they do not come from the network, and
    responses that a downloader middleware consumes before they reach your
    spider, e.g. redirect responses that :class:`~scrapy.downloadermiddlewares.redirect.RedirectMiddleware`
    turns into new requests. Compare with :stat:`response_received_count`.

    Set by :class:`~scrapy.downloadermiddlewares.stats.DownloaderStats`.

.. stat:: downloader/response_status_count/{status_code}

``downloader/response_status_count/{status_code}``
    Number of responses received, per HTTP status code, e.g. ``200`` or
    ``404``. It covers the same responses as :stat:`downloader/response_count`.

    Set by :class:`~scrapy.downloadermiddlewares.stats.DownloaderStats`.

.. stat:: dupefilter/filtered

``dupefilter/filtered``
    Number of requests dropped as duplicates.

    Set by :class:`~scrapy.dupefilters.RFPDupeFilter`.

.. stat:: elapsed_time_seconds

``elapsed_time_seconds``
    Time, as a :class:`float`, in seconds, between the :signal:`spider_opened`
    and the :signal:`spider_closed` signals.

    Set by :class:`~scrapy.extensions.corestats.CoreStats`.

.. stat:: feedexport/failed_count/{storage}

``feedexport/failed_count/{storage}``
    Number of :ref:`feeds <topics-feed-exports>` that could not be stored, per
    :ref:`storage backend <topics-feed-storage-backends>`, where ``{storage}``
    is the class name of the storage backend, e.g. ``FileFeedStorage``.

.. stat:: feedexport/success_count/{storage}

``feedexport/success_count/{storage}``
    Number of :ref:`feeds <topics-feed-exports>` stored successfully, per
    :ref:`storage backend <topics-feed-storage-backends>`, where ``{storage}``
    is the class name of the storage backend, e.g. ``FileFeedStorage``.

.. stat:: file_count

``file_count``
    Number of files handled by the :ref:`media pipelines
    <topics-media-pipeline>`.

.. stat:: file_status_count/{status}

``file_status_count/{status}``
    Number of files handled by the :ref:`media pipelines
    <topics-media-pipeline>`, per status, where ``{status}`` is one of:

    -   ``downloaded``: the file was downloaded.

    -   ``cached``: the file came from the
        :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`
        cache.

    -   ``uptodate``: the file was already in the storage backend and had not
        :ref:`expired <file-expiration>`, so it was not downloaded again.

.. stat:: finish_reason

``finish_reason``
    String indicating why the crawl finished. It matches the *reason* argument
    of the :signal:`spider_closed` signal.

    Scrapy uses the following reasons:

    -   ``cancelled``: the spider was closed without a more specific reason,
        e.g. because :exc:`~scrapy.exceptions.CloseSpider` was raised without
        one.

    -   ``closespider_errorcount``: see :setting:`CLOSESPIDER_ERRORCOUNT`.

    -   ``closespider_itemcount``: see :setting:`CLOSESPIDER_ITEMCOUNT`.

    -   ``closespider_pagecount``: see :setting:`CLOSESPIDER_PAGECOUNT`.

    -   ``closespider_pagecount_no_item``: see
        :setting:`CLOSESPIDER_PAGECOUNT_NO_ITEM`.

    -   ``closespider_timeout``: see :setting:`CLOSESPIDER_TIMEOUT`.

    -   ``closespider_timeout_no_item``: see
        :setting:`CLOSESPIDER_TIMEOUT_NO_ITEM`.

    -   ``finished``: the spider became idle with no pending requests, i.e. it
        finished normally.

    -   ``memusage_exceeded``: see :setting:`MEMUSAGE_LIMIT_MB`.

    -   ``robotstxt_denied``: no :ref:`start request <start-requests>` could be
        crawled, and robots.txt rules denied at least one of them, see
        :class:`~scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware`.

    -   ``shutdown``: the crawl was interrupted, e.g. by a system signal such
        as ``SIGINT`` (:kbd:`Ctrl-C`).

    -   ``start_error``: :meth:`~scrapy.Spider.start` raised an exception, so
        some :ref:`start requests <start-requests>` may never have been sent,
        see :ref:`start-error`.

    Third-party components and your own code may use any other reason, e.g. by
    raising :exc:`~scrapy.exceptions.CloseSpider` with it.

    Set by :class:`~scrapy.extensions.corestats.CoreStats`.

.. stat:: finish_time

``finish_time``
    Timezone-aware :class:`~datetime.datetime` object, in UTC, indicating when
    the :signal:`spider_closed` signal was sent.

    Set by :class:`~scrapy.extensions.corestats.CoreStats`.

.. stat:: httpcache/errorrecovery

``httpcache/errorrecovery``
    Number of times that a stale cached response was used because downloading a
    fresh response raised an exception.

    Set by :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`.

.. stat:: httpcache/firsthand

``httpcache/firsthand``
    Number of responses that were downloaded without a matching cache entry to
    validate against, i.e. responses for requests counted in
    :stat:`httpcache/miss`.

    It is lower than :stat:`httpcache/miss` when some of those requests yield
    no response, either because they are dropped (see
    :stat:`httpcache/ignore`) or because their download fails.

    Set by :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`.

.. stat:: httpcache/hit

``httpcache/hit``
    Number of requests served from the cache.

    Set by :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`.

.. stat:: httpcache/ignore

``httpcache/ignore``
    Number of requests dropped because they were not in the cache and
    :setting:`HTTPCACHE_IGNORE_MISSING` is ``True``.

    Set by :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`.

.. stat:: httpcache/invalidate

``httpcache/invalidate``
    Number of times that a cached response failed validation and was replaced
    with a freshly downloaded response.

    Set by :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`.

.. stat:: httpcache/miss

``httpcache/miss``
    Number of requests for which no cache entry could be read, either because
    there was none or because reading it failed, in which case the request is
    also counted in :stat:`httpcache/retrieve_error`. Those requests are
    downloaded (see :stat:`httpcache/firsthand`), or dropped if
    :setting:`HTTPCACHE_IGNORE_MISSING` is ``True`` (see
    :stat:`httpcache/ignore`).

    Requests with a stale cache entry are not counted here; see
    :stat:`httpcache/revalidate` and :stat:`httpcache/invalidate`.

    Set by :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`.

.. stat:: httpcache/retrieve_error

``httpcache/retrieve_error``
    Number of cache entries that could not be read, and hence were treated as
    cache misses. Those requests are also counted in :stat:`httpcache/miss`.

    Set by :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`.

.. stat:: httpcache/revalidate

``httpcache/revalidate``
    Number of times that a cached response was successfully validated against
    the target server, and hence used instead of the fresh response.

    Set by :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`.

.. stat:: httpcache/store

``httpcache/store``
    Number of responses stored in the cache.

    Set by :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`.

.. stat:: httpcache/uncacheable

``httpcache/uncacheable``
    Number of responses not stored in the cache because the
    :setting:`HTTPCACHE_POLICY` did not allow it.

    Every response considered for caching is counted either here or in
    :stat:`httpcache/store`, so ``httpcache/store + httpcache/uncacheable``
    equals ``httpcache/firsthand + httpcache/invalidate``.

    Set by :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`.

.. stat:: httpcompression/response_bytes

``httpcompression/response_bytes``
    Total size, in bytes, of decompressed response bodies, counting only the
    body and only responses that were actually decompressed. Compare with
    :stat:`downloader/response_bytes`.

    Set by
    :class:`~scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware`.

.. stat:: httpcompression/response_count

``httpcompression/response_count``
    Number of decompressed responses.

    Set by
    :class:`~scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware`.

.. stat:: httperror/response_ignored_count

``httperror/response_ignored_count``
    Number of responses dropped because of their HTTP status code.

    Set by :class:`~scrapy.spidermiddlewares.httperror.HttpErrorMiddleware`.

.. stat:: httperror/response_ignored_status_count/{status_code}

``httperror/response_ignored_status_count/{status_code}``
    Number of responses dropped because of their HTTP status code, per HTTP
    status code, e.g. ``404``.

    Set by :class:`~scrapy.spidermiddlewares.httperror.HttpErrorMiddleware`.

.. stat:: item_dropped_count

``item_dropped_count``
    Number of items dropped by an :ref:`item pipeline
    <topics-item-pipeline>`, i.e. number of times that the
    :signal:`item_dropped` signal was sent.

    Set by :class:`~scrapy.extensions.corestats.CoreStats`.

.. stat:: item_dropped_reasons_count/{exception}

``item_dropped_reasons_count/{exception}``
    Number of items dropped, per exception, where ``{exception}`` is the class
    name of the exception that caused the item to be dropped.

    Only :exc:`~scrapy.exceptions.DropItem` and its subclasses drop items, and
    each one is counted under its own class name, e.g.
    ``item_dropped_reasons_count/DropItem`` for
    :exc:`~scrapy.exceptions.DropItem` itself and
    ``item_dropped_reasons_count/MyDropItem`` for a ``MyDropItem`` subclass of
    it. Any other exception raised by an :ref:`item pipeline
    <topics-item-pipeline>` triggers the :signal:`item_error` signal instead of
    :signal:`item_dropped`, and is not counted here or in
    :stat:`item_dropped_count`.

    Set by :class:`~scrapy.extensions.corestats.CoreStats`.

.. stat:: item_scraped_count

``item_scraped_count``
    Number of items that passed all :ref:`item pipelines
    <topics-item-pipeline>`, i.e. number of times that the
    :signal:`item_scraped` signal was sent.

    Set by :class:`~scrapy.extensions.corestats.CoreStats`.

.. stat:: items_per_minute

``items_per_minute``
    Average number of items scraped per minute during the crawl.

    It is ``None`` if the crawl took less than a minute.

    Set by :class:`~scrapy.extensions.logstats.LogStats`.

.. stat:: log_count/{level}

``log_count/{level}``
    Number of log messages, per logging level name, e.g. ``INFO`` or
    ``WARNING``.

    Only messages that the :setting:`LOG_LEVEL` setting allows are counted.

    Set by :class:`~scrapy.extensions.logcount.LogCount`.

.. stat:: memdebug/gc_garbage_count

``memdebug/gc_garbage_count``
    Number of objects in :data:`gc.garbage` when the spider is closed.

    Set by :class:`~scrapy.extensions.memdebug.MemoryDebugger`, which requires
    :setting:`MEMDEBUG_ENABLED` to be ``True``.

.. stat:: memdebug/live_refs/{cls}

``memdebug/live_refs/{cls}``
    Number of live objects of class ``{cls}`` when the spider is closed, as
    reported by :ref:`trackref <topics-leaks-trackrefs>`, e.g.
    ``memdebug/live_refs/HtmlResponse``.

    Only set for classes with at least 1 live object.

    Set by :class:`~scrapy.extensions.memdebug.MemoryDebugger`, which requires
    :setting:`MEMDEBUG_ENABLED` to be ``True``.

.. stat:: memusage/limit_reached

``memusage/limit_reached``
    ``1`` if memory usage exceeded :setting:`MEMUSAGE_LIMIT_MB`, which also
    stops the crawl.

    Set by :class:`~scrapy.extensions.memusage.MemoryUsage`.

.. stat:: memusage/max

``memusage/max``
    Maximum peak memory usage, in bytes, observed during the crawl.

    Set by :class:`~scrapy.extensions.memusage.MemoryUsage`.

.. stat:: memusage/startup

``memusage/startup``
    Peak memory usage, in bytes, when the engine started.

    Set by :class:`~scrapy.extensions.memusage.MemoryUsage`.

.. stat:: memusage/warning_reached

``memusage/warning_reached``
    ``1`` if memory usage exceeded :setting:`MEMUSAGE_WARNING_MB`.

    Set by :class:`~scrapy.extensions.memusage.MemoryUsage`.

.. stat:: offsite/domains

``offsite/domains``
    Number of distinct domains for which at least 1 request was dropped for
    being offsite.

    Set by :class:`~scrapy.downloadermiddlewares.offsite.OffsiteMiddleware`.

.. stat:: offsite/filtered

``offsite/filtered``
    Number of requests dropped for being offsite.

    Set by :class:`~scrapy.downloadermiddlewares.offsite.OffsiteMiddleware`.

.. stat:: request_depth_count/{depth}

``request_depth_count/{depth}``
    Number of requests scheduled at depth ``{depth}``, e.g.
    ``request_depth_count/2``.

    Set by :class:`~scrapy.spidermiddlewares.depth.DepthMiddleware`, which
    requires :setting:`DEPTH_STATS_VERBOSE` to be ``True`` for this stat.

.. stat:: request_depth_max

``request_depth_max``
    Maximum depth reached.

    Set by :class:`~scrapy.spidermiddlewares.depth.DepthMiddleware`.

.. stat:: response_received_count

``response_received_count``
    Number of responses received, i.e. number of times that the
    :signal:`response_received` signal was sent.

    Unlike :stat:`downloader/response_count`, it does not count responses that
    a downloader middleware consumes before they reach the engine, e.g.
    redirect responses that :class:`~scrapy.downloadermiddlewares.redirect.RedirectMiddleware`
    turns into new requests. Both count responses that :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`
    serves from the cache.

    Set by :class:`~scrapy.extensions.corestats.CoreStats`.

.. stat:: responses_per_minute

``responses_per_minute``
    Average number of responses received per minute during the crawl.

    It is ``None`` if the crawl took less than a minute.

    Set by :class:`~scrapy.extensions.logstats.LogStats`.

.. stat:: retry/count

``retry/count``
    Number of requests retried.

    Set by :func:`~scrapy.downloadermiddlewares.retry.get_retry_request`, which
    :class:`~scrapy.downloadermiddlewares.retry.RetryMiddleware` uses.

.. stat:: retry/max_reached

``retry/max_reached``
    Number of requests that were not retried because they had already been
    retried :setting:`RETRY_TIMES` times.

    Set by :func:`~scrapy.downloadermiddlewares.retry.get_retry_request`, which
    :class:`~scrapy.downloadermiddlewares.retry.RetryMiddleware` uses.

.. stat:: retry/reason_count/{reason}

``retry/reason_count/{reason}``
    Number of requests retried, per reason, e.g.
    ``retry/reason_count/twisted.internet.error.TimeoutError`` or
    ``retry/reason_count/504 Gateway Time-out``.

    Set by :func:`~scrapy.downloadermiddlewares.retry.get_retry_request`, which
    :class:`~scrapy.downloadermiddlewares.retry.RetryMiddleware` uses.

.. note:: Code calling
    :func:`~scrapy.downloadermiddlewares.retry.get_retry_request` may pass a
    custom *stats_base_key*, in which case ``retry`` is replaced with that key
    in the 3 stats above.

.. stat:: robotstxt/exception_count/{exception_type}

``robotstxt/exception_count/{exception_type}``
    Number of exceptions raised while downloading ``robots.txt`` files, per
    exception type, where ``{exception_type}`` is the string representation of
    the exception class, e.g. ``<class
    'twisted.internet.error.DNSLookupError'>``.

    Set by
    :class:`~scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware`.

.. stat:: robotstxt/forbidden

``robotstxt/forbidden``
    Number of requests dropped for being disallowed by ``robots.txt``.

    Set by
    :class:`~scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware`.

.. stat:: robotstxt/request_count

``robotstxt/request_count``
    Number of ``robots.txt`` files requested, i.e. 1 per network location for
    which at least 1 request was sent.

    Set by
    :class:`~scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware`.

.. stat:: robotstxt/response_count

``robotstxt/response_count``
    Number of ``robots.txt`` responses received.

    Set by
    :class:`~scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware`.

.. stat:: robotstxt/response_status_count/{status_code}

``robotstxt/response_status_count/{status_code}``
    Number of ``robots.txt`` responses received, per HTTP status code, e.g.
    ``404``.

    Set by
    :class:`~scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware`.

.. stat:: scheduler/dequeued

``scheduler/dequeued``
    Number of requests read from the :ref:`scheduler <topics-scheduler>`.

.. stat:: scheduler/dequeued/disk

``scheduler/dequeued/disk``
    Number of requests read from the disk queue of the :ref:`scheduler
    <topics-scheduler>`.

.. stat:: scheduler/dequeued/memory

``scheduler/dequeued/memory``
    Number of requests read from the memory queue of the :ref:`scheduler
    <topics-scheduler>`.

.. stat:: scheduler/enqueued

``scheduler/enqueued``
    Number of requests stored into the :ref:`scheduler <topics-scheduler>`.

.. stat:: scheduler/enqueued/disk

``scheduler/enqueued/disk``
    Number of requests stored into the disk queue of the :ref:`scheduler
    <topics-scheduler>`.

.. stat:: scheduler/enqueued/memory

``scheduler/enqueued/memory``
    Number of requests stored into the memory queue of the :ref:`scheduler
    <topics-scheduler>`.

.. stat:: scheduler/unserializable

``scheduler/unserializable``
    Number of requests that could not be stored into the disk queue of the
    :ref:`scheduler <topics-scheduler>` because they could not be
    :ref:`serialized <request-serialization>`, and hence were stored into the
    memory queue instead.

.. stat:: spider_exceptions/count

``spider_exceptions/count``
    Number of unhandled exceptions raised by spider callbacks or by
    :meth:`~scrapy.Spider.start`.

    Set by the :ref:`engine <topics-architecture>` and the :ref:`scraper
    <topics-architecture>`.

.. stat:: spider_exceptions/{exception}

``spider_exceptions/{exception}``
    Same as :stat:`spider_exceptions/count`, per exception, where
    ``{exception}`` is the class name of the exception, e.g.
    ``spider_exceptions/ValueError``.

    Set by the :ref:`engine <topics-architecture>` and the :ref:`scraper
    <topics-architecture>`.

.. stat:: start_time

``start_time``
    Timezone-aware :class:`~datetime.datetime` object, in UTC, indicating when
    the :signal:`spider_opened` signal was sent.

    Set by :class:`~scrapy.extensions.corestats.CoreStats`.

.. stat:: urllength/request_ignored_count

``urllength/request_ignored_count``
    Number of requests dropped for having a URL longer than
    :setting:`URLLENGTH_LIMIT`.

    Set by :class:`~scrapy.spidermiddlewares.urllength.UrlLengthMiddleware`.
