.. _topics-api-stats:

==============
Statistics API
==============

There are several Stats Collectors available under the
:mod:`scrapy.statscollectors` module and they all implement the Stats
Collector API defined by the :class:`~scrapy.statscollectors.StatsCollector`
class (which they all inherit from).

.. module:: scrapy.statscollectors
   :synopsis: Stats Collectors

.. class:: StatsCollector

    .. method:: get_value(key, default=None)

        Return the value for the given stats key or default if it doesn't exist.

    .. method:: get_stats()

        Get all stats from the currently running spider as a dict.

    .. method:: set_value(key, value)

        Set the given value for the given stats key.

    .. method:: set_stats(stats)

        Override the current stats with the dict passed in ``stats`` argument.

    .. method:: inc_value(key, count=1, start=0)

        Increment the value of the given stats key, by the given count,
        assuming the start value given (when it's not set).

    .. method:: max_value(key, value)

        Set the given value for the given key only if current value for the
        same key is lower than value. If there is no current value for the
        given key, the value is always set.

    .. method:: min_value(key, value)

        Set the given value for the given key only if current value for the
        same key is greater than value. If there is no current value for the
        given key, the value is always set.

    .. method:: clear_stats()

        Clear all stats.

    The following methods are not part of the stats collection api but instead
    used when implementing custom stats collectors:

    .. method:: open_spider(spider)

        Open the given spider for stats collection.

    .. method:: close_spider(spider)

        Close the given spider. After this is called, no more specific stats
        can be accessed or collected.

.. _reactor: https://twistedmatrix.com/documents/current/core/howto/reactor-basics.html
