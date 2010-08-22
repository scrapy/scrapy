from scrapy.crawler import Crawler
from scrapy.extension import ExtensionManager
from scrapy.utils.misc import load_object
from scrapy.conf import settings

_spiders = load_object(settings['SPIDER_MANAGER_CLASS'])()
_extensions = ExtensionManager()
crawler = Crawler(_spiders, _extensions)
