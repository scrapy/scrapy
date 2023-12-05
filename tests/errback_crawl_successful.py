import unittest
from scrapy.crawler import Crawler, CrawlerProcess
from twisted.internet.defer import Deferred
from scrapy.spiders import Spider
import logging

class MyTestSpider(Spider):
    name = "mytestspider"
    start_urls = ['http://example.com']

class TestCrawlerCompletion(unittest.TestCase):
    def test_crawler_completion_without_errors(self):
        class CustomCrawler(Crawler):
            def __init__(self, spidercls, *args, **kwargs):
                super().__init__(spidercls, *args, **kwargs)

            def start(self):
                # Simulate processing and return a successful Deferred
                deferred = Deferred()
                deferred.callback("Crawling process completed successfully")
                return deferred

        def handle_result(result):
            # Handle the successful crawling result
            logging.info(f"Crawling process result: {result}")

        process = CrawlerProcess()

        # Create an instance of CustomCrawler with a dummy spider class
        crawler = CustomCrawler(MyTestSpider)

        # Add a callback to handle the successful crawling result
        deferred = crawler.start()
        deferred.addCallback(handle_result)

        # Run the process
        process.crawl(MyTestSpider)
        process.start()

if __name__ == '__main__':
    unittest.main()