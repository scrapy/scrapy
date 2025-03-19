import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.reactor import is_asyncio_reactor_installed


class ReactorCheckExtension:
    def __init__(self):
        if not is_asyncio_reactor_installed():
            raise RuntimeError("ReactorCheckExtension requires the asyncio reactor.")


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


process = CrawlerProcess(
    settings={
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "EXTENSIONS": {ReactorCheckExtension: 0},
    }
)
process.crawl(NoRequestsSpider)
process.start()
