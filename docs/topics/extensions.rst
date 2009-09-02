.. _topics-extensions:

==========
Extensions
==========

The extensions framework provide a mechanism for inserting your own
custom functionality into Scrapy. 

Extensions are just regular classes that are instantiated at Scrapy startup,
when extensions are initialized.

Extension settings
==================

Extensions use the :ref:`Scrapy settings <topics-settings>` to manage their
settings, just like any other Scrapy code.

It is customary for extensions to prefix their settings with their own name, to
avoid collision with existing (and future) extensions. For example, an
hypothetic extension to handle `Google Sitemaps`_ would use settings like
`GOOGLESITEMAP_ENABLED`, `GOOGLESITEMAP_DEPTH`, and so on.

.. _Google Sitemaps: http://en.wikipedia.org/wiki/Sitemaps

Loading & activating extensions
===============================

Extensions are loaded and activated at startup by instantiating a single
instance of the extension class. Therefore, all the extension initialization
code must be performed in the class constructor (``__init__`` method).

To make an extension available, add it to the :setting:`EXTENSIONS` setting in
your Scrapy settings. In :setting:`EXTENSIONS`, each extension is represented
by a string: the full Python path to the extension's class name. For example::

    EXTENSIONS = {
        'scrapy.stats.corestats.CoreStats': 500,
        'scrapy.management.web.WebConsole': 500,
        'scrapy.management.telnet.TelnetConsole': 500,
        'scrapy.contrib.webconsole.enginestatus.EngineStatus': 500,
        'scrapy.contrib.webconsole.stats.StatsDump': 500,
        'scrapy.contrib.debug.StackTraceDump': 500,
    }


As you can see, the :setting:`EXTENSIONS` setting is a dict where the keys are
the extension paths, and their values are the orders, which define the
extension *loading* order. Extensions orders are not as important as middleware
orders though, and they are typically irrelevant, ie. it doesn't matter in
which order the extensions are loaded because they don't depend on each other
[1].

However this feature can be exploited if you need to add an extension which
depends on other extension already loaded.

[1] This is is why the :setting:`EXTENSIONS_BASE` setting in Scrapy (which
contains all built-in extensions enabled by default) defines all the extensions
with the same order (``500``).

Available, enabled and disabled extensions
==========================================

Not all available extensions will be enabled. Some of them usually depend on a
particular setting. For example, the HTTP Cache extension is available by default
but disabled unless the :setting:`HTTPCACHE_DIR` setting is set.  Both enabled
and disabled extension can be accessed through the
:ref:`topics-extensions-ref-manager`.

Accessing enabled extensions
============================

Even though it's not usually needed, you can access extension objects through
the :ref:`topics-extensions-ref-manager` which is populated when extensions are
loaded.  For example, to access the ``WebConsole`` extension::

    from scrapy.extension import extensions
    webconsole_extension = extensions.enabled['WebConsole']

.. seealso::

    :ref:`topics-extensions-ref-manager`, for the complete Extension manager
    reference.

Writing your own extension
==========================

Writing your own extension is easy. Each extension is a single Python class
which doesn't need to implement any particular method. 

All extension initialization code must be performed in the class constructor
(``__init__`` method). If that method raises the
:exc:`~scrapy.core.exceptions.NotConfigured` exception, the extension will be
disabled. Otherwise, the extension will be enabled.

Let's take a look at the following example extension which just logs a message
everytime a domain/spider is opened and closed::

    from scrapy.xlib.pydispatch import dispatcher
    from scrapy.core import signals

    class SpiderOpenCloseLogging(object):

        def __init__(self):
            dispatcher.connect(self.domain_opened, signal=signals.domain_opened)
            dispatcher.connect(self.domain_closed, signal=signals.domain_closed)

        def domain_opened(self, domain, spider):
            log.msg("opened domain %s" % domain)

        def domain_closed(self, domain, spider):
            log.msg("closed domain %s" % domain)


.. _topics-extensions-ref:

Built-in extensions reference
=============================

.. _topics-extensions-ref-manager:

Extension manager
-----------------

.. module:: scrapy.extension
   :synopsis: The extension manager

