import signal

from twisted.internet import reactor, defer

from scrapy.xlib.pydispatch import dispatcher
from scrapy.core.engine import ExecutionEngine
from scrapy.core.queue import ExecutionQueue
from scrapy.extension import ExtensionManager
from scrapy.utils.ossignal import install_shutdown_handlers, signal_names
from scrapy import log, signals


class Crawler(object):

    def __init__(self, settings, spiders):
        self.configured = False
        self.settings = settings
        self.spiders = spiders
        self.engine = ExecutionEngine(self)

    def configure(self, queue=None):
        self.extensions = ExtensionManager.from_settings(self.settings)
        if not self.spiders.loaded:
            self.spiders.load()

        self.queue = queue or ExecutionQueue()
        self.engine.configure(self._spider_closed)
        self.configured = True

    @defer.inlineCallbacks
    def _start_next_spider(self):
        spider, requests = yield defer.maybeDeferred(self.queue.get_next)
        if spider:
            self._start_spider(spider, requests)
        if self.engine.has_capacity() and not self._nextcall.active():
            self._nextcall = reactor.callLater(self.queue.polling_delay, \
                self._spider_closed)

    @defer.inlineCallbacks
    def _start_spider(self, spider, requests):
        """Don't call this method. Use self.queue to start new spiders"""
        yield defer.maybeDeferred(self.engine.open_spider, spider)
        for request in requests:
            self.engine.crawl(request, spider)

    @defer.inlineCallbacks
    def _spider_closed(self, spider=None):
        if not self.engine.open_spiders:
            is_finished = yield defer.maybeDeferred(self.queue.is_finished)
            if is_finished:
                self.stop()
                return
        if self.engine.has_capacity():
            self._start_next_spider()

    @defer.inlineCallbacks
    def start(self):
        yield defer.maybeDeferred(self.engine.start)
        self._nextcall = reactor.callLater(0, self._start_next_spider)

    @defer.inlineCallbacks
    def stop(self):
        if self._nextcall.active():
            self._nextcall.cancel()
        if self.engine.running:
            yield defer.maybeDeferred(self.engine.stop)


class CrawlerProcess(Crawler):
    """A class to run a single Scrapy crawler in a process. It provides
    automatic control of the Twisted reactor and installs some convenient
    signals for shutting down the crawl.
    """

    def __init__(self, *a, **kw):
        super(CrawlerProcess, self).__init__(*a, **kw)
        dispatcher.connect(self.stop, signals.engine_stopped)
        install_shutdown_handlers(self._signal_shutdown)

    def start(self):
        super(CrawlerProcess, self).start()
        reactor.addSystemEventTrigger('before', 'shutdown', self.stop)
        reactor.run(installSignalHandlers=False) # blocking call

    def stop(self):
        d = super(CrawlerProcess, self).stop()
        d.addBoth(self._stop_reactor)
        return d

    def _stop_reactor(self, _=None):
        try:
            reactor.stop()
        except RuntimeError: # raised if already stopped or in shutdown stage
            pass

    def _signal_shutdown(self, signum, _):
        install_shutdown_handlers(self._signal_kill)
        signame = signal_names[signum]
        log.msg("Received %s, shutting down gracefully. Send again to force " \
            "unclean shutdown" % signame, level=log.INFO)
        reactor.callFromThread(self.stop)

    def _signal_kill(self, signum, _):
        install_shutdown_handlers(signal.SIG_IGN)
        signame = signal_names[signum]
        log.msg('Received %s twice, forcing unclean shutdown' % signame, \
            level=log.INFO)
        reactor.callFromThread(self._stop_reactor)
