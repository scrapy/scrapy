.. _topics-stats:

================
Stats Collection
================

Overview
========

Scrapy provides a convenient service for collecting stats in the form of
key/values, both globally and per spider/domain. It's called the Stats
Collector, and it's a singleton which can be imported and used quickly, as
illustrated by the examples in the :ref:`topics-stats-usecases` section below.

The stats collection is enabled by default but can be disabled through the
:setting:`STATS_ENABLED` setting.

However, the Stats Collector is always available, so you can always import it
in your module and use its API (to increment or set new stat keys), regardless
of whether the stats collection is enabled or not. If it's disabled, the API
will still work but it won't collect anything. This is aimed at simplifying the
stats collector usage: you should spend no more than one line of code for
collecting stats in your spider, Scrapy extension, or whatever code you're
using the Stats Collector from.

Another feature of the Stats Collector is that it's very efficient (when
enabled) and extremely efficient (almost unnoticeable) when disabled.

The Stats Collector keeps one stats table per open spider/domain and one global
stats table. You can't set or get stats from a closed domain, but the
domain-specific stats table is automatically opened when the spider is opened,
and closed when the spider is closed.

.. _topics-stats-usecases:

Common Stats Collector uses
===========================

Import the stats collector::

    from scrapy.stats import stats

Set global stat value::

    stats.set_value('hostname', socket.gethostname())

Increment global stat value::

    stats.inc_value('spiders_crawled')

Set global stat value only if greater than previous::

    stats.max_value('max_items_scraped', value)

Set global stat value only if lower than previous::

    stats.min_value('min_free_memory_percent', value)

Get global stat value::

    >>> stats.get_value('spiders_crawled')
    8

Get all global stats from a given domain::

    >>> stats.get_stats()
    {'hostname': 'localhost', 'spiders_crawled': 8}

Set domain/spider specific stat value (domains must be opened first, but this
task is handled automatically by the Scrapy engine)::

    stats.set_value('start_time', datetime.now(), domain='example.com')

Increment domain-specific stat value::

    stats.inc_value('pages_crawled', domain='example.com')

Set domain-specific stat value only if greater than previous::

    stats.max_value('max_items_scraped', value, domain='example.com')

Set domain-specific stat value only if lower than previous::

    stats.min_value('min_free_memory_percent', value, domain='example.com')

Get domain-specific stat value::

    >>> stats.get_value('pages_crawled', domain='example.com')
    1238

Get all stats from a given domain::

    >>> stats.get_stats('pages_crawled', domain='example.com')
    {'pages_crawled': 1238, 'start_time': datetime.datetime(2009, 7, 14, 21, 47, 28, 977139)}

.. _topics-stats-ref:

Stats Collector API
===================

There are several Stats Collectors available under the
:mod:`scrapy.stats.collector` module and they all implement the Stats
Collector API defined by the :class:`~scrapy.stats.collector.StatsCollector`
class (which they all inherit from).

.. module:: scrapy.stats.collector
   :synopsis: Basic Stats Collectors

