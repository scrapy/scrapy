import unittest
from scrapy.crawler import Crawler, CrawlerProcess
from twisted.internet.defer import Deferred
from scrapy.spiders import Spider
import logging

class MyTestSpider(Spider):
    name = "mytestspider"
    start_urls = ['http://example.com']

class TestCrawlerErrbackLogging(unittest.TestCase):
    def test_errback_logging(self):
        class CustomCrawler(Crawler):
            def __init__(self, spidercls, *args, **kwargs):
                super().__init__(spidercls, *args, **kwargs)

            def start(self):
                # Simulate processing and return a Deferred with an error
                deferred = Deferred()
                deferred.errback(ValueError("Simulated Error"))
                return deferred

        def handle_error(failure):
            # Handle the error within the errback and log it
            logger.error(f"Error occurred during crawling: {failure.getErrorMessage()}")

        process = CrawlerProcess()

        # Set up logging to capture log messages
        logging.basicConfig(level=logging.DEBUG)
        logger = logging.getLogger('TestCrawlerErrbackLogging')

        # Create an instance of CustomCrawler with a dummy spider class
        crawler = CustomCrawler(MyTestSpider)

        # Add an errback to handle exceptions raised during the crawl process
        deferred = crawler.start()
        deferred.addErrback(handle_error)

        # Run the process
        process.crawl(MyTestSpider)
        process.start()

        # Check if the error message was logged
        logs = [record.getMessage() for record in logger.handlers[0].records if record.levelname == 'ERROR']
        self.assertIn("Error occurred during crawling", logs)

if __name__ == '__main__':
    unittest.main()
