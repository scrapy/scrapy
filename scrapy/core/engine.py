"""
This is the Scrapy engine which controls the Scheduler, Downloader and Spiders.

For more information see docs/topics/architecture.rst

"""
from datetime import datetime

from twisted.internet import reactor, task
from twisted.internet.error import CannotListenError
from twisted.python.failure import Failure
from scrapy.xlib.pydispatch import dispatcher

from scrapy import log
from scrapy.stats import stats
from scrapy.conf import settings
from scrapy.core import signals
from scrapy.core.downloader import Downloader
from scrapy.core.scraper import Scraper
from scrapy.core.exceptions import IgnoreRequest, DontCloseDomain
from scrapy.http import Response, Request
from scrapy.spider import spiders
from scrapy.utils.misc import load_object
from scrapy.utils.signal import send_catch_log
from scrapy.utils.defer import mustbe_deferred

class ExecutionEngine(object):

    def __init__(self):
        self.configured = False
        self.keep_alive = False
        self.closing = {} # dict (domain -> reason) of spiders being closed
        self.tasks = []
        self.ports = []
        self.running = False
        self.paused = False
        self.control_reactor = True
        self._next_request_pending = set()

    def configure(self):
        """
        Configure execution engine with the given scheduling policy and downloader.
        """
        self.scheduler = load_object(settings['SCHEDULER'])()
        self.domain_scheduler = load_object(settings['DOMAIN_SCHEDULER'])()
        self.downloader = Downloader()
        self.scraper = Scraper(self)
        self.configured = True

    def addtask(self, function, interval, args=None, kwargs=None, now=False):
        """
        Adds a looping task. Use this instead of twisted task.LooopingCall to
        make sure the reactor is left in a clean state after the engine is
        stopped.
        """
        if not args:
            args = []
        if not kwargs:
            kwargs = {}
        tsk = task.LoopingCall(function, *args, **kwargs)
        self.tasks.append((tsk, interval, now))
        if self.running:
            tsk.start(interval, now)
        return tsk

    def removetask(self, tsk):
        """Remove a looping task previously added with addtask() method"""
        self.tasks = [(t, i, n) for (t, i, n) in self.tasks if t is not tsk]
        if tsk.running:
            tsk.stop()

    def listenTCP(self, *args, **kwargs):
        if self.running:
            self.ports.append(reactor.listenTCP(*args, **kwargs))
        else:
            self.ports.append((args, kwargs))

    def clean_reactor(self):
        """Leaves the reactor in a clean state by removing all pending tasks
        and listening ports. It can only be called when the engine is not
        running.
        """
        if not self.running:
            for tsk, _, _ in self.tasks:
                if tsk.running:
                    tsk.stop()
            self.tasks = []
            for p in [p for p in self.ports if not isinstance(p, tuple)]:
                p.stopListening()
            self.ports = []

    def start(self, control_reactor=True):
        """Start the execution engine"""
        if not self.running:
            self.control_reactor = control_reactor
            reactor.callLater(0, self._mainloop)
            self.start_time = datetime.utcnow()
            send_catch_log(signal=signals.engine_started, sender=self.__class__)
            self.addtask(self._mainloop, 5.0)
            for tsk, interval, now in self.tasks:
                tsk.start(interval, now)
            for args, kwargs in [t for t in self.ports if isinstance(t, tuple)]:
                try:
                    reactor.listenTCP(*args, **kwargs)
                except CannotListenError:
                    log.msg("Cannot listen on TCP port %d" % args[0], level=log.ERROR)
            self.running = True
            if control_reactor:
                reactor.run() # blocking call

    def stop(self):
        """Stop the execution engine"""
        if self.running:
            self.running = False
            for domain in self.open_domains:
                spider = spiders.fromdomain(domain)
                send_catch_log(signal=signals.domain_closed, sender=self.__class__, \
                    domain=domain, spider=spider, reason='shutdown')
                stats.close_domain(domain, reason='shutdown')
            for tsk, _, _ in self.tasks: # stop looping calls
                if tsk.running:
                    tsk.stop()
            self.tasks = []
            for p in [p for p in self.ports if not isinstance(p, tuple)]:
                p.stopListening()
            if self.control_reactor and reactor.running:
                reactor.stop()
            send_catch_log(signal=signals.engine_stopped, sender=self.__class__)

    def pause(self):
        """Pause the execution engine"""
        self.paused = True

    def unpause(self):
        """Resume the execution engine"""
        self.paused = False

    def is_idle(self):
        return self.scheduler.is_idle() and self.downloader.is_idle() and self.scraper.is_idle()

    def next_domain(self):
        domain = self.domain_scheduler.next_domain()
        if domain:
            self.open_domain(domain)
        return domain

    def next_request(self, domain, now=False):
        """Scrape the next request for the domain passed.

        The next request to be scraped is retrieved from the scheduler and
        requested from the downloader.

        The domain is closed if there are no more pages to scrape.
        """
        if now:
            self._next_request_pending.discard(domain)
        elif domain not in self._next_request_pending:
            self._next_request_pending.add(domain)
            return reactor.callLater(0, self.next_request, domain, now=True)
        else:
            return

        if self.paused:
            return reactor.callLater(5, self.next_request, domain)

        while not self._needs_backout(domain):
            if not self._next_request(domain):
                break

        if self.domain_is_idle(domain):
            self._domain_idle(domain)

    def _needs_backout(self, domain):
        return not self.running \
            or self.domain_is_closed(domain) \
            or self.downloader.sites[domain].needs_backout() \
            or self.scraper.sites[domain].needs_backout()

    def _next_request(self, domain):
        # Next pending request from scheduler
        request, deferred = self.scheduler.next_request(domain)
        if request:
            spider = spiders.fromdomain(domain)
            dwld = mustbe_deferred(self.download, request, spider)
            dwld.chainDeferred(deferred).addBoth(lambda _: deferred)
            return dwld.addErrback(log.err)

    def domain_is_idle(self, domain):
        scraper_idle = domain in self.scraper.sites and self.scraper.sites[domain].is_idle()
        pending = self.scheduler.domain_has_pending_requests(domain)
        downloading = domain in self.downloader.sites and self.downloader.sites[domain].active
        return scraper_idle and not (pending or downloading)

    def domain_is_closed(self, domain):
        """Return True if the domain is fully closed (ie. not even in the
        closing stage)"""
        return domain not in self.downloader.sites

    def domain_is_open(self, domain):
        """Return True if the domain is fully opened (ie. not in closing
        stage)"""
        return domain in self.downloader.sites and domain not in self.closing

    @property
    def open_domains(self):
        return self.downloader.sites.keys()

    def crawl(self, request, spider):
        schd = mustbe_deferred(self.schedule, request, spider)
        schd.addBoth(self.scraper.enqueue_scrape, request, spider)
        schd.addErrback(log.err)
        schd.addBoth(lambda _: self.next_request(spider.domain_name))

    def schedule(self, request, spider):
        domain = spider.domain_name
        if domain in self.closing:
            raise IgnoreRequest()
        if not self.scheduler.domain_is_open(domain):
            self.scheduler.open_domain(domain)
            if self.domain_is_closed(domain): # scheduler auto-open
                self.domain_scheduler.add_domain(domain)
        self.next_request(domain)
        return self.scheduler.enqueue_request(domain, request)

    def _mainloop(self):
        """Add more domains to be scraped if the downloader has the capacity.

        If there is nothing else scheduled then stop the execution engine.
        """
        if not self.running or self.paused:
            return

        while self.running and self.downloader.has_capacity():
            if not self.next_domain():
                return self._stop_if_idle()

    def download(self, request, spider):
        domain = spider.domain_name
        referer = request.headers.get('Referer')

        def _on_success(response):
            """handle the result of a page download"""
            assert isinstance(response, (Response, Request))
            if isinstance(response, Response):
                response.request = request # tie request to response received
                log.msg("Crawled %s (referer: <%s>)" % (response, referer), level=log.DEBUG, \
                    domain=domain)
                return response
            elif isinstance(response, Request):
                newrequest = response
                schd = mustbe_deferred(self.schedule, newrequest, spider)
                schd.chainDeferred(newrequest.deferred)
                return newrequest.deferred

        def _on_error(_failure):
            """handle an error processing a page"""
            ex = _failure.value
            errmsg = str(_failure) if not isinstance(ex, IgnoreRequest) \
                else _failure.getErrorMessage()
            log.msg("Downloading <%s> (referer: <%s>): %s" % (request.url, referer, errmsg), \
                log.ERROR, domain=domain)
            return Failure(IgnoreRequest(str(ex)))

        def _on_complete(_):
            self.next_request(domain)
            return _

        dwld = mustbe_deferred(self.downloader.fetch, request, spider)
        dwld.addCallbacks(_on_success, _on_error)
        dwld.addBoth(_on_complete)
        return dwld

    def open_domain(self, domain):
        log.msg("Domain opened", domain=domain)
        spider = spiders.fromdomain(domain)
        self.next_request(domain)

        self.downloader.open_domain(domain)
        self.scraper.open_domain(domain)
        stats.open_domain(domain)

        # XXX: sent for backwards compatibility (will be removed in Scrapy 0.8)
        send_catch_log(signals.domain_open, sender=self.__class__, \
            domain=domain, spider=spider)

        send_catch_log(signals.domain_opened, sender=self.__class__, \
            domain=domain, spider=spider)

    def _domain_idle(self, domain):
        """Called when a domain gets idle. This function is called when there
        are no remaining pages to download or schedule. It can be called
        multiple times. If some extension raises a DontCloseDomain exception
        (in the domain_idle signal handler) the domain is not closed until the
        next loop and this function is guaranteed to be called (at least) once
        again for this domain.
        """
        spider = spiders.fromdomain(domain)
        try:
            dispatcher.send(signal=signals.domain_idle, sender=self.__class__, \
                domain=domain, spider=spider)
        except DontCloseDomain:
            self.next_request(domain)
            return
        except:
            log.err(_why="Exception catched on domain_idle signal dispatch")
        if self.domain_is_idle(domain):
            self.close_domain(domain, reason='finished')

    def _stop_if_idle(self):
        """Call the stop method if the system has no outstanding tasks. """
        if self.is_idle() and not self.keep_alive:
            self.stop()

    def close_domain(self, domain, reason='cancelled'):
        """Close (cancel) domain and clear all its outstanding requests"""
        if domain not in self.closing:
            log.msg("Closing domain (%s)" % reason, domain=domain)
            self.closing[domain] = reason
            self.downloader.close_domain(domain)
            self.scheduler.clear_pending_requests(domain)
            self._finish_closing_domain_if_idle(domain)

    def _finish_closing_domain_if_idle(self, domain):
        """Call _finish_closing_domain if domain is idle"""
        if self.domain_is_idle(domain):
            self._finish_closing_domain(domain)
        else:
            reactor.callLater(5, self._finish_closing_domain_if_idle, domain)

    def _finish_closing_domain(self, domain):
        """This function is called after the domain has been closed"""
        spider = spiders.fromdomain(domain) 
        self.scheduler.close_domain(domain)
        self.scraper.close_domain(domain)
        reason = self.closing.pop(domain, 'finished')
        send_catch_log(signal=signals.domain_closed, sender=self.__class__, \
            domain=domain, spider=spider, reason=reason)
        stats.close_domain(domain, reason=reason)
        log.msg("Domain closed (%s)" % reason, domain=domain) 
        self._mainloop()

    def getstatus(self):
        """
        Return a report of the current engine status
        """
        s = "Execution engine status\n\n"

        global_tests = [
            "datetime.utcnow()-self.start_time", 
            "self.is_idle()", 
            "self.scheduler.is_idle()",
            "len(self.scheduler.pending_requests)",
            "self.downloader.is_idle()",
            "len(self.downloader.sites)",
            "self.downloader.has_capacity()",
            "self.scraper.is_idle()",
            "len(self.scraper.sites)",
            ]
        domain_tests = [
            "self.domain_is_idle(domain)",
            "self.closing.get(domain)",
            "self.scheduler.domain_has_pending_requests(domain)",
            "len(self.scheduler.pending_requests[domain])",
            "len(self.downloader.sites[domain].queue)",
            "len(self.downloader.sites[domain].active)",
            "len(self.downloader.sites[domain].transferring)",
            "self.downloader.sites[domain].closing",
            "self.downloader.sites[domain].lastseen",
            "len(self.scraper.sites[domain].queue)",
            "len(self.scraper.sites[domain].active)",
            "self.scraper.sites[domain].active_size",
            "self.scraper.sites[domain].itemproc_size",
            "self.scraper.sites[domain].needs_backout()",
            ]

        for test in global_tests:
            try:
                s += "%-47s : %s\n" % (test, eval(test))
            except Exception, e:
                s += "%-47s : %s (exception)\n" % (test, type(e).__name__)
        s += "\n"
        for domain in self.downloader.sites:
            s += "%s\n" % domain
            for test in domain_tests:
                try:
                    s += "  %-50s : %s\n" % (test, eval(test))
                except Exception, e:
                    s += "  %-50s : %s (exception)\n" % (test, type(e).__name__)
        return s

    def st(self): # shortcut for printing engine status (useful in telnet console)
        print self.getstatus()

scrapyengine = ExecutionEngine()
