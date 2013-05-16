.. _benchmarking:

============
Benchmarking
============

.. versionadded:: 0.17

Scrapy comes with a simple benchmarking suite that spawns a local HTTP server
and crawls it at the maximum possible speed. The goal of this benchmarking is
to get an idea of how Scrapy performs in your hardware, in order to have a
common baseline for comparisons. It uses a simple spider that does nothing and
just follows links.

To run it use::

    scrapy bench

You should see an output like this::

    2013-05-16 13:08:46-0300 [scrapy] INFO: Scrapy 0.17.0 started (bot: scrapybot)
    2013-05-16 13:08:47-0300 [follow] INFO: Spider opened
    2013-05-16 13:08:47-0300 [follow] INFO: Crawled 0 pages (at 0 pages/min), scraped 0 items (at 0 items/min)
    2013-05-16 13:08:48-0300 [follow] INFO: Crawled 74 pages (at 4440 pages/min), scraped 0 items (at 0 items/min)
    2013-05-16 13:08:49-0300 [follow] INFO: Crawled 143 pages (at 4140 pages/min), scraped 0 items (at 0 items/min)
    2013-05-16 13:08:50-0300 [follow] INFO: Crawled 210 pages (at 4020 pages/min), scraped 0 items (at 0 items/min)
    2013-05-16 13:08:51-0300 [follow] INFO: Crawled 274 pages (at 3840 pages/min), scraped 0 items (at 0 items/min)
    2013-05-16 13:08:52-0300 [follow] INFO: Crawled 343 pages (at 4140 pages/min), scraped 0 items (at 0 items/min)
    2013-05-16 13:08:53-0300 [follow] INFO: Crawled 410 pages (at 4020 pages/min), scraped 0 items (at 0 items/min)
    2013-05-16 13:08:54-0300 [follow] INFO: Crawled 474 pages (at 3840 pages/min), scraped 0 items (at 0 items/min)
    2013-05-16 13:08:55-0300 [follow] INFO: Crawled 538 pages (at 3840 pages/min), scraped 0 items (at 0 items/min)
    2013-05-16 13:08:56-0300 [follow] INFO: Crawled 602 pages (at 3840 pages/min), scraped 0 items (at 0 items/min)
    2013-05-16 13:08:57-0300 [follow] INFO: Closing spider (closespider_timeout)
    2013-05-16 13:08:57-0300 [follow] INFO: Crawled 666 pages (at 3840 pages/min), scraped 0 items (at 0 items/min)
    2013-05-16 13:08:57-0300 [follow] INFO: Dumping Scrapy stats:
        {'downloader/request_bytes': 231508,
         'downloader/request_count': 682,
         'downloader/request_method_count/GET': 682,
         'downloader/response_bytes': 1172802,
         'downloader/response_count': 682,
         'downloader/response_status_count/200': 682,
         'finish_reason': 'closespider_timeout',
         'finish_time': datetime.datetime(2013, 5, 16, 16, 8, 57, 985539),
         'log_count/INFO': 14,
         'request_depth_max': 34,
         'response_received_count': 682,
         'scheduler/dequeued': 682,
         'scheduler/dequeued/memory': 682,
         'scheduler/enqueued': 12767,
         'scheduler/enqueued/memory': 12767,
         'start_time': datetime.datetime(2013, 5, 16, 16, 8, 47, 676539)}
    2013-05-16 13:08:57-0300 [follow] INFO: Spider closed (closespider_timeout)

That tells you that Scrapy is able to crawl about 3900 pages per minute in the
hardware where you run it. Note that this is a very simple spider intended to
follow links, any custom spider you write will probably do more stuff which
results in slower crawl rates. How slower depends on how much your spider does
and how well it's written.

In the future, more cases will be added to the benchmarking suite to cover
other common scenarios.
