=======================
Stats Produced by Scrapy
=======================

Scrapy spiders expose a collection of statistics through
the `crawler.stats` attribute. These stats are useful to
inspect the progress and performance of a crawl.

This page lists some of the commonly seen statistics keys.

.. contents::
   :depth: 2
   :local:

Log-related
===========

- *log_count/DEBUG*: number of DEBUG log messages.
- *log_count/INFO*: number of INFO log messages.
- *log_count/WARNING*: number of WARNING log messages.
- *log_count/ERROR*: number of ERROR log messages.

Scheduler
=========

- *scheduler/enqueued*: number of requests placed into the scheduler.
- *scheduler/enqueued/memory*: requests kept in memory by the scheduler.
- *scheduler/dequeued*: number of requests pulled from the scheduler.
- *scheduler/dequeued/memory*: requests pulled from memory by the scheduler.

Downloader
==========

- *downloader/request_count*: total number of requests made.
- *downloader/request_method_count/<METHOD>*: number of requests per HTTP method (e.g., GET, POST).
- *downloader/request_bytes*: total bytes sent in requests.
- *downloader/response_count*: total number of responses received.
- *downloader/response_status_count/<CODE>*: number of responses with a given HTTP status code (e.g., 200, 404, 500).
- *downloader/response_bytes*: total size of responses (in bytes).
- *response_received_count*: number of responses successfully received.

Items and Processing
==================

- *item_scraped_count*: number of items scraped by the spider.
- *item_dropped_count*: number of items dropped by item pipelines.

Spider Execution
===============

- *start_time*: datetime when the crawl started.
- *finish_time*: datetime when the crawl finished.
- *request_depth_max*: maximum depth reached by the spider during crawling.

Notes
=====

This list covers the most commonly encountered statistics, but is not
exhaustive. Additional stats may be available depending on which
middlewares, extensions, or pipelines are enabled in your Scrapy project.
