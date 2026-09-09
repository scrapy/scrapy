from scrapy.crawler import AsyncCrawlerProcess
from scrapy.utils.reactor import install_reactor

install_reactor()

AsyncCrawlerProcess(settings={"TWISTED_REACTOR_ENABLED": False})
