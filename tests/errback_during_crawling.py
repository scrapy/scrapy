import unittest
import logging
from scrapy.crawler import Crawler, CrawlerProcess
from twisted.internet.defer import Deferred
from scrapy.spiders import Spider

class MyTestSpider(Spider):
    name = "mytestspider"
    start_urls = ['http://example.com']

class TestCrawlerErrback(unittest.TestCase):
    def test_crawler_with_deferred(self):
        class CustomCrawler(Crawler):
            def __init__(self, spidercls, *args, **kwargs):
                super().__init__(spidercls, *args, **kwargs)

            def start(self):
                # Simulate processing and return a Deferred with an error
                deferred = Deferred()
                deferred.errback(ValueError("Simulated Error"))
                return deferred

        def handle_error(failure):
            # Handle the error within the errback
            logging.error(f"Error occurred during crawling: {failure.getErrorMessage()}")

        process = CrawlerProcess()

        # Create an instance of CustomCrawler with a dummy spider class
        crawler = CustomCrawler(MyTestSpider)

        # Add an errback to handle exceptions raised during the crawl process
        deferred = crawler.start()
        deferred.addErrback(handle_error)

        # Run the process
        process.crawl(MyTestSpider)
        process.start()

if __name__ == '__main__':
    unittest.main()