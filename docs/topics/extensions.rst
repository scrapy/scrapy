.. _topics-extensions:

==========
Extensions
==========

The extensions framework provides a mechanism for inserting your own
custom functionality into Scrapy.

Extensions are just regular classes that are instantiated at Scrapy startup,
when extensions are initialized.

Extension settings
==================

Extensions use the :ref:`Scrapy settings <topics-settings>` to manage their
settings, just like any other Scrapy code.

It is customary for extensions to prefix their settings with their own name, to
avoid collision with existing (and future) extensions. For example, a
hypothetic extension to handle `Google Sitemaps`_ would use settings like
``GOOGLESITEMAP_ENABLED``, ``GOOGLESITEMAP_DEPTH``, and so on.

.. _Google Sitemaps: https://en.wikipedia.org/wiki/Sitemaps

Loading & activating extensions
===============================

Extensions are loaded and activated at startup by instantiating a single
instance of the extension class. Therefore, all the extension initialization
code must be performed in the class ``__init__`` method.

To make an extension available, add it to the :setting:`EXTENSIONS` setting in
your Scrapy settings. In :setting:`EXTENSIONS`, each extension is represented
by a string: the full Python path to the extension's class name. For example::

    EXTENSIONS = {
        'scrapy.extensions.corestats.CoreStats': 500,
        'scrapy.extensions.telnet.TelnetConsole': 500,
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
``None``. For example::

    EXTENSIONS = {
        'scrapy.extensions.corestats.CoreStats': None,
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

Here is the code of such extension::

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
            if not crawler.settings.getbool('MYEXT_ENABLED'):
                raise NotConfigured

            # get the number of items from settings
            item_count = crawler.settings.getint('MYEXT_ITEMCOUNT', 1000)

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
* :setting:`CLOSESPIDER_ITEMCOUNT`
* :setting:`CLOSESPIDER_PAGECOUNT`
* :setting:`CLOSESPIDER_ERRORCOUNT`

.. setting:: CLOSESPIDER_TIMEOUT

CLOSESPIDER_TIMEOUT
"""""""""""""""""""

Default: ``0``

An integer which specifies a number of seconds. If the spider remains open for
more than that number of second, it will be automatically closed with the
reason ``closespider_timeout``. If zero (or non set), spiders won't be closed by
timeout.

.. setting:: CLOSESPIDER_ITEMCOUNT

CLOSESPIDER_ITEMCOUNT
"""""""""""""""""""""

Default: ``0``

An integer which specifies a number of items. If the spider scrapes more than
that amount and those items are passed by the item pipeline, the
spider will be closed with the reason ``closespider_itemcount``.
Requests which  are currently in the downloader queue (up to
:setting:`CONCURRENT_REQUESTS` requests) are still processed.
If zero (or non set), spiders won't be closed by number of passed items.

.. setting:: CLOSESPIDER_PAGECOUNT

CLOSESPIDER_PAGECOUNT
"""""""""""""""""""""

.. versionadded:: 0.11

Default: ``0``

An integer which specifies the maximum number of responses to crawl. If the spider
crawls more than that, the spider will be closed with the reason
``closespider_pagecount``. If zero (or non set), spiders won't be closed by
number of crawled responses.

.. setting:: CLOSESPIDER_ERRORCOUNT

CLOSESPIDER_ERRORCOUNT
""""""""""""""""""""""

.. versionadded:: 0.11

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

.. module:: scrapy.extensions.debug
   :synopsis: Extensions for debugging Scrapy

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

For more info see `Debugging in Python`_.

This extension only works on POSIX-compliant platforms (i.e. not Windows).

.. _Debugging in Python: https://pythonconquerstheuniverse.wordpress.com/2009/09/10/debugging-in-python/
