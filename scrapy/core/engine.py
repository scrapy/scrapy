"""
This is the Scrapy engine which controls the Scheduler, Downloader and Spiders.

For more information see docs/topics/architecture.rst

"""
from time import time

from twisted.internet import reactor, defer
from twisted.python.failure import Failure

from scrapy import log, signals
from scrapy.stats import stats
from scrapy.core.downloader import Downloader
from scrapy.core.scraper import Scraper
from scrapy.exceptions import IgnoreRequest, DontCloseSpider
from scrapy.http import Response, Request
from scrapy.utils.misc import load_object
from scrapy.utils.signal import send_catch_log, send_catch_log_deferred
from scrapy.utils.defer import mustbe_deferred

class ExecutionEngine(object):

    def __init__(self, settings, spider_closed_callback):
        self.settings = settings
        self.closing = {} # dict (spider -> reason) of spiders being closed
        self.closing_dfds = {} # dict (spider -> deferred) of spiders being closed
        self.running = False
        self.paused = False
        self._next_request_calls = {}
        self.scheduler = load_object(settings['SCHEDULER'])()
        self.downloader = Downloader()
        self.scraper = Scraper(self, self.settings)
        self._spider_closed_callback = spider_closed_callback

    @defer.inlineCallbacks
    def start(self):
        """Start the execution engine"""
        assert not self.running, "Engine already running"
        self.start_time = time()
        yield send_catch_log_deferred(signal=signals.engine_started)
        self.running = True

    def stop(self):
        """Stop the execution engine gracefully"""
        assert self.running, "Engine not running"
        self.running = False
        dfd = self._close_all_spiders()
        return dfd.addBoth(lambda _: self._finish_stopping_engine())

    def pause(self):
        """Pause the execution engine"""
        self.paused = True

    def unpause(self):
        """Resume the execution engine"""
        self.paused = False

    def is_idle(self):
        return self.scheduler.is_idle() and self.downloader.is_idle() and \
            self.scraper.is_idle()

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
            dwld.addErrback(log.err, "Unhandled error on engine._next_request()",
                spider=spider)
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

    def has_capacity(self):
        """Does the engine have capacity to handle more spiders"""
        return len(self.downloader.sites) < self.downloader.concurrent_spiders

    def crawl(self, request, spider):
        assert spider in self.open_spiders, \
            "Spider %r not opened when crawling: %s" % (spider.name, request)
        if spider in self.closing: # ignore requests for spiders being closed
            return
        schd = mustbe_deferred(self.schedule, request, spider)
        # FIXME: we can't log errors because we would be preventing them from
        # propagating to the request errback. This should be fixed after the
        # next core refactoring.
        #schd.addErrback(log.err, "Error on engine.crawl()")
        schd.addBoth(self.scraper.enqueue_scrape, request, spider)
        schd.addErrback(log.err, "Unhandled error on engine.crawl()", spider=spider)
        schd.addBoth(lambda _: self.next_request(spider))

    def schedule(self, request, spider):
        if spider in self.closing:
            raise IgnoreRequest()
        self.next_request(spider)
        return self.scheduler.enqueue_request(spider, request)

    def download(self, request, spider):
        def _on_success(response):
            """handle the result of a page download"""
            assert isinstance(response, (Response, Request))
            if isinstance(response, Response):
                response.request = request # tie request to response received
                log.msg(log.formatter.crawled(request, response, spider), \
                    level=log.DEBUG, spider=spider)
                return response
            elif isinstance(response, Request):
                return mustbe_deferred(self.schedule, response, spider)

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
                log.msg("Error downloading <%s>: %s" % (request.url, errmsg), \
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

    @defer.inlineCallbacks
    def open_spider(self, spider):
        assert self.has_capacity(), "No free spider slots when opening %r" % \
            spider.name
        log.msg("Spider opened", spider=spider)
        yield self.scheduler.open_spider(spider)
        self.downloader.open_spider(spider)
        yield self.scraper.open_spider(spider)
        stats.open_spider(spider)
        yield send_catch_log_deferred(signals.spider_opened, spider=spider)
        self.next_request(spider)

    def _spider_idle(self, spider):
        """Called when a spider gets idle. This function is called when there
        are no remaining pages to download or schedule. It can be called
        multiple times. If some extension raises a DontCloseSpider exception
        (in the spider_idle signal handler) the spider is not closed until the
        next loop and this function is guaranteed to be called (at least) once
        again for this spider.
        """
        res = send_catch_log(signal=signals.spider_idle, \
            spider=spider, dont_log=DontCloseSpider)
        if any(isinstance(x, Failure) and isinstance(x.value, DontCloseSpider) \
                for _, x in res):
            reactor.callLater(5, self.next_request, spider)
            return

        if self.spider_is_idle(spider):
            self.close_spider(spider, reason='finished')

    def close_spider(self, spider, reason='cancelled'):
        """Close (cancel) spider and clear all its outstanding requests"""
        if spider in self.closing:
            return defer.succeed(None)
        log.msg("Closing spider (%s)" % reason, spider=spider)
        self.closing[spider] = reason
        self.scheduler.clear_pending_requests(spider)
        dfd = self.downloader.close_spider(spider)
        self.closing_dfds[spider] = dfd
        dfd.addBoth(lambda _: self.scheduler.close_spider(spider))
        dfd.addErrback(log.err, "Unhandled error in scheduler.close_spider()", \
            spider=spider)
        dfd.addBoth(lambda _: self.scraper.close_spider(spider))
        dfd.addErrback(log.err, "Unhandled error in scraper.close_spider()", \
            spider=spider)
        dfd.addBoth(lambda _: self._finish_closing_spider(spider))
        return dfd

    def _close_all_spiders(self):
        dfds = [self.close_spider(s, reason='shutdown') for s in self.open_spiders]
        dfds += self.closing_dfds.values()
        dlist = defer.DeferredList(dfds)
        return dlist

    def _finish_closing_spider(self, spider):
        """This function is called after the spider has been closed"""
        reason = self.closing.pop(spider, 'finished')
        call = self._next_request_calls.pop(spider, None)
        if call and call.active():
            call.cancel()
        dfd = send_catch_log_deferred(signal=signals.spider_closed, \
            spider=spider, reason=reason)
        dfd.addBoth(lambda _: stats.close_spider(spider, reason=reason))
        dfd.addErrback(log.err, "Unhandled error in stats.close_spider()",
            spider=spider)
        dfd.addBoth(lambda _: log.msg("Spider closed (%s)" % reason, spider=spider))
        dfd.addBoth(lambda _: self.closing_dfds.pop(spider).callback(spider))
        dfd.addBoth(lambda _: self._spider_closed_callback(spider))
        return dfd

    @defer.inlineCallbacks
    def _finish_stopping_engine(self):
        yield send_catch_log_deferred(signal=signals.engine_stopped)
