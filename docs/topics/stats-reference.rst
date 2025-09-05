.. _topics-stats-reference:

======================
Stats Produced by Scrapy
======================

Scrapy spiders expose a collection of statistics through the ``crawler.stats`` attribute. These stats are useful to inspect the progress and performance of a crawl, debug issues, and monitor spider behavior in production environments.

This page lists the statistics keys that are commonly available across different Scrapy configurations and use cases.

.. contents::
   :depth: 2
   :local:

Accessing Stats
===============

Stats can be accessed in several ways:

* Within spider code: ``self.crawler.stats.get_value('stat_name')``
* In extensions or pipelines: ``crawler.stats.get_value('stat_name')``  
* Via the stats extension's ``spider_closed`` signal handler
* Through custom logging or monitoring integrations

Core Statistics Categories
==========================

Spider Execution
----------------

* **start_time**: datetime when the crawl started.
* **finish_time**: datetime when the crawl finished.
* **elapsed_time_seconds**: total time spent crawling (in seconds).
* **spider_exceptions/<exception_class>**: count of exceptions raised by spider callbacks, grouped by exception type.

Request Scheduling
------------------

* **scheduler/enqueued**: cumulative count of all requests that have been submitted to the scheduler.
* **scheduler/enqueued/memory**: count of requests currently queued in the scheduler's in-memory storage.
* **scheduler/enqueued/disk**: count of requests currently queued in the scheduler's disk-based storage (when using disk queues).
* **scheduler/dequeued**: cumulative count of requests that have been retrieved from the scheduler for processing.
* **scheduler/dequeued/memory**: count of requests that were retrieved from the scheduler's in-memory storage.
* **scheduler/dequeued/disk**: count of requests that were retrieved from the scheduler's disk-based storage.

Downloader Statistics
---------------------

* **downloader/request_count**: total number of requests processed by the downloader.
* **downloader/request_method_count/GET**: number of GET requests made.
* **downloader/request_method_count/POST**: number of POST requests made.
* **downloader/request_method_count/<METHOD>**: number of requests for any HTTP method.
* **downloader/request_bytes**: total number of bytes sent in all requests (including headers and body).
* **downloader/response_count**: total number of responses received by the downloader.
* **downloader/response_bytes**: total number of bytes received in all responses (including headers and body).
* **downloader/response_status_count/200**: number of responses with HTTP status code 200.
* **downloader/response_status_count/404**: number of responses with HTTP status code 404.
* **downloader/response_status_count/<CODE>**: number of responses for any HTTP status code.
* **response_received_count**: number of responses that were successfully processed (equivalent to response_count in most cases).

Duplicate Filtering
-------------------

* **dupefilter/filtered**: number of requests filtered out as duplicates by the duplicate filter.
* **dupefilter/filtered/disk**: number of duplicate requests filtered using disk-based storage.
* **dupefilter/filtered/memory**: number of duplicate requests filtered using in-memory storage.

Item Processing
---------------

* **item_scraped_count**: total number of items extracted by spider callbacks.
* **item_dropped_count**: number of items that were dropped by item pipelines.
* **item_dropped_reasons/<reason>**: number of items dropped, grouped by the reason provided by item pipelines.

Request Depth Tracking
----------------------

* **request_depth_max**: maximum depth level reached during crawling (useful for understanding crawl scope).
* **request_depth_<N>**: number of requests processed at depth level N (where N is 0, 1, 2, etc.).

Logging Statistics
------------------

* **log_count/DEBUG**: number of DEBUG level log messages generated.
* **log_count/INFO**: number of INFO level log messages generated.
* **log_count/WARNING**: number of WARNING level log messages generated.
* **log_count/ERROR**: number of ERROR level log messages generated.
* **log_count/CRITICAL**: number of CRITICAL level log messages generated.

Retry Statistics
----------------

* **retry/count**: total number of request retries attempted.
* **retry/max_reached**: number of requests that reached the maximum retry limit and were abandoned.
* **retry/reason_count/<reason>**: number of retries grouped by failure reason (e.g., timeout, connection error).

Robustness and Error Handling
------------------------------

* **downloader/exception_count**: total number of exceptions that occurred in the downloader.
* **downloader/exception_type_count/<exception_class>**: number of downloader exceptions grouped by exception type.
* **spider_exceptions**: total count of all exceptions raised by spider callbacks.
* **robotstxt/forbidden**: number of requests forbidden by robots.txt rules (when RobotsTxtMiddleware is enabled).
* **robotstxt/allowed**: number of requests allowed by robots.txt rules.

Memory and Performance
----------------------

* **memusage/startup**: memory usage at spider startup (when MemoryUsage extension is enabled).
* **memusage/peak**: peak memory usage during the crawl.
* **httpcache/hit**: number of responses served from HTTP cache (when HttpCacheMiddleware is enabled).
* **httpcache/miss**: number of responses that were not found in HTTP cache.

Middleware and Extension Specific Stats
=======================================

Different middlewares and extensions may add their own statistics:

AutoThrottle Extension
----------------------

* **autothrottle/response_interval_avg**: average response time used for throttling calculations.

Cookies Middleware
------------------

* **cookies/set**: number of cookies set by the server.
* **cookies/sent**: number of cookies sent in requests.

Redirect Middleware
-------------------

* **redirect/count**: total number of redirects followed.
* **redirect/max_reached**: number of requests that reached maximum redirect limit.

Compression Middleware
----------------------

* **compression/gzip/response_bytes**: bytes received in gzipped responses.
* **compression/deflate/response_bytes**: bytes received in deflate-compressed responses.

Usage Examples
==============

Monitoring Crawl Health
-----------------------

.. code-block:: python

    def spider_closed(self, spider, reason):
        stats = spider.crawler.stats
        
        # Check for high error rates
        total_requests = stats.get_value('downloader/request_count', 0)
        error_4xx = sum(stats.get_value(f'downloader/response_status_count/{code}', 0) 
                       for code in range(400, 500))
        
        if total_requests > 0 and error_4xx / total_requests > 0.1:
            spider.logger.warning("High 4xx error rate detected")

Performance Analysis
--------------------

.. code-block:: python

    # Calculate success rate
    total_responses = self.crawler.stats.get_value('response_received_count', 0)
    items_scraped = self.crawler.stats.get_value('item_scraped_count', 0)

    if total_responses > 0:
        success_rate = items_scraped / total_responses
        self.logger.info(f"Item extraction success rate: {success_rate:.2%}")

Notes
=====

* This list covers commonly available statistics, but the exact stats present depend on your Scrapy configuration, enabled middlewares, extensions, and pipelines.
* Custom middlewares, extensions, and pipelines can define their own statistics using ``crawler.stats.inc_value()``, ``crawler.stats.set_value()``, and related methods.
* Stats are reset at the beginning of each crawl and are not persistent between runs unless explicitly saved.
* Some statistics may only appear when specific conditions are met (e.g., retry stats only appear if retries actually occur).
* Memory-related stats require the MemoryUsage extension to be enabled.
* For production monitoring, consider implementing custom stats collection to track metrics specific to your use case.
