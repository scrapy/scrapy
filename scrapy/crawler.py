import six
import signal
import logging
import warnings

from twisted.internet import reactor, defer
from zope.interface.verify import verifyClass, DoesNotImplement

from scrapy.core.engine import ExecutionEngine
from scrapy.resolver import CachingThreadedResolver
from scrapy.interfaces import ISpiderLoader
from scrapy.extensions import ExtensionManager
from scrapy.settings import Settings
from scrapy.signalmanager import SignalManager
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.ossignal import install_shutdown_handlers, signal_names
from scrapy.utils.misc import load_object
from scrapy.utils.log import LogCounterHandler, configure_logging, log_scrapy_info
from scrapy import signals

logger = logging.getLogger(__name__)


class Crawler(object):

    def __init__(self, spidercls, settings):
        if isinstance(settings, dict):
            settings = Settings(settings)

        self.spidercls = spidercls
        self.settings = settings.copy()

        self.signals = SignalManager(self)
        self.stats = load_object(self.settings['STATS_CLASS'])(self)

        handler = LogCounterHandler(self, level=settings.get('LOG_LEVEL'))
        logging.root.addHandler(handler)
        self.signals.connect(lambda: logging.root.removeHandler(handler),
                             signals.engine_stopped)

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
    """
    This is a convenient helper class that keeps track of, manages and runs
    crawlers inside an already setup Twisted `reactor`_.

    The CrawlerRunner object must be instantiated with a
    :class:`~scrapy.settings.Settings` object.

    This class shouldn't be needed (since Scrapy is responsible of using it
    accordingly) unless writing scripts that manually handle the crawling
    process. See :ref:`run-from-script` for an example.
    """

    crawlers = property(
        lambda self: self._crawlers,
        doc="Set of :class:`crawlers <scrapy.crawler.Crawler>` started by "
            ":meth:`crawl` and managed by this class."
    )

    def __init__(self, settings):
        if isinstance(settings, dict):
            settings = Settings(settings)
        self.settings = settings
        self.spider_loader = _get_spider_loader(settings)
        self._crawlers = set()
        self._active = set()

    @property
    def spiders(self):
        warnings.warn("CrawlerRunner.spiders attribute is renamed to "
                      "CrawlerRunner.spider_loader.",
                      category=ScrapyDeprecationWarning, stacklevel=2)
        return self.spider_loader

    def crawl(self, crawler_or_spidercls, *args, **kwargs):
        """
        Run a crawler with the provided arguments.

        It will call the given Crawler's :meth:`~Crawler.crawl` method, while
        keeping track of it so it can be stopped later.

        If `crawler_or_spidercls` isn't a :class:`~scrapy.crawler.Crawler`
        instance, this method will try to create one using this parameter as
        the spider class given to it.

        Returns a deferred that is fired when the crawling is finished.

        :param crawler_or_spidercls: already created crawler, or a spider class
            or spider's name inside the project to create it
        :type crawler_or_spidercls: :class:`~scrapy.crawler.Crawler` instance,
            :class:`~scrapy.spider.Spider` subclass or string

        :param list args: arguments to initialize the spider

        :param dict kwargs: keyword arguments to initialize the spider
        """
        crawler = crawler_or_spidercls
        if not isinstance(crawler_or_spidercls, Crawler):
            crawler = self._create_crawler(crawler_or_spidercls)

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

    def stop(self):
        """
        Stops simultaneously all the crawling jobs taking place.

        Returns a deferred that is fired when they all have ended.
        """
        return defer.DeferredList([c.stop() for c in list(self.crawlers)])

    @defer.inlineCallbacks
    def join(self):
        """
        join()

        Returns a deferred that is fired when all managed :attr:`crawlers` have
        completed their executions.
        """
        while self._active:
            yield defer.DeferredList(self._active)


class CrawlerProcess(CrawlerRunner):
    """
    A class to run multiple scrapy crawlers in a process simultaneously.

    This class extends :class:`~scrapy.crawler.CrawlerRunner` by adding support
    for starting a Twisted `reactor`_ and handling shutdown signals, like the
    keyboard interrupt command Ctrl-C. It also configures top-level logging.

    This utility should be a better fit than
    :class:`~scrapy.crawler.CrawlerRunner` if you aren't running another
    Twisted `reactor`_ within your application.

    The CrawlerProcess object must be instantiated with a
    :class:`~scrapy.settings.Settings` object.

    This class shouldn't be needed (since Scrapy is responsible of using it
    accordingly) unless writing scripts that manually handle the crawling
    process. See :ref:`run-from-script` for an example.
    """

    def __init__(self, settings):
        super(CrawlerProcess, self).__init__(settings)
        install_shutdown_handlers(self._signal_shutdown)
        self.stopping = False
        configure_logging(settings)
        log_scrapy_info(settings)

    def _signal_shutdown(self, signum, _):
        install_shutdown_handlers(self._signal_kill)
        signame = signal_names[signum]
        logger.info("Received %(signame)s, shutting down gracefully. Send again to force ",
                    {'signame': signame})
        reactor.callFromThread(self.stop)

    def _signal_kill(self, signum, _):
        install_shutdown_handlers(signal.SIG_IGN)
        signame = signal_names[signum]
        logger.info('Received %(signame)s twice, forcing unclean shutdown',
                    {'signame': signame})
        reactor.callFromThread(self._stop_reactor)

    def start(self, stop_after_crawl=True):
        """
        This method starts a Twisted `reactor`_, adjusts its pool size to
        :setting:`REACTOR_THREADPOOL_MAXSIZE`, and installs a DNS cache based
        on :setting:`DNSCACHE_ENABLED` and :setting:`DNSCACHE_SIZE`.

        If `stop_after_crawl` is True, the reactor will be stopped after all
        crawlers have finished, using :meth:`join`.

        :param boolean stop_after_crawl: stop or not the reactor when all
            crawlers have finished
        """
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
    try:
        verifyClass(ISpiderLoader, loader_cls)
    except DoesNotImplement:
        warnings.warn(
            'SPIDER_LOADER_CLASS (previously named SPIDER_MANAGER_CLASS) does '
            'not fully implement scrapy.interfaces.ISpiderLoader interface. '
            'Please add all missing methods to avoid unexpected runtime errors.',
            category=ScrapyDeprecationWarning, stacklevel=2
        )
    return loader_cls.from_settings(settings.frozencopy())
