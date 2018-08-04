from scrapy.core import config
from scrapy.core import engine

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
    def __init__(self, Request):
        self.Request = Request
        self.crawler = engine.concraw
        self.spider = engine.conspid
        self.downloader = Downloader(self.crawler)
        self.logformatter = engine.concraw.logformatter
        self.signals = engine.concraw.signals

    def fetch(self):
        request = self.Request
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

