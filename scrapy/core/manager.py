import signal

from twisted.internet import reactor

from scrapy.extension import extensions
from scrapy import log
from scrapy.http import Request
from scrapy.core.engine import scrapyengine
from scrapy.spider import spiders
from scrapy.utils.misc import load_object, arg_to_iter
from scrapy.utils.url import is_url
from scrapy.conf import settings

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
            self._install_signals()
        reactor.addSystemEventTrigger('before', 'shutdown', self.stop)

        if not log.started:
            log.start()
        if not extensions.loaded:
            extensions.load()
        if not spiders.loaded:
            spiders.load()
        log.msg("Enabled extensions: %s" % ", ".join(extensions.enabled.iterkeys()),
            level=log.DEBUG)

        scheduler = load_object(settings['SCHEDULER'])()
        scrapyengine.configure(scheduler=scheduler)
        
    def crawl(self, *args):
        """Schedule the given args for crawling. args is a list of urls or domains"""

        requests = self._parse_args(args)
        # schedule initial requests to be scraped at engine start
        for domain in requests or ():
            spider = spiders.fromdomain(domain) 
            for request in requests[domain]:
                scrapyengine.crawl(request, spider)

    def runonce(self, *args):
        """Run the engine until it finishes scraping all domains and then exit"""
        self.configure()
        self.crawl(*args)
        scrapyengine.start()

    def start(self, control_reactor=True):
        """Start the scrapy server, without scheduling any domains"""
        self.configure(control_reactor)
        scrapyengine.keep_alive = True
        scrapyengine.start(control_reactor=control_reactor)
        if control_reactor:
            self.stop()

    def stop(self):
        """Stop the scrapy server, shutting down the execution engine"""
        self.interrupted = True
        scrapyengine.stop()
        log.log_level = -999 # disable logging
        if self.control_reactor:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            if hasattr(signal, "SIGBREAK"):
                signal.signal(signal.SIGBREAK, signal.SIG_IGN)

    def reload_spiders(self):
        """Reload all enabled spiders except for the ones that are currently
        running.
        """
        spiders.reload(skip_domains=scrapyengine.open_domains)

    def _install_signals(self):
        def sig_handler_terminate(signalinfo, param):
            log.msg('Received shutdown request, waiting for deferreds to finish...', log.INFO)
            self.stop()

        signal.signal(signal.SIGTERM, sig_handler_terminate)
        # only handle SIGINT if there isn't already a handler (e.g. for Pdb)
        if signal.getsignal(signal.SIGINT) == signal.default_int_handler:
            signal.signal(signal.SIGINT, sig_handler_terminate)
        # Catch Ctrl-Break in windows
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, sig_handler_terminate)

    def _parse_args(self, args):
        """ Parse crawl arguments and return a dict domains -> [requests] """
        if not args:
            args = [p.domain_name for p in spiders.enabled]

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

scrapymanager = ExecutionManager()
