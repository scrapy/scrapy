import signal
from collections import defaultdict

from twisted.internet import reactor

from scrapy.extension import extensions
from scrapy import log
from scrapy.http import Request
from scrapy.core.engine import scrapyengine
from scrapy.spider import BaseSpider, spiders
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.url import is_url
from scrapy.utils.ossignal import install_shutdown_handlers, signal_names

def _get_spider_requests(*args):
    """Collect requests and spiders from the given arguments. Returns a dict of
    spider -> list of requests
    """
    spider_requests = defaultdict(list)
    for arg in args:
        if isinstance(arg, tuple):
            request, spider = arg
            spider_requests[spider] = request
        elif isinstance(arg, Request):
            spider = spiders.fromurl(arg.url) or BaseSpider('default')
            if spider:
                spider_requests[spider] += [arg]
            else:
                log.msg('Could not find spider for request: %s' % arg, log.ERROR)
        elif isinstance(arg, BaseSpider):
            spider_requests[arg] += arg.start_requests()
        elif is_url(arg):
            spider = spiders.fromurl(arg) or BaseSpider('default')
            if spider:
                for req in arg_to_iter(spider.make_requests_from_url(arg)):
                    spider_requests[spider] += [req]
            else:
                log.msg('Could not find spider for url: %s' % arg, log.ERROR)
        elif isinstance(arg, basestring):
            spider = spiders.fromdomain(arg)
            if spider:
                spider_requests[spider] += spider.start_requests()
            else:
                log.msg('Could not find spider for domain: %s' % arg, log.ERROR)
        else:
            raise TypeError("Unsupported argument: %r" % arg)
    return spider_requests


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
        
    def crawl(self, *args):
        """Schedule the given args for crawling. args is a list of urls or domains"""
        assert self.configured, "Scrapy Manager not yet configured"
        spider_requests = _get_spider_requests(*args)
        for spider, requests in spider_requests.iteritems():
            for request in requests:
                scrapyengine.crawl(request, spider)

    def runonce(self, *args):
        """Run the engine until it finishes scraping all domains and then exit"""
        self.crawl(*args)
        scrapyengine.start()
        if self.control_reactor:
            reactor.run(installSignalHandlers=False)

    def start(self):
        """Start the scrapy server, without scheduling any domains"""
        scrapyengine.keep_alive = True
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
