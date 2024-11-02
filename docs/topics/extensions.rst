.. _topics-extensions:

==========
Extensions
==========

The extensions framework provides a mechanism for inserting your own
custom functionality into Scrapy.

Extensions are just regular classes.

Extension settings
==================

Extensions use the :ref:`Scrapy settings <topics-settings>` to manage their
settings, just like any other Scrapy code.

It is customary for extensions to prefix their settings with their own name, to
avoid collision with existing (and future) extensions. For example, a
hypothetical extension to handle `Google Sitemaps`_ would use settings like
``GOOGLESITEMAP_ENABLED``, ``GOOGLESITEMAP_DEPTH``, and so on.

.. _Google Sitemaps: https://en.wikipedia.org/wiki/Sitemaps

Loading & activating extensions
===============================

Extensions are loaded and activated at startup by instantiating a single
instance of the extension class per spider being run. All the extension
initialization code must be performed in the class ``__init__`` method.

To make an extension available, add it to the :setting:`EXTENSIONS` setting in
your Scrapy settings. In :setting:`EXTENSIONS`, each extension is represented
by a string: the full Python path to the extension's class name. For example:

.. code-block:: python

    EXTENSIONS = {
        "scrapy.extensions.corestats.CoreStats": 500,
        "scrapy.extensions.telnet.TelnetConsole": 500,
    }


As you can see, the :setting:`EXTENSIONS` setting is a dict where the keys are
the extension paths, and their values are the orders, which define the
extension *loading* order. The :setting:`EXTENSIONS` setting is merged with the
:setting:`EXTENSIONS_BASE` setting defined in Scrapy (and not meant to be
overridden) and then sorted by order to get the final sorted list of enabled
extensions.

As extensions typically do not depend on each other, their loading order is
irrelevant in most cases. This is why the :setting:`EXTENSIONS_BASE` setting
defines all extensions with the same order (``0``). However, this feature can
be exploited if you need to add an extension which depends on other extensions
already loaded.

Available, enabled and disabled extensions
==========================================

Not all available extensions will be enabled. Some of them usually depend on a
particular setting. For example, the HTTP Cache extension is available by default
but disabled unless the :setting:`HTTPCACHE_ENABLED` setting is set.

Disabling an extension
======================

In order to disable an extension that comes enabled by default (i.e. those
included in the :setting:`EXTENSIONS_BASE` setting) you must set its order to
``None``. For example:

.. code-block:: python

    EXTENSIONS = {
        "scrapy.extensions.corestats.CoreStats": None,
    }

Writing your own extension
==========================

Each extension is a Python class. The main entry point for a Scrapy extension
(this also includes middlewares and pipelines) is the ``from_crawler``
class method which receives a ``Crawler`` instance. Through the Crawler object
you can access settings, signals, stats, and also control the crawling behaviour.

Typically, extensions connect to :ref:`signals <topics-signals>` and perform
tasks triggered by them.

Finally, if the ``from_crawler`` method raises the
:exc:`~scrapy.exceptions.NotConfigured` exception, the extension will be
disabled. Otherwise, the extension will be enabled.

Sample extension
----------------

Here we will implement a simple extension to illustrate the concepts described
in the previous section. This extension will log a message every time:

* a spider is opened
* a spider is closed
* a specific number of items are scraped

The extension will be enabled through the ``MYEXT_ENABLED`` setting and the
number of items will be specified through the ``MYEXT_ITEMCOUNT`` setting.

Here is the code of such extension:

.. code-block:: python

    import logging
    from scrapy import signals
    from scrapy.exceptions import NotConfigured

    logger = logging.getLogger(__name__)


    class SpiderOpenCloseLogging:
        def __init__(self, item_count):
            self.item_count = item_count
            self.items_scraped = 0

        @classmethod
        def from_crawler(cls, crawler):
            # first check if the extension should be enabled and raise
            # NotConfigured otherwise
            if not crawler.settings.getbool("MYEXT_ENABLED"):
                raise NotConfigured

            # get the number of items from settings
            item_count = crawler.settings.getint("MYEXT_ITEMCOUNT", 1000)

            # instantiate the extension object
            ext = cls(item_count)

            # connect the extension object to signals
            crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
            crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
            crawler.signals.connect(ext.item_scraped, signal=signals.item_scraped)

            # return the extension object
            return ext

        def spider_opened(self, spider):
            logger.info("opened spider %s", spider.name)

        def spider_closed(self, spider):
            logger.info("closed spider %s", spider.name)

        def item_scraped(self, item, spider):
            self.items_scraped += 1
            if self.items_scraped % self.item_count == 0:
                logger.info("scraped %d items", self.items_scraped)


