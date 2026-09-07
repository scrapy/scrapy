.. _optimize:

============
Optimization
============

A crawl goes as fast as its slowest part allows. :ref:`Find out which part that
is <optimize-bottleneck>` before changing any setting.

:ref:`Broad crawls <broad-crawls>` have their own set of recommended
adjustments.

.. _optimize-bottleneck:

Finding the bottleneck
======================

The bottleneck depends on the spider: on the same machine, one crawl can be
limited by its own parsing code and another by the target website. So measure
the crawl that you want to optimize.

:class:`~scrapy.extensions.logstats.LogStats` reports crawl speed every
:setting:`LOGSTATS_INTERVAL` seconds:

.. code-block:: text

    [scrapy.extensions.logstats] INFO: Crawled 1200 pages (at 60 pages/min), scraped 1150 items (at 58 items/min)

A rate that stays flat as you raise :setting:`CONCURRENT_REQUESTS` means
something else is the limit.


Reading the engine status
-------------------------

The :ref:`telnet console <topics-telnetconsole>` reports, through ``est()``,
what every part of the engine is doing at a given moment:

.. code-block:: text

    len(engine.downloader.active)                   : 16
    len(engine.scheduler.mqs)                       : 92
    len(engine.scraper.slot.active)                 : 0
    engine.scraper.slot.active_size                 : 0
    engine.scraper.slot.needs_backout()             : False

Take a few readings at different points of the crawl:

-   ``len(engine.downloader.active)`` stays at :setting:`CONCURRENT_REQUESTS`:
    the downloader is the limit. You are waiting on the network or on the
    target website. See :ref:`optimize-concurrency`.

-   ``len(engine.downloader.active)`` stays below
    :setting:`CONCURRENT_REQUESTS` while the scheduler queues (``mqs``,
    ``dqs``) hold requests: something throttles those requests before they
    reach the downloader, usually :setting:`CONCURRENT_REQUESTS_PER_DOMAIN`,
    :setting:`DOWNLOAD_DELAY` or :ref:`AutoThrottle <topics-autothrottle>`.

-   Both the downloader and the scheduler queues stay near empty: your spider
    is not producing requests fast enough. A crawl that walks pagination one
    page at a time cannot use more concurrency than it creates. See
    :ref:`optimize-requests`.

-   ``needs_backout()`` is ``True``, or ``active_size`` approaches
    :setting:`SCRAPER_SLOT_MAX_ACTIVE_SIZE`: responses arrive faster than your
    callbacks and :ref:`item pipelines <topics-item-pipeline>` handle them. The
    bottleneck is your own code.

-   ``len(engine.scheduler.mqs)`` grows without settling: the crawl discovers
    requests faster than it downloads them. This is what makes long crawls run
    out of memory.


Reading resource usage
----------------------

CPU
    Scrapy runs in a single process, and everything except DNS resolution and
    code you explicitly move to a thread runs in a single thread. One CPU core
    is the ceiling; a process sitting at 100% of a core is CPU-bound no matter
    how many cores the machine has.

    Use a sampling profiler, such as py-spy_, to find out which code is
    spending that CPU. :ref:`Selectors <topics-selectors>` and item pipelines
    are the usual answer.

    .. _py-spy: https://github.com/benfred/py-spy

Memory
    The :ref:`memory usage extension <topics-extensions-ref-memusage>` records
    :stat:`memusage/startup` and :stat:`memusage/max`. A :stat:`memusage/max`
    far above :stat:`memusage/startup` is expected; what matters is whether it
    keeps growing for as long as the crawl runs.

    Growth that tracks ``len(engine.scheduler.mqs)`` is a scheduling problem,
    covered in :ref:`optimize-memory`. Growth that does not is a :ref:`memory
    leak <topics-leaks>`.

Network
    Compare :stat:`downloader/response_bytes` over the crawl time against your
    available bandwidth. Saturated bandwidth caps concurrency regardless of any
    setting.

    DNS resolution is separate: it runs on a thread pool of
    :setting:`REACTOR_THREADPOOL_MAXSIZE` threads, and results are cached
    (:setting:`DNSCACHE_ENABLED`, :setting:`DNSCACHE_SIZE`). It only becomes a
    limit of its own when there are many different domains to resolve, as in
    :ref:`broad crawls <broad-crawls>`, where it shows up as slow starts and
    DNS timeouts.

