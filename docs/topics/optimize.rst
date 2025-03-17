.. _optimize:

=============
Optimizations
=============

Scrapy offers different ways to optimize crawls based on :ref:`resource
constraints <optimize-resources>` and :ref:`use cases <broad-crawls>`.

.. _optimize-resources:

Lowering resource usage
=======================

…

..
    TODO:
        Network input and output
            optional compression packages


.. _broad-crawls:
.. _topics-broad-crawls:

Optimizing broad crawls
=======================

While Scrapy is well suited for **broad crawls**, i.e. crawls that target many
websites, the default :ref:`settings <topics-settings>` are optimized for
crawls targetting a single website.

For broad crawls, consider these adjustments:

.. _broad-crawls-scheduler-priority-queue:

-   Set :setting:`SCHEDULER_PRIORITY_QUEUE` to
    :class:`~scrapy.pqueues.DownloaderAwarePriorityQueue`.

.. _broad-crawls-concurrency:

Increase concurrency
--------------------

Concurrency is the number of requests that are processed in parallel. There is
a global limit (:setting:`CONCURRENT_REQUESTS`) and an additional limit that
can be set either per domain (:setting:`CONCURRENT_REQUESTS_PER_DOMAIN`) or per
IP (:setting:`CONCURRENT_REQUESTS_PER_IP`).

.. note:: The scheduler priority queue :ref:`recommended for broad crawls
          <broad-crawls-scheduler-priority-queue>` does not support
          :setting:`CONCURRENT_REQUESTS_PER_IP`.

The default global concurrency limit in Scrapy is not suitable for crawling
many different domains in parallel, so you will want to increase it. How much
to increase it will depend on how much CPU and memory your crawler will have
available.

A good starting point is ``100``:

.. code-block:: python

    CONCURRENT_REQUESTS = 100

But the best way to find out is by doing some trials and identifying at what
concurrency your Scrapy process gets CPU bounded. For optimum performance, you
should pick a concurrency where CPU usage is at 80-90%.

Increasing concurrency also increases memory usage. If memory usage is a
concern, you might need to lower your global concurrency limit accordingly.


Increase Twisted IO thread pool maximum size
--------------------------------------------

Currently Scrapy does DNS resolution in a blocking way with usage of thread
pool. With higher concurrency levels the crawling could be slow or even fail
hitting DNS resolver timeouts. Possible solution to increase the number of
threads handling DNS queries. The DNS queue will be processed faster speeding
up establishing of connection and crawling overall.

To increase maximum thread pool size use:

.. code-block:: python

    REACTOR_THREADPOOL_MAXSIZE = 20

Setup your own DNS
------------------

If you have multiple crawling processes and single central DNS, it can act
like DoS attack on the DNS server resulting to slow down of entire network or
even blocking your machines. To avoid this setup your own DNS server with
local cache and upstream to some large DNS like OpenDNS or Verizon.

Reduce log level
----------------

When doing broad crawls you are often only interested in the crawl rates you
get and any errors found. These stats are reported by Scrapy when using the
``INFO`` log level. In order to save CPU (and log storage requirements) you
should not use ``DEBUG`` log level when performing large broad crawls in
production. Using ``DEBUG`` level when developing your (broad) crawler may be
fine though.

To set the log level use:

.. code-block:: python

    LOG_LEVEL = "INFO"

Disable cookies
---------------

Disable cookies unless you *really* need. Cookies are often not needed when
doing broad crawls (search engine crawlers ignore them), and they improve
performance by saving some CPU cycles and reducing the memory footprint of your
Scrapy crawler.

To disable cookies use:

.. code-block:: python

    COOKIES_ENABLED = False

Disable retries
---------------

Retrying failed HTTP requests can slow down the crawls substantially, specially
when sites causes are very slow (or fail) to respond, thus causing a timeout
error which gets retried many times, unnecessarily, preventing crawler capacity
to be reused for other domains.

To disable retries use:

.. code-block:: python

    RETRY_ENABLED = False

Reduce download timeout
-----------------------

Unless you are crawling from a very slow connection (which shouldn't be the
case for broad crawls) reduce the download timeout so that stuck requests are
discarded quickly and free up capacity to process the next ones.

To reduce the download timeout use:

.. code-block:: python

    DOWNLOAD_TIMEOUT = 15

Disable redirects
-----------------

Consider disabling redirects, unless you are interested in following them. When
doing broad crawls it's common to save redirects and resolve them when
revisiting the site at a later crawl. This also help to keep the number of
request constant per crawl batch, otherwise redirect loops may cause the
crawler to dedicate too many resources on any specific domain.

To disable redirects use:

.. code-block:: python

    REDIRECT_ENABLED = False

.. _broad-crawls-bfo:

Crawl in BFO order
------------------

:ref:`Scrapy crawls in DFO order by default <faq-bfo-dfo>`.

In broad crawls, however, page crawling tends to be faster than page
processing. As a result, unprocessed early requests stay in memory until the
final depth is reached, which can significantly increase memory usage.

:ref:`Crawl in BFO order <faq-bfo-dfo>` instead to save memory.


Be mindful of memory leaks
--------------------------

If your broad crawl shows a high memory usage, in addition to :ref:`crawling in
BFO order <broad-crawls-bfo>` and :ref:`lowering concurrency
<broad-crawls-concurrency>` you should :ref:`debug your memory leaks
<topics-leaks>`.


Install a specific Twisted reactor
----------------------------------

If the crawl is exceeding the system's capabilities, you might want to try
installing a specific Twisted reactor, via the :setting:`TWISTED_REACTOR` setting.
