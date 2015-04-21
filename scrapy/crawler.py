import six
import signal
import warnings

from twisted.internet import reactor, defer
from zope.interface.verify import verifyClass

from scrapy.core.engine import ExecutionEngine
from scrapy.resolver import CachingThreadedResolver
from scrapy.interfaces import ISpiderLoader
from scrapy.extension import ExtensionManager
from scrapy.settings import Settings
from scrapy.signalmanager import SignalManager
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.ossignal import install_shutdown_handlers, signal_names
from scrapy.utils.misc import load_object
from scrapy import log, signals


class Crawler(object):

    def __init__(self, spidercls, settings):
        if isinstance(settings, dict):
            settings = Settings(settings)

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
                          "CrawlerRunner.spider_loader or instantiate "
                          "scrapy.spiderloader.SpiderLoader with your "
                          "settings.",
                          category=ScrapyDeprecationWarning, stacklevel=2)
            self._spiders = _get_spider_loader(self.settings.frozencopy())
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
        if isinstance(settings, dict):
            settings = Settings(settings)
        self.settings = settings
        self.spider_loader = _get_spider_loader(settings)
        self.crawlers = set()
        self._active = set()

    @property
    def spiders(self):
        warnings.warn("CrawlerRunner.spiders attribute is renamed to "
                      "CrawlerRunner.spider_loader.",
                      category=ScrapyDeprecationWarning, stacklevel=2)
        return self.spider_loader

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
            spidercls = self.spider_loader.load(spidercls)
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

        cache_size = self.settings.getint('DNSCACHE_SIZE') if self.settings.getbool('DNSCACHE_ENABLED') else 0
        reactor.installResolver(CachingThreadedResolver(reactor, cache_size,
                                                            self.settings.getfloat('DNS_TIMEOUT')))
        tp = reactor.getThreadPool()
        tp.adjustPoolsize(maxthreads=self.settings.getint('REACTOR_THREADPOOL_MAXSIZE'))
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


def _get_spider_loader(settings):
    """ Get SpiderLoader instance from settings """
    if settings.get('SPIDER_MANAGER_CLASS'):
        warnings.warn(
            'SPIDER_MANAGER_CLASS option is deprecated. '
            'Please use SPIDER_LOADER_CLASS.',
            category=ScrapyDeprecationWarning, stacklevel=2
        )
    cls_path = settings.get('SPIDER_MANAGER_CLASS',
                            settings.get('SPIDER_LOADER_CLASS'))
    loader_cls = load_object(cls_path)
    verifyClass(ISpiderLoader, loader_cls)
    return loader_cls.from_settings(settings.frozencopy())
