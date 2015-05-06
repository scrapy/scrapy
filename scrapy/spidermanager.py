"""
Backwards compatibility shim. Use scrapy.spiderloader instead.
"""
from scrapy.spiderloader import SpiderLoader
from scrapy.utils.deprecate import create_deprecated_class

SpiderManager = create_deprecated_class('SpiderManager', SpiderLoader)
