import signal

from twisted.internet import reactor

from scrapy.extension import extensions
from scrapy import log
from scrapy.http import Request
from scrapy.core.engine import scrapyengine
from scrapy.spider import BaseSpider, spiders
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.url import is_url
from scrapy.utils.ossignal import install_shutdown_handlers, signal_names


class ExecutionManager(object):
    """Process a list of sites or urls.

    This class should be used in a main for process a list of sites/urls.

    It extracts products and could be used to store results in a database or
    just for testing spiders.
    """
    def __init__(self):
        self.interrupted = False
        self.configured = False
        self.control_reactor = True

    def configure(self, control_reactor=True):
        self.control_reactor = control_reactor
        if control_reactor:
            install_shutdown_handlers(self._signal_shutdown)
        reactor.addSystemEventTrigger('before', 'shutdown', scrapyengine.stop)

        if not log.started:
            log.start()
        if not extensions.loaded:
            extensions.load()
        if not spiders.loaded:
            spiders.load()
        log.msg("Enabled extensions: %s" % ", ".join(extensions.enabled.iterkeys()),
            level=log.DEBUG)

        scrapyengine.configure()
        self.configured = True
        
    def crawl_url(self, url, spider=None):
        """Schedule given url for crawling."""
        spider = spider or spiders.fromurl(url)
        if spider:
            requests = arg_to_iter(spider.make_requests_from_url(url))
            self._crawl_requests(requests, spider)
        else:
            log.msg('Could not find spider for url: %s' % url, log.ERROR)

    def crawl_request(self, request, spider=None):
        """Schedule request for crawling."""
        assert self.configured, "Scrapy Manager not yet configured"
        spider = spider or spiders.fromurl(request.url)
        if spider:
            scrapyengine.crawl(request, spider)
        else:
            log.msg('Could not find spider for request: %s' % url, log.ERROR)

    def crawl_domain(self, domain):
        """Schedule given domain for crawling."""
        spider = spiders.fromdomain(domain)
        if spider:
            self.crawl_spider(spider)
        else:
            log.msg('Could not find spider for domain: %s' % domain, log.ERROR)

    def crawl_spider(self, spider):
        """Schedule spider for crawling."""
        requests = spider.start_requests()
        self._crawl_requests(requests, spider)

    def _crawl_requests(self, requests, spider):
        for req in requests:
            self.crawl_request(req, spider)

    def start(self, keep_alive=False):
        """Start the scrapy server, without scheduling any domains"""
        scrapyengine.keep_alive = keep_alive
        scrapyengine.start()
        if self.control_reactor:
            reactor.run(installSignalHandlers=False)

    def stop(self):
        """Stop the scrapy server, shutting down the execution engine"""
        self.interrupted = True
        scrapyengine.stop()

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
        reactor.callFromThread(scrapyengine.kill)
        install_shutdown_handlers(signal.SIG_IGN)

scrapymanager = ExecutionManager()
