import six
import warnings

from twisted.internet import defer

from scrapy.core.engine import ExecutionEngine
from scrapy.extension import ExtensionManager
from scrapy.signalmanager import SignalManager
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.misc import load_object
from scrapy import log, signals


class Crawler(object):

    def __init__(self, spidercls, settings):
        self.spidercls = spidercls
        self.settings = settings.copy()

        self.signals = SignalManager(self)
        self.stats = load_object(self.settings['STATS_CLASS'])(self)
        lf_cls = load_object(self.settings['LOG_FORMATTER'])
        self.logformatter = lf_cls.from_crawler(self)
        self.extensions = ExtensionManager.from_crawler(self)

        self.spidercls.update_settings(self.settings)
        self.settings.freeze()

        self.crawling = False
        self.spider = None
        self.engine = None

    @property
    def spiders(self):
        if not hasattr(self, '_spiders'):
            warnings.warn("Crawler.spiders is deprecated, use "
                          "CrawlerRunner.spiders or instantiate "
                          "scrapy.spidermanager.SpiderManager with your "
                          "settings.",
                          category=ScrapyDeprecationWarning, stacklevel=2)
            spman_cls = load_object(self.settings['SPIDER_MANAGER_CLASS'])
            self._spiders = spman_cls.from_settings(self.settings)
        return self._spiders

    @defer.inlineCallbacks
    def crawl(self, *args, **kwargs):
        assert not self.crawling, "Crawling already taking place"
        self.crawling = True

        try:
            self.spider = self._create_spider(*args, **kwargs)
            self.engine = self._create_engine()
            start_requests = iter(self.spider.start_requests())
            yield self.engine.open_spider(self.spider, start_requests)
            yield defer.maybeDeferred(self.engine.start)
        except Exception:
            self.crawling = False
            raise

    def _create_spider(self, *args, **kwargs):
        return self.spidercls.from_crawler(self, *args, **kwargs)

    def _create_engine(self):
        return ExecutionEngine(self, lambda _: self.stop())

    @defer.inlineCallbacks
    def stop(self):
        if self.crawling:
            self.crawling = False
            yield defer.maybeDeferred(self.engine.stop)


class CrawlerRunner(object):

    def __init__(self, settings):
        self.settings = settings
        smcls = load_object(settings['SPIDER_MANAGER_CLASS'])
        self.spiders = smcls.from_settings(settings.frozencopy())
        self.crawlers = set()
        self._active = set()

    def crawl(self, crawler_or_spidercls, *args, **kwargs):
        crawler = crawler_or_spidercls
        if not isinstance(crawler_or_spidercls, Crawler):
            crawler = self._create_crawler(crawler_or_spidercls)
            self._setup_crawler_logging(crawler)

        self.crawlers.add(crawler)
        d = crawler.crawl(*args, **kwargs)
        self._active.add(d)

        def _done(result):
            self.crawlers.discard(crawler)
            self._active.discard(d)
            return result

        return d.addBoth(_done)

    def _create_crawler(self, spidercls):
        if isinstance(spidercls, six.string_types):
            spidercls = self.spiders.load(spidercls)
        return Crawler(spidercls, self.settings)

    def _setup_crawler_logging(self, crawler):
        log_observer = log.start_from_crawler(crawler)
        if log_observer:
            crawler.signals.connect(log_observer.stop, signals.engine_stopped)

    def stop(self):
        return defer.DeferredList([c.stop() for c in list(self.crawlers)])

    @defer.inlineCallbacks
    def join(self):
        """Wait for all managed crawlers to complete"""
        while self._active:
            yield defer.DeferredList(self._active)
