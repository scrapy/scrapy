from scrapy.conf import settings
from scrapy.utils.misc import load_object
from scrapy.crawler import Crawler

_spiders = load_object(settings['SPIDER_MANAGER_CLASS'])()
crawler = Crawler(_spiders)
