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
`GOOGLESITEMAP_ENABLED`, `GOOGLESITEMAP_DEPTH`, and so on.

.. _Google Sitemaps: https://en.wikipedia.org/wiki/Sitemaps

Loading & activating extensions
===============================

Extensions are loaded and activated at startup by instantiating a single
instance of the extension class. Therefore, all the extension initialization
code must be performed in the class constructor (``__init__`` method).

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

In order to disable an extension that comes enabled by default (ie. those
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

    class SpiderOpenCloseLogging(object):

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

.. autoclass:: scrapy.extensions.logstats.LogStats


Core Stats extension
~~~~~~~~~~~~~~~~~~~~

.. autoclass:: scrapy.extensions.corestats.CoreStats


.. _topics-extensions-ref-telnetconsole:

Telnet console extension
~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: scrapy.extensions.telnet.TelnetConsole


.. _topics-extensions-ref-memusage:

Memory usage extension
~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: scrapy.extensions.memusage.MemoryUsage


Memory debugger extension
~~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: scrapy.extensions.memdebug.MemoryDebugger


Close spider extension
~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: scrapy.extensions.closespider.CloseSpider


StatsMailer extension
~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: scrapy.extensions.statsmailer.StatsMailer


Debugging extensions
--------------------

Stack trace dump extension
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: scrapy.extensions.debug.StackTraceDump


Debugger extension
~~~~~~~~~~~~~~~~~~

.. autoclass:: scrapy.extensions.debug.Debugger
