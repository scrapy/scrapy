import signal

from twisted.internet import reactor

from scrapy.extension import extensions
from scrapy import log
from scrapy.http import Request
from scrapy.core.engine import scrapyengine
from scrapy.spider import spiders
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.url import is_url
from scrapy.utils.ossignal import install_shutdown_handlers, signal_names

def _parse_args(args):
    """Parse crawl arguments and return a dict of domains -> list of requests"""
    requests, urls, sites = set(), set(), set()
    for a in args:
        if isinstance(a, Request):
            requests.add(a)
        elif is_url(a):
            urls.add(a)
        else:
            sites.add(a)

    perdomain = {}

    # sites
    for domain in sites:
        spider = spiders.fromdomain(domain)
        if not spider:
            log.msg('Could not find spider for %s' % domain, log.ERROR)
            continue
        reqs = spider.start_requests()
        perdomain.setdefault(domain, []).extend(reqs)

    # urls
    for url in urls:
        spider = spiders.fromurl(url)
        if spider:
            for req in arg_to_iter(spider.make_requests_from_url(url)):
                perdomain.setdefault(spider.domain_name, []).append(req)
        else:
            log.msg('Could not find spider for <%s>' % url, log.ERROR)

    # requests
    for request in requests:
        spider = spiders.fromurl(request.url)
        if not spider:
            log.msg('Could not find spider for %s' % request, log.ERROR)
            continue
        perdomain.setdefault(spider.domain_name, []).append(request)
    return perdomain


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

        requests = _parse_args(args)
        # schedule initial requests to be scraped at engine start
        for domain in requests or ():
            spider = spiders.fromdomain(domain) 
            for request in requests[domain]:
                scrapyengine.crawl(request, spider)

    def runonce(self, *args):
        """Run the engine until it finishes scraping all domains and then exit"""
        assert self.configured, "Scrapy Manger not yet configured"
        self.crawl(*args)
        scrapyengine.start()
        if self.control_reactor:
            reactor.run(installSignalHandlers=False)

    def start(self):
        """Start the scrapy server, without scheduling any domains"""
        assert self.configured, "Scrapy Manger not yet configured"
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
