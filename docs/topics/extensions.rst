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
        'scrapy.contrib.corestats.CoreStats': 500,
        'scrapy.webservice.WebService': 500,
        'scrapy.telnet.TelnetConsole': 500,
    }


As you can see, the :setting:`EXTENSIONS` setting is a dict where the keys are
the extension paths, and their values are the orders, which define the
extension *loading* order. Extensions orders are not as important as middleware
orders though, and they are typically irrelevant, ie. it doesn't matter in
which order the extensions are loaded because they don't depend on each other
[1].

However, this feature can be exploited if you need to add an extension which
depends on other extensions already loaded.

[1] This is is why the :setting:`EXTENSIONS_BASE` setting in Scrapy (which
contains all built-in extensions enabled by default) defines all the extensions
with the same order (``500``).

Available, enabled and disabled extensions
==========================================

Not all available extensions will be enabled. Some of them usually depend on a
particular setting. For example, the HTTP Cache extension is available by default
but disabled unless the :setting:`HTTPCACHE_DIR` setting is set.  Both enabled
and disabled extensions can be accessed through the
:ref:`topics-extensions-ref-manager`.

Accessing enabled extensions
============================

Even though it's not usually needed, you can access extension objects through
the :ref:`topics-extensions-ref-manager` which is populated when extensions are
loaded.  For example, to access the ``WebService`` extension::

    from scrapy.project import extensions
    webservice_extension = extensions.enabled['WebService']

.. see also::

    :ref:`topics-extensions-ref-manager`, for the complete Extension Manager
    reference.

Writing your own extension
==========================

Writing your own extension is easy. Each extension is a single Python class
which doesn't need to implement any particular method. 

All extension initialization code must be performed in the class constructor
(``__init__`` method). If that method raises the
:exc:`~scrapy.exceptions.NotConfigured` exception, the extension will be
disabled. Otherwise, the extension will be enabled.

Let's take a look at the following example extension which just logs a message
every time a domain/spider is opened and closed::

    from scrapy.xlib.pydispatch import dispatcher
    from scrapy import signals

    class SpiderOpenCloseLogging(object):

        def __init__(self):
            dispatcher.connect(self.spider_opened, signal=signals.spider_opened)
            dispatcher.connect(self.spider_closed, signal=signals.spider_closed)

        def spider_opened(self, spider):
            log.msg("opened spider %s" % spider.name)

        def spider_closed(self, spider):
            log.msg("closed spider %s" % spider.name)


.. _topics-extensions-ref-manager:

Extension Manager
=================

.. module:: scrapy.extension
   :synopsis: The extension manager

The Extension Manager is responsible for loading and keeping track of installed
extensions and it's configured through the :setting:`EXTENSIONS` setting which
contains a dictionary of all available extensions and their order similar to
how you :ref:`configure the downloader middlewares
<topics-downloader-middleware-setting>`.

