from scrapy.crawler import AsyncCrawlerProcess
from scrapy.utils.reactor import install_reactor

install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")

AsyncCrawlerProcess(settings={"TWISTED_ENABLED": False})
