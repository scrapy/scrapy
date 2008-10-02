import signal

from scrapy.extension import extensions
from scrapy import log
from scrapy.http import Request
from scrapy.core.engine import scrapyengine
from scrapy.spider import spiders
from scrapy.utils.misc import load_class
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

    def configure(self, *args, **opts):
        self._install_signals()

        extensions.load()
        log.msg("Enabled extensions: %s" % ", ".join(extensions.enabled.iterkeys()))

        scheduler = load_class(settings['SCHEDULER'])()

        scrapyengine.configure(scheduler=scheduler)

        self.prioritizer_class = load_class(settings['PRIORITIZER'])

        requests = self._parse_args(args)
        self.priorities = self.prioritizer_class(requests.keys())

        #applies a time (in seconds) between succesive requests crawl
        #useful for applications that runs softly distributed in time
        self.crawl_delay = opts.get("crawl_delay", 0)
        
        
    def crawl(self, *args):
        """Schedule the given args for crawling. args is a list of urls or domains"""

        requests = self._parse_args(args)
        # schedule initial requets to be scraped at engine start
        
        def _issue():
            for domain in requests or ():
                spider = spiders.fromdomain(domain)
                priority = self.priorities.get_priority(domain)
                for request in requests[domain]:
                    yield request, spider, priority

        if self.crawl_delay:
            gen = _issue()
            def _soft_crawl():
                try:
                    request, spider, priority = gen.next()
                    scrapyengine.crawl(request, spider, domain_priority=priority)
                    log.msg("Delaying %ss the next request." % self.crawl_delay)
                except StopIteration:
                    self.stop()

            scrapyengine.addtask(_soft_crawl, self.crawl_delay)

        else:
            for request, spider, priority in _issue():
                scrapyengine.crawl(request, spider, domain_priority=priority)

    def runonce(self, *args, **opts):
        """Run the engine until it finishes scraping all domains and then exit"""
        self.configure(*args, **opts)
        self.crawl(*args)
        scrapyengine.start()

    def start(self, **opts):
        """Start the scrapy server, without scheduling any domains"""
        self.configure(**opts)
        scrapyengine.keep_alive = True
        scrapyengine.start()# blocking call
        self.stop()

    def stop(self):
        """Stop the scrapy server, shutting down the execution engine"""
        self.interrupted = True
        scrapyengine.stop()
        log.log_level = -999 # disable logging
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, signal.SIG_IGN)

    def reload_spiders(self):
        """
        Reload all enabled spiders except for the ones that are currently
        running.

        """
        spiders.reload(skip_domains=scrapyengine.open_domains)
        # reload priorities for the new domains
        self.priorities = self.prioritizer_class(spiders.asdict(include_disabled=False).keys())

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
        def _add(domain, request):
            if domain not in perdomain:
                perdomain[domain] = []
            perdomain[domain] += [request]

        # sites
        for domain in sites:
            spider = spiders.fromdomain(domain)
            if not spider:
                log.msg('Could not found spider for %s' % domain, log.ERROR)
                continue
            for url in self._start_urls(spider):
                request = Request(url, callback=spider.parse, dont_filter=True)
                _add(domain, request)
        # urls
        for url in urls:
            spider = spiders.fromurl(url)
            if spider:
                request = Request(url=url, callback=spider.parse, dont_filter=True)
                _add(spider.domain_name, request)
            else:
                log.msg('Could not found spider for <%s>' % url, log.ERROR)

        # requests
        for request in requests:
            if request.domain:
                spider = spiders.fromdomain(request.domain)
            else:
                spider = spiders.fromurl(request.url)
            if not spider:
                log.msg('Could not found spider for %s' % request, log.ERROR)
                continue
            _add(spider.domain_name, request)
        return perdomain

    def _start_urls(self, spider):
        return spider.start_urls if hasattr(spider.start_urls, '__iter__') else [spider.start_urls]
        
scrapymanager = ExecutionManager()
