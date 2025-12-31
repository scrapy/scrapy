.. _topics-lifecycle:

=============================
Request to Response Lifecycle
=============================

This document explains how a :class:`~scrapy.Request` flows through Scrapy's
internals, from creation in a spider to the delivery of a
:class:`~scrapy.http.Response` back to a spider callback. Understanding this
lifecycle helps when debugging, optimizing performance, or extending Scrapy
with custom components.

For a high-level component overview, see :ref:`topics-architecture`. This page
focuses on the detailed sequence of operations.

.. _lifecycle-overview:

Lifecycle overview
==================

A request passes through these main phases:

1. **Creation**: A spider yields requests and items from its :meth:`~scrapy.Spider.start` method
2. **Start processing**: Spider middleware processes start output via :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_start`
3. **Scheduling**: The engine passes the request to the scheduler for queuing
4. **Downloading**: The scheduler returns the request to the engine, which sends it to the downloader
5. **Response handling**: The downloader returns a response to the engine
6. **Spider processing**: The engine passes the response to the spider for callback execution
7. **Output processing**: Items go to pipelines; new requests return to step 3

The following sections describe each phase in detail.

.. _lifecycle-engine-role:

The engine as orchestrator
==========================

The :ref:`execution engine <component-engine>` controls all data flow between
Scrapy components. It does not process requests or responses itself; instead,
it coordinates when each component acts and manages the transitions between
phases.

The engine's responsibilities include:

- Obtaining start requests from the spider and passing them to the scheduler
- Requesting the next request from the scheduler when capacity is available
- Sending requests to the downloader and receiving responses
- Passing responses to the scraper for spider callback execution
- Routing callback output (items and new requests) to the appropriate components
- Monitoring idle conditions and initiating spider closure

The engine implements backpressure by checking whether the downloader or
scraper can accept more work before dequeuing additional requests from the
scheduler. This prevents memory exhaustion when spiders generate requests
faster than they can be processed.

**Backpressure conditions**

The engine pauses request processing when any of these conditions are true:

- The downloader has reached its concurrency limit (:setting:`CONCURRENT_REQUESTS`)
- The scraper's active response size exceeds its threshold (:setting:`SCRAPER_SLOT_MAX_ACTIVE_SIZE`)
- The engine is shutting down

When the engine starts, it emits the :signal:`engine_started` signal.

.. _lifecycle-start-processing:

Start request processing
========================

Before any crawling begins, the spider's :meth:`~scrapy.Spider.start` method
(or the deprecated :meth:`~scrapy.Spider.start_requests`) generates the initial
requests and items. This output passes through :ref:`spider middleware
<component-spider-middleware>` before requests reach the scheduler.

**Start processing flow**

1. The engine opens the spider and emits the :signal:`spider_opened` signal
2. The engine calls the spider middleware manager's ``process_start()`` method
3. Each spider middleware's :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_start`
   method can filter, transform, or replace the start output
4. Requests from the processed output are passed to the scheduler
5. Items from the processed output are sent directly to pipelines

Spider middlewares can use ``process_start()`` to:

- Filter out certain start requests based on custom logic
- Add metadata to requests (e.g., setting ``request.meta`` values)
- Transform URLs or request parameters
- Inject additional requests not in the original start output

For details on implementing ``process_start()``, see
:ref:`topics-spider-middleware`.

.. _lifecycle-scheduling:

Request scheduling and duplicate filtering
==========================================

When the engine receives a request (from start processing or spider callbacks),
it passes the request to the :ref:`scheduler <component-scheduler>`.

**Scheduling process**

1. The engine emits the :signal:`request_scheduled` signal
2. If a signal handler raises :exc:`~scrapy.exceptions.IgnoreRequest`, the request is dropped
3. The scheduler checks for duplicates using the configured duplicate filter
4. If the request is a duplicate (and ``dont_filter=False``), it is rejected and the :signal:`request_dropped` signal is emitted
5. Otherwise, the request is added to the scheduler's queue

**Duplicate filtering**

The default duplicate filter (:class:`~scrapy.dupefilters.RFPDupeFilter`) uses
request fingerprints to identify duplicates. A fingerprint is computed from the
request's URL, method, and body. The filter maintains a set of seen
fingerprints and rejects requests whose fingerprint already exists.

To bypass duplicate filtering for a specific request, set ``dont_filter=True``
when creating the request::

    yield scrapy.Request(url, dont_filter=True)

For custom duplicate filtering logic, implement a class following the
:class:`~scrapy.dupefilters.BaseDupeFilter` interface and configure it via
the :setting:`DUPEFILTER_CLASS` setting.

**Queue structure**

The default scheduler maintains two queues:

- **Memory queue**: Stores requests in memory for fast access
- **Disk queue**: Persists requests to disk when a job directory is configured

When dequeuing, the scheduler checks the memory queue first, then falls back to
the disk queue. This design supports :ref:`pausing and resuming crawls
<topics-jobs>`.

