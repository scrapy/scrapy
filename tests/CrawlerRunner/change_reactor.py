from scrapy import Spider
from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging


class NoRequestsSpider(Spider):
    name = "no_request"

    custom_settings = {
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    }

    def start_requests(self):
        return []


configure_logging({"LOG_FORMAT": "%(levelname)s: %(message)s", "LOG_LEVEL": "DEBUG"})


from scrapy.utils.reactor import install_reactor

install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")

runner = CrawlerRunner()

d = runner.crawl(NoRequestsSpider)

from twisted.internet import reactor

d.addBoth(callback=lambda _: reactor.stop())
reactor.run()
