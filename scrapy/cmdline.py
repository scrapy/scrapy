from testfixtures import LogCapture
from twisted.internet import defer
from twisted.trial.unittest import TestCase
from scrapy.http import Request
from scrapy.utils.test import get_crawler
from tests.mockserver import MockServer
from tests.spiders import MockServerSpider

class InjectArgumentsDownloaderMiddleware:
    """
    Allow downloader middlewares to update the keyword arguments
    """
    def process_request(self, request, spider):
        if request.callback.__name__ == "parse_downloader_mw":
            request.cb_kwargs.setdefault('from_process_request', True)
        return None

    def process_response(self, request, response, spider):
        if request.callback.__name__ == "parse_downloader_mw":
            request.cb_kwargs.setdefault('from_process_response', True)
        return response
    

class InjectArgumentsSpiderMiddleware:
    """
    Allow spider middlewares to update the keyword arguments 
    """
    def process_start_requests(self, start_requests, spider):    
        for request in start_requests:
            if request.callback.__name__ == "parse_spider_mw":
                request.cb_kwargs.setdefault('from_process_start_requests', True)
            yield request
            
    def process_spider_input(self, response, spider):     
        request = response.request   
        if request.callback.__name__ == "parse_spider_mw":
            request.cb_kwargs.setdefault('from_process_spider_input' , True)  
        return None    

    def process_spider_output(self, response, result, spider):
        for element in result:
            if isinstance(element, Request) and element.callback.__name__ == "parse_spider_mw_2":
                element.cb_kwargs.setdefault('from_process_spider_output', True)
            yield element

class KeywordArgumentsSpider(MockServerSpider):

    name = "kwargs"
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {
            InjectArgumentsDownloaderMiddleware: 750,
        },
        "SPIDER_MIDDLEWARES": {
            InjectArgumentsSpiderMiddleware: 750,
        },
    }

    checks = []
    
    def start_requests(self):
              
        yield Request(self.mockserver.url("/first"), meta={"key":"value", "number":123, "callback":"some_callback"}, callback=self.parse_first)       
        yield Request(self.mockserver.url("/general_with"),self.parse_general,
                      meta= {"key":"value","number":123,"callback":"some_callback"})
        yield Request(self.mockserver.url("/general_without"), self.parse_general)
        yield Request(self.mockserver.url("/no_kwargs"), self.parse_no_kwargs)
        yield Request(self.mockserver.url("/default"),meta={"key":"value", "number":123},callback=self.parse_default)
        yield Request(self.mockserver.url("/takes_less"),meta={"key":"value", "callback":"some_callback"},callback=self.parse_takes_less)
        yield Request(self.mockserver.url("/takes_more"),meta={"key":"value", "number":123, "callback":"some_callback", "other":"another_callback"},callback=self.parse_takes_more)
        yield Request(self.mockserver.url("/downloader_mw"), callback=self.parse_downloader_mw)
        yield Request(self.mockserver.url("/spider_mw"), callback=self.parse_spider_mw)

        
    def parse_first(self, response):
        key = response.meta["key"]
        number = response.meta["number"]
        
        self.checks.append(key == "value")
        self.checks.append(number == 123)
        
        self.crawler.stats.inc_value("boolean_checks", 2)
        
        yield response.follow(
            self.mockserver.url("/two"),
            self.parse_second,
            meta={"new_key": "new_value"},
        )
        
    def parse_second(self, response):       
        new_key = response.meta["new_key"]
        
        self.checks.append(new_key == "new_value")
        self.crawler.stats.inc_value("boolean_checks")
        
    def parse_general(self, response, **kwargs): 
        if response.url.endswith("/general_with"):
            self.checks.append(kwargs["key"] == "value")
            self.checks.append(kwargs["number"] == 123)
            self.checks.append(kwargs["callback"] == "some_callback")
            
            self.crawler.stats.inc_value("boolean_checks", 3)
        elif response.url.endswith("/general_without"):
            self.checks.append(kwargs == {})
            self.crawler.stats.inc_value("boolean_checks")
            
    def parse_no_kwargs(self, response):
        self.checks.append(response.url.endswith("/no_kwargs"))
        self.crawler.stats.inc_value("boolean_checks")
        
    def parse_default(self, response):
        key = response.meta["key"]
        number = response.meta["number"]
        default = response.meta.setdefault("default",99)
        
        self.checks.append(response.url.endswith("/default"))
        self.checks.append(key == "value")
        self.checks.append(number == 123)
        self.checks.append(default == 99)
        
        self.crawler.stats.inc_value("boolean_checks", 4)
        
    def parse_takes_less(self, response):
        """
        Should raise
        TypeError: parse_takes_less() got an unexpected keyword argument 'number'
        """
        pass

    def parse_takes_more(self, response):
        """
        Should raise
        TypeError: parse_takes_more() missing 1 required positional argument: 'other'
        """
        pass              

    def parse_downloader_mw (self, response):       
        from_process_request = response.request.cb_kwargs.get('from_process_request')
        from_process_response = response.request.cb_kwargs.get('from_process_response')
        
        self.checks.append(bool(from_process_request))
        self.checks.append(bool(from_process_response))
        
        self.crawler.stats.inc_value("boolean_checks", 2)

    def parse_spider_mw (self, response):
        from_process_spider_input = response.request.cb_kwargs.get('from_process_spider_input') 
        from_process_start_requests = response.request.cb_kwargs.get('from_process_start_requests')         

        self.checks.append(bool(from_process_spider_input))
        self.checks.append(bool(from_process_start_requests))
          
        self.crawler.stats.inc_value("boolean_checks", 2)
        return Request(self.mockserver.url("/spider_mw_2"), self.parse_spider_mw_2)
        

    def parse_spider_mw_2 (self, response):       
        from_process_spider_output = response.request.cb_kwargs["from_process_spider_output"]
        self.checks.append(bool(from_process_spider_output))
        self.crawler.stats.inc_value("boolean_checks",1)


class CallbackKeywordArgumentsTestCase (TestCase):
     
    maxDiff = None
   
    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_callback_kwargs(self):
        crawler = get_crawler(KeywordArgumentsSpider)
        with LogCapture() as log:
            yield crawler.crawl(mockserver=self.mockserver)
            
        self.assertTrue(all(crawler.spider.checks))
        self.assertEqual(
            len(crawler.spider.checks), crawler.stats.get_value("boolean_checks")
        )
        exceptions = {}
        for line in log.records:
            for key in ("takes_less", "takes_more"):
                if key in line.getMessage():
                    exceptions[key] = line
        self.assertEqual(exceptions["takes_less"].exc_info[0], TypeError)
        self.assertTrue(
            str(exceptions["takes_less"].exc_info[1]).endswith("parse_takes_less() got an unexpected keyword argument 'number'"),
                       msg="Exception message: " + str(exceptions["takes_less"].exc_info[1]))

        self.assertEqual(exceptions["takes_more"].exc_info[0], TypeError)
        self.assertTrue(
            str(exceptions["takes_more"].exc_info[1]).endswith("parse_takes_more() missing 1 required positional argument: 'other'"),
                       msg="Exception message: " + str(exceptions["takes_more"].exc_info[1])) 
