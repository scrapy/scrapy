"""
Download web pages using asynchronous IO
"""

import datetime

from twisted.internet import reactor, defer

from scrapy.core.exceptions import IgnoreRequest
from scrapy.spider import spiders
from scrapy.core.downloader.middleware import DownloaderMiddlewareManager
from scrapy.core.downloader.handlers import download_any
from scrapy.conf import settings
from scrapy.utils.defer import chain_deferred, mustbe_deferred


class SiteInfo(object):
    """This is a simple data record that encapsulates the details we hold on
    each domain which we are scraping.
    """
    def __init__(self, download_delay=None, max_concurrent_requests=None):
        if download_delay is None:
            self.download_delay = settings.getint('DOWNLOAD_DELAY')
        else:
            self.download_delay = download_delay
        if download_delay:
            self.max_concurrent_requests = 1
        elif max_concurrent_requests is None:
            self.max_concurrent_requests = settings.getint('REQUESTS_PER_DOMAIN')
        else:
            self.max_concurrent_requests =  max_concurrent_requests

        self.queue = []
        self.active = set()
        self.transferring = set()
        self.closed = False
        self.lastseen = None

    def is_idle(self):
        return not (self.active or self.transferring)

    def capacity(self):
        return self.max_concurrent_requests - len(self.transferring)

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
        self.concurrent_domains = settings.getint('CONCURRENT_DOMAINS')

    def fetch(self, request, spider):
        """ Main method to use to request a download

        This method includes middleware mangling. Middleware can returns a
        Response object, then request never reach downloader queue, and it will
        not be downloaded from site.
        """
        site = self.sites[spider.domain_name]
        if site.closed:
            raise IgnoreRequest('Can\'t fetch on a closed domain')

        site.active.add(request)
        def _deactivate(_):
            site.active.remove(request)
            return _

        return self.middleware.download(self.enqueue, request, spider).addBoth(_deactivate)

    def enqueue(self, request, spider):
        """Enqueue a Request for a effective download from site"""
        deferred = defer.Deferred()
        site = self.sites[spider.domain_name]
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

        # Delay queue processing if a download_delay is configured
        now = datetime.datetime.now()
        if site.download_delay and site.lastseen:
            delta = now - site.lastseen
            penalty = site.download_delay - delta.seconds
            if penalty > 0:
                reactor.callLater(penalty, self.process_queue, spider=spider)
                return
        site.lastseen = now

        # Process requests in queue if there are free slots to transfer for this site
        while site.queue and site.capacity() > 0:
            request, deferred = site.queue.pop(0)
            self._download(site, request, spider).chainDeferred(deferred)

        # Free site resources if domain was asked to be closed and it is idle.
        if site.closed and site.is_idle():
            del self.sites[domain]
            self.engine.closed_domain(domain) # notify engine.

    def _download(self, site, request, spider):
        site.transferring.add(request)
        def _transferred(_):
            site.transferring.remove(request)
            self.process_queue(spider)
            return _
        return mustbe_deferred(download_any, request, spider).addBoth(_transferred)

    def open_domain(self, domain):
        """Allocate resources to begin processing a domain"""
        if domain in self.sites:
            raise RuntimeError('Downloader domain already opened: %s' % domain)

        spider = spiders.fromdomain(domain)
        self.sites[domain] = SiteInfo(
            download_delay=getattr(spider, 'download_delay', None),
            max_concurrent_requests=getattr(spider, 'max_concurrent_requests', None)
        )

    def close_domain(self, domain):
        """Free any resources associated with the given domain"""
        site = self.sites.get(domain)
        if not site or site.closed:
            raise RuntimeError('Downloader domain already closed: %s' % domain)

        site.closed = True
        spider = spiders.fromdomain(domain)
        self.process_queue(spider)

    def needs_backout(self, domain):
        site = self.sites.get(domain)
        return (site.needs_backout() if site else True)

    # Most of the following functions must be reviewed to decide if are really needed
    def domain_is_open(self, domain):
        return domain in self.sites

    def outstanding(self, domain):
        """The number of outstanding requests for a domain
        This includes both active requests and pending requests.
        """
        site = self.sites.get(domain)
        if site:
            return site.outstanding()

    def has_capacity(self):
        """Does the downloader have capacity to handle more domains"""
        return len(self.sites) < self.concurrent_domains

    def is_idle(self):
        return not self.sites

