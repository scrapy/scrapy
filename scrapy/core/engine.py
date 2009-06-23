"""
This is the Scrapy engine which controls the Scheduler, Downloader and Spiders.

For more information see docs/topics/architecture.rst

"""
from datetime import datetime

from twisted.internet import defer, reactor, task
from twisted.internet.error import CannotListenError
from twisted.python.failure import Failure
from pydispatch import dispatcher

from scrapy import log
from scrapy.stats import stats
from scrapy.conf import settings
from scrapy.core import signals
from scrapy.core.scheduler import Scheduler
from scrapy.core.downloader import Downloader
from scrapy.core.exceptions import IgnoreRequest, DontCloseDomain
from scrapy.http import Response, Request
from scrapy.item import ScrapedItem
from scrapy.item.pipeline import ItemPipelineManager
from scrapy.spider import spiders
from scrapy.spider.middleware import SpiderMiddlewareManager
from scrapy.utils.defer import chain_deferred, deferred_imap
from scrapy.utils.request import request_info
from scrapy.utils.misc import load_object
from scrapy.utils.defer import mustbe_deferred

class ExecutionEngine(object):
    """
    The Execution Engine controls execution of the scraping process.

    The process begins with the _mainloop() method, which is called
    periodically to add more domains to scrape. It adds the first page for a
    domain to the scheduler by calling _schedule_page and calls
    process_scheduled_requests, which starts the scraping process for a domain.

    The process_scheduled_requests method asks the scheduler for the next
    available page for a given domain and requests it from the downloader. The
    downloader will execute a callback function that was added in the
    _schedule_page method. This callback with process the output from the
    spider and then call process_scheduled_requests to continue the scraping
    process for that domain.
    """

    def __init__(self):
        self.configured = False
        self.keep_alive = False
        self.closing = {} # domains being closed
        self.debug_mode = settings.getbool('ENGINE_DEBUG')
        self.tasks = []
        self.ports = []
        self.running = False
        self.paused = False
        self.control_reactor = True

    def configure(self, scheduler=None, downloader=None):
        """
        Configure execution engine with the given scheduling policy and downloader.
        """
        self.scheduler = scheduler or Scheduler()
        self.domain_scheduler = load_object(settings['DOMAIN_SCHEDULER'])()
        self.downloader = downloader or Downloader()
        self.spidermiddleware = SpiderMiddlewareManager()
        self._scraping = {}
        self.pipeline = ItemPipelineManager()

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
            self.start_time = datetime.now()
            signals.send_catch_log(signal=signals.engine_started, sender=self.__class__)
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
                signals.send_catch_log(signal=signals.domain_closed, sender=self.__class__, domain=domain, spider=spider, reason='shutdown')
            for tsk, _, _ in self.tasks: # stop looping calls
                if tsk.running:
                    tsk.stop()
            self.tasks = []
            for p in [p for p in self.ports if not isinstance(p, tuple)]:
                p.stopListening()
            if self.control_reactor and reactor.running:
                reactor.stop()
            signals.send_catch_log(signal=signals.engine_stopped, sender=self.__class__)

    def pause(self):
        """Pause the execution engine"""
        self.paused = True

    def unpause(self):
        """Resume the execution engine"""
        self.paused = False

    def is_idle(self):
        return self.scheduler.is_idle() and self.pipeline.is_idle() and self.downloader.is_idle() and not self._scraping

    def next_domain(self):
        domain = self.domain_scheduler.next_domain()
        if domain:
            spider = spiders.fromdomain(domain)
            self.open_domain(domain, spider)
        return domain

    def next_request(self, spider, now=False):
        """Scrape the next request for the domain passed.

        The next request to be scraped is retrieved from the scheduler and
        requested from the downloader.

        The domain is closed if there are no more pages to scrape.
        """
        if self.paused:
            return reactor.callLater(5, self.next_request, spider)

        # call next_request in next reactor loop by default
        if not now:
            return reactor.callLater(0, self.next_request, spider, now=True)

        domain = spider.domain_name

        if not self.running or \
                self.domain_is_closed(domain) or \
                self.downloader.sites[domain].needs_backout():
            return

        # Next pending request from scheduler
        request, deferred = self.scheduler.next_request(domain)
        if request:
            mustbe_deferred(self.download, request, spider).chainDeferred(deferred)
        elif self.domain_is_idle(domain):
            self._domain_idle(domain)

    def domain_is_idle(self, domain):
        scraping = self._scraping.get(domain)
        pending = self.scheduler.domain_has_pending_requests(domain)
        downloading = domain in self.downloader.sites and self.downloader.sites[domain].active
        haspipe = not self.pipeline.domain_is_idle(domain)
        return not (pending or downloading or haspipe or scraping)

    def domain_is_closed(self, domain):
        return domain not in self.downloader.sites

    @property
    def open_domains(self):
        return self.downloader.sites.keys()

    def crawl(self, request, spider):
        domain = spider.domain_name

        def _process_response(response):
            assert isinstance(response, (Response, Exception)), "Expecting Response or Exception, got %s" % type(response).__name__

            def cb_spidermiddleware_output(spmw_result):
                def cb_spider_output(output):
                    def cb_pipeline_output(pipe_result, item):
                        if isinstance(pipe_result, Failure):
                            # can only be a DropItem exception, since other exceptions are caught in the Item Pipeline (item/pipeline.py)
                            signals.send_catch_log(signal=signals.item_dropped, sender=self.__class__, item=item, spider=spider, response=response, exception=pipe_result.value)
                        else:
                            signals.send_catch_log(signal=signals.item_passed, sender=self.__class__, item=item, spider=spider, response=response, pipe_output=pipe_result)
                        self.next_request(spider)

                    if domain in self.closing:
                        return
                    elif isinstance(output, ScrapedItem):
                        log.msg("Scraped %s in <%s>" % (output, request.url), log.INFO, domain=domain)
                        signals.send_catch_log(signal=signals.item_scraped, sender=self.__class__, item=output, spider=spider, response=response)
                        piped = self.pipeline.pipe(output, spider)
                        piped.addBoth(cb_pipeline_output, output)
                    elif isinstance(output, Request):
                        signals.send_catch_log(signal=signals.request_received, sender=self.__class__, request=output, spider=spider, response=response)
                        self.crawl(request=output, spider=spider)
                    elif output is None:
                        pass # may be next time.
                    else:
                        log.msg("Spider must return Request, ScrapedItem or None, got '%s' while processing %s" % (type(output).__name__, request), log.WARNING, domain=domain)

                return deferred_imap(cb_spider_output, spmw_result)

            def eb_user(_failure):
                if not isinstance(_failure.value, IgnoreRequest):
                    referer = None if not isinstance(response, Response) else response.request.headers.get('Referer', None)
                    log.msg("Error while spider was processing <%s> from <%s>: %s" % (request.url, referer, _failure), log.ERROR, domain=domain)
                    stats.incpath("%s/spider_exceptions/%s" % (domain, _failure.value.__class__.__name__))

            def eb_framework(_failure):
                log.msg('FRAMEWORK BUG processing %s: %s' % (request, _failure), log.ERROR, domain=domain)


            scd = self.spidermiddleware.scrape(request, response, spider)
            scd.addCallbacks(cb_spidermiddleware_output, eb_user)
            scd.addErrback(eb_framework)

            self._scraping[domain].add(response)
            scd.addBoth(lambda _: self._scraping[domain].remove(response))
            return scd

        def _cleanfailure(_failure):
            ex = _failure.value
            if not isinstance(ex, IgnoreRequest):
                log.msg("Unknown error propagated in %s: %s" % (request, _failure), log.ERROR, domain=domain)
            request.deferred.addErrback(lambda _:None)
            request.deferred.errback(_failure) # TODO: merge into spider middleware.

        schd = self.schedule(request, spider)
        schd.addCallbacks(_process_response, _cleanfailure)
        return schd

    def schedule(self, request, spider):
        domain = spider.domain_name
        if domain in self.closing:
            raise IgnoreRequest()
        if not self.scheduler.domain_is_open(domain):
            self.scheduler.open_domain(domain)
            if self.domain_is_closed(domain): # scheduler auto-open
                self.domain_scheduler.add_domain(domain)
        self.next_request(spider)
        return self.scheduler.enqueue_request(domain, request)

    def _mainloop(self):
        """Add more domains to be scraped if the downloader has the capacity.

        If there is nothing else scheduled then stop the execution engine.
        """
        if not self.running or self.paused:
            return

        # main domain starter loop
        while self.running and self.downloader.has_capacity():
            if not self.next_domain():
                return self._stop_if_idle()

    def download(self, request, spider):
        if self.debug_mode:
            log.msg('Downloading %s' % request_info(request), log.DEBUG)
        domain = spider.domain_name
        referer = request.headers.get('Referer', None)

        def _on_success(response):
            """handle the result of a page download"""
            assert isinstance(response, (Response, Request))
            if self.debug_mode:
                log.msg("Requested %s" % request_info(request), level=log.DEBUG, domain=domain)
            if isinstance(response, Response):
                response.request = request # tie request to obtained response
                log.msg("Crawled %s from <%s>" % (response, referer), level=log.DEBUG, domain=domain)
                return response
            elif isinstance(response, Request):
                newrequest = response # proper alias
                schd = self.schedule(newrequest, spider)
                chain_deferred(schd, newrequest.deferred)
                return schd

        def _on_error(_failure):
            """handle an error processing a page"""
            ex = _failure.value
            errmsg = str(_failure) if not isinstance(ex, IgnoreRequest) else _failure.getErrorMessage()
            log.msg("Downloading <%s> from <%s>: %s" % (request.url, referer, errmsg), log.ERROR, domain=domain)
            return Failure(IgnoreRequest(str(ex)))

        def _on_complete(_):
            self.next_request(spider)

        dwld = self.downloader.fetch(request, spider)
        dwld.addCallbacks(_on_success, _on_error)
        deferred = defer.Deferred()
        chain_deferred(dwld, deferred)
        dwld.addBoth(_on_complete)
        return deferred

    def open_domain(self, domain, spider=None):
        log.msg("Domain opened", domain=domain)
        spider = spider or spiders.fromdomain(domain)
        self.next_request(spider)

        self.closing.pop(domain, None)
        self.downloader.open_domain(domain)
        self.pipeline.open_domain(domain)
        self._scraping[domain] = set()

        signals.send_catch_log(signals.domain_open, sender=self.__class__, domain=domain, spider=spider)
        signals.send_catch_log(signals.domain_opened, sender=self.__class__, domain=domain, spider=spider)

    def _domain_idle(self, domain):
        """Called when a domain gets idle. This function is called when there are no
        remaining pages to download or schedule. It can be called multiple
        times. If some extension raises a DontCloseDomain exception (in the
        domain_idle signal handler) the domain is not closed until the next
        loop and this function is guaranteed to be called (at least) once again
        for this domain.
        """
        spider = spiders.fromdomain(domain)
        try:
            dispatcher.send(signal=signals.domain_idle, sender=self.__class__, domain=domain, spider=spider)
        except DontCloseDomain:
            self.next_request(spider)
            return
        except:
            log.exc("Exception catched on domain_idle signal dispatch")
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
        self.pipeline.close_domain(domain)
        del self._scraping[domain]
        reason = self.closing.get(domain, 'finished')
        signals.send_catch_log(signal=signals.domain_closed, sender=self.__class__, domain=domain, spider=spider, reason=reason)
        log.msg("Domain closed (%s)" % reason, domain=domain) 
        self.closing.pop(domain, None)
        self._mainloop()

    def getstatus(self):
        """
        Return a report of the current engine status
        """
        s = "Execution engine status\n\n"

        global_tests = [
            "datetime.now()-self.start_time", 
            "self.is_idle()", 
            "self.scheduler.is_idle()",
            "len(self.scheduler.pending_requests)",
            "self.downloader.is_idle()",
            "len(self.downloader.sites)",
            "self.downloader.has_capacity()",
            "self.pipeline.is_idle()",
            "len(self.pipeline.domaininfo)",
            "len(self._scraping)",
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
            "self.pipeline.domain_is_idle(domain)",
            "len(self.pipeline.domaininfo[domain])",
            "len(self._scraping[domain])",
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
