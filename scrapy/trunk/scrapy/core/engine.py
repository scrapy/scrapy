"""
Core execution engine for the web crawling framework. This controls the 
scheduler, downloader and spiders.
"""
from datetime import datetime

from twisted.internet import defer, reactor, task
from twisted.python.failure import Failure
from pydispatch import dispatcher

from scrapy import log
from scrapy.conf import settings
from scrapy.core import signals
from scrapy.core.scheduler import Scheduler
from scrapy.core.downloader import Downloader
from scrapy.core.exceptions import IgnoreRequest, HttpException, DontCloseDomain
from scrapy.http import Response, Request
from scrapy.item import ScrapedItem
from scrapy.item.pipeline import ItemPipeline
from scrapy.spider import spiders
from scrapy.spider.middleware import SpiderMiddlewareManager
from scrapy.utils.defer import chain_deferred, defer_succeed, mustbe_deferred, deferred_degenerate

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
        self.domain_close_delay = settings.getint('DOMAIN_CLOSE_DELAY') # seconds after an idle domain will be closed
        self.initializing = set() # domais in intialization state
        self.cancelled = set() # domains in cancelation state
        self.debug_mode = settings.getbool('ENGINE_DEBUG')
        self.tasks = []
        self.ports = []
        self.running = False
        self.paused = False

    def configure(self, scheduler=None, downloader=None):
        """
        Configure execution engine with the given scheduling policy and downloader.
        """
        self.scheduler = scheduler or Scheduler()
        self.downloader = downloader or Downloader()
        self.spidermiddleware = SpiderMiddlewareManager()
        self._scraping = {}
        self.pipeline = ItemPipeline()
        # key dictionary of per domain lists of initial requests to scrape
        self.starters = {}

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

    def start(self):
        """Start the execution engine"""
        if not self.running:
            reactor.callWhenRunning(self._mainloop)
            self.start_time = datetime.now()
            signals.send_catch_log(signal=signals.engine_started, sender=self.__class__)
            self.addtask(self._mainloop, 5.0)
            for tsk, interval, now in self.tasks:
                tsk.start(interval, now)
            for args, kwargs in [t for t in self.ports if isinstance(t, tuple)]:
                reactor.listenTCP(*args, **kwargs)
            self.running = True
            reactor.run() # blocking call

    def stop(self):
        """Stop the execution engine"""
        if self.running:
            self.running = False
            for domain in self.open_domains:
                spider = spiders.fromdomain(domain)
                signals.send_catch_log(signal=signals.domain_closed, sender=self.__class__, domain=domain, spider=spider, status='cancelled')
            for tsk, _, _ in self.tasks: # stop looping calls
                if tsk.running:
                    tsk.stop()
            self.tasks = []
            for p in [p for p in self.ports if not isinstance(p, tuple)]:
                p.stopListening()
            if reactor.running:
                reactor.stop()
            signals.send_catch_log(signal=signals.engine_stopped, sender=self.__class__)

    def pause(self):
        """Pause the execution engine"""
        self.paused = True

    def resume(self):
        """Resume the execution engine"""
        self.paused = False

    def is_idle(self):
        return self.scheduler.is_idle() and self.pipeline.is_idle() and self.downloader.is_idle() and not self._scraping

    def next_domain(self):
        domain = self.scheduler.next_domain()
        if domain:
            spider = spiders.fromdomain(domain)
            self.open_domain(domain, spider)
        return domain

    def next_request(self, spider, breakloop=True):
        """Scrape the next request for the domain passed.

        The next request to be scraped is retrieved from the scheduler and
        requested from the downloader.

        The domain is closed if there are no more pages to scrape.
        """
        if self.paused:
            return reactor.callLater(5, self.next_request, spider)

        if breakloop:
            # delaying make reentrant call to next_request safe
            return reactor.callLater(0, self.next_request, spider, breakloop=False)

        domain = spider.domain_name

        # check that the engine is still running and domain is open
        if not self.running:
            return

        # backout enqueing downloads if domain needs it
        if self.downloader.needs_backout(domain):
            return

        # Next pending request from scheduler
        request, deferred = self.scheduler.next_request(domain)
        if request:
            try:
                dwld = self.download(request, spider)
            except IgnoreRequest, ex:
                log.msg(ex.message, log.WARNING, domain=domain)
            except Exception, ex:
                log.exc("Bug in download code: %s" % request, domain=domain)
                self._domain_idle(domain)
            else:
                chain_deferred(dwld, deferred)
        else:
            if self.domain_is_idle(domain):
                self._domain_idle(domain)

    def domain_is_idle(self, domain):
        scraping = self._scraping.get(domain)
        pending = self.scheduler.domain_has_pending(domain)
        downloading = not self.downloader.domain_is_idle(domain)
        haspipe = not self.pipeline.domain_is_idle(domain)
        oninit = domain in self.initializing
        if pending or downloading or haspipe or oninit or scraping:
            return False
        elif self.domain_close_delay:
            lastseen = self.downloader.lastseen(domain)
            if not lastseen: # domain not yet started
                return False
            now = datetime.now()
            delta = now - lastseen
            return (delta.seconds >= self.domain_close_delay)
        else:
            return True

    def domain_is_open(self, domain):
        return domain in self.downloader.sites

    @property
    def open_domains(self):
        return self.downloader.sites.keys()

    def crawl(self, request, spider, priority=1, domain_priority=1):
        domain = spider.domain_name

        def _process(response):
            assert isinstance(response, (Response, Exception))

            def _onpipelinefinish(pipe_result, item):
                # _ can only be an item or a DropItem failure, since other
                # failures are caught in ItemPipeine (item/pipeline.py)
                if isinstance(pipe_result, Failure):
                    signals.send_catch_log(signal=signals.item_dropped, sender=self.__class__, item=item, spider=spider, response=response, exception=pipe_result.value)
                else:
                    signals.send_catch_log(signal=signals.item_passed, sender=self.__class__, item=item, spider=spider, response=response, pipe_output=pipe_result)
                self.next_request(spider)

            def _onsuccess_per_item(item):
                if isinstance(item, ScrapedItem):
                    log.msg("Scraped %s in <%s>" % (item, request.url), log.DEBUG, domain=domain)
                    signals.send_catch_log(signal=signals.item_scraped, sender=self.__class__, item=item, spider=spider, response=response)
                    piped = self.pipeline.pipe(item, spider, response) # TODO: remove response
                    piped.addBoth(_onpipelinefinish, item)
                elif isinstance(item, Request):
                    signals.send_catch_log(signal=signals.request_received, sender=self.__class__, request=item, spider=spider, response=response)
                    self.crawl(request=item, spider=spider, priority=priority)
                else:
                    log.msg('Garbage found in spider output while processing %s, got type %s' % (request, type(item)), log.TRACE, domain=domain)

            class _ResultContainer(object):
                def append(self, item):
                    _onsuccess_per_item(item)

            def _onsuccess(result):
                return deferred_degenerate(result, _ResultContainer())

            def _onerror(_failure):
                if not isinstance(_failure.value, IgnoreRequest):
                    referer = None if not isinstance(response, Response) else response.request.headers.get('Referer', None)
                    log.msg("Error while spider was processing <%s> from <%s>: %s" % (request.url, referer, _failure), log.ERROR, domain=domain)

            def _bugtrap(_failure):
                log.msg('FRAMEWORK BUG processing %s: %s' % (request, _failure), log.ERROR, domain=domain)


            scd = self.scrape(request, response, spider)
            scd.addCallbacks(_onsuccess, _onerror)
            scd.addErrback(_bugtrap)

            self._scraping[domain].add(response)
            scd.addBoth(lambda _: self._scraping[domain].remove(response))
            return scd

        def _cleanfailure(_failure):
            ex = _failure.value
            if not isinstance(ex, IgnoreRequest):
                log.msg("Unknown error propagated in %s: %s" % (request, _failure), log.ERROR, domain=domain)
            request.deferred.addErrback(lambda _:None)
            request.deferred.errback(_failure) #TODO: merge into spider middleware.

        schd = self.schedule(request, spider, priority, domain_priority)
        schd.addCallbacks(_process, _cleanfailure)
        return schd

    def scrape(self, request, response, spider):
        return self.spidermiddleware.scrape(request, response, spider)

    def schedule(self, request, spider, priority=1, domain_priority=1):
        domain = spider.domain_name
        if not self.scheduler.domain_is_open(domain):
            if self.debug_mode: 
                log.msg('Scheduling %s (delayed)' % request.traceinfo(), log.TRACE)
            return self._add_starter(request, spider, domain_priority)
        if self.debug_mode: 
            log.msg('Scheduling %s (now)' % request.traceinfo(), log.TRACE)
        schd = self.scheduler.enqueue_request(domain, request, priority)
        self.next_request(spider)
        return schd

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

        # purge idle domains - (domain_close_delay support)
        if self.domain_close_delay:
            for domain in self.downloader.sites:
                if self.domain_is_idle(domain):
                    self._domain_idle(domain)

    def _add_starter(self, request, spider, domain_priority):
        domain = spider.domain_name
        if not self.scheduler.is_pending(domain):
            self.scheduler.add_domain(domain, priority=domain_priority)
            self.starters[domain] = []
        deferred = defer.Deferred()
        self.starters[domain] += [(request, deferred)]
        return deferred

    def _run_starters(self, spider):
        domain = spider.domain_name
        starters = self.starters.get(domain, [])
        while starters:
            request, deferred = starters.pop(0)
            schd = self.schedule(request, spider)
            chain_deferred(schd, deferred)
        del self.starters[domain]

    def download(self, request, spider):
        log.msg('Downloading %s' % request.traceinfo(), log.TRACE)
        domain = spider.domain_name

        def _on_success(response):
            """handle the result of a page download"""
            assert isinstance(response, (Response, Request))
            log.msg("Requested %s" % request.traceinfo(), level=log.TRACE, domain=domain)
            if isinstance(response, Response):
                response.request = request # tie request to obtained response
                cached = 'cached' if response.cached else 'live'
                log.msg("Crawled %s <%s> from <%s>" % (cached, response.url, request.headers.get('referer')), level=log.DEBUG, domain=domain)
                return response
            elif isinstance(response, Request):
                redirected = response # proper alias
                schd = self.schedule(redirected, spider, priority=4)
                chain_deferred(schd, redirected.deferred)
                return schd

        def _on_error(_failure):
            """handle an error processing a page"""
            ex = _failure.value
            if isinstance(ex, IgnoreRequest):
                log.msg(_failure.getErrorMessage(), level=log.DEBUG, domain=domain)
                return _failure
            referer = request.headers.get('Referer', None)
            errmsg = str(ex) if isinstance(ex, HttpException) else str(_failure)
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

    def initialize(self, spider):
        domain = spider.domain_name
        if not hasattr(spider, 'init_domain'):
            return defer_succeed(True)

        def _initialize(req):
            if isinstance(req, Request):
                _response = None
                def _referer(response):
                    req.deferred.addCallback(_setreferer, response)
                    return response

                def _setreferer(result, response):
                    if isinstance(result, Request):
                        result.headers.setdefault('Referer', response.url)
                    return result

                def _onerror(_failure):
                    ex = _failure.value
                    if isinstance(ex, IgnoreRequest):
                        log.msg(ex.message, log.DEBUG, domain=domain)
                    else:
                        return _failure

                schd = self.schedule(req, spider)
                schd.addCallback(_referer)
                chain_deferred(schd, req.deferred)
                schd.addErrback(_onerror)
                schd.addBoth(_initialize)
                return schd
            return req

        def _bugtrap(_failure):
            log.msg("Bug in %s init_domain code: %s" % (domain, _failure), log.ERROR, domain=domain)

        def _state(state):
            self.initializing.remove(domain)
            if state is True:
                log.msg('Succeded initialization for %s' % domain, log.INFO, domain=domain)
            else:
                log.msg('Failed initialization for %s' % domain, log.INFO, domain=domain)
            return state

        log.msg('Started initialization for %s' % domain, log.INFO, domain=domain)
        self.initializing.add(domain)
        req = spider.init_domain()
        deferred = mustbe_deferred(_initialize, req)
        deferred.addErrback(_bugtrap)
        deferred.addCallback(_state)
        return deferred

    def open_domain(self, domain, spider=None):
        log.msg("Domain opened", domain=domain)
        spider = spider or spiders.fromdomain(domain)

        self.scheduler.open_domain(domain)
        self.downloader.open_domain(domain)
        self.pipeline.open_domain(domain)
        self._scraping[domain] = set()
        signals.send_catch_log(signals.domain_open, sender=self.__class__, domain=domain, spider=spider)

        # init_domain
        dfd = self.initialize(spider)
        def _state(state):
            if state is True:
                signals.send_catch_log(signals.domain_opened, sender=self.__class__, domain=domain, spider=spider)
                self._run_starters(spider)
            else:
                self._domain_idle(domain)
        dfd.addCallback(_state)

    def close_domain(self, domain):
        """Close (cancel) domain and clear all its outstanding requests"""
        if domain not in self.cancelled:
            self.cancelled.add(domain)
            self._close_domain(domain)

    def _close_domain(self, domain):
        self.downloader.close_domain(domain)

    def _domain_idle(self, domain):
        """
        Called when a domain gets idle. This function is called when there are no
        remaining pages to download or scheduled. It can be called multiple
        times. If the some extensions raises a DontCloseDomain exception the
        domain won't be closed and this function is garanteed to be called
        again (at least once) for this domain.
        """
        # we get a callback from the downloader which completes closing
        #log.msg("Finishing scraping %s" % domain, domain=domain)
        #from traceback import print_stack; print_stack()

        spider = spiders.fromdomain(domain)
        try:
            dispatcher.send(signal=signals.domain_idle, sender=self.__class__, domain=domain, spider=spider)
        except DontCloseDomain:
            return
        except:
            log.exc("Exception catched on domain_idle signal dispatch")

        if self.domain_is_idle(domain):
            self._close_domain(domain)

    def _stop_if_idle(self):
        """Call the stop method if the system has no outstanding tasks. """
        if self.is_idle() and not self.keep_alive:
            self.stop()

    def closed_domain(self, domain):
        """
        This function is called after the domain has been closed, and throws
        the domain_closed signal which is meant to be used for cleaning up
        purposes. In contrast to domain_idle, this function is called only
        ONCE for each domain run.
        """ 
        spider = spiders.fromdomain(domain) 
        self.scheduler.close_domain(domain)
        self.pipeline.close_domain(domain)
        del self._scraping[domain]
        status = 'cancelled' if domain in self.cancelled else 'finished'
        signals.send_catch_log(signal=signals.domain_closed, sender=self.__class__, domain=domain, spider=spider, status=status)
        log.msg("Domain closed (%s)" % status, domain=domain) 
        self.cancelled.discard(domain)
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
            "len(self.scheduler.pending_domains_count)",
            "self.downloader.is_idle()",
            "len(self.downloader.sites)",
            "self.downloader.has_capacity()",
            "self.pipeline.is_idle()",
            "len(self.pipeline.domaininfo)",
            ]
        domain_tests = [
            "self.domain_is_idle(domain)",
            "self.scheduler.domain_has_pending(domain)",
            "len(self.scheduler.pending_requests[domain])",
            "self.downloader.outstanding(domain)",
            "len(self.downloader.request_queue(domain))",
            "len(self.downloader.active_requests(domain))",
            "self.pipeline.domain_is_idle(domain)",
            "len(self.pipeline.domaininfo[domain])",
            ]

        for test in global_tests:
            s += "%-47s : %s\n" % (test, eval(test))
        s += "\n"
        for domain in self.downloader.sites:
            s += "%s\n" % domain
            for test in domain_tests:
                s += "  %-45s : %s\n" % (test, eval(test))

        return s

    def st(self): # shortcut for printing engine status (useful in telnet console)
        print self.getstatus()

scrapyengine = ExecutionEngine()
