from scrapy.spider.models import BaseSpider
from scrapy.utils.misc import load_object
from scrapy.conf import settings

spiders = load_object(settings['SPIDER_MANAGER_CLASS'])()
