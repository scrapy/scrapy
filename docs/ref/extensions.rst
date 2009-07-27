.. _ref-extensions:

=============================
Built-in extensions reference
=============================

This document explains all extensions that come with Scrapy. For information on
how to use them and how to write your own extensions, see the :ref:`extensions
usage guide <topics-extensions>`.


General purpose extensions
==========================

Core Stats extension
--------------------

.. module:: scrapy.stats.corestats
   :synopsis: Core stats collection

.. class:: scrapy.stats.corestats.CoreStats

Enable the collection of core statistics, provided the stats collection are
enabled (see :ref:`topics-stats`).

Response Libxml2 extension
--------------------------

.. module:: scrapy.xpath.extension
   :synopsis: Libxml2 document caching for Responses

.. class:: scrapy.path.extension.ResponseLibxml2

Causes the :class:`~scrapy.http.Response` objects to grow a new method
(``getlibxml2doc()``) which returns a (cached) libxml2 document of their
contents. :ref:`XPath Selectors <topics-selectors>` use this extension for
better performance, so it's highly recommended not to disable it.

.. _ref-extensions-webconsole:

Web console extension
---------------------

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

.. _ref-extensions-telnetconsole:

Telnet console extension
------------------------

.. module:: scrapy.management.telnet
   :synopsis: Telnet management console 

.. class:: scrapy.management.telnet.TelnetConsole

Provides a telnet console for getting into a Python interpreter inside the
currently running Scrapy process, which can be very useful for debugging. 

The telnet console must be enabled by the :setting:`TELNETCONSOLE_ENABLED`
setting, and the server will listen in the port specified in
:setting:`WEBCONSOLE_PORT`.

Spider reloader extension
-------------------------

.. module:: scrapy.contrib.spider.reloader
   :synopsis: Spider reloader extension

.. class:: scrapy.contrib.spider.reloader.SpiderReloader

Reload spider objects once they've finished scraping, to release the resources
and references to other objects they may hold.

.. _ref-extensions-memusage:

Memory usage extension
----------------------

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
-------------------------

.. module:: scrapy.contrib.memdebug
   :synopsis: Memory debugger extension

.. class:: scrapy.contrib.memdebug.MemoryDebugger

A memory debugger which collects some info about objects uncollected by the
garbage collector and libxml2 memory leaks. To enable this extension turn on
the :setting:`MEMDEBUG_ENABLED` setting. The report will be printed to standard
output. If the :setting:`MEMDEBUG_NOTIFY` setting contains a list of emails the
report will also be sent to those addresses.

Close domain extension
----------------------

.. module:: scrapy.contrib.closedomain
   :synopsis: Close domain extension

.. class:: scrapy.contrib.closedomain.CloseDomain

Closes a domain/spider automatically when some conditions are met, using a
specific closing reason for each condition.

The conditions for closing a domain can be configured through the following
settings. Other conditions will be supported in the future.

.. setting:: CLOSEDOMAIN_TIMEOUT

CLOSEDOMAIN_TIMEOUT
~~~~~~~~~~~~~~~~~~~

Default: ``0``

An integer which specifies a number of seconds. If the domain remains open for
more than that number of second, it will be automatically closed with the
reason ``closedomain_timeout``. If zero (or non set) domains won't be closed by
timeout.

.. setting:: CLOSEDOMAIN_ITEMPASSED

CLOSEDOMAIN_ITEMPASSED
~~~~~~~~~~~~~~~~~~~~~~

Default: ``0``

An integer which specifies a number of items. If the spider scrapes more than
that amount if items and those items are passed by the item pipeline, the
domain will be closed with the reason ``closedomain_itempassed``. If zero (or
non set) domains won't be closed by number of passed items.

Stack trace dump extension
---------------------------

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

Response soup extension
-----------------------

.. module:: scrapy.contrib.response.soup
   :synopsis: Response soup extension

.. class:: scrapy.contrib.response.soup.ResponseSoup

The ResponseSoup extension causes the :class:`~scrapy.http.Response` objects to
grow a new method (``getsoup()``) which returns a cached `BeautifulSoup`_
object of their body, and a ``soup`` attribute with the same effect. The
``soup`` attribute is provided only for convenience, as you cannot pass pass
any BeautifulSoup constructor arguments (use the ``getsoup()`` method for those
cases). 

The advantage of using the Response soup extension over instantiating a
BeautifulSoup object directly is performance, as BeautifulSoup is known to be
very slow.

For example, if you have a downloader middleware and a spider that both need to
construct a BeautifulSoup object of the responses, you would be constructing
two BeautifulSoup objects unless you use this extension which caches the first
one.

.. _BeautifulSoup: http://www.crummy.com/software/BeautifulSoup/documentation.html

StatsMailer extension
---------------------

.. module:: scrapy.contrib.statsmailer
   :synopsis: StatsMailer extension

.. class:: scrapy.contrib.statsmailer.StatsMailer

This simple extension can be used to send a notification email every time a
domain has finished scraping, including the Scrapy stats collected. The email
will be sent to all recipients specified in the :setting:`STATSMAILER_RCPTS`
setting.

Web console extensions
======================

.. module:: scrapy.contrib.webconsole
   :synopsis: Contains most built-in web console extensions

Here is a list of built-in web console extensions. For clarity "web console
extension" is abbreviated as "WC extension".

For more information see the see the :ref:`web console documentation
<topics-webconsole>`.

Scheduler queue WC extension
----------------------------

.. module:: scrapy.contrib.webconsole.scheduler
   :synopsis: Scheduler queue web console extension

.. class:: scrapy.contrib.webconsole.scheduler.SchedulerQueue

Display a list of all pending Requests in the Scheduler queue, grouped by
domain/spider.

Spider live stats WC extension
------------------------------

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
---------------------------

.. module:: scrapy.contrib.webconsole.enginestatus
   :synopsis: Engine status web console extension

.. class:: scrapy.contrib.webconsole.enginestatus.EngineStatus

Display the current status of the Scrapy Engine, which is just the output of
the Scrapy engine ``getstatus()`` method.

Stats collector dump WC extension 
----------------------------------

.. module:: scrapy.contrib.webconsole.stats
   :synopsis: Stats dump web console extension

.. class:: scrapy.contrib.webconsole.stats.StatsDump

Display the stats collected so far by the stats collector.

Spider stats WC extension
-------------------------

.. module:: scrapy.contrib.webconsole.spiderstats
   :synopsis: Spider stats web console extension

.. class:: scrapy.contrib.webconsole.spiderstats.SpiderStats


