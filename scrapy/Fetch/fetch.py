from scrapy.utils.log import logformatter_adapter, failure_to_exc_info
from scrapy import signals
from scrapy.core.downloader import Downloader 
from twisted.internet.defer import Deferred
import asyncio
import logging
import scrapy

logger = logging.getLogger(__name__)



class Fetch():
    def __init__(self, url,crawler=None, spider=None):
        self.url = url
        self.crawler = crawler
        self.spider = spider
        self.downloader = Downloader(crawler)
        self.logformatter = crawler.logformatter
        self.signals = crawler.signals

    def fetch(self):
        request = scrapy.Request(url=self.url)
        def _on_success(response):
            response.request = request # tie request to response received
            print("The Response {}".format(response))
            logkws = self.logformatter.crawled(request, response, self.spider)
            logger.log(*logformatter_adapter(logkws), extra={'spider': self.spider})
            self.signals.send_catch_log(signal=signals.response_received,response=response, request=request, spider=self.spider)
            print("Before the response !!")
            return response

        dwld = self.downloader.fetch(request, self.spider)
        print("The Value of dwld !! {}".format(dwld))
        return dwld.addCallbacks(_on_success)

    def __await__(self):
        print("Inside the fetch command!!")
        obj = self.fetch()
        future = obj.asFuture(asyncio.get_event_loop())
        print("The Type and result of future {} {}".format(future,future.result))
        return future.__await__()

