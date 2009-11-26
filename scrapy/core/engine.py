"""
This is the Scrapy engine which controls the Scheduler, Downloader and Spiders.

For more information see docs/topics/architecture.rst

"""
from time import time

from twisted.internet import reactor, task, defer
from twisted.python.failure import Failure
from scrapy.xlib.pydispatch import dispatcher

from scrapy import log
from scrapy.stats import stats
from scrapy.conf import settings
from scrapy.core import signals
from scrapy.core.downloader import Downloader
from scrapy.core.scraper import Scraper
from scrapy.core.exceptions import IgnoreRequest, DontCloseSpider
from scrapy.http import Response, Request
from scrapy.spider import spiders
from scrapy.utils.misc import load_object
from scrapy.utils.signal import send_catch_log
from scrapy.utils.defer import mustbe_deferred

class ExecutionEngine(object):

    def __init__(self):
        self.configured = False
        self.keep_alive = False
        self.closing = {} # dict (spider -> reason) of spiders being closed
        self.running = False
        self.killed = False
        self.paused = False
        self._next_request_calls = {}
        self._mainloop_task = task.LoopingCall(self._mainloop)
        self._crawled_logline = load_object(settings['LOG_FORMATTER_CRAWLED'])

    def configure(self):
        """
        Configure execution engine with the given scheduling policy and downloader.
        """
        self.scheduler = load_object(settings['SCHEDULER'])()
        self.spider_scheduler = load_object(settings['SPIDER_SCHEDULER'])()
        self.downloader = Downloader()
        self.scraper = Scraper(self)
        self.configured = True

    def start(self):
        """Start the execution engine"""
        if self.running:
            return
        self.start_time = time()
        send_catch_log(signal=signals.engine_started, sender=self.__class__)
        self._mainloop_task.start(5.0, now=True)
        reactor.callWhenRunning(self._mainloop)
        self.running = True

    def stop(self):
        """Stop the execution engine gracefully"""
        if not self.running:
            return
        self.running = False
        def before_shutdown():
            dfd = self._close_all_spiders()
            return dfd.addBoth(lambda _: self._finish_stopping_engine())
        reactor.addSystemEventTrigger('before', 'shutdown', before_shutdown)
        if self._mainloop_task.running:
            self._mainloop_task.stop()
        try:
            reactor.stop()
        except RuntimeError: # raised if already stopped or in shutdown stage
            pass

    def kill(self):
        """Forces shutdown without waiting for pending transfers to finish.
        stop() must have been called first
        """
        if self.running:
            return
        self.killed = True

    def pause(self):
        """Pause the execution engine"""
        self.paused = True

    def unpause(self):
        """Resume the execution engine"""
        self.paused = False

    def is_idle(self):
        return self.scheduler.is_idle() and self.downloader.is_idle() and \
            self.scraper.is_idle()

    def next_spider(self):
        spider = self.spider_scheduler.next_spider()
        if spider:
            self.open_spider(spider)
            return True

    def next_request(self, spider, now=False):
        """Scrape the next request for the spider passed.

        The next request to be scraped is retrieved from the scheduler and
        requested from the downloader.

        The spider is closed if there are no more pages to scrape.
        """
        if now:
            self._next_request_calls.pop(spider, None)
        elif spider not in self._next_request_calls:
            call = reactor.callLater(0, self.next_request, spider, now=True)
            self._next_request_calls[spider] = call
            return call
        else:
            return

        if self.paused:
            return reactor.callLater(5, self.next_request, spider)

        while not self._needs_backout(spider):
            if not self._next_request(spider):
                break

        if self.spider_is_idle(spider):
            self._spider_idle(spider)

    def _needs_backout(self, spider):
        return not self.running \
            or self.spider_is_closed(spider) \
            or self.downloader.sites[spider].needs_backout() \
            or self.scraper.sites[spider].needs_backout()

    def _next_request(self, spider):
        # Next pending request from scheduler
        request, deferred = self.scheduler.next_request(spider)
        if request:
            dwld = mustbe_deferred(self.download, request, spider)
            dwld.chainDeferred(deferred).addBoth(lambda _: deferred)
            dwld.addErrback(log.err, "Unhandled error on engine._next_request")
            return dwld

    def spider_is_idle(self, spider):
        scraper_idle = spider in self.scraper.sites \
            and self.scraper.sites[spider].is_idle()
        pending = self.scheduler.spider_has_pending_requests(spider)
        downloading = spider in self.downloader.sites \
            and self.downloader.sites[spider].active
        return scraper_idle and not (pending or downloading)

    def spider_is_closed(self, spider):
        """Return True if the spider is fully closed (ie. not even in the
        closing stage)"""
        return spider not in self.downloader.sites

    def spider_is_open(self, spider):
        """Return True if the spider is fully opened (ie. not in closing
        stage)"""
        return spider in self.downloader.sites and spider not in self.closing

    @property
    def open_spiders(self):
        return self.downloader.sites.keys()

    def crawl(self, request, spider):
        if not request.deferred.callbacks:
            log.msg("Unable to crawl Request with no callback: %s" % request,
                level=log.ERROR, spider=spider)
            return
        schd = mustbe_deferred(self.schedule, request, spider)
        # FIXME: we can't log errors because we would be preventing them from
        # propagating to the request errback. This should be fixed after the
        # next core refactoring.
        #schd.addErrback(log.err, "Error on engine.crawl()")
        schd.addBoth(self.scraper.enqueue_scrape, request, spider)
        schd.addErrback(log.err, "Unhandled error on engine.crawl()")
        schd.addBoth(lambda _: self.next_request(spider))

    def schedule(self, request, spider):
        if spider in self.closing:
            raise IgnoreRequest()
        if not self.scheduler.spider_is_open(spider):
            self.scheduler.open_spider(spider)
            if self.spider_is_closed(spider): # scheduler auto-open
                self.spider_scheduler.add_spider(spider)
        self.next_request(spider)
        return self.scheduler.enqueue_request(spider, request)

    def _mainloop(self):
        """Add more spiders to be scraped if the downloader has the capacity.

        If there is nothing else scheduled then stop the execution engine.
        """
        if not self.running or self.paused:
            return

        while self.running and self.downloader.has_capacity():
            if not self.next_spider():
                return self._stop_if_idle()

    def download(self, request, spider):
        def _on_success(response):
            """handle the result of a page download"""
            assert isinstance(response, (Response, Request))
            if isinstance(response, Response):
                response.request = request # tie request to response received
                log.msg(self._crawled_logline(request, response), \
                    level=log.DEBUG, spider=spider)
                return response
            elif isinstance(response, Request):
                newrequest = response
                schd = mustbe_deferred(self.schedule, newrequest, spider)
                schd.chainDeferred(newrequest.deferred)
                return newrequest.deferred

        def _on_error(_failure):
            """handle an error processing a page"""
            exc = _failure.value
            if isinstance(exc, IgnoreRequest):
                errmsg = _failure.getErrorMessage()
                level = exc.level
            else:
                errmsg = str(_failure)
                level = log.ERROR
            if errmsg:
                log.msg("Crawling <%s>: %s" % (request.url, errmsg), \
                    level=level, spider=spider)
            return Failure(IgnoreRequest(str(exc)))

        def _on_complete(_):
            self.next_request(spider)
            return _

        if spider not in self.downloader.sites:
            return defer.fail(Failure(IgnoreRequest())).addBoth(_on_complete)

        dwld = mustbe_deferred(self.downloader.fetch, request, spider)
        dwld.addCallbacks(_on_success, _on_error)
        dwld.addBoth(_on_complete)
        return dwld

    def open_spider(self, spider):
        log.msg("Spider opened", spider=spider)
        self.next_request(spider)

        self.downloader.open_spider(spider)
        self.scraper.open_spider(spider)
        stats.open_spider(spider)

        send_catch_log(signals.spider_opened, sender=self.__class__, spider=spider)

    def _spider_idle(self, spider):
        """Called when a spider gets idle. This function is called when there
        are no remaining pages to download or schedule. It can be called
        multiple times. If some extension raises a DontCloseSpider exception
        (in the spider_idle signal handler) the spider is not closed until the
        next loop and this function is guaranteed to be called (at least) once
        again for this spider.
        """
        try:
            dispatcher.send(signal=signals.spider_idle, sender=self.__class__, \
                spider=spider)
        except DontCloseSpider:
            reactor.callLater(5, self.next_request, spider)
            return
        except Exception, e:
            log.msg("Exception caught on 'spider_idle' signal dispatch: %r" % e, \
                level=log.ERROR)
        if self.spider_is_idle(spider):
            self.close_spider(spider, reason='finished')

    def _stop_if_idle(self):
        """Call the stop method if the system has no outstanding tasks. """
        if self.is_idle() and not self.keep_alive:
            self.stop()

    def close_spider(self, spider, reason='cancelled'):
        """Close (cancel) spider and clear all its outstanding requests"""
        if spider not in self.closing:
            log.msg("Closing spider (%s)" % reason, spider=spider)
            self.closing[spider] = reason
            self.downloader.close_spider(spider)
            self.scheduler.clear_pending_requests(spider)
            return self._finish_closing_spider_if_idle(spider)
        return defer.succeed(None)

    def _close_all_spiders(self):
        dfds = [self.close_spider(s, reason='shutdown') for s in self.open_spiders]
        dlist = defer.DeferredList(dfds)
        return dlist

    def _finish_closing_spider_if_idle(self, spider):
        """Call _finish_closing_spider if spider is idle"""
        if self.spider_is_idle(spider) or self.killed:
            return self._finish_closing_spider(spider)
        else:
            dfd = defer.Deferred()
            dfd.addCallback(self._finish_closing_spider_if_idle)
            delay = 5 if self.running else 1
            reactor.callLater(delay, dfd.callback, spider)
            return dfd

    def _finish_closing_spider(self, spider):
        """This function is called after the spider has been closed"""
        self.scheduler.close_spider(spider)
        self.scraper.close_spider(spider)
        reason = self.closing.pop(spider, 'finished')
        send_catch_log(signal=signals.spider_closed, sender=self.__class__, \
            spider=spider, reason=reason)
        stats.close_spider(spider, reason=reason)
        call = self._next_request_calls.pop(spider, None)
        if call and call.active():
            call.cancel()
        dfd = defer.maybeDeferred(spiders.close_spider, spider)
        dfd.addBoth(log.msg, "Spider closed (%s)" % reason, spider=spider)
        reactor.callLater(0, self._mainloop)
        return dfd

    def _finish_stopping_engine(self):
        send_catch_log(signal=signals.engine_stopped, sender=self.__class__)

scrapyengine = ExecutionEngine()