.. _topics-extensions-ref:

Built-in extensions reference
=============================

General purpose extensions
--------------------------

Log Stats extension
~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.extensions.logstats
   :synopsis: Basic stats logging

.. class:: LogStats

Log basic stats like crawled pages and scraped items.

Core Stats extension
~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.extensions.corestats
   :synopsis: Core stats collection

.. class:: CoreStats

Enable the collection of core statistics, provided the stats collection is
enabled (see :ref:`topics-stats`).

.. _topics-extensions-ref-telnetconsole:

Telnet console extension
~~~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.extensions.telnet
   :synopsis: Telnet console

.. class:: TelnetConsole

Provides a telnet console for getting into a Python interpreter inside the
currently running Scrapy process, which can be very useful for debugging.

The telnet console must be enabled by the :setting:`TELNETCONSOLE_ENABLED`
setting, and the server will listen in the port specified in
:setting:`TELNETCONSOLE_PORT`.

.. _topics-extensions-ref-memusage:

Memory usage extension
~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.extensions.memusage
   :synopsis: Memory usage extension

.. class:: MemoryUsage

.. note:: This extension does not work in Windows.

Monitors the memory used by the Scrapy process that runs the spider and:

1. sends a notification e-mail when it exceeds a certain value
2. closes the spider when it exceeds a certain value

The notification e-mails can be triggered when a certain warning value is
reached (:setting:`MEMUSAGE_WARNING_MB`) and when the maximum value is reached
(:setting:`MEMUSAGE_LIMIT_MB`) which will also cause the spider to be closed
and the Scrapy process to be terminated.

This extension is enabled by the :setting:`MEMUSAGE_ENABLED` setting and
can be configured with the following settings:

* :setting:`MEMUSAGE_LIMIT_MB`
* :setting:`MEMUSAGE_WARNING_MB`
* :setting:`MEMUSAGE_NOTIFY_MAIL`
* :setting:`MEMUSAGE_CHECK_INTERVAL_SECONDS`

Memory debugger extension
~~~~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.extensions.memdebug
   :synopsis: Memory debugger extension

.. class:: MemoryDebugger

An extension for debugging memory usage. It collects information about:

* objects uncollected by the Python garbage collector
* objects left alive that shouldn't. For more info, see :ref:`topics-leaks-trackrefs`

To enable this extension, turn on the :setting:`MEMDEBUG_ENABLED` setting. The
info will be stored in the stats.

.. _topics-extensions-ref-spiderstate:

Spider state extension
~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.extensions.spiderstate
   :synopsis: Spider state extension

.. class:: SpiderState

Manages spider state data by loading it before a crawl and saving it after.

Give a value to the :setting:`JOBDIR` setting to enable this extension.
When enabled, this extension manages the :attr:`~scrapy.Spider.state` 
attribute of your :class:`~scrapy.Spider` instance:
    
-   When your spider closes (:signal:`spider_closed`), the contents of its 
    :attr:`~scrapy.Spider.state` attribute are serialized into a file named 
    ``spider.state`` in the :setting:`JOBDIR` folder.
-   When your spider opens (:signal:`spider_opened`), if a previously-generated 
    ``spider.state`` file exists in the :setting:`JOBDIR` folder, it is loaded 
    into the :attr:`~scrapy.Spider.state` attribute.


For an example, see :ref:`topics-keeping-persistent-state-between-batches`.

Close spider extension
~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.extensions.closespider
   :synopsis: Close spider extension

.. class:: CloseSpider

Closes a spider automatically when some conditions are met, using a specific
closing reason for each condition.

The conditions for closing a spider can be configured through the following
settings:

* :setting:`CLOSESPIDER_TIMEOUT`
* :setting:`CLOSESPIDER_TIMEOUT_NO_ITEM`
* :setting:`CLOSESPIDER_ITEMCOUNT`
* :setting:`CLOSESPIDER_PAGECOUNT`
* :setting:`CLOSESPIDER_ERRORCOUNT`

.. note::

   When a certain closing condition is met, requests which are 
   currently in the downloader queue (up to :setting:`CONCURRENT_REQUESTS` 
   requests) are still processed.

