import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.asyncio import is_asyncio_available
from scrapy.utils.reactor import (
    install_reactor,
    is_asyncio_reactor_installed,
    is_reactor_installed,
)

if is_reactor_installed():
    raise RuntimeError(
        "Reactor already installed before is_asyncio_reactor_installed()."
    )

try:
    is_asyncio_reactor_installed()
except RuntimeError:
    pass
else:
    raise RuntimeError("is_asyncio_reactor_installed() did not raise RuntimeError.")

try:
    is_asyncio_available()
except RuntimeError:
    pass
else:
    raise RuntimeError("is_asyncio_available() did not raise RuntimeError.")

if is_reactor_installed():
    raise RuntimeError(
        "Reactor already installed after is_asyncio_reactor_installed()."
    )

install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")

if not is_asyncio_reactor_installed():
    raise RuntimeError("Wrong reactor installed after install_reactor().")


class ReactorCheckExtension:
    def __init__(self):
        if not is_asyncio_reactor_installed():
            raise RuntimeError("ReactorCheckExtension requires the asyncio reactor.")
        if not is_asyncio_available():
            raise RuntimeError("ReactorCheckExtension requires asyncio support.")


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
