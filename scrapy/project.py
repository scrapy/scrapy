from scrapy.crawler import Crawler
from scrapy.utils.misc import load_object
from scrapy.conf import settings

_spiders = load_object(settings['SPIDER_MANAGER_CLASS'])()
crawler = Crawler(settings, _spiders)
