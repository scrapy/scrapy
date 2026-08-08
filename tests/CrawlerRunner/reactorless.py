from scrapy.crawler import CrawlerRunner

CrawlerRunner(settings={"TWISTED_REACTOR_ENABLED": False})
