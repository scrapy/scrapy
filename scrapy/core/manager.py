import signal

from twisted.internet import reactor, defer

from scrapy.core.engine import ExecutionEngine
from scrapy.core.queue import ExecutionQueue
from scrapy.extension import extensions
from scrapy import log
from scrapy.spider import spiders
from scrapy.utils.ossignal import install_shutdown_handlers, signal_names


class ExecutionManager(object):

    def __init__(self):
        self.configured = False
        self.control_reactor = True
        self.engine = ExecutionEngine()

    def configure(self, control_reactor=True, queue=None):
        self.control_reactor = control_reactor
        if control_reactor:
            install_shutdown_handlers(self._signal_shutdown)

        if not log.started:
            log.start()
        if not extensions.loaded:
            extensions.load()
        if not spiders.loaded:
            spiders.load()
        log.msg("Enabled extensions: %s" % ", ".join(extensions.enabled.iterkeys()),
            level=log.DEBUG)

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
        reactor.addSystemEventTrigger('before', 'shutdown', self.stop)
        if self.control_reactor:
            reactor.run(installSignalHandlers=False)

    @defer.inlineCallbacks
    def stop(self):
        if self._nextcall.active():
            self._nextcall.cancel()
        if self.engine.running:
            yield defer.maybeDeferred(self.engine.stop)
        try:
            reactor.stop()
        except RuntimeError: # raised if already stopped or in shutdown stage
            pass

    def _signal_shutdown(self, signum, _):
        signame = signal_names[signum]
        log.msg("Received %s, shutting down gracefully. Send again to force " \
            "unclean shutdown" % signame, level=log.INFO)
        reactor.callFromThread(self.stop)
        install_shutdown_handlers(self._signal_kill)

    def _signal_kill(self, signum, _):
        signame = signal_names[signum]
        log.msg('Received %s twice, forcing unclean shutdown' % signame, \
            level=log.INFO)
        log.log_level = log.SILENT # disable logging of confusing tracebacks
        reactor.callFromThread(self.engine.kill)
        install_shutdown_handlers(signal.SIG_IGN)

scrapymanager = ExecutionManager()
