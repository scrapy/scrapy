"""The :mod:`scrapy.statscollectors` module defines the :class:`StatsCollector`
class and some additional subclasses for collecting scraping stats.

.. seealso:: :ref:`topics-stats`
"""
import pprint
import logging

logger = logging.getLogger(__name__)


class StatsCollector(object):
    """Base class for :ref:`stats collectors <topics-stats>`, extensions that
    collect statistics.

    The :meth:`open_spider` and :meth:`open_spider` methods are not part of the
    stats collection API but instead used when implementing custom stats
    collectors.
    """

    def __init__(self, crawler):
        self._dump = crawler.settings.getbool('STATS_DUMP')
        self._stats = {}

    def get_value(self, key, default=None, spider=None):
        """Return the value for the given stats key or default if it doesn't
        exist."""
        return self._stats.get(key, default)

    def get_stats(self, spider=None):
        """Get all stats from the currently running spider as a dict."""
        return self._stats

    def set_value(self, key, value, spider=None):
        """Set the given value for the given stats key."""
        self._stats[key] = value

    def set_stats(self, stats, spider=None):
        """Override the current stats with the dict passed in ``stats``
        argument."""
        self._stats = stats

    def inc_value(self, key, count=1, start=0, spider=None):
        """Increment the value of the given stats key, by the given count,
        assuming the start value given (when it's not set)."""
        d = self._stats
        d[key] = d.setdefault(key, start) + count

    def max_value(self, key, value, spider=None):
        """Set the given value for the given key only if current value for the
        same key is lower than value. If there is no current value for the
        given key, the value is always set."""
        self._stats[key] = max(self._stats.setdefault(key, value), value)

    def min_value(self, key, value, spider=None):
        """Set the given value for the given key only if current value for the
        same key is greater than value. If there is no current value for the
        given key, the value is always set."""
        self._stats[key] = min(self._stats.setdefault(key, value), value)

    def clear_stats(self, spider=None):
        """Clear all stats."""
        self._stats.clear()

    def open_spider(self, spider):
        """Open the given spider for stats collection."""
        pass

    def close_spider(self, spider, reason):
        """Close the given spider. After this is called, no more specific stats
        can be accessed or collected."""
        if self._dump:
            logger.info("Dumping Scrapy stats:\n" + pprint.pformat(self._stats),
                        extra={'spider': spider})
        self._persist_stats(self._stats, spider)

    def _persist_stats(self, stats, spider):
        pass


class MemoryStatsCollector(StatsCollector):
    """A simple stats collector that keeps the stats of the last scraping run (for
    each spider) in memory, after they're closed. The stats can be accessed
    through the :attr:`spider_stats` attribute, which is a dict keyed by spider
    domain name.

    This is the default Stats Collector used in Scrapy.
    """

    def __init__(self, crawler):
        super(MemoryStatsCollector, self).__init__(crawler)
        #: A dict of dicts (keyed by spider name) containing the stats of the
        #: last scraping run for each spider.
        self.spider_stats = {}

    def _persist_stats(self, stats, spider):
        self.spider_stats[spider.name] = stats


class DummyStatsCollector(StatsCollector):
    """A Stats collector which does nothing but is very efficient (because it does
    nothing). This stats collector can be set via the :setting:`STATS_CLASS`
    setting, to disable stats collect in order to improve performance. However,
    the performance penalty of stats collection is usually marginal compared to
    other Scrapy workload like parsing pages."""

    def get_value(self, key, default=None, spider=None):
        return default

    def set_value(self, key, value, spider=None):
        pass

    def set_stats(self, stats, spider=None):
        pass

    def inc_value(self, key, count=1, start=0, spider=None):
        pass

    def max_value(self, key, value, spider=None):
        pass

    def min_value(self, key, value, spider=None):
        pass


