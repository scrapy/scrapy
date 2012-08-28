.. _topics-stats:

================
Stats Collection
================

Scrapy provides a convenient facility for collecting stats in the form of
key/values, both globally and per spider. It's called the Stats Collector, and
can be accesed through the :attr:`~scrapy.crawler.Crawler.stats` attribute of
the :ref:`topics-api-crawler`, as illustrated by the examples in the
:ref:`topics-stats-usecases` section below.

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

Access the stats collector throught the :attr:`~scrapy.crawler.Crawler.stats`
attribute::

    @classmethod
    def from_crawler(cls, crawler):
        stats = crawler.stats

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

Set spider specific stat value::

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

    >>> stats.get_stats(spider=some_spider)
    {'pages_crawled': 1238, 'start_time': datetime.datetime(2009, 7, 14, 21, 47, 28, 977139)}

Available Stats Collectors
==========================

Besides the basic :class:`StatsCollector` there are other Stats Collectors
available in Scrapy which extend the basic Stats Collector. You can select
which Stats Collector to use through the :setting:`STATS_CLASS` setting. The
default Stats Collector used is the :class:`MemoryStatsCollector`. 

.. module:: scrapy.statscol
   :synopsis: Stats Collectors

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

    A Stats collector which does nothing but is very efficient (beacuse it does
    nothing). This stats collector can be set via the :setting:`STATS_CLASS`
    setting, to disable stats collect in order to improve performance. However,
    the performance penalty of stats collection is usually marginal compared to
    other Scrapy workload like parsing pages.


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