For more details on the scheduler, see :ref:`topics-scheduler`.

.. _lifecycle-downloading:

Downloading
===========

When the engine determines it has capacity for more downloads, it requests
the next request from the scheduler and passes it to the
:ref:`downloader <component-downloader>`.

**Download process**

1. The engine calls the downloader with the request
2. The request passes through the :ref:`downloader middleware chain <component-downloader-middleware>` (``process_request`` methods)
3. If no middleware returns a response, the request reaches a download handler
4. The download handler performs the actual HTTP request
5. The response passes back through the downloader middleware chain (``process_response`` methods)
6. The final response returns to the engine

**Downloader middleware integration**

Downloader middlewares can intercept requests before they reach the network
and responses before they reach the spider. Common uses include:

- Setting headers (User-Agent, cookies, authentication)
- Handling redirects and retries
- Caching responses
- Returning synthetic responses without making network requests

Each middleware's ``process_request`` method can:

- Return ``None`` to continue to the next middleware
- Return a :class:`~scrapy.http.Response` to skip remaining middlewares and the download handler
- Return a :class:`~scrapy.Request` to reschedule a different request
- Raise :exc:`~scrapy.exceptions.IgnoreRequest` to abort the request

For details on writing downloader middlewares, see
:ref:`topics-downloader-middleware`.

**Concurrency and delays**

The downloader enforces concurrency limits at two levels:

