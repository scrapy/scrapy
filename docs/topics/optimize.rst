.. _optimize:

============
Optimization
============

Scrapy offers different ways to speed up crawls for specific :ref:`use cases
<broad-crawls>` and to :ref:`lower resource usage <optimize-resources>`.

.. _broad-crawls:
.. _topics-broad-crawls:

Speeding up broad crawls
========================

While Scrapy is well suited for **broad crawls**, i.e. crawls that target many
websites, the default :ref:`settings <topics-settings>` are optimized for
crawls targetting a single website.

For broad crawls, consider these adjustments:

-   .. _broad-crawls-concurrency:

    Increase the global concurrency:

    -   Set :setting:`CONCURRENT_REQUESTS` as close to
        :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` × [number of target domains]
        (e.g. 8 × 10 domains = 80 concurrent requests) as your CPU and memory
        allow.

    -   Increase :setting:`SCRAPER_SLOT_MAX_ACTIVE_SIZE` when increasing
        :setting:`CONCURRENT_REQUESTS` stops making a difference.

    If your CPU or memory become a bottleneck, see :ref:`optimize-resources`.

-   Optimize request scheduling:

    -   .. _broad-crawls-scheduler-priority-queue:

        Set :setting:`SCHEDULER_PRIORITY_QUEUE` to
        :class:`~scrapy.pqueues.DownloaderAwarePriorityQueue`.

    -   .. _broad-crawls-bfo:

        If memory is a bottleneck, see if :ref:`crawling in breadth-first order
        (BFO) <faq-bfo-dfo>` lowers memory usage.

-   Improve DNS resolution speed:

    -   Set up your own DNS server, with a local cache and upstream to a `large
        DNS server`_, to avoid slowing down your network.

        .. _large DNS server: https://en.wikipedia.org/wiki/Public_recursive_name_server#Notable_public_DNS_service_operators

    -   Increase :setting:`REACTOR_THREADPOOL_MAXSIZE` to the minimum value
        that avoids DNS resolution timeouts and makes a noticeable positive
        impact in crawl speed.

-   Lower the negative impact of some responses:

    -   Set :setting:`RETRY_ENABLED` to ``False`` or, if you need retries,
        consider lowering :setting:`RETRY_TIMES` and fine-tuning other
        :ref:`retry settings <retry-settings>`.

    -   Lower :setting:`DOWNLOAD_TIMEOUT` to a more reasonable value, to
        discard stuck requests more quickly.

    -   Set :setting:`REDIRECT_ENABLED` to ``False`` unless you want to follow
        redirects.


.. _optimize-resources:

Lowering resource usage
=======================

.. _optimize-memory:

Lowering memory usage
---------------------

-   Lower :setting:`SCRAPER_SLOT_MAX_ACTIVE_SIZE`.

-   Lower the number of :ref:`scheduled requests <topics-scheduler>` held in
    memory:

    -   Increase the :attr:`~scrapy.Request.priority` of requests whose
        :attr:`~scrapy.Request.callback` cannot yield additional
        requests.

    -   If you have multiple :ref:`start requests <start-requests>`, consider
        :ref:`lazy <start-requests-lazy>` or :ref:`idle <start-requests-idle>`
        scheduling.

    -   Set :setting:`JOBDIR` to offload all scheduled requests to disk.

-   Be in the lookout for :ref:`memory leaks <topics-leaks>`.


Lowering network usage
----------------------

-   Install brotli_ and zstandard_ to support brotli-compressed_ and
    zstd-compressed_ responses.

    .. _brotli-compressed: https://www.ietf.org/rfc/rfc7932.txt
    .. _brotli: https://pypi.org/project/Brotli/
    .. _zstd-compressed: https://www.ietf.org/rfc/rfc8478.txt
    .. _zstandard: https://pypi.org/project/zstandard/


Lowering CPU usage
------------------

-   Set :setting:`LOG_LEVEL` to ``"INFO"`` or higher.


Other tips
----------

-   Try :ref:`using the asyncio reactor <install-asyncio>`, installing
    :doc:`uvloop <uvloop:index>` and setting :setting:`ASYNCIO_EVENT_LOOP` to
    :class:`uvloop.Loop`.

    Alternatively, try switching :setting:`TWISTED_REACTOR` to :doc:`some other
    reactor <core/howto/choosing-reactor>`.

-   Disable unused :ref:`components <topics-components>`.

    For example, set :setting:`COOKIES_ENABLED` to ``False`` unless you need
    cookies.