.. setting:: CLOSESPIDER_TIMEOUT

CLOSESPIDER_TIMEOUT
"""""""""""""""""""

Default: ``0``

An integer which specifies a number of seconds. If the spider remains open for
more than that number of second, it will be automatically closed with the
reason ``closespider_timeout``. If zero (or non set), spiders won't be closed by
timeout.

.. setting:: CLOSESPIDER_TIMEOUT_NO_ITEM

CLOSESPIDER_TIMEOUT_NO_ITEM
"""""""""""""""""""""""""""

Default: ``0``

An integer which specifies a number of seconds. If the spider has not produced
any items in the last number of seconds, it will be closed with the reason
``closespider_timeout_no_item``. If zero (or non set), spiders won't be closed
regardless if it hasn't produced any items.

.. setting:: CLOSESPIDER_ITEMCOUNT

CLOSESPIDER_ITEMCOUNT
"""""""""""""""""""""

Default: ``0``

An integer which specifies a number of items. If the spider scrapes more than
that amount and those items are passed by the item pipeline, the
spider will be closed with the reason ``closespider_itemcount``.
If zero (or non set), spiders won't be closed by number of passed items.

.. setting:: CLOSESPIDER_PAGECOUNT

CLOSESPIDER_PAGECOUNT
"""""""""""""""""""""

Default: ``0``

An integer which specifies the maximum number of responses to crawl. If the spider
crawls more than that, the spider will be closed with the reason
``closespider_pagecount``. If zero (or non set), spiders won't be closed by
number of crawled responses.

.. setting:: CLOSESPIDER_PAGECOUNT_NO_ITEM

CLOSESPIDER_PAGECOUNT_NO_ITEM
"""""""""""""""""""""""""""""

Default: ``0``

An integer which specifies the maximum number of consecutive responses to crawl
without items scraped. If the spider crawls more consecutive responses than that
and no items are scraped in the meantime, the spider will be closed with the
reason ``closespider_pagecount_no_item``. If zero (or not set), spiders won't be
closed by number of crawled responses with no items.

.. setting:: CLOSESPIDER_ERRORCOUNT

