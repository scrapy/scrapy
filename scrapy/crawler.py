import signal

from twisted.internet import reactor, defer

from scrapy.core.engine import ExecutionEngine
from scrapy.resolver import CachingThreadedResolver
from scrapy.extension import ExtensionManager
from scrapy.signalmanager import SignalManager
from scrapy.utils.ossignal import install_shutdown_handlers, signal_names
from scrapy.utils.misc import load_object
from scrapy import log, signals


class Crawler(object):

    def __init__(self, settings):
        self.configured = False
        self.settings = settings
        self.signals = SignalManager(self)
        self.stats = load_object(settings['STATS_CLASS'])(self)

        spman_cls = load_object(self.settings['SPIDER_MANAGER_CLASS'])
        self.spiders = spman_cls.from_crawler(self)

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
        lf_cls = load_object(self.settings['LOG_FORMATTER'])
        self.logformatter = lf_cls.from_crawler(self)
        self.extensions = ExtensionManager.from_crawler(self)
        self.engine = ExecutionEngine(self, self._spider_closed)

    def crawl(self, spider, requests=None):
        spider.set_crawler(self)

        if self.configured and self.engine.running:
            assert not self.scheduled
            return self.schedule(spider, requests)
        else:
            self.scheduled.setdefault(spider, []).append(requests)

    def schedule(self, spider, batches=[]):
        requests = []
        for batch in batches:
            if batch is None:
                batch = spider.start_requests()
            requests.extend(batch)

        return self.engine.open_spider(spider, requests)

    def _spider_closed(self, spider=None):
        if not self.engine.open_spiders:
            self.stop()

    @defer.inlineCallbacks
    def start(self):
        yield defer.maybeDeferred(self.configure)

        for spider, batches in self.scheduled.iteritems():
            yield self.schedule(spider, batches)

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
        self.start_crawling()
        self.start_reactor()

    def start_reactor(self):
        if self.settings.getbool('DNSCACHE_ENABLED'):
            reactor.installResolver(CachingThreadedResolver(reactor))
        reactor.addSystemEventTrigger('before', 'shutdown', self.stop)
        reactor.run(installSignalHandlers=False)  # blocking call

    def start_crawling(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def stop_reactor(self, _=None):
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
        reactor.callFromThread(self.stop_reactor)


class CrawlerProcess(ProcessMixin):
    """ A class to run multiple scrapy crawlers in a process sequentially
    """

    def __init__(self, settings):
        super(CrawlerProcess, self).__init__(settings)

        self.settings = settings
        self.crawlers = {}
        self.stopping = False

    def create_crawler(self, name=None):
        if name not in self.crawlers:
            self.crawlers[name] = Crawler(self.settings)

        return self.crawlers[name]

    def start_crawler(self):
        name, crawler = self.crawlers.popitem()

        sflo = log.start_from_crawler(crawler)
        crawler.configure()
        crawler.install()
        crawler.signals.connect(crawler.uninstall, signals.engine_stopped)
        if sflo:
            crawler.signals.connect(sflo.stop, signals.engine_stopped)

        crawler.signals.connect(self.check_done, signals.engine_stopped)
        crawler.start()

        return name, crawler

    def check_done(self, **kwargs):
        if self.crawlers and not self.stopping:
            self.start_crawler()
        else:
            self.stop_reactor()

    def start_crawling(self):
        log.scrapy_info(self.settings)
        self.start_crawler()

    @defer.inlineCallbacks
    def stop(self):
        self.stopping = True

        for crawler in self.crawlers.itervalues():
            if crawler.configured:
                yield crawler.stop()
