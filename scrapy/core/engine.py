"""
This is the Scrapy engine which controls the Scheduler, Downloader and Spiders.

For more information see docs/topics/architecture.rst

"""
import warnings
from time import time

from twisted.internet import defer
from twisted.python.failure import Failure

from scrapy import log, signals
from scrapy.core.downloader import Downloader
from scrapy.core.scraper import Scraper
from scrapy.exceptions import DontCloseSpider, ScrapyDeprecationWarning
from scrapy.http import Response, Request
from scrapy.utils.misc import load_object
from scrapy.utils.reactor import CallLaterOnce


class Slot(object):

    def __init__(self, start_requests, close_if_idle, nextcall, scheduler):
        self.closing = False
        self.inprogress = set() # requests in progress
        self.start_requests = iter(start_requests)
        self.close_if_idle = close_if_idle
        self.nextcall = nextcall
        self.scheduler = scheduler

    def add_request(self, request):
        self.inprogress.add(request)

    def remove_request(self, request):
        self.inprogress.remove(request)
        self._maybe_fire_closing()

    def close(self):
        self.closing = defer.Deferred()
        self._maybe_fire_closing()
        return self.closing

    def _maybe_fire_closing(self):
        if self.closing and not self.inprogress:
            if self.nextcall:
                self.nextcall.cancel()
            self.closing.callback(None)