CLOSESPIDER_ERRORCOUNT
""""""""""""""""""""""

Default: ``0``

An integer which specifies the maximum number of errors to receive before
closing the spider. If the spider generates more than that number of errors,
it will be closed with the reason ``closespider_errorcount``. If zero (or non
set), spiders won't be closed by number of errors.

StatsMailer extension
~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.extensions.statsmailer
   :synopsis: StatsMailer extension

.. class:: StatsMailer

This simple extension can be used to send a notification e-mail every time a
domain has finished scraping, including the Scrapy stats collected. The email
will be sent to all recipients specified in the :setting:`STATSMAILER_RCPTS`
setting.

Emails can be sent using the :class:`~scrapy.mail.MailSender` class. To see a
full list of parameters, including examples on how to instantiate
:class:`~scrapy.mail.MailSender` and use mail settings, see
:ref:`topics-email`.

.. module:: scrapy.extensions.debug
   :synopsis: Extensions for debugging Scrapy

.. module:: scrapy.extensions.periodic_log
   :synopsis: Periodic stats logging

Periodic log extension
~~~~~~~~~~~~~~~~~~~~~~

.. class:: PeriodicLog

This extension periodically logs rich stat data as a JSON object::

    2023-08-04 02:30:57 [scrapy.extensions.logstats] INFO: Crawled 976 pages (at 162 pages/min), scraped 925 items (at 161 items/min)
    2023-08-04 02:30:57 [scrapy.extensions.periodic_log] INFO: {
        "delta": {
            "downloader/request_bytes": 55582,
            "downloader/request_count": 162,
            "downloader/request_method_count/GET": 162,
            "downloader/response_bytes": 618133,
            "downloader/response_count": 162,
            "downloader/response_status_count/200": 162,
            "item_scraped_count": 161
        },
        "stats": {
            "downloader/request_bytes": 338243,
            "downloader/request_count": 992,
            "downloader/request_method_count/GET": 992,
            "downloader/response_bytes": 3836736,
            "downloader/response_count": 976,
            "downloader/response_status_count/200": 976,
            "item_scraped_count": 925,
            "log_count/INFO": 21,
            "log_count/WARNING": 1,
            "scheduler/dequeued": 992,
            "scheduler/dequeued/memory": 992,
            "scheduler/enqueued": 1050,
            "scheduler/enqueued/memory": 1050
        },
        "time": {
            "elapsed": 360.008903,
            "log_interval": 60.0,
            "log_interval_real": 60.006694,
            "start_time": "2023-08-03 23:24:57",
            "utcnow": "2023-08-03 23:30:57"
        }
    }

This extension logs the following configurable sections:

-   ``"delta"`` shows how some numeric stats have changed since the last stats
    log message.

    The :setting:`PERIODIC_LOG_DELTA` setting determines the target stats. They
    must have ``int`` or ``float`` values.

-   ``"stats"`` shows the current value of some stats.

    The :setting:`PERIODIC_LOG_STATS` setting determines the target stats.

-   ``"time"`` shows detailed timing data.

    The :setting:`PERIODIC_LOG_TIMING_ENABLED` setting determines whether or
    not to show this section.

This extension logs data at the start, then on a fixed time interval
configurable through the :setting:`LOGSTATS_INTERVAL` setting, and finally
right before the crawl ends.


Example extension configuration:

.. code-block:: python

    custom_settings = {
        "LOG_LEVEL": "INFO",
        "PERIODIC_LOG_STATS": {
            "include": ["downloader/", "scheduler/", "log_count/", "item_scraped_count/"],
        },
        "PERIODIC_LOG_DELTA": {"include": ["downloader/"]},
        "PERIODIC_LOG_TIMING_ENABLED": True,
        "EXTENSIONS": {
            "scrapy.extensions.periodic_log.PeriodicLog": 0,
        },
    }

.. setting:: PERIODIC_LOG_DELTA

PERIODIC_LOG_DELTA
""""""""""""""""""

Default: ``None``

* ``"PERIODIC_LOG_DELTA": True`` - show deltas for all ``int`` and ``float`` stat values.
* ``"PERIODIC_LOG_DELTA": {"include": ["downloader/", "scheduler/"]}`` - show deltas for stats with names containing any configured substring.
* ``"PERIODIC_LOG_DELTA": {"exclude": ["downloader/"]}`` - show deltas for all stats with names not containing any configured substring.

.. setting:: PERIODIC_LOG_STATS

PERIODIC_LOG_STATS
""""""""""""""""""

Default: ``None``

* ``"PERIODIC_LOG_STATS": True`` - show the current value of all stats.
* ``"PERIODIC_LOG_STATS": {"include": ["downloader/", "scheduler/"]}`` - show current values for stats with names containing any configured substring.
* ``"PERIODIC_LOG_STATS": {"exclude": ["downloader/"]}`` - show current values for all stats with names not containing any configured substring.


.. setting:: PERIODIC_LOG_TIMING_ENABLED

PERIODIC_LOG_TIMING_ENABLED
"""""""""""""""""""""""""""

Default: ``False``

``True`` enables logging of timing data (i.e. the ``"time"`` section).


Debugging extensions
--------------------

Stack trace dump extension
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. class:: StackTraceDump

Dumps information about the running process when a `SIGQUIT`_ or `SIGUSR2`_
signal is received. The information dumped is the following:

1. engine status (using ``scrapy.utils.engine.get_engine_status()``)
2. live references (see :ref:`topics-leaks-trackrefs`)
3. stack trace of all threads

After the stack trace and engine status is dumped, the Scrapy process continues
running normally.

This extension only works on POSIX-compliant platforms (i.e. not Windows),
because the `SIGQUIT`_ and `SIGUSR2`_ signals are not available on Windows.

There are at least two ways to send Scrapy the `SIGQUIT`_ signal:

1. By pressing Ctrl-\ while a Scrapy process is running (Linux only?)
2. By running this command (assuming ``<pid>`` is the process id of the Scrapy
   process)::

    kill -QUIT <pid>

.. _SIGUSR2: https://en.wikipedia.org/wiki/SIGUSR1_and_SIGUSR2
.. _SIGQUIT: https://en.wikipedia.org/wiki/SIGQUIT

Debugger extension
~~~~~~~~~~~~~~~~~~

.. class:: Debugger

Invokes a :doc:`Python debugger <library/pdb>` inside a running Scrapy process when a `SIGUSR2`_
signal is received. After the debugger is exited, the Scrapy process continues
running normally.

This extension only works on POSIX-compliant platforms (i.e. not Windows).