Disk
    :ref:`Feed exports <topics-feed-exports>` write to disk on most crawls,
    although item data is usually small enough for that not to matter. The ones
    to suspect are
    :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware` and
    the :ref:`media pipelines <topics-media-pipeline>`, which write whole
    responses, and :setting:`JOBDIR`, which writes every scheduled request.


.. _optimize-concurrency:

Sending more requests at a time
===============================

:setting:`CONCURRENT_REQUESTS` caps how many requests are being downloaded at
any given moment, :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` caps how many of
those may target the same domain, and :setting:`DOWNLOAD_DELAY` sets a minimum
wait between two consecutive requests to the same domain. A project generated by
:command:`startproject` gets one request per second per domain out of these.

Raise them to crawl a single website faster, and see
:ref:`broad-crawls-concurrency` to spread requests across many websites
instead.

The limit that matters, though, is the one the target website tolerates.
Exceeding it gets you throttled, served errors or banned, all of which make the
crawl slower than a lower concurrency would have been. To find that limit:

-   Read the :ref:`robots.txt <topics-dlmw-robots>` file of the website. Scrapy
    does not act on its ``Crawl-delay`` and ``Request-rate`` directives, so when
    they are present, translate them into :setting:`DOWNLOAD_DELAY` and
    concurrency settings yourself.

-   Check the traffic that the website already gets, using a service like
    `SimilarWeb`_ or `Cloudflare Radar`_. A rate that is a rounding error next
    to what the website serves anyway is unlikely to be a problem for it.

    .. _SimilarWeb: https://www.similarweb.com/
    .. _Cloudflare Radar: https://radar.cloudflare.com/

-   Look for a documented way in. An API, a bulk export or a search endpoint is
    both faster for you and cheaper for the website than crawling its pages, and
    the terms of service may state a rate.

-   Crawl when the website is idle, in its own timezone, so that the capacity
    you take is capacity nobody else wanted.

-   Raise concurrency gradually and watch the website respond.
    :stat:`downloader/response_status_count/{status_code}` counts for 429, 503
    or the ban page of the website, growing :stat:`retry/count`, or a
    :ref:`download latency <download-latency>` that climbs as you push harder,
    all mean you have gone past the limit.


.. _optimize-requests:

Producing requests faster
=========================

A spider that discovers its requests one response at a time keeps the
downloader idle no matter how high you set :setting:`CONCURRENT_REQUESTS`. To
put more requests in the scheduler earlier:

-   Request every page at once when you can work out how many there are, e.g.
    from a page count or from a result count and a page size in the first
    response, instead of following a link to the next page on every response.

-   Get URLs from a source that lists many of them at once, such as a sitemap
    or a search or export endpoint of the target website. For a crawl that
    needs nothing else, :class:`~scrapy.spiders.SitemapSpider` reads sitemaps
    for you.

-   Raise the :attr:`~scrapy.Request.priority` of pagination requests, so that
    they are downloaded before the requests that they compete with, and
    discover the rest of the crawl sooner.

Each of these trades memory for speed: a request produced before the downloader
can take it waits in the scheduler, or on disk if you set :setting:`JOBDIR`.
Pushed far enough, they turn memory or disk into your new bottleneck, which is
why :ref:`optimize-memory` recommends the reverse of the last point.


.. _optimize-resources:

Lowering resource usage
=======================

.. _optimize-memory:

Lowering memory usage
---------------------

-   Lower :setting:`SCRAPER_SLOT_MAX_ACTIVE_SIZE`.

-   Lower :setting:`DOWNLOAD_MAXSIZE`, which allows a single response to take up
    to 1 GiB of memory by default, multiplied by your concurrency. Set
    :setting:`DOWNLOAD_WARNSIZE` first to find out whether the website actually
    serves responses that big.

