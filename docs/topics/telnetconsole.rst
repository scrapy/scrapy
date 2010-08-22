.. _topics-telnetconsole:

==============
Telnet Console
==============

.. module:: scrapy.telnet
   :synopsis: The Telnet Console

Scrapy comes with a built-in telnet console for inspecting and controlling a
Scrapy running process. The telnet console is just a regular python shell
running inside the Scrapy process, so you can do literally anything from it.

The telnet console is a :ref:`built-in Scrapy extension
<topics-extensions-ref>` which comes enabled by default, but you can also
disable it if you want. For more information about the extension itself see
:ref:`topics-extensions-ref-telnetconsole`.

.. highlight:: none

How to access the telnet console
================================

The telnet console listens in the TCP port defined in the
:setting:`TELNETCONSOLE_PORT` setting, which defaults to ``6023``. To access
the console you need to type::

    telnet localhost 6023
    >>>
    
You need the telnet program which comes installed by default in Windows, and
most Linux distros.

Available variables in the telnet console
=========================================

The telnet console is like a regular Python shell running inside the Scrapy
process, so you can do anything from it including importing new modules, etc. 

However, the telnet console comes with some default variables defined for
convenience:

+----------------+-------------------------------------------------------------------+
| Shortcut       | Description                                                       |
+================+===================================================================+
| ``manager``    | the Project Crawler object (``scrapy.project.crawler``)           |
+----------------+-------------------------------------------------------------------+
| ``engine``     | the Scrapy engine object (``scrapy.project.crawler.engine``)      |
+----------------+-------------------------------------------------------------------+
| ``extensions`` | the Extension Manager (``scrapy.project.crawler.extensions``)     |
+----------------+-------------------------------------------------------------------+
| ``stats``      | the Stats Collector (``scrapy.stats.stats``)                      |
+----------------+-------------------------------------------------------------------+
| ``settings``   | the Scrapy settings object (``scrapy.conf.settings``)             |
+----------------+-------------------------------------------------------------------+
| ``est``        | print a report of the current engine status                       |
+----------------+-------------------------------------------------------------------+
| ``prefs``      | for memory debugging (see :ref:`topics-leaks`)                    |
+----------------+-------------------------------------------------------------------+
| ``p``          | a shortcut to the `pprint.pprint`_ function                       |
+----------------+-------------------------------------------------------------------+
| ``hpy``        | for memory debugging (see :ref:`topics-leaks`)                    |
+----------------+-------------------------------------------------------------------+

.. _pprint.pprint: http://docs.python.org/library/pprint.html#pprint.pprint

Telnet console usage examples
=============================

Here are some example tasks you can do with the telnet console:

View engine status
------------------

You can use the ``est()`` method of the Scrapy engine to quickly show its state
using the telnet console::

    telnet localhost 6023
    >>> est()
    Execution engine status

    datetime.now()-self.start_time                  : 0:00:09.051588
    self.is_idle()                                  : False
    self.scheduler.is_idle()                        : False
    len(self.scheduler.pending_requests)            : 1
    self.downloader.is_idle()                       : False
    len(self.downloader.sites)                      : 1
    self.downloader.has_capacity()                  : True
    self.pipeline.is_idle()                         : False
    len(self.pipeline.domaininfo)                   : 1
    len(self._scraping)                             : 1

    example.com
      self.domain_is_idle(domain)                        : False
      self.closing.get(domain)                           : None
      self.scheduler.domain_has_pending_requests(domain) : True
      len(self.scheduler.pending_requests[domain])       : 97
      len(self.downloader.sites[domain].queue)           : 17
      len(self.downloader.sites[domain].active)          : 25
      len(self.downloader.sites[domain].transferring)    : 8
      self.downloader.sites[domain].closing              : False
      self.downloader.sites[domain].lastseen             : 2009-06-23 15:20:16.563675
      self.pipeline.domain_is_idle(domain)               : True
      len(self.pipeline.domaininfo[domain])              : 0
      len(self._scraping[domain])                        : 0


Pause, resume and stop the Scrapy engine
----------------------------------------

To pause::

    telnet localhost 6023
    >>> engine.pause()
    >>>

To resume::

    telnet localhost 6023
    >>> engine.unpause()
    >>>

To stop::

    telnet localhost 6023
    >>> engine.stop()
    Connection closed by foreign host.

Telnet Console signals
======================

.. signal:: update_telnet_vars
.. function:: update_telnet_vars(telnet_vars)

    Sent just before the telnet console is opened. You can hook up to this
    signal to add, remove or update the variables that will be available in the
    telnet local namespace. In order to do that, you need to update the
    ``telnet_vars`` dict in your handler.

    :param telnet_vars: the dict of telnet variables
    :type telnet_vars: dict

