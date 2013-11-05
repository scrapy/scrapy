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
        self._start_requests = lambda: ()
        self._spider = None
        # TODO: move SpiderManager to CrawlerProcess
        spman_cls = load_object(self.settings['SPIDER_MANAGER_CLASS'])
        self.spiders = spman_cls.from_crawler(self)

    def install(self):
        # TODO: remove together with scrapy.project.crawler usage
        import scrapy.project
        assert not hasattr(scrapy.project, 'crawler'), "crawler already installed"
        scrapy.project.crawler = self

    def uninstall(self):
        # TODO: remove together with scrapy.project.crawler usage
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
        assert self._spider is None, 'Spider already attached'
        self._spider = spider
        spider.set_crawler(self)
        if requests is None:
            self._start_requests = spider.start_requests
        else:
            self._start_requests = lambda: requests

    def _spider_closed(self, spider=None):
        if not self.engine.open_spiders:
            self.stop()

    @defer.inlineCallbacks
    def start(self):
        yield defer.maybeDeferred(self.configure)
        if self._spider:
            yield self.engine.open_spider(self._spider, self._start_requests())
        yield defer.maybeDeferred(self.engine.start)

    @defer.inlineCallbacks
    def stop(self):
        if self.configured and self.engine.running:
            yield defer.maybeDeferred(self.engine.stop)


class CrawlerProcess(object):
    """ A class to run multiple scrapy crawlers in a process sequentially"""

    def __init__(self, settings):
        install_shutdown_handlers(self._signal_shutdown)
        self.settings = settings
        self.crawlers = {}
        self.stopping = False
        self._started = None

    def create_crawler(self, name=None):
        if name not in self.crawlers:
            self.crawlers[name] = Crawler(self.settings)

        return self.crawlers[name]

    def start(self):
        if self.start_crawling():
            self.start_reactor()

    @defer.inlineCallbacks
    def stop(self):
        self.stopping = True
        if self._active_crawler:
            yield self._active_crawler.stop()

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

    # ------------------------------------------------------------------------#
    # The following public methods can't be considered stable and may change at
    # any moment.
    #
    # start_crawling and start_reactor are called from scrapy.commands.shell
    # They are splitted because reactor is started on a different thread than IPython shell.
    #
    def start_crawling(self):
        log.scrapy_info(self.settings)
        return self._start_crawler() is not None

    def start_reactor(self):
        if self.settings.getbool('DNSCACHE_ENABLED'):
            reactor.installResolver(CachingThreadedResolver(reactor))
        reactor.addSystemEventTrigger('before', 'shutdown', self.stop)
        reactor.run(installSignalHandlers=False)  # blocking call

    def _start_crawler(self):
        if not self.crawlers or self.stopping:
            return

        name, crawler = self.crawlers.popitem()
        self._active_crawler = crawler
        sflo = log.start_from_crawler(crawler)
        crawler.configure()
        crawler.install()
        crawler.signals.connect(crawler.uninstall, signals.engine_stopped)
        if sflo:
            crawler.signals.connect(sflo.stop, signals.engine_stopped)
        crawler.signals.connect(self._check_done, signals.engine_stopped)
        crawler.start()
        return name, crawler

    def _check_done(self, **kwargs):
        if not self._start_crawler():
            self._stop_reactor()

    def _stop_reactor(self, _=None):
        try:
            reactor.stop()
        except RuntimeError:  # raised if already stopped or in shutdown stage
            pass
