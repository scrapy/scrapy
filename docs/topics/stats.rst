.. currentmodule:: scrapy.statscollectors

.. _topics-stats:

================
Stats Collection
================

Scrapy provides a convenient facility for collecting stats in the form of
key/values, where values are often counters. The facility is called the Stats
Collector, and can be accessed through the :attr:`~scrapy.crawler.Crawler.stats`
attribute of the :ref:`topics-api-crawler`, as illustrated by the examples in
the :ref:`topics-stats-usecases` section below.

However, the Stats Collector is always available, so you can always import it
in your module and use its API (to increment or set new stat keys), regardless
of whether the stats collection is enabled or not. If it's disabled, the API
will still work but it won't collect anything. This is aimed at simplifying the
stats collector usage: you should spend no more than one line of code for
collecting stats in your spider, Scrapy extension, or whatever code you're
using the Stats Collector from.

Another feature of the Stats Collector is that it's very efficient (when
enabled) and extremely efficient (almost unnoticeable) when disabled.

The Stats Collector keeps a stats table per open spider which is automatically
opened when the spider is opened, and closed when the spider is closed.

.. _topics-stats-usecases:

Common Stats Collector uses
===========================

Access the stats collector through the :attr:`~scrapy.crawler.Crawler.stats`
attribute. Here is an example of an extension that access stats::

    class ExtensionThatAccessStats(object):

        def __init__(self, stats):
            self.stats = stats

        @classmethod
        def from_crawler(cls, crawler):
            return cls(crawler.stats)

.. doctest::
   :hide:

    >>> from scrapy import Spider
    >>> from scrapy.crawler import Crawler
    >>> from scrapy.statscollectors import MemoryStatsCollector
    >>> stats = MemoryStatsCollector(Crawler(Spider))

Set stat value::

    >>> from datetime import datetime
    >>> stats.set_value('start_time', datetime(2008, 6, 26))

Increment stat value::

    >>> stats.inc_value('custom_count')

Set stat value only if greater than previous::

    >>> stats.max_value('max_items_scraped', 100)

Set stat value only if lower than previous::

    >>> stats.min_value('min_free_memory_percent', 10)

Get stat value::

    >>> stats.get_value('custom_count')
    1

Get all stats::

    >>> stats.get_stats()
    {'start_time': datetime.datetime(2008, 6, 26, 0, 0), 'custom_count': 1, 'max_items_scraped': 100, 'min_free_memory_percent': 10}

Available Stats Collectors
==========================

Besides the basic :class:`StatsCollector` there are other Stats Collectors
available in Scrapy which extend the basic Stats Collector. You can select
which Stats Collector to use through the :setting:`STATS_CLASS` setting. The
default Stats Collector used is the :class:`MemoryStatsCollector`.

Available statistics collectors are :class:`DummyStatsCollector` and
:class:`MemoryStatsCollector`.
