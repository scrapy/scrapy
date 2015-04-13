import signal

from twisted.internet import reactor

from scrapy import log
from scrapy.crawler import CrawlerRunner
from scrapy.resolver import CachingThreadedResolver
from scrapy.utils.ossignal import install_shutdown_handlers, signal_names


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
