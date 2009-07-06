"""Extract information from pages"""

from itertools import imap
from twisted.internet import task
from twisted.python.failure import Failure

from scrapy.utils.defer import defer_result
from scrapy.utils.misc import arg_to_iter
from scrapy.core.exceptions import IgnoreRequest
from scrapy.core import signals
from scrapy.http import Request, Response
from scrapy.spider.middleware import SpiderMiddlewareManager
from scrapy import log
from scrapy.stats import stats

class Scraper(object):

    def __init__(self, engine):
        self.sites = {}
        self.middleware = SpiderMiddlewareManager()
        self.engine = engine

    def open_domain(self, domain):
        """Open the given domain for scraping and allocate resources for it"""
        if domain in self.sites:
            raise RuntimeError('Scraper domain already opened: %s' % domain)
        self.sites[domain] = set()

    def close_domain(self, domain):
        """Close a domain being scraped and release its resources"""
        if domain not in self.sites:
            raise RuntimeError('Scraper domain already closed: %s' % domain)
        del self.sites[domain]

    def is_idle(self):
        """Return True if there isn't any more spiders to process"""
        return not self.sites

    def scrape(self, response, request, spider):
        """Handle the downloaded response or failure trough the spider
        callback/errback"""
        assert isinstance(response, (Response, Failure))
        domain = spider.domain_name

        self.sites[domain].add(response)
        def _finish_scraping(_):
            self.sites[domain].remove(response)
            return _

        dfd = self._scrape(response, request, spider) # returns spiders processed output
        dfd.addErrback(self.handle_spider_error, request, spider)
        dfd.addCallback(self.handle_spider_output, request, spider)
        dfd.addBoth(_finish_scraping)
        dfd.addErrback(log.err, 'Scraper bug processing %s' % request, \
            domain=domain)
        return dfd

    def _scrape(self, request_result, request, spider):
        """Handle the diferent cases of request's result been a Response or a Failure"""
        if not isinstance(request_result, Failure):
            return self.middleware.scrape_response(self.call_spider, \
                request_result, request, spider)
        else:
            # FIXME: don't ignore errors in spider middleware
            dfd = self.call_spider(request_result, request, spider)
            return dfd.addErrback(self._check_propagated_failure, \
                request_result, request, spider)

    def call_spider(self, result, request, spider):
        defer_result(result).chainDeferred(request.deferred)
        return request.deferred.addCallback(arg_to_iter)

    def handle_spider_error(self, _failure, request, spider, propagated_failure=None):
        referer = request.headers.get('Referer', None)
        msg = "SPIDER BUG processing <%s> from <%s>: %s" % (request.url, referer, _failure)
        log.msg(msg, log.ERROR, domain=spider.domain_name)
        stats.incpath("%s/spider_exceptions/%s" % (spider.domain_name, _failure.value.__class__.__name__))

    def handle_spider_output(self, result, request, spider):
        func = lambda o: self.process_spider_output(o, request, spider)
        return task.coiterate(imap(func, result or []))

    def process_spider_output(self, output, request, spider):
        if spider.domain_name in self.engine.closing:
            return
        elif isinstance(output, Request):
            signals.send_catch_log(signal=signals.request_received, request=output, spider=spider)
            self.engine.crawl(request=output, spider=spider)
        elif output is None:
            pass # may be next time.
        else:
            log.msg("Spider must return Request, ScrapedItem or None, got '%s' while processing %s" \
                    % (type(output).__name__, request), log.WARNING, domain=spider.domain_name)

    def _check_propagated_failure(self, spider_failure, propagated_failure, request, spider):
        """Log and silence the bugs raised outside of spiders, but still allow
        spiders to be notified about general failures while downloading spider
        generated requests
        """
        # ignored requests are commonly propagated exceptions safes to be silenced
        if isinstance(spider_failure.value, IgnoreRequest):
            return
        elif spider_failure is propagated_failure:
            log.err(spider_failure, 'Unhandled error propagated to spider and wasn\'t handled')
            return # stop propagating this error
        else:
            return spider_failure # exceptions raised in the spider code
