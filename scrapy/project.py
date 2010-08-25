from scrapy.crawler import CrawlerProcess
from scrapy.utils.misc import load_object
from scrapy.conf import settings

_spiders = load_object(settings['SPIDER_MANAGER_CLASS'])()
crawler = CrawlerProcess(settings, _spiders)
