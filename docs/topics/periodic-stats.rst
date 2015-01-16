.. _topics-periodic-stats:

==============
Periodic Stats
==============

Sometimes you want to monitor statistics or be notified about certain events that occur in your crawling process.
Scrapy provides the tools for periodically generate and process data from a :ref:`topics-stats`.

Some use cases can be:

- Monitor and graph scraping data over time (memory usage, http codes, errors, scraped items, etc).
- Get notified when a crawl job has finished or alerted when something happens.
- Use your own stat values to monitor custom data or events.

You can for instance generate and export your stats and create some time-based graphs using a 3rd party
tool like `Kibana`_.


To achieve this is you must configure a :ref:`topics-stats-periodicstatscollector` with a list of:

- :ref:`topics-stats-valueobservers`: To select and configure the filtered periodic stats.
- :ref:`topics-stats-statspipelines` To process the generated stats.

.. _topics-stats-periodicstatscollector:

Periodic Stats Collector
========================

:class:`PeriodicStatsCollector` is a special :class:`MemoryStatsCollector` class, it has exactly the same funcionality
but can be configured to periodically generate and process stats.

All configuration is done via settings. To use it, simply change the :setting:`STATS_CLASS` setting like this::

    STATS_CLASS = 'scrapy.contrib.periodicstats.PeriodicStatsCollector'


Stat values can be filtered defining :ref:`topics-stats-valueobservers`, but sometimes you want all the available
stats. You can get this with the :setting:`PERIODIC_STATS_EXPORT_ALL` setting::

    PERIODIC_STATS_EXPORT_ALL = True

And to define the interval for generating all the stats you must use
the :setting:`PERIODIC_STATS_EXPORT_ALL_INTERVAL` setting::

    PERIODIC_STATS_EXPORT_ALL_INTERVAL = 30  # time in seconds


You can always deactivate the periodic stats generation with the :setting:`PERIODIC_STATS_ENABLED` setting
(:class:`MemoryStatsCollector` functionality will still remain the same)::

    PERIODIC_STATS_ENABLED = False



.. _topics-stats-valueobservers:

Value Observers
===============

:class:`PeriodicStatsObserver` class allows to select data from the available :ref:`topics-stats` and define when it
should be generated.

They can be defined using the :setting:`PERIODIC_STATS_OBSERVERS` setting::

    from scrapy.contrib import periodicstats as stats

    PERIODIC_STATS_OBSERVERS = [
        stats.Observer(key='downloader/response_count'),
    ]

The previous example will generate the number of responses every second::

    {'downloader/response_count': 5}   # for t=1
    {'downloader/response_count': 34}  # for t=2
    {'downloader/response_count': 45}  # for t=3
    ...

More examples of use below.


PeriodicStatsObserver
---------------------

.. module:: scrapy.contrib.periodicstats
.. class:: PeriodicStatsObserver(key[, use_re_key=False, use_partial_values=False, export_key=None, export_interval=1, only_export_on_change=False, only_export_on_close=False])

    Class that monitors a stats value and decides to show it or not across intervals.

    :param key: the stats key to use
    :type key: string

    :param use_re_key: whether key parameter is a regular expression or not
    :type use_re_key: bool

    :param use_partial_values: defines how numeric values are calculated. If active only variations during the interval will be shown, if disabled (default) the total cumulated value will be used.
    :type use_partial_values: bool

    :param export_key: the key to use for this value, if not defined ``key`` parameter will be used.
    :type export_key: string

    :param export_interval: the interval in seconds that will be used to generate this value.
    :type export_interval: int

    :param only_export_on_change: If active, value will be only generated if has changed since the last interval.
    :type only_export_on_change: bool

    :param only_export_on_close: If active, value will be only generated when the spider is closed.
    :type only_export_on_close: bool

You can define many observers::

    PERIODIC_STATS_OBSERVERS = [
        stats.Observer(key='downloader/request_count'),
        stats.Observer(key='downloader/response_count'),
        stats.Observer(key='httpcache/hit'),
    ]

    """
    Generated stats:
    {'downloader/request_count': 10, 'downloader/request_count': 10, 'httpcache/hit': 0}  # for t=1
    {'downloader/request_count': 23, 'downloader/request_count': 20, 'httpcache/hit': 3}  # for t=2
    {'downloader/request_count': 23, 'downloader/request_count': 20, 'httpcache/hit': 3}  # for t=3
    {'downloader/request_count': 34, 'downloader/request_count': 28, 'httpcache/hit': 7}  # for t=4
    ...
    """

To use a different name for the stats value use the ``export_key`` parameter::

    PERIODIC_STATS_OBSERVERS = [
        stats.Observer(key='downloader/request_count', export_key='requests'),
        stats.Observer(key='downloader/response_count', export_key='responses'),
        stats.Observer(key='httpcache/hit', export_key='from_cache'),
    ]

    """
    Generated stats:
    {'requests': 10, 'responses': 10, 'from_cache': 0}   # for t=1
    {'requests': 23, 'responses': 20, 'from_cache': 3}   # for t=2
    {'requests': 23, 'responses': 20, 'from_cache': 3}   # for t=3
    {'requests': 34, 'responses': 28, 'from_cache': 7}   # for t=4
    ...
    """

