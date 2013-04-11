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
| ``crawler``    | the Scrapy Crawler (:class:`scrapy.crawler.Crawler` object)       |
+----------------+-------------------------------------------------------------------+
| ``engine``     | Crawler.engine attribute                                          |
+----------------+-------------------------------------------------------------------+
| ``spider``     | the active spider                                                 |
+----------------+-------------------------------------------------------------------+
| ``slot``       | the engine slot                                                   |
+----------------+-------------------------------------------------------------------+
| ``extensions`` | the Extension Manager (Crawler.extensions attribute)              |
+----------------+-------------------------------------------------------------------+
| ``stats``      | the Stats Collector (Crawler.stats attribute)                     |
+----------------+-------------------------------------------------------------------+
| ``settings``   | the Scrapy settings object (Crawler.settings attribute)           |
+----------------+-------------------------------------------------------------------+
| ``est``        | print a report of the engine status                               |
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

    time()-engine.start_time                        : 9.24237799644
    engine.has_capacity()                           : False
    engine.downloader.is_idle()                     : False
    len(engine.downloader.slots)                    : 2
    len(engine.downloader.active)                   : 16
    engine.scraper.is_idle()                        : False

    Spider: <GayotSpider 'gayotcom' at 0x2dc2b10>
      engine.spider_is_idle(spider)                      : False
      engine.slots[spider].closing                       : False
      len(engine.slots[spider].inprogress)               : 21
      len(engine.slots[spider].scheduler.dqs or [])      : 0
      len(engine.slots[spider].scheduler.mqs)            : 4453
      len(engine.scraper.slot.queue)                     : 0
      len(engine.scraper.slot.active)                    : 5
      engine.scraper.slot.active_size                    : 1515069
      engine.scraper.slot.itemproc_size                  : 0
      engine.scraper.slot.needs_backout()                : False


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

Telnet settings
===============

These are the settings that control the telnet console's behaviour:

.. setting:: TELNETCONSOLE_PORT

TELNETCONSOLE_PORT
------------------

Default: ``[6023, 6073]``

The port range to use for the telnet console. If set to ``None`` or ``0``, a
dynamically assigned port is used.


.. setting:: TELNETCONSOLE_HOST

TELNETCONSOLE_HOST
------------------

Default: ``'0.0.0.0'``

The interface the telnet console should listen on