-   Lower the number of :ref:`scheduled requests <topics-scheduler>` held in
    memory:

    -   Increase the :attr:`~scrapy.Request.priority` of requests whose
        :attr:`~scrapy.Request.callback` cannot yield additional requests.

        For example, the following spider uses a higher priority (1) for book
        requests than for pagination requests:

        .. code-block:: python

            from scrapy import Spider


            class BooksToScrapeComSpider(Spider):
                name = "books_toscrape_com"
                start_urls = [
                    "http://books.toscrape.com/catalogue/category/books/mystery_3/index.html"
                ]

                def parse(self, response):
                    next_page_links = response.css(".next a")
                    yield from response.follow_all(next_page_links)
                    book_links = response.css("article a")
                    yield from response.follow_all(book_links, callback=self.parse_book, priority=1)

                def parse_book(self, response):
                    yield {
                        "name": response.css("h1::text").get(),
                        "price": response.css(".price_color::text").re_first("£(.*)"),
                        "url": response.url,
                    }

        .. note:: If the number of request-yielding, low-priority requests
            scheduled at any given time is lower than concurrency settings
            (:setting:`CONCURRENT_REQUESTS_PER_DOMAIN` or
            :setting:`CONCURRENT_REQUESTS`), as in the example above, this can
            slow down your crawl by turning those requests into a bottleneck.

    -   If you have many :ref:`start requests <start-requests>`, consider
        :ref:`delaying their iteration <start-requests-lazy>`.

    -   Set :setting:`JOBDIR` to offload all scheduled requests to disk.

-   Be on the lookout for :ref:`memory leaks <topics-leaks>`.


Lowering network usage
----------------------

-   Enable :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`
    while developing your spider, so that re-runs do not download the same
    responses again.


Lowering CPU usage
------------------

-   Set :setting:`LOG_LEVEL` to ``"INFO"`` or higher.

-   Restrict what you parse. A :ref:`selector <topics-selectors>` over a
    smaller part of the response, or a single query whose result you reuse,
    beats repeated queries over the whole document.


Other tips
----------

-   Try :ref:`using the asyncio reactor <install-asyncio>` with uvloop_ as
    :ref:`custom event loop <using-custom-loops>`, i.e. setting
    :setting:`ASYNCIO_EVENT_LOOP` to ``"uvloop.Loop"``.

    .. _uvloop: https://github.com/MagicStack/uvloop

    Alternatively, try :ref:`switching to a non-asyncio reactor
    <disable-asyncio>`.

-   Disable unused :ref:`components <topics-components>`.

    For example, set :setting:`COOKIES_ENABLED` to ``False`` unless you need
    cookies.

-   Split the crawl across separate processes to use more than one CPU core.
    See :ref:`distributed-crawls`.


.. _broad-crawls:
.. _topics-broad-crawls:

Speeding up broad crawls
========================

While Scrapy is well suited for **broad crawls**, i.e. crawls that target many
websites, the default :ref:`settings <topics-settings>` are optimized for
crawls targeting a single website.

For broad crawls, consider these adjustments:

-   .. _broad-crawls-concurrency:

    Increase the global concurrency:

    -   Set :setting:`CONCURRENT_REQUESTS` as close to
        :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` × [number of target domains]
        (e.g. 8 × 10 domains = 80 concurrent requests) as your CPU and memory
        allow.

    -   Increase :setting:`SCRAPER_SLOT_MAX_ACTIVE_SIZE` when increasing
        :setting:`CONCURRENT_REQUESTS` stops making a difference.

-   .. _broad-crawls-bfo:

    If memory is a bottleneck, see if :ref:`crawling in BFO order <bfo>` lowers
    memory usage.

-   Improve DNS resolution speed:

    -   Set up your own DNS server, with a local cache and upstream to a `large
        DNS server`_, to avoid slowing down your network.

        .. _large DNS server: https://en.wikipedia.org/wiki/Public_recursive_name_server#Notable_public_DNS_service_operators

    -   Increase :setting:`REACTOR_THREADPOOL_MAXSIZE` to the minimum value
        that avoids DNS resolution timeouts and makes a noticeable positive
        impact in crawl speed.

-   Lower the negative impact of some responses:

    -   Set :setting:`RETRY_ENABLED` to ``False`` or, if you need retries,
        consider lowering :setting:`RETRY_TIMES`.

    -   Lower :setting:`DOWNLOAD_TIMEOUT` to a more reasonable value, to
        discard stuck requests more quickly.

    -   Set :setting:`REDIRECT_ENABLED` to ``False`` unless you want to follow
        redirects.
