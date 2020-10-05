"""
Check settings extension

See documentation in docs/topics/extensions.rst
"""
import logging
import pprint
import operator

from fuzzywuzzy.fuzz import ratio
from scrapy import signals
from scrapy.exceptions import NotConfigured

logger = logging.getLogger(__name__)


class CheckSettings:
    def __init__(self, crawler):
        self.settings = crawler.settings
        self.check_settings_min = crawler.settings.getint("CHECK_SETTINGS_MIN")
        self.not_used_settings = [s for s in self.settings
                                  if not self.settings.attributes[s].hit]
        self.suggestions = self.get_suggestions()

    def get_suggestions(self):
        similar = {}
        setting_keys = list(self.settings.attributes.keys())
        for not_used in self.not_used_settings:
            most_similar = max(((idx, ratio(valid, not_used)) for idx, valid in
                                enumerate(setting_keys)
                                if valid not in self.not_used_settings),
                               key=operator.itemgetter(1))

            if self.check_settings_min <= most_similar[1]:
                similar[not_used] = setting_keys[most_similar[0]]
        return similar

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool("CHECK_SETTINGS_ENABLED"):
            raise NotConfigured
        ext = cls(crawler)
        crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
        return ext

    def spider_opened(self):
        if self.not_used_settings:
            logger.warning("Not used settings: \n%(not_used)s",
                           {"not_used": pprint.pformat(self.not_used_settings)})
        if self.suggestions:
            suggestion_list = [("%s, did you mean %s ?" % (key, value))
                               for key, value in self.suggestions.items()]
            logger.info("Settings suggestions: \n%(suggestion)s",
                        {"suggestion": pprint.pformat(suggestion_list)})
