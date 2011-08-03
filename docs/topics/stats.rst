.. _topics-stats:

================
Stats Collection
================

Overview
========

Scrapy provides a convenient service for collecting stats in the form of
key/values, both globally and per spider. It's called the Stats Collector, and
it's a singleton which can be imported and used quickly, as illustrated by the
examples in the :ref:`topics-stats-usecases` section below.

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

The Stats Collector keeps one stats table per open spider and one global stats
table. You can't set or get stats from a closed spider, but the spider-specific
stats table is automatically opened when the spider is opened, and closed when
the spider is closed.

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

Get all global stats (ie. not particular to any spider)::

    >>> stats.get_stats()
    {'hostname': 'localhost', 'spiders_crawled': 8}

Set spider specific stat value (spider stats must be opened first, but this
task is handled automatically by the Scrapy engine)::

    stats.set_value('start_time', datetime.now(), spider=some_spider)

Where ``some_spider`` is a :class:`~scrapy.spider.BaseSpider` object.

Increment spider-specific stat value::

    stats.inc_value('pages_crawled', spider=some_spider)

Set spider-specific stat value only if greater than previous::

    stats.max_value('max_items_scraped', value, spider=some_spider)

Set spider-specific stat value only if lower than previous::

    stats.min_value('min_free_memory_percent', value, spider=some_spider)

Get spider-specific stat value::

    >>> stats.get_value('pages_crawled', spider=some_spider)
    1238

Get all stats from a given spider::

    >>> stats.get_stats('pages_crawled', spider=some_spider)
    {'pages_crawled': 1238, 'start_time': datetime.datetime(2009, 7, 14, 21, 47, 28, 977139)}

.. _topics-stats-ref:

Stats Collector API
===================

There are several Stats Collectors available under the
:mod:`scrapy.statscol` module and they all implement the Stats
Collector API defined by the :class:`~scrapy.statscol.StatsCollector`
class (which they all inherit from).

.. module:: scrapy.statscol
   :synopsis: Basic Stats Collectors

.. class:: StatsCollector
    
    .. method:: get_value(key, default=None, spider=None)
 
        Return the value for the given stats key or default if it doesn't exist.
        If spider is ``None`` the global stats table is consulted, otherwise the
        spider specific one is. If the spider is not yet opened a ``KeyError``
        exception is raised.

    .. method:: get_stats(spider=None)

        Get all stats from the given spider (if spider is given) or all global
        stats otherwise, as a dict. If spider is not opened ``KeyError`` is
        raised.

    .. method:: set_value(key, value, spider=None)

        Set the given value for the given stats key on the global stats (if
        spider is not given) or the spider-specific stats (if spider is given),
        which must be opened or a ``KeyError`` will be raised.

    .. method:: set_stats(stats, spider=None)

        Set the given stats (as a dict) for the given spider. If the spider is
        not opened a ``KeyError`` will be raised.

    .. method:: inc_value(key, count=1, start=0, spider=None)

        Increment the value of the given stats key, by the given count,
        assuming the start value given (when it's not set). If spider is not
        given the global stats table is used, otherwise the spider-specific
        stats table is used, which must be opened or a ``KeyError`` will be
        raised.

    .. method:: max_value(key, value, spider=None)

        Set the given value for the given key only if current value for the
        same key is lower than value. If there is no current value for the
        given key, the value is always set. If spider is not given, the global
        stats table is used, otherwise the spider-specific stats table is used,
        which must be opened or a KeyError will be raised.

    .. method:: min_value(key, value, spider=None)

        Set the given value for the given key only if current value for the
        same key is greater than value. If there is no current value for the
        given key, the value is always set. If spider is not given, the global
        stats table is used, otherwise the spider-specific stats table is used,
        which must be opened or a KeyError will be raised.

    .. method:: clear_stats(spider=None)

        Clear all global stats (if spider is not given) or all spider-specific
        stats if spider is given, in which case it must be opened or a
        ``KeyError`` will be raised.

    .. method:: iter_spider_stats()

        Return a iterator over ``(spider, spider_stats)`` for each open spider
        currently tracked by the stats collector, where ``spider_stats`` is the
        dict containing all spider-specific stats.

        Global stats are not included in the iterator. If you want to get
        those, use :meth:`get_stats` method.

    .. method:: open_spider(spider)

        Open the given spider for stats collection. This method must be called
        prior to working with any stats specific to that spider, but this task
        is handled automatically by the Scrapy engine.

    .. method:: close_spider(spider)

        Close the given spider. After this is called, no more specific stats
        for this spider can be accessed. This method is called automatically on
        the :signal:`spider_closed` signal.

    .. method:: engine_stopped()

        Called after the engine is stopped, to dump or persist global stats.

Available Stats Collectors
==========================

Besides the basic :class:`StatsCollector` there are other Stats Collectors
available in Scrapy which extend the basic Stats Collector. You can select
which Stats Collector to use through the :setting:`STATS_CLASS` setting. The
default Stats Collector used is the :class:`MemoryStatsCollector`. 

When stats are disabled (through the :setting:`STATS_ENABLED` setting) the
:setting:`STATS_CLASS` setting is ignored and the :class:`DummyStatsCollector`
is used.

MemoryStatsCollector
--------------------

.. class:: MemoryStatsCollector

    A simple stats collector that keeps the stats of the last scraping run (for
    each spider) in memory, after they're closed. The stats can be accessed
    through the :attr:`spider_stats` attribute, which is a dict keyed by spider
    domain name.

    This is the default Stats Collector used in Scrapy.

    .. attribute:: spider_stats

       A dict of dicts (keyed by spider name) containing the stats of the last
       scraping run for each spider.

DummyStatsCollector
-------------------

.. class:: DummyStatsCollector

    A Stats collector which does nothing but is very efficient. This is the
    Stats Collector used when stats are disabled (through the
    :setting:`STATS_ENABLED` setting).

Stats signals
=============

The Stats Collector provides some signals for extending the stats collection
functionality:

.. currentmodule:: scrapy.signals

.. signal:: stats_spider_opened
.. function:: stats_spider_opened(spider)

    Sent right after the stats spider is opened. You can use this signal to add
    startup stats for the spider (example: start time).

    :param spider: the stats spider just opened
    :type spider: str

.. signal:: stats_spider_closing
.. function:: stats_spider_closing(spider, reason)

    Sent just before the stats spider is closed. You can use this signal to add
    some closing stats (example: finish time).

    :param spider: the stats spider about to be closed
    :type spider: str

    :param reason: the reason why the spider is being closed. See
        :signal:`spider_closed` signal for more info.
    :type reason: str

.. signal:: stats_spider_closed
.. function:: stats_spider_closed(spider, reason, spider_stats)

    Sent right after the stats spider is closed. You can use this signal to
    collect resources, but not to add any more stats as the stats spider has
    already been closed (use :signal:`stats_spider_closing` for that instead).

    :param spider: the stats spider just closed
    :type spider: str

    :param reason: the reason why the spider was closed. See
        :signal:`spider_closed` signal for more info.
    :type reason: str

    :param spider_stats: the stats of the spider just closed.
    :type reason: dict
