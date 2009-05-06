"""
Download web pages using asynchronous IO
"""

import datetime

from twisted.internet import reactor, defer

from scrapy.core.exceptions import IgnoreRequest
from scrapy.spider import spiders
from scrapy.core.downloader.handlers import download_any
from scrapy.core.downloader.middleware import DownloaderMiddlewareManager
from scrapy import log
from scrapy.conf import settings
from scrapy.utils.defer import chain_deferred, mustbe_deferred
from scrapy.utils.request import request_info


class SiteDetails(object):
    """This is a simple data record that encapsulates the details we hold on
    each domain which we are scraping.
    """
    def __init__(self, download_delay=None, max_concurrent_requests=2):
        self.download_delay = download_delay
        self.max_concurrent_requests = max_concurrent_requests if not download_delay else 1

        self.queue = []
        self.active = set()
        self.downloading = set()
        self.closed = False
        self.lastseen = None

    def is_idle(self):
        return not (self.active or self.downloading)

    def capacity(self):
        return self.max_concurrent_requests - len(self.downloading)

    def outstanding(self):
        return len(self.active) + len(self.queue)

    def needs_backout(self):
        return self.outstanding() > (2 * self.max_concurrent_requests)


class Downloader(object):
    """Mantain many concurrent downloads and provide an HTTP abstraction.
    It supports a limited number of connections per domain and many domains in
    parallel.
    """

    def __init__(self, engine):
        """Create the downlaoder. 
        
        ``engine`` is the scrapy engine controlling this downloader
        """

        self.engine = engine
        self.sites = {}
        self.middleware = DownloaderMiddlewareManager()
        self.middleware.download_function = self.enqueue
        self.download_function = download_any
        self.concurrent_domains = settings.getint('CONCURRENT_DOMAINS')
        self.debug_mode = settings.getbool('DOWNLOADER_DEBUG')

    def fetch(self, request, spider):
        """ Main method to use to request a download

        This method includes middleware mangling. Middleware can returns a
        Response object, then request never reach downloader queue, and it will
        not be downloaded from site.
        """
        domain = spider.domain_name
        site = self.sites[domain]
        if not site or site.closed:
            raise IgnoreRequest('Unable to fetch (domain already closed): %s' % request)

        site.active.add(request)
        def _deactivate(_):
            site.active.remove(request)
            return _
        dwld = self.middleware.download(request, spider)
        dwld.addBoth(_deactivate)
        return dwld

    def enqueue(self, request, spider):
        """ Enqueue a Request for a effective download from site
        """
        domain = spider.domain_name
        site = self.sites.get(domain)
        if not site or site.closed:
            raise IgnoreRequest('Trying to enqueue %s from closed site %s' % (request, domain))

        deferred = defer.Deferred()
        site.queue.append((request, deferred))
        self.process_queue(spider)
        return deferred

    def process_queue(self, spider):
        """ Effective download requests from site queue
        """
        domain = spider.domain_name
        site = self.sites.get(domain)
        if not site:
            return

        # download delay handling
        now = datetime.datetime.now()
        if site.download_delay and site.lastseen:
            delta = now - site.lastseen
            penalty = site.download_delay - delta.seconds
            if penalty > 0:
                reactor.callLater(penalty, self.process_queue, spider=spider)
                return
        site.lastseen = now

        while site.queue and site.capacity()>0:
            request, deferred = site.queue.pop(0)
            self._download(request, spider, deferred)

        if site.closed and site.is_idle():
            del self.sites[domain]
            self.engine.closed_domain(domain)

    def _download(self, request, spider, deferred):
        if self.debug_mode:
            log.msg('Activating %s' % request_info(request), log.DEBUG)
        domain = spider.domain_name
        site = self.sites.get(domain)
        site.downloading.add(request)

        def _remove(result):
            if self.debug_mode:
                log.msg('Deactivating %s' % request_info(request), log.DEBUG)
            site.downloading.remove(request)
            return result

        def _finish(result):
            self.process_queue(spider)

        dwld = mustbe_deferred(self.download_function, request, spider)
        dwld.addBoth(_remove)
        chain_deferred(dwld, deferred)
        dwld.addBoth(_finish)

    def open_domain(self, domain):
        """Allocate resources to begin processing a domain"""
        spider = spiders.fromdomain(domain)
        if domain in self.sites: # reopen
            self.sites[domain].closed = False
            return

        # Instanciate site specific handling based on info provided by spider
        delay = getattr(spider, 'download_delay', None) or settings.getint("DOWNLOAD_DELAY", 0)
        maxcr = getattr(spider, 'max_concurrent_requests', settings.getint('REQUESTS_PER_DOMAIN'))
        site = SiteDetails(download_delay=delay, max_concurrent_requests=maxcr)
        self.sites[domain] = site

    def close_domain(self, domain):
        """Free any resources associated with the given domain"""
        if self.debug_mode:
            log.msg("Downloader closing domain %s" % domain, log.DEBUG, domain=domain)
        site = self.sites.get(domain)
        if site:
            site.closed = True
            spider = spiders.fromdomain(domain)
            self.process_queue(spider)
        else:
            if self.debug_mode:
                log.msg('Domain %s already closed' % domain, log.DEBUG, domain=domain)

    def needs_backout(self, domain):
        site = self.sites.get(domain)
        return (site.needs_backout() if site else True)

    # Most of the following functions must be reviewed to decide if are really needed
    def domain_is_open(self, domain):
        return domain in self.sites

    def lastseen(self, domain):
        if domain in self.sites:
            return self.sites[domain].lastseen

    def outstanding(self, domain):
        """The number of outstanding requests for a domain
        This includes both active requests and pending requests.
        """
        site = self.sites.get(domain)
        if site:
            return site.outstanding()

    def domain_is_idle(self, domain):
        return not self.outstanding(domain)

    def request_queue(self, domain):
        site = self.sites.get(domain)
        return site.queue if site else []

    def active_requests(self, domain):
        site = self.sites.get(domain)
        return site.active if site else []

    def has_capacity(self):
        """Does the downloader have capacity to handle more domains"""
        return len(self.sites) < self.concurrent_domains

    def is_idle(self):
        return not self.sites

