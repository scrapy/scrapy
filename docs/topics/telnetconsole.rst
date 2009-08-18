.. _topics-telnetconsole:

==============
Telnet Console
==============

.. module:: scrapy.management.telnet
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

Available aliases in the telnet console
=======================================

The telnet console is like a regular Python shell running inside the Scrapy
process, so you can do anything from it including imports, etc. 

However, the telnet console comes with some default aliases defined for
convenience:

    * ``engine``: the Scrapy engine object (``scrapy.core.engine.scrapyengine``)
    * ``manager``: the Scrapy manager object (``scrapy.core.manager.scrapymanager``)
    * ``extensions``: the extensions object (``scrapy.extension.extensions``)
    * ``stats``: the Scrapy stats object (``scrapy.stats.stats``)
    * ``settings``: the Scrapy settings object (``scrapy.conf.settings``)
    * ``p``: the pprint function (``pprint.pprint``)
    * ``hpy``: for memory debugging (see :ref:`topics-telnetconsole-leaks`)

Some example of using the telnet console
========================================

Here are some example tasks you can do with the telnet console:

View engine status
------------------

You can use the ``st()`` method of the Scrapy engine to quickly show its state
using the telnet console::

    telnet localhost 6023
    >>> engine.st()
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


Pause, resume and stop Scrapy engine
------------------------------------

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

.. _topics-telnetconsole-leaks:

How to debug memory leaks using the telnet console
==================================================

The Telnet Console can be used to debug memory leaks, for example, if your
Scrapy process is getting too big. You need the `guppy`_ module available. If
you use setuptools, you can install it by typing::

    easy_install guppy

.. _guppy: http://pypi.python.org/pypi/guppy
.. _setuptools: http://pypi.python.org/pypi/setuptools

Here's an example to view all Python objects available in the heap::

    >>> x = hpy.heap()
    >>> x.bytype
    Partition of a set of 297033 objects. Total size = 52587824 bytes.
     Index  Count   %     Size   % Cumulative  % Type
         0  22307   8 16423880  31  16423880  31 dict
         1 122285  41 12441544  24  28865424  55 str
         2  68346  23  5966696  11  34832120  66 tuple
         3    227   0  5836528  11  40668648  77 unicode
         4   2461   1  2222272   4  42890920  82 type
         5  16870   6  2024400   4  44915320  85 function
         6  13949   5  1673880   3  46589200  89 types.CodeType
         7  13422   5  1653104   3  48242304  92 list
         8   3735   1  1173680   2  49415984  94 _sre.SRE_Pattern
         9   1209   0   456936   1  49872920  95 scrapy.http.headers.Headers
    <1676 more rows. Type e.g. '_.more' to view.>

You can see that most space is used by dicts. Then, if you want to see from
which attribute those dicts are referenced you can do::

    >>> x.bytype[0].byvia
    Partition of a set of 22307 objects. Total size = 16423880 bytes.
     Index  Count   %     Size   % Cumulative  % Referred Via:
         0  10982  49  9416336  57   9416336  57 '.__dict__'
         1   1820   8  2681504  16  12097840  74 '.__dict__', '.func_globals'
         2   3097  14  1122904   7  13220744  80
         3    990   4   277200   2  13497944  82 "['cookies']"
         4    987   4   276360   2  13774304  84 "['cache']"
         5    985   4   275800   2  14050104  86 "['meta']"
         6    897   4   251160   2  14301264  87 '[2]'
         7      1   0   196888   1  14498152  88 "['moduleDict']", "['modules']"
         8    672   3   188160   1  14686312  89 "['cb_kwargs']"
         9     27   0   155016   1  14841328  90 '[1]'
    <333 more rows. Type e.g. '_.more' to view.>

As you can see, the guppy module is very powerful, but also requires some
knowledge about Python internals. For more info about guppy read the `guppy
documentation`_.

.. _guppy documentation: http://guppy-pe.sourceforge.net/

