import six
import signal
import warnings

from twisted.internet import reactor, defer

from scrapy.core.engine import ExecutionEngine
from scrapy.resolver import CachingThreadedResolver
from scrapy.extension import ExtensionManager
from scrapy.signalmanager import SignalManager
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.ossignal import install_shutdown_handlers, signal_names
from scrapy.utils.misc import load_object
from scrapy import log, signals


class Crawler(object):

    def __init__(self, spidercls, settings):
        self.spidercls = spidercls
        self.settings = settings
        self.signals = SignalManager(self)
        self.stats = load_object(self.settings['STATS_CLASS'])(self)
        lf_cls = load_object(self.settings['LOG_FORMATTER'])
        self.logformatter = lf_cls.from_crawler(self)
        self.extensions = ExtensionManager.from_crawler(self)

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

    def crawl(self, spidercls, *args, **kwargs):
        crawler = self._create_crawler(spidercls)
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

        crawler_settings = self.settings.copy()
        spidercls.update_settings(crawler_settings)
        crawler_settings.freeze()
        return Crawler(spidercls, crawler_settings)

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


class CrawlerProcess(CrawlerRunner):
    """A class to run multiple scrapy crawlers in a process simultaneously"""

    def __init__(self, settings):
        super(CrawlerProcess, self).__init__(settings)
        install_shutdown_handlers(self._signal_shutdown)
        self.stopping = False
        self.log_observer = log.start_from_settings(self.settings)
        log.scrapy_info(settings)

    def _signal_shutdown(self, signum, _):
        install_shutdown_handlers(self._signal_kill)
        signame = signal_names[signum]
        log.msg(format="Received %(signame)s, shutting down gracefully. Send again to force ",
                level=log.INFO, signame=signame)
        reactor.callFromThread(self.stop)

    def _signal_kill(self, signum, _):
        install_shutdown_handlers(signal.SIG_IGN)
        signame = signal_names[signum]
        log.msg(format='Received %(signame)s twice, forcing unclean shutdown',
                level=log.INFO, signame=signame)
        self._stop_logging()
        reactor.callFromThread(self._stop_reactor)

    def start(self, stop_after_crawl=True):
        if stop_after_crawl:
            d = self.join()
            # Don't start the reactor if the deferreds are already fired
            if d.called:
                return
            d.addBoth(lambda _: self._stop_reactor())

        if self.settings.getbool('DNSCACHE_ENABLED'):
            reactor.installResolver(CachingThreadedResolver(reactor))

        reactor.addSystemEventTrigger('before', 'shutdown', self.stop)
        reactor.run(installSignalHandlers=False)  # blocking call

    def _stop_logging(self):
        if self.log_observer:
            self.log_observer.stop()

    def _stop_reactor(self, _=None):
        try:
            reactor.stop()
        except RuntimeError:  # raised if already stopped or in shutdown stage
            pass