- **Global**: :setting:`CONCURRENT_REQUESTS` limits total simultaneous downloads
- **Per-domain or per-IP**: :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` or :setting:`CONCURRENT_REQUESTS_PER_IP` limit downloads to each target

Download delays can be configured via :setting:`DOWNLOAD_DELAY`. When set, the
downloader waits at least this many seconds between consecutive requests to
the same domain. The :setting:`RANDOMIZE_DOWNLOAD_DELAY` setting adds
randomization to make request timing less predictable.

**Signals emitted during download**

- :signal:`request_reached_downloader`: When a request enters the downloader's active set
- :signal:`response_downloaded`: When the download handler returns a response
- :signal:`request_left_downloader`: When processing for a request completes
- :signal:`bytes_received`: When data chunks arrive during download
- :signal:`headers_received`: When HTTP headers are received

.. _lifecycle-spider-processing:

Spider callback execution
=========================

After the engine receives a response from the downloader, it passes the
response to the scraper, which manages spider callback execution.

**Callback execution process**

1. The response enters the scraper's queue
2. The response passes through :ref:`spider middleware <component-spider-middleware>` (``process_spider_input`` methods)
3. The spider's callback method is invoked with the response
4. The callback's output (an iterable of items and requests) passes through spider middleware (``process_spider_output`` methods)
5. Items and requests are extracted from the processed output

**Callback selection**

The callback is determined by the request that generated the response:

- If ``request.callback`` is set, that function is called
- Otherwise, the spider's default ``_parse`` method (which calls ``parse``) is used

If the download resulted in an error and the request has an ``errback``, that
function is called instead with a :class:`~twisted.python.failure.Failure`
object.

**Spider middleware integration**

Spider middlewares process data at two points in the lifecycle:

1. **Start processing**: Via ``process_start()`` before initial requests reach
   the scheduler (see :ref:`lifecycle-start-processing`)
2. **Callback processing**: Via ``process_spider_input()`` and
   ``process_spider_output()`` for responses and callback output

Common uses for callback processing include:

- Filtering responses (e.g., by HTTP status code or content type)
- Handling spider exceptions
- Modifying the items or requests yielded by callbacks

For details on writing spider middlewares, see :ref:`topics-spider-middleware`.

**Signals emitted during spider processing**

- :signal:`response_received`: When the engine receives a response (before spider processing)
- :signal:`spider_error`: When a spider callback raises an exception

.. _lifecycle-item-processing:

Item pipeline processing
========================

When a spider callback yields an item (a dict, :class:`~scrapy.Item`, or
dataclass), the scraper passes it to the :ref:`item pipeline
<component-pipelines>`.

**Pipeline execution**

1. The item passes to the first pipeline's ``process_item`` method
2. If the pipeline returns an item, it passes to the next pipeline
3. This continues until all pipelines have processed the item
4. If any pipeline raises :exc:`~scrapy.exceptions.DropItem`, processing stops

**Pipeline configuration**

Pipelines are enabled via the :setting:`ITEM_PIPELINES` setting, which maps
pipeline classes to integer priority values. Lower values execute first.

**Signals emitted during item processing**

- :signal:`item_scraped`: When an item successfully passes through all pipelines
- :signal:`item_dropped`: When a pipeline raises :exc:`~scrapy.exceptions.DropItem`
- :signal:`item_error`: When a pipeline raises an unexpected exception

For details on writing item pipelines, see :ref:`topics-item-pipeline`.

.. _lifecycle-new-requests:

New request handling
====================

When a spider callback yields a :class:`~scrapy.Request`, the scraper extracts
it from the callback output and passes it back to the engine. The engine then
schedules the request, and the lifecycle repeats from the scheduling phase.

This recursive flow continues until:

- The scheduler has no pending requests
- All active downloads have completed
- The spider's start iterator is exhausted
- The scraper has no active responses

When all these conditions are met, the spider is considered idle.

.. _lifecycle-error-handling:

Error handling
==============

Scrapy handles errors at multiple points in the lifecycle.

**Download errors**

When a download fails (network error, timeout, etc.):

1. The error passes through downloader middleware ``process_exception`` methods
2. If a middleware returns a response or request, normal processing continues
3. Otherwise, if the request has an ``errback``, it is called with the failure
4. If no ``errback`` exists, the error is logged

The :class:`~scrapy.downloadermiddlewares.retry.RetryMiddleware` handles
retries for failed requests. It reschedules requests that fail due to
connection errors, timeouts, or certain HTTP status codes, up to a
configurable limit (:setting:`RETRY_TIMES`).

**Spider callback errors**

When a spider callback raises an exception:

1. The error passes through spider middleware ``process_spider_exception`` methods
2. If a middleware yields items or requests, those are processed normally
3. The :signal:`spider_error` signal is emitted
4. If the exception is :exc:`~scrapy.exceptions.CloseSpider`, the spider shuts down

**Item pipeline errors**

When a pipeline's ``process_item`` raises an exception:

- :exc:`~scrapy.exceptions.DropItem`: The item is dropped (normal behavior)
- Other exceptions: The :signal:`item_error` signal is emitted and the error is logged

.. _lifecycle-spider-idle:

Spider idle and closure
=======================

The engine periodically checks whether the spider is idle. A spider is
considered idle when:

- The scraper has no responses being processed
- The downloader has no active requests
- The start request iterator is exhausted
- The scheduler has no pending requests

When the spider becomes idle:

1. The engine emits the :signal:`spider_idle` signal
2. Signal handlers can schedule new requests to keep the spider running
3. If a handler raises :exc:`~scrapy.exceptions.DontCloseSpider`, the spider remains open
4. Otherwise, the engine initiates spider closure and emits the :signal:`spider_closed` signal

The closure reason is "finished" by default, but can be customized by raising
:exc:`~scrapy.exceptions.CloseSpider` with a reason argument.

.. _lifecycle-customization:

Customization points
====================

This section summarizes where you can customize the request lifecycle.

**Component replacement**

These settings allow replacing core components with custom implementations:

- :setting:`SCHEDULER`: Custom scheduler class
- :setting:`DUPEFILTER_CLASS`: Custom duplicate filter
- :setting:`DOWNLOADER`: Custom downloader class

**Middleware chains**

These settings configure middleware that processes requests and responses:

- :setting:`DOWNLOADER_MIDDLEWARES`: Modify requests before download and responses after
- :setting:`SPIDER_MIDDLEWARES`: Process responses before callbacks and output after

**Pipeline chain**

- :setting:`ITEM_PIPELINES`: Process items after extraction

**Signal handlers**

:ref:`Signals <topics-signals>` allow reacting to lifecycle events without
modifying core components. Extensions typically connect to signals to implement
cross-cutting functionality.

**Per-request customization**

Individual requests support these customization options:

- ``callback``: Function to process the response
- ``errback``: Function to handle download errors
- ``dont_filter``: Skip duplicate filtering
- ``priority``: Influence dequeue order in the scheduler
- ``meta``: Pass data between middlewares and callbacks

For the complete request API, see :ref:`topics-request-response`.

.. _lifecycle-diagram:

Lifecycle sequence diagram
==========================

The following diagram illustrates the request lifecycle::

    Spider          Engine          Scheduler       Downloader      Scraper
       |               |                |               |              |
       |               |                |               |              |
       |=== START PHASE ================================================|
       |               |                |               |              |
       |--start()----->|                |               |              |
       |  [Spider MW: process_start()]  |               |              |
       |               |---enqueue----->|               |              |
       |               |                |               |              |
       |=== CRAWL PHASE (repeats) ======================================|
       |               |                |               |              |
       |               |<--next_request-|               |              |
       |               |                |               |              |
       |               |----Request-----|-------------->|              |
       |               |                | [Downloader Middlewares]     |
       |               |                | [Download Handler]           |
       |               |                |               |              |
       |               |<---Response----|---------------|              |
       |               |                |               |              |
       |               |----Response----|---------------|------------->|
       |               |                |               |              |
       |               |                |               | [Spider MW]  |
       |               |                |               | [Callback]   |
       |<--items,reqs--|----------------|---------------|--------------|
       |               |                |               |              |
       |               |  [Items to Pipeline, Requests to Scheduler]   |
       |               |                |               |              |

The crawl phase repeats until the spider is idle and no handlers prevent closure.