You can use several observers at the same key, but then ``export_key`` can't be repeated::

    PERIODIC_STATS_OBSERVERS = [
        stats.Observer(key='downloader/request_count', export_key='requests_counter'),
        stats.Observer(key='downloader/request_count', export_key='another_request_counter'),
    ]

    """
    Generated stats:
    {'requests_counter': 10, 'another_request_counter': 10}  # for t=1
    {'requests_counter': 23, 'another_request_counter': 23}  # for t=2
    {'requests_counter': 23, 'another_request_counter': 23}  # for t=3
    {'requests_counter': 34, 'another_request_counter': 34}  # for t=4
    ...
    """

By default values are accumulated, but we can also use just differences between intervals with the
``use_partial_values`` parameter::

    PERIODIC_STATS_OBSERVERS = [
        stats.Observer(key='downloader/request_count', export_key='requests', use_partial_values=True),
    ]

    """
    Generated stats:
    {'requests': 10}  # for t=1
    {'requests': 13}  # for t=2
    {'requests': 0}   # for t=3
    {'requests': 11}  # for t=4
    ...
    """

To minimize generated data we can choose to export data only when it changes with the
``only_export_on_change`` parameter::

    PERIODIC_STATS_OBSERVERS = [
        stats.Observer(key='downloader/request_count', export_key='requests', only_export_on_change=True),
    ]

    """
    Generated stats:
    {'requests': 10}  # for t=1
    {'requests': 13}  # for t=2
    {}                # for t=3
    {'requests': 11}  # for t=4
    ...
    """

We can define export intervals per key with the ``export_interval`` parameter::

    PERIODIC_STATS_OBSERVERS = [
        stats.Observer(key='downloader/request_count', export_key='requests', export_interval=1),
        stats.Observer(key='downloader/response_count', export_key='responses', export_interval=2),
    ]

    """
    Generated stats:
    {'requests': 10, 'responses': 10}  # for t=1
    {'requests': 23}                   # for t=2
    {'requests': 23, 'responses': 20}  # for t=3
    {'requests': 34}                   # for t=4
    ...
    """

To export only stats when a spider is finished use the ``only_export_on_close`` parameter::

    PERIODIC_STATS_OBSERVERS = [
        stats.Observer(key='downloader/request_count', export_key='requests', only_export_on_close=True),
    ]

    """
    Generated stats:
    {}                  # for t=1
    {}                  # for t=2
    {}                  # for t=3
    {}                  # for t=4
    ...
    {'requests': 2759}  # on spider_close
    """

Regular expressions can be used to group/filter data with the ``use_re_key`` parameter:::

    PERIODIC_STATS_OBSERVERS = [
        stats.Observer(key='downloader/response_status_count/2..', use_re_key=True, export_key='2xx'),
        stats.Observer(key='downloader/response_status_count/3..', use_re_key=True, export_key='3xx'),
        stats.Observer(key='downloader/response_status_count/4..', use_re_key=True, export_key='4xx'),
        stats.Observer(key='downloader/response_status_count/5..', use_re_key=True, export_key='5xx'),
    ]

    """
    Generated stats:
    {'2xx': 10}                               # for t=1
    {'2xx': 34, '3xx': 1, '4xx':1}            # for t=2
    {'2xx': 67, '3xx': 4, '4xx':2, '5xx': 1}  # for t=3
    {'2xx': 90, '3xx': 8, '4xx':2, '5xx': 1}  # for t=4
    ...
    """

.. _topics-stats-statspipelines:

Stats Pipelines
===============

:class:`PeriodicStatsPipeline` objects receive and process the stats generated by the :class:`PeriodicStatsObserver`
objects for every :ref:`topics-stats-periodicstatscollector` iteration.

You can define the pipeline objects to use with the :setting:`PERIODIC_STATS_PIPELINES` setting::

    PERIODIC_STATS_PIPELINES = [
        'scrapy.contrib.periodicstats.PeriodicStatsLogger',
    ]


PeriodicStatsPipeline
---------------------

.. module:: scrapy.contrib.periodicstats
.. class:: PeriodicStatsPipeline

    .. method:: open_spider(spider)

        Called when the spider is opened.

        :param spider: the spider for which the stats are processed.
        :type spider: :class:`~scrapy.spider.Spider` object

    .. method:: close_spider(spider)

        Called when the spider is closed.

        :param spider: the spider for which the stats are processed.
        :type spider: :class:`~scrapy.spider.Spider` object

    .. method:: process_stats(spider, interval, stats)

        Called for every :class:`PeriodicStatsCollector` iteration with the stats to be processed.

        :meth:`process_stats` should return the passed stats or ``None``.

        If it returns the passed stats, they will be passed to the next middleware.

        If it returns ``None``, no further middlewares will be called.

        :param spider: the spider for which the stats are processed.
        :type spider: :class:`~scrapy.spider.Spider` object


You can define your own :class:`PeriodicStatsPipeline` objects to periodically export stats.


.. _Kibana: http://www.elasticsearch.org/overview/kibana/