The Extension Manager is responsible for loading and keeping track of installed
extensions and it's configured through the :setting:`EXTENSIONS` setting which
contains a dictionary of all available extensions and their order similar to
how you :ref:`configure the downloader middlewares
<topics-downloader-middleware-setting>`.

.. class:: ExtensionManager

    The extension manager is a singleton object, which is instantiated at module
    loading time and can be accessed like this::

        from scrapy.extension import extensions

    .. attribute:: loaded

        A boolean which is True if extensions are already loaded or False if
        they're not.

    .. attribute:: enabled

        A dict with the enabled extensions. The keys are the extension class names,
        and the values are the extension objects. Example::

            >>> from scrapy.extension import extensions
            >>> extensions.load()
            >>> print extensions.enabled
            {'CoreStats': <scrapy.stats.corestats.CoreStats object at 0x9e272ac>,
             'WebConsoke': <scrapy.management.telnet.TelnetConsole instance at 0xa05670c>,
            ...

    .. attribute:: disabled

        A dict with the disabled extensions. The keys are the extension class names,
        and the values are the extension class paths (because objects are never
        instantiated for disabled extensions). Example::

            >>> from scrapy.extension import extensions
            >>> extensions.load()
            >>> print extensions.disabled
            {'MemoryDebugger': 'scrapy.contrib.webconsole.stats.MemoryDebugger',
             'MyExtension': 'myproject.extensions.MyExtension',
            ...

    .. method:: load()

        Load the available extensions configured in the :setting:`EXTENSIONS`
        setting. On a standard run, this method is usually called by the Execution
        Manager, but you may need to call it explicitly if you're dealing with
        code outside Scrapy.

    .. method:: reload()

        Reload the available extensions. See :meth:`load`.

General purpose extensions
--------------------------

Core Stats extension
~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.stats.corestats
   :synopsis: Core stats collection

.. class:: scrapy.stats.corestats.CoreStats

Enable the collection of core statistics, provided the stats collection are
enabled (see :ref:`topics-stats`).

.. _topics-extensions-ref-webconsole:

Web console extension
~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.management.web
   :synopsis: Web management console 

.. class:: scrapy.management.web.WebConsole

Provides an extensible web server for managing a Scrapy process. It's enabled
by the :setting:`WEBCONSOLE_ENABLED` setting. The server will listen in the
port specified in :setting:`WEBCONSOLE_PORT`, and will log to the file
specified in :setting:`WEBCONSOLE_LOGFILE`.

The web server is designed to be extended by other extensions which can add
their own management web interfaces. 

See also :ref:`topics-webconsole` for information on how to write your own web
console extension, and "Web console extensions" below for a list of available
built-in (web console) extensions.

.. _topics-extensions-ref-telnetconsole:

Telnet console extension
~~~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.management.telnet
   :synopsis: Telnet management console 

.. class:: scrapy.management.telnet.TelnetConsole

Provides a telnet console for getting into a Python interpreter inside the
currently running Scrapy process, which can be very useful for debugging. 

The telnet console must be enabled by the :setting:`TELNETCONSOLE_ENABLED`
setting, and the server will listen in the port specified in
:setting:`WEBCONSOLE_PORT`.

.. _topics-extensions-ref-memusage:

Memory usage extension
~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.contrib.memusage
   :synopsis: Memory usage extension

.. class:: scrapy.contrib.memusage.MemoryUsage

Allows monitoring the memory used by a Scrapy process and:

1, send a notification email when it exceeds a certain value
2. terminate the Scrapy process when it exceeds a certain value 

The notification emails can be triggered when a certain warning value is
reached (:setting:`MEMUSAGE_WARNING_MB`) and when the maximum value is reached
(:setting:`MEMUSAGE_LIMIT_MB`) which will also cause the Scrapy process to be
terminated.

This extension is enabled by the :setting:`MEMUSAGE_ENABLED` setting and
can be configured with the following settings:

* :setting:`MEMUSAGE_LIMIT_MB`
* :setting:`MEMUSAGE_WARNING_MB`
* :setting:`MEMUSAGE_NOTIFY_MAIL`
* :setting:`MEMUSAGE_REPORT`

Memory debugger extension
~~~~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.contrib.memdebug
   :synopsis: Memory debugger extension

.. class:: scrapy.contrib.memdebug.MemoryDebugger

A memory debugger which collects some info about objects uncollected by the
garbage collector and libxml2 memory leaks. To enable this extension turn on
the :setting:`MEMDEBUG_ENABLED` setting. The report will be printed to standard
output. If the :setting:`MEMDEBUG_NOTIFY` setting contains a list of emails the
report will also be sent to those addresses.

Close domain extension
~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.contrib.closedomain
   :synopsis: Close domain extension

.. class:: scrapy.contrib.closedomain.CloseDomain

Closes a domain/spider automatically when some conditions are met, using a
specific closing reason for each condition.

The conditions for closing a domain can be configured through the following
settings. Other conditions will be supported in the future.

.. setting:: CLOSEDOMAIN_TIMEOUT

CLOSEDOMAIN_TIMEOUT
"""""""""""""""""""

Default: ``0``

An integer which specifies a number of seconds. If the domain remains open for
more than that number of second, it will be automatically closed with the
reason ``closedomain_timeout``. If zero (or non set) domains won't be closed by
timeout.

.. setting:: CLOSEDOMAIN_ITEMPASSED

CLOSEDOMAIN_ITEMPASSED
""""""""""""""""""""""

Default: ``0``

An integer which specifies a number of items. If the spider scrapes more than
that amount if items and those items are passed by the item pipeline, the
domain will be closed with the reason ``closedomain_itempassed``. If zero (or
non set) domains won't be closed by number of passed items.

Stack trace dump extension
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.contrib.debug
   :synopsis: Extensions for debugging Scrapy

.. class:: scrapy.contrib.debug.StackTraceDump

Adds a `SIGUSR1`_ signal handler which dumps the stack trace of a runnning
Scrapy process when a ``SIGUSR1`` signal is catched. After the stack trace is
dumped, the Scrapy process continues to run normally.

The stack trace is sent to standard output, or to the Scrapy log file if
:setting:`LOG_STDOUT` is enabled.

This extension only works on POSIX-compliant platforms (ie. not Windows).

.. _SIGUSR1: http://en.wikipedia.org/wiki/SIGUSR1_and_SIGUSR2

StatsMailer extension
~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.contrib.statsmailer
   :synopsis: StatsMailer extension

.. class:: scrapy.contrib.statsmailer.StatsMailer

This simple extension can be used to send a notification email every time a
domain has finished scraping, including the Scrapy stats collected. The email
will be sent to all recipients specified in the :setting:`STATSMAILER_RCPTS`
setting.

Web console extensions
----------------------

.. module:: scrapy.contrib.webconsole
   :synopsis: Contains most built-in web console extensions

Here is a list of built-in web console extensions. For clarity "web console
extension" is abbreviated as "WC extension".

For more information see the see the :ref:`web console documentation
<topics-webconsole>`.

Scheduler queue WC extension
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.contrib.webconsole.scheduler
   :synopsis: Scheduler queue web console extension

.. class:: scrapy.contrib.webconsole.scheduler.SchedulerQueue

Display a list of all pending Requests in the Scheduler queue, grouped by
domain/spider.

Spider live stats WC extension
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.contrib.webconsole.livestats
   :synopsis: Spider live stats web console extension

.. class:: scrapy.contrib.webconsole.livestats.LiveStats

Display a table with stats of all spider crawled by the current Scrapy run,
including:

* Number of items scraped
* Number of pages crawled
* Number of pending requests in the scheduler
* Number of pending requests in the downloader queue
* Number of requests currently being downloaded

Engine status WC extension
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.contrib.webconsole.enginestatus
   :synopsis: Engine status web console extension

.. class:: scrapy.contrib.webconsole.enginestatus.EngineStatus

Display the current status of the Scrapy Engine, which is just the output of
the Scrapy engine ``getstatus()`` method.

Stats collector dump WC extension 
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.contrib.webconsole.stats
   :synopsis: Stats dump web console extension

.. class:: scrapy.contrib.webconsole.stats.StatsDump

Display the stats collected so far by the stats collector.