.. class:: ExtensionManager

    The Extension Manager is a singleton object, which is instantiated at module
    loading time and can be accessed like this::

        from scrapy.project import extensions

    .. attribute:: loaded

        A boolean which is True if extensions are already loaded or False if
        they're not.

    .. attribute:: enabled

        A dict with the enabled extensions. The keys are the extension class names,
        and the values are the extension objects. Example::

            >>> from scrapy.project import extensions
            >>> extensions.load()
            >>> print extensions.enabled
            {'CoreStats': <scrapy.contrib.corestats.CoreStats object at 0x9e272ac>,
             'WebService': <scrapy.management.telnet.TelnetConsole instance at 0xa05670c>,
            ...

    .. attribute:: disabled

        A dict with the disabled extensions. The keys are the extension class names,
        and the values are the extension class paths (because objects are never
        instantiated for disabled extensions). Example::

            >>> from scrapy.project import extensions
            >>> extensions.load()
            >>> print extensions.disabled
            {'MemoryDebugger': 'scrapy.contrib.memdebug.MemoryDebugger',
             'MyExtension': 'myproject.extensions.MyExtension',
            ...

    .. method:: load()

        Load the available extensions configured in the :setting:`EXTENSIONS`
        setting. On a standard run, this method is usually called by the Execution
        Manager, but you may need to call it explicitly if you're dealing with
        code outside Scrapy.

    .. method:: reload()

        Reload the available extensions. See :meth:`load`.


.. _topics-extensions-ref:

Built-in extensions reference
=============================

General purpose extensions
--------------------------

Core Stats extension
~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.contrib.corestats.corestats
   :synopsis: Core stats collection

.. class:: CoreStats

Enable the collection of core statistics, provided the stats collection is
enabled (see :ref:`topics-stats`).

.. _topics-extensions-ref-webservice:

Web service extension
~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.webservice
   :synopsis: Web service

.. class:: scrapy.webservice.WebService

See `topics-webservice`.

.. _topics-extensions-ref-telnetconsole:

Telnet console extension
~~~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.telnet
   :synopsis: Telnet console 

.. class:: scrapy.telnet.TelnetConsole

Provides a telnet console for getting into a Python interpreter inside the
currently running Scrapy process, which can be very useful for debugging. 

The telnet console must be enabled by the :setting:`TELNETCONSOLE_ENABLED`
setting, and the server will listen in the port specified in
:setting:`TELNETCONSOLE_PORT`.

.. _topics-extensions-ref-memusage:

Memory usage extension
~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.contrib.memusage
   :synopsis: Memory usage extension

.. class:: scrapy.contrib.memusage.MemoryUsage

.. note:: This extension does not work in Windows.

Allows monitoring the memory used by a Scrapy process and:

1, send a notification e-mail when it exceeds a certain value
2. terminate the Scrapy process when it exceeds a certain value 

The notification e-mails can be triggered when a certain warning value is
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
garbage collector and libxml2 memory leaks. To enable this extension, turn on
the :setting:`MEMDEBUG_ENABLED` setting. The report will be printed to standard
output. If the :setting:`MEMDEBUG_NOTIFY` setting contains a list of e-mails the
report will also be sent to those addresses.

Close spider extension
~~~~~~~~~~~~~~~~~~~~~~

.. module:: scrapy.contrib.closespider
   :synopsis: Close spider extension

.. class:: scrapy.contrib.closespider.CloseSpider

Closes a spider automatically when some conditions are met, using a specific
closing reason for each condition.

The conditions for closing a spider can be configured through the following
settings:

* :setting:`CLOSESPIDER_TIMEOUT`
* :setting:`CLOSESPIDER_ITEMPASSED`
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

.. setting:: CLOSESPIDER_ITEMPASSED

CLOSESPIDER_ITEMPASSED
""""""""""""""""""""""

Default: ``0``

An integer which specifies a number of items. If the spider scrapes more than
that amount if items and those items are passed by the item pipeline, the
spider will be closed with the reason ``closespider_itempassed``. If zero (or
non set), spiders won't be closed by number of passed items.

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

.. module:: scrapy.contrib.statsmailer
   :synopsis: StatsMailer extension

.. class:: scrapy.contrib.statsmailer.StatsMailer

This simple extension can be used to send a notification e-mail every time a
domain has finished scraping, including the Scrapy stats collected. The email
will be sent to all recipients specified in the :setting:`STATSMAILER_RCPTS`
setting.

.. module:: scrapy.contrib.debug
   :synopsis: Extensions for debugging Scrapy

Debugging extensions
--------------------

Stack trace dump extension
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. class:: scrapy.contrib.debug.StackTraceDump

Dumps the stack trace of a runnning Scrapy process when a `SIGUSR2`_ signal is
received. After the stack trace is dumped, the Scrapy process continues running
normally.

The stack trace is sent to standard output.

This extension only works on POSIX-compliant platforms (ie. not Windows).

.. _SIGUSR2: http://en.wikipedia.org/wiki/SIGUSR1_and_SIGUSR2

Debugger extension
~~~~~~~~~~~~~~~~~~

.. class:: scrapy.contrib.debug.Debugger

Invokes a `Python debugger`_ inside a running Scrapy process when a `SIGUSR2`_
signal is received. After the debugger is exited, the Scrapy process continues
running normally.

For more info see `Debugging in Python`.

This extension only works on POSIX-compliant platforms (ie. not Windows).

.. _Python debugger: http://docs.python.org/library/pdb.html
.. _Debugging in Python: http://www.ferg.org/papers/debugging_in_python.html
