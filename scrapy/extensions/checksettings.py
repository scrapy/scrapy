"""
Check settings extension

See documentation in docs/topics/extensions.rst
"""
import logging
import pprint

from fuzzywuzzy.fuzz import ratio
from scrapy import signals
from scrapy.exceptions import NotConfigured

logger = logging.getLogger(__name__)


class CheckSettings:
    def __init__(self, not_used_settings):
        self.not_used_settings = not_used_settings

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool("CHECK_SETTINGS_ENABLED"):
            raise NotConfigured
        settings = crawler.settings
        not_used_settings = [s  for s in settings if not settings.attributes[s].hit]
        ext = cls(not_used_settings)

        crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)

        return ext

    def spider_opened(self):
        if self.not_used_settings:
            logger.warning("Not used settings: \n%s", pprint.pformat(self.not_used_settings))

