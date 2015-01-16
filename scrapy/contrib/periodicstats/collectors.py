from collections import defaultdict
import re

from twisted.internet import task

from scrapy.statscol import MemoryStatsCollector
from scrapy.exceptions import NotConfigured
from scrapy.utils.misc import load_object
from scrapy.contrib.periodicstats.observers import PeriodicStatsObserver
from scrapy.contrib.periodicstats.pipelines import PeriodicStatsPipeline


DEFAULT_PERIODIC_STATS_ENABLED = True
DEFAULT_PERIODIC_STATS_EXPORT_ALL = False
DEFAULT_PERIODIC_STATS_EXPORT_ALL_INTERVAL = 60


class PeriodicStatsCollector(MemoryStatsCollector):
    """
    Stats collector class that periodically generates stats and pass them to pipelines for processing
    """

    def __init__(self, crawler):
        super(PeriodicStatsCollector, self).__init__(crawler=crawler)
        self._enabled = crawler.settings.get('PERIODIC_STATS_ENABLED',
                                             DEFAULT_PERIODIC_STATS_ENABLED)
        if self._enabled:
            self._export_all = crawler.settings.get('PERIODIC_STATS_EXPORT_ALL',
                                                    DEFAULT_PERIODIC_STATS_EXPORT_ALL)
            self._export_all_interval = crawler.settings.get('PERIODIC_STATS_EXPORT_ALL_INTERVAL',
                                                             DEFAULT_PERIODIC_STATS_EXPORT_ALL_INTERVAL)
            self._load_observers(crawler)
            self._load_pipelines(crawler)
            self._interval = 0

    def open_spider(self, spider):
        super(PeriodicStatsCollector, self).open_spider(spider)
        if self._enabled:
            for pipeline in self._pipelines:
                pipeline.open_spider(spider)
            self._task = task.LoopingCall(self._process_interval_stats, spider)
            self._task.start(1)

    def close_spider(self, spider, reason):
        super(PeriodicStatsCollector, self).close_spider(spider, reason)
        if self._enabled:
            self._process_interval_stats(spider=spider, is_close=True)
            for pipeline in self._pipelines:
                pipeline.close_spider(spider, reason)

    def set_value(self, key, value, spider=None):
        super(PeriodicStatsCollector, self).set_value(key=key, value=value, spider=spider)
        if self._enabled:
            for observer in self._get_key_observers(key):
                observer.set_value(value=value)

    def inc_value(self, key, count=1, start=0, spider=None):
        super(PeriodicStatsCollector, self).inc_value(key=key, count=count, start=start, spider=spider)
        if self._enabled:
            for observer in self._get_key_observers(key):
                observer.inc_value(count=count, start=start)

    def max_value(self, key, value, spider=None):
        super(PeriodicStatsCollector, self).max_value(key=key, value=value, spider=spider)
        if self._enabled:
            self.set_value(key=key, value=self.get_value(key), spider=spider)

    def min_value(self, key, value, spider=None):
        super(PeriodicStatsCollector, self).min_value(key=key, value=value, spider=spider)
        if self._enabled:
            self.set_value(key=key, value=self.get_value(key), spider=spider)

    def _load_observers(self, crawler):
        """
        Loads the stats value observers
        """
        export_keys = set()
        self._observers = defaultdict(list)
        self._re_observers = defaultdict(list)
        for observer in crawler.settings.get('PERIODIC_STATS_OBSERVERS', {}):
            if not isinstance(observer, PeriodicStatsObserver):
                raise NotConfigured('Stats observers must subclass PeriodicStatsObserver')
            observer_export_key = observer.export_key
            if observer_export_key in export_keys:
                raise NotConfigured('Duplicate export key "%s"' % observer_export_key)
            export_keys.add(observer_export_key)
            if not observer.use_re_key:
                self._observers[observer.key].append(observer)
            else:
                self._re_observers[observer.key].append(observer)

    def _load_pipelines(self, crawler):
        """
        Loads the stats processor pipelines
        """
        self._pipelines = []
        for pipeline in crawler.settings.get('PERIODIC_STATS_PIPELINES', []):
            if not isinstance(pipeline, basestring):
                raise NotConfigured('Stats pipelines must be defined as an object string path in settings')
            pipeline_class = load_object(pipeline)
            if not issubclass(pipeline_class, PeriodicStatsPipeline):
                raise NotConfigured('Stats pipelines must subclass PeriodicStatsPipeline')
            pipeline = pipeline_class.from_crawler(crawler)
            self._pipelines.append(pipeline)

    def _process_interval_stats(self, spider, is_close=False):
        """
        Returns the interval stats for the current interval
        """
        stats = self._get_interval_base_stats(spider=spider, is_close=is_close)
        stats.update(self._get_interval_observers_stats(self._observers, force=is_close))
        stats.update(self._get_interval_observers_stats(self._re_observers, force=is_close))
        for pipeline in self._pipelines:
            stats = pipeline.process_stats(spider=spider,
                                           interval=self._interval+1,
                                           stats=stats)
            if not stats:
                break
        self._interval += 1
        return stats

    def _get_key_observers(self, key):
        """
        Returns a list of observers for the passed key
        """
        observers = []
        for re_key, re_observers in self._re_observers.iteritems():
            if re.match(re_key, key):
                observers += re_observers
        observers += self._observers.get(key, [])
        return observers

    def _get_interval_observers_stats(self, observers_dict, force):
        """
        Returns the interval stats for the passed observers dict
        """
        interval_stats = {}
        for key, observers in observers_dict.iteritems():
            for observer in observers:
                export_name, value_stats = observer.get_interval_stats(force=force)
                if value_stats is not None:
                    interval_stats[export_name] = value_stats
        return interval_stats

    def _get_interval_base_stats(self, spider, is_close):
        """
        Returns the base stats if export_all parameter is active
        """
        if self._export_all and (not self._interval % self._export_all_interval or is_close):
            return self.get_stats(spider)
        return {}
