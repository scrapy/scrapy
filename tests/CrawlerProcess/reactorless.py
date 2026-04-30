from scrapy.crawler import CrawlerProcess

CrawlerProcess(settings={"TWISTED_REACTOR_ENABLED": False})
