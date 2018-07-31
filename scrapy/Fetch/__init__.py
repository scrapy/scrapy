from scrapy.utils.log import logformatter_adapter, failure_to_exc_info
from scrapy import signals
from scrapy.core.downloader import Downloader 
from twisted.internet.defer import Deferred
import asyncio
import logging
import scrapy
import warnings

logger = logging.getLogger(__name__)



class Fetch():
    def __init__(self, url,crawler=None,spider=None, callback=None, method='GET', headers=None, body=None,
                 cookies=None, meta=None, encoding='utf-8', priority=0,
                 dont_filter=False, errback=None, flags=None):
        self.url = url
        self.crawler = crawler
        self.spider = spider
        self.downloader = Downloader(crawler)
        self.logformatter = crawler.logformatter
        self.signals = crawler.signals
        


        self.encoding = encoding  # this one has to be set first
        self.method = method
        self.priority = priority
        if callback is not None:
            warnings.warn("Please do not use callbacks/errbacks with scrapy.Fetch. This method is an awaitable, and may not work well with a callback!")
        self.callback = callback
        self.errback = errback

        self.cookies = cookies 
        self.headers = headers
        self.dont_filter = dont_filter
        self.body = body
        
        self.meta = meta
        self.flags = flags
        self.crawler = crawler
        self.spider = spider

    def fetch(self):
        request = scrapy.Request(url=self.url, callback=None, method=self.method, headers=self.headers, body=self.body,cookies=self.cookies, meta=self.meta, encoding=self.encoding,priority=self.priority, dont_filter=self.dont_filter, errback=None, flags=self.flags)
        def _on_success(response):
            response.request = request # tie request to response received
            logkws = self.logformatter.crawled(request, response, self.spider)
            logger.log(*logformatter_adapter(logkws), extra={'spider': self.spider})
            self.signals.send_catch_log(signal=signals.response_received,response=response, request=request, spider=self.spider)
            
            return response

        dwld = self.downloader.fetch(request, self.spider)
       
        return dwld.addCallbacks(_on_success)

    def __await__(self):
        
        obj = self.fetch()
        future = obj.asFuture(asyncio.get_event_loop())
        return future.__await__()

