import signal

from twisted.internet import reactor, defer

from scrapy.core.engine import ExecutionEngine
from scrapy.resolver import CachingThreadedResolver
from scrapy.extension import ExtensionManager
from scrapy.signalmanager import SignalManager
from scrapy.utils.ossignal import install_shutdown_handlers, signal_names
from scrapy.utils.misc import load_object
from scrapy.settings import overridden_settings
from scrapy import log, signals


class Crawler(object):

    def __init__(self, settings):
        self.configured = False
        self.settings = settings
        self.signals = SignalManager(self)
        self.stats = load_object(settings['STATS_CLASS'])(self)

        self.scheduled = {}

    def install(self):
        import scrapy.project
        assert not hasattr(scrapy.project, 'crawler'), "crawler already installed"
        scrapy.project.crawler = self

    def uninstall(self):
        import scrapy.project
        assert hasattr(scrapy.project, 'crawler'), "crawler not installed"
        del scrapy.project.crawler

    def configure(self):
        if self.configured:
            return
        self.configured = True
        d = dict(overridden_settings(self.settings))
        log.msg(format="Overridden settings: %(settings)r", settings=d, level=log.DEBUG)
        lf_cls = load_object(self.settings['LOG_FORMATTER'])
        self.logformatter = lf_cls.from_crawler(self)
        self.extensions = ExtensionManager.from_crawler(self)
        spman_cls = load_object(self.settings['SPIDER_MANAGER_CLASS'])
        self.spiders = spman_cls.from_crawler(self)
        self.engine = ExecutionEngine(self, self._spider_closed)

    def crawl(self, spider, requests=None):
        spider.set_crawler(self)
        if requests is None:
            requests = spider.start_requests()

        if self.configured and self.engine.running:
            assert not self.scheduled
            return self.engine.open_spider(spider, requests)
        else:
            self.scheduled.setdefault(spider, []).extend(requests)

    def _spider_closed(self, spider=None):
        if not self.engine.open_spiders:
            self.stop()

    @defer.inlineCallbacks
    def start(self):
        yield defer.maybeDeferred(self.configure)

        for spider, requests in self.scheduled.iteritems():
            yield self.engine.open_spider(spider, requests)

        yield defer.maybeDeferred(self.engine.start)

    @defer.inlineCallbacks
    def stop(self):
        if self.engine.running:
            yield defer.maybeDeferred(self.engine.stop)


class ProcessMixin(object):
    """ Mixin which provides automatic control of the Twisted reactor and
        installs some convenient signals for shutting it down
    """

    def __init__(self, *a, **kw):
        install_shutdown_handlers(self._signal_shutdown)

    def start(self):
        if self.settings.getbool('DNSCACHE_ENABLED'):
            reactor.installResolver(CachingThreadedResolver(reactor))
        reactor.addSystemEventTrigger('before', 'shutdown', self.stop)
        reactor.run(installSignalHandlers=False)  # blocking call

    def stop(self):
        raise NotImplementedError

    def _stop_reactor(self, _=None):
        try:
            reactor.stop()
        except RuntimeError:  # raised if already stopped or in shutdown stage
            pass

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
        reactor.callFromThread(self._stop_reactor)


class CrawlerProcess(Crawler, ProcessMixin):
    """ A class to run a single Scrapy crawler in a process
    """

    def __init__(self, *a, **kw):
        Crawler.__init__(self, *a, **kw)
        ProcessMixin.__init__(self, *a, **kw)
        self.signals.connect(self.stop, signals.engine_stopped)

    def start(self):
        Crawler.start(self)
        ProcessMixin.start(self)

    def stop(self):
        d = Crawler.stop(self)
        d.addBoth(self._stop_reactor)
        return d


class MultiCrawlerProcess(ProcessMixin):
    """ A class to run multiple scrapy crawlers in a process sequentially
    """

    def __init__(self, settings):
        super(MultiCrawlerProcess, self).__init__(settings)

        self.settings = settings
        self.crawlers = {}
        self.stopping = False

    def create_crawler(self, name):
        if name not in self.crawlers:
            self.crawlers[name] = Crawler(self.settings)

        return self.crawlers[name]

    def start_crawler(self):
        name, crawler = self.crawlers.popitem()

        crawler.sflo = log.start_from_crawler(crawler)
        if crawler.sflo:
            crawler.signals.connect(crawler.sflo.stop, signals.engine_stopped)

        crawler.signals.connect(self.check_done, signals.engine_stopped)
        crawler.start()

        return name, crawler

    def check_done(self, **kwargs):
        if self.crawlers and not self.stopping:
            self.start_crawler()
        else:
            self._stop_reactor()

    def start(self):
        self.start_crawler()
        super(MultiCrawlerProcess, self).start()

    @defer.inlineCallbacks
    def stop(self):
        self.stopping = True

        for crawler in self.crawlers.itervalues():
            if crawler.configured:
                yield crawler.stop()
