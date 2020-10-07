"""
Check settings extension

See documentation in docs/topics/extensions.rst
"""
import logging
import pprint

from difflib import get_close_matches

from scrapy import signals
from scrapy.exceptions import NotConfigured

logger = logging.getLogger(__name__)


class CheckSettings:
    def __init__(self, crawler):
        self.settings = crawler.settings
        self.not_used_settings = []
        self.sim_min = 0.8

    def get_suggestions(self):
        setting_keys = list(self.settings.attributes.keys() - self.not_used_settings)
        return {
            not_used: match[0]
            for not_used, match in [(
                not_used,
                get_close_matches(not_used, setting_keys, n=1, cutoff=self.sim_min))
                for not_used in self.not_used_settings]
            if match
        }

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool("CHECK_SETTINGS_ENABLED"):
            raise NotConfigured
        ext = cls(crawler)
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        return ext

    def spider_closed(self):
        self.not_used_settings = [s for s in self.settings
                                  if not self.settings.attributes[s].has_been_read]
        suggestions = self.get_suggestions()
        if self.not_used_settings:
            logger.warning("Not used settings: \n%(not_used)s",
                           {"not_used": pprint.pformat(self.not_used_settings)})

        if suggestions:
            suggestion_list = [("%s, did you mean %s ?" % (key, value))
                               for key, value in suggestions.items()]
            logger.info("Settings suggestions: \n%(suggestion)s",
                        {"suggestion": pprint.pformat(suggestion_list)})