.. class:: StatsCollector
    
    .. method:: get_value(key, default=None, domain=None)
 
        Return the value for the given stats key or default if it doesn't exist.
        If domain is ``None`` the global stats table is consulted, other the
        domain specific one is. If the domain is not yet opened a ``KeyError``
        exception is raised.

    .. method:: get_stats(domain=None)

        Get all stats from the given domain/spider (if domain is given) or all
        global stats otherwise, as a dict. If domain is not opened ``KeyError``
        is raied.

    .. method:: set_value(key, value, domain=None)

        Set the given value for the given stats key on the global stats (if
        domain is not given) or the domain-specific stats (if domain is given),
        which must be opened or a ``KeyError`` will be raised.

    .. method:: set_stats(stats, domain=None)

        Set the given stats (as a dict) for the given domain. If the domain is
        not opened a ``KeyError`` will be raised.

    .. method:: inc_value(key, count=1, start=0, domain=None)

        Increment the value of the given stats key, by the given count,
        assuming the start value given (when it's not set). If domain is not
        given the global stats table is used, otherwise the domain-specific
        stats table is used, which must be opened or a ``KeyError`` will be
        raised.

    .. method:: max_value(key, value, domain=None)

        Set the given value for the given key only if current value for the
        same key is lower than value. If there is no current value for the
        given key, the value is always set. If domain is not given the global
        stats table is used, otherwise the domain-specific stats table is used,
        which must be opened or a KeyError will be raised.

    .. method:: min_value(key, value, domain=None)

        Set the given value for the given key only if current value for the
        same key is greater than value. If there is no current value for the
        given key, the value is always set. If domain is not given the global
        stats table is used, otherwise the domain-specific stats table is used,
        which must be opened or a KeyError will be raised.

    .. method:: clear_stats(domain=None)

        Clear all global stats (if domain is not given) or all domain-specific
        stats if domain is given, in which case it must be opened or a
        ``KeyError`` will be raised.

    .. method:: list_domains()

        Return a list of all opened domains.

    .. method:: open_domain(domain)

        Open the given domain for stats collection. This method must be called
        prior to working with any stats specific to that domain, but this task
        is handled automatically by the Scrapy engine.

    .. method:: close_domain(domain)

        Close the given domain. After this is called, no more specific stats
        for this domain can be accessed. This method is called automatically on
        the :signal:`domain_closed` signal.

Available Stats Collectors
==========================

Besides the basic :class:`StatsCollector` there are other Stats Collectors
available in Scrapy which extend the basic Stats Collector. You can select
which Stats Collector to use through the :setting:`STATS_CLASS` setting. The
default Stats Collector is the :class:`MemoryStatsCollector` is used. 

When stats are disabled (through the :setting:`STATS_ENABLED` setting) the
:setting:`STATS_CLASS` setting is ignored and the :class:`DummyStatsCollector`
is used.

MemoryStatsCollector
--------------------

.. class:: MemoryStatsCollector

    A simple stats collector that keeps the stats of the last scraping run (for
    each domain) in memory, which can be accessed through the ``domain_stats``
    attribute

    This is the default Stats Collector used in Scrapy.

    .. attribute:: domain_stats

       A dict of dicts (keyed by domain) containing the stats of the last
       scraping run for each domain.

DummyStatsCollector
-------------------

.. class:: DummyStatsCollector

    A Stats collector which does nothing but is very efficient. This is the
    Stats Collector used when stats are diabled (through the
    :setting:`STATS_ENABLED` setting).

SimpledbStatsCollector
----------------------

.. module:: scrapy.stats.collector.simpledb
   :synopsis: Simpledb Stats Collector

.. class:: SimpledbStatsCollector

    A Stats collector which persists stats to `Amazon SimpleDB`_, using one
    SimpleDB item per scraping run (ie. it keeps history of all scraping runs).
    The data is persisted to the SimpleDB domain specified by the
    :setting:`STATS_SDB_DOMAIN` setting. The domain will be created if it
    doesn't exist.
    
    In addition to the existing stats keys the following keys are added at
    persitance time:

        * ``domain``: the spider domain (so you can use it later for querying stats
          for that domain) 
        * ``timestamp``: the timestamp when the stats were persisited

    Both the ``domain`` and ``timestamp`` are used for generating the SimpleDB
    item name in order to avoid overwriting stats of previous scraping runs.

    As `required by SimpleDB`_, datetime's are stored in ISO 8601 format and
    numbers are zero-padded to 16 digits. Negative numbers are not currently
    supported.

    This Stats Collector requires the `boto`_ library.

.. _Amazon SimpleDB: http://aws.amazon.com/simpledb/
.. _required by SimpleDB: http://docs.amazonwebservices.com/AmazonSimpleDB/2009-04-15/DeveloperGuide/ZeroPadding.html
.. _boto: http://code.google.com/p/boto/

This Stats Collector can be configured through the following settings:

.. setting:: STATS_SDB_DOMAIN

STATS_SDB_DOMAIN
~~~~~~~~~~~~~~~~

Default: ``'scrapy_stats'``

A string containing the SimpleDB domain to use in the
:class:`SimpledbStatsCollector`.

.. setting:: STATS_SDB_ASYNC

STATS_SDB_ASYNC
~~~~~~~~~~~~~~~

Default: ``False``

If ``True`` communication with SimpleDB will be performed asynchronously. If
``False`` blocking IO will be used instead. This is the default as using
asynchronous communication can result in the stats not being persisted if the
Scrapy engine is shut down in the middle (for example, when you run only one
spider in a process and then exit).

Stats signals
=============

The Stats Collector provides some signals for extending the stats collection
functionality:

.. module:: scrapy.stats.signals
   :synopsis: Stats Collector signals

.. signal:: stats_domain_opened
.. function:: stats_domain_opened(domain)

    Sent right after the stats domain is opened. You can use this signal to add
    startup stats for domain (example: start time).

    :param domain: the stats domain just opened
    :type domain: str

.. signal:: stats_domain_closing
.. function:: stats_domain_closing(domain, reason)

    Sent just before the stats domain is closed. You can use this signal to add
    some closing stats (example: finish time).

    :param domain: the stats domain about to be closed
    :type domain: str

    :param reason: the reason why the domain is being closed. See
        :signal:`domain_closed` signal for more info.
    :type reason: str

.. signal:: stats_domain_closed
.. function:: stats_domain_closed(domain, reason, domain_stats)

    Sent right after the stats domain is closed. You can use this signal to
    collect resources, but not to add any more stats as the stats domain has
    already been close (use :signal:`stats_domain_closing` for that instead).

    :param domain: the stats domain just closed
    :type domain: str

    :param reason: the reason why the domain was closed. See
        :signal:`domain_closed` signal for more info.
    :type reason: str

    :param domain_stats: the stats of the domain just closed.
    :type reason: dict