class ExecutionEngine(object):

    def __init__(self, crawler, spider_closed_callback):
        self.crawler = crawler
        self.settings = crawler.settings
        self.signals = crawler.signals
        self.logformatter = crawler.logformatter
        self.slots = {}
        self.running = False
        self.paused = False
        self.scheduler_cls = load_object(self.settings['SCHEDULER'])
        self.downloader = Downloader(crawler)
        self.scraper = Scraper(crawler)
        self._concurrent_spiders = self.settings.getint('CONCURRENT_SPIDERS', 1)
        if self._concurrent_spiders != 1:
            warnings.warn("CONCURRENT_SPIDERS settings is deprecated, use " \
                "Scrapyd max_proc config instead", ScrapyDeprecationWarning)
        self._spider_closed_callback = spider_closed_callback

    @defer.inlineCallbacks
    def start(self):
        """Start the execution engine"""
        assert not self.running, "Engine already running"
        self.start_time = time()
        yield self.signals.send_catch_log_deferred(signal=signals.engine_started)
        self.running = True
        self._closewait = defer.Deferred()
        yield self._closewait

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

    def _next_request(self, spider):
        try:
            slot = self.slots[spider]
        except KeyError:
            return

        if self.paused:
            slot.nextcall.schedule(5)
            return

        while not self._needs_backout(spider):
            if not self._next_request_from_scheduler(spider):
                break

        if slot.start_requests and not self._needs_backout(spider):
            try:
                request = slot.start_requests.next()
            except StopIteration:
                slot.start_requests = None
            except Exception, exc:
                log.err(None, 'Obtaining request from start requests', \
                        spider=spider)
            else:
                self.crawl(request, spider)

        if self.spider_is_idle(spider) and slot.close_if_idle:
            self._spider_idle(spider)

    def _needs_backout(self, spider):
        slot = self.slots[spider]
        return not self.running \
            or slot.closing \
            or self.downloader.needs_backout() \
            or self.scraper.slot.needs_backout()

    def _next_request_from_scheduler(self, spider):
        slot = self.slots[spider]
        request = slot.scheduler.next_request()
        if not request:
            return
        d = self._download(request, spider)
        d.addBoth(self._handle_downloader_output, request, spider)
        d.addErrback(log.msg, spider=spider)
        d.addBoth(lambda _: slot.remove_request(request))
        d.addErrback(log.msg, spider=spider)
        d.addBoth(lambda _: slot.nextcall.schedule())
        d.addErrback(log.msg, spider=spider)
        return d

    def _handle_downloader_output(self, response, request, spider):
        assert isinstance(response, (Request, Response, Failure)), response
        # downloader middleware can return requests (for example, redirects)
        if isinstance(response, Request):
            self.crawl(response, spider)
            return
        # response is a Response or Failure
        d = self.scraper.enqueue_scrape(response, request, spider)
        d.addErrback(log.err, spider=spider)
        return d

    def spider_is_idle(self, spider):
        scraper_idle = self.scraper.slot.is_idle()
        pending = self.slots[spider].scheduler.has_pending_requests()
        downloading = bool(self.downloader.active)
        idle = scraper_idle and not (pending or downloading)
        return idle

    @property
    def open_spiders(self):
        return self.slots.keys()

    def has_capacity(self):
        """Does the engine have capacity to handle more spiders"""
        return len(self.slots) < self._concurrent_spiders

    def crawl(self, request, spider):
        assert spider in self.open_spiders, \
            "Spider %r not opened when crawling: %s" % (spider.name, request)
        self.schedule(request, spider)
        self.slots[spider].nextcall.schedule()

    def schedule(self, request, spider):
        self.signals.send_catch_log(signal=signals.request_scheduled,
                request=request, spider=spider)
        return self.slots[spider].scheduler.enqueue_request(request)

    def download(self, request, spider):
        slot = self.slots[spider]
        slot.add_request(request)
        d = self._download(request, spider)
        d.addBoth(self._downloaded, slot, request, spider)
        return d

    def _downloaded(self, response, slot, request, spider):
        slot.remove_request(request)
        return self.download(response, spider) \
                if isinstance(response, Request) else response

    def _download(self, request, spider):
        slot = self.slots[spider]
        slot.add_request(request)
        def _on_success(response):
            assert isinstance(response, (Response, Request))
            if isinstance(response, Response):
                response.request = request # tie request to response received
                logkws = self.logformatter.crawled(request, response, spider)
                log.msg(spider=spider, **logkws)
                self.signals.send_catch_log(signal=signals.response_received, \
                    response=response, request=request, spider=spider)
            return response

        def _on_complete(_):
            slot.nextcall.schedule()
            return _

        dwld = self.downloader.fetch(request, spider)
        dwld.addCallbacks(_on_success)
        dwld.addBoth(_on_complete)
        return dwld

    @defer.inlineCallbacks
    def open_spider(self, spider, start_requests=(), close_if_idle=True):
        assert self.has_capacity(), "No free spider slots when opening %r" % \
            spider.name
        log.msg("Spider opened", spider=spider)
        nextcall = CallLaterOnce(self._next_request, spider)
        scheduler = self.scheduler_cls.from_crawler(self.crawler)
        start_requests = yield self.scraper.spidermw.process_start_requests(start_requests, spider)
        slot = Slot(start_requests, close_if_idle, nextcall, scheduler)
        self.slots[spider] = slot
        yield scheduler.open(spider)
        yield self.scraper.open_spider(spider)
        self.crawler.stats.open_spider(spider)
        yield self.signals.send_catch_log_deferred(signals.spider_opened, spider=spider)
        slot.nextcall.schedule()

    def _spider_idle(self, spider):
        """Called when a spider gets idle. This function is called when there
        are no remaining pages to download or schedule. It can be called
        multiple times. If some extension raises a DontCloseSpider exception
        (in the spider_idle signal handler) the spider is not closed until the
        next loop and this function is guaranteed to be called (at least) once
        again for this spider.
        """
        res = self.signals.send_catch_log(signal=signals.spider_idle, \
            spider=spider, dont_log=DontCloseSpider)
        if any(isinstance(x, Failure) and isinstance(x.value, DontCloseSpider) \
                for _, x in res):
            self.slots[spider].nextcall.schedule(5)
            return

        if self.spider_is_idle(spider):
            self.close_spider(spider, reason='finished')

    def close_spider(self, spider, reason='cancelled'):
        """Close (cancel) spider and clear all its outstanding requests"""

        slot = self.slots[spider]
        if slot.closing:
            return slot.closing
        log.msg(format="Closing spider (%(reason)s)", reason=reason, spider=spider)

        dfd = slot.close()

        dfd.addBoth(lambda _: self.downloader.close())
        dfd.addErrback(log.err, spider=spider)

        dfd.addBoth(lambda _: self.scraper.close_spider(spider))
        dfd.addErrback(log.err, spider=spider)

        dfd.addBoth(lambda _: slot.scheduler.close(reason))
        dfd.addErrback(log.err, spider=spider)

        # XXX: spider_stats argument was added for backwards compatibility with
        # stats collection refactoring added in 0.15. it should be removed in 0.17.
        dfd.addBoth(lambda _: self.signals.send_catch_log_deferred(signal=signals.spider_closed, \
            spider=spider, reason=reason, spider_stats=self.crawler.stats.get_stats()))
        dfd.addErrback(log.err, spider=spider)

        dfd.addBoth(lambda _: self.crawler.stats.close_spider(spider, reason=reason))
        dfd.addErrback(log.err, spider=spider)

        dfd.addBoth(lambda _: log.msg(format="Spider closed (%(reason)s)", reason=reason, spider=spider))

        dfd.addBoth(lambda _: self.slots.pop(spider))
        dfd.addErrback(log.err, spider=spider)

        dfd.addBoth(lambda _: self._spider_closed_callback(spider))

        return dfd

    def _close_all_spiders(self):
        dfds = [self.close_spider(s, reason='shutdown') for s in self.open_spiders]
        dlist = defer.DeferredList(dfds)
        return dlist

    @defer.inlineCallbacks
    def _finish_stopping_engine(self):
        yield self.signals.send_catch_log_deferred(signal=signals.engine_stopped)
        self._closewait.callback(None)
