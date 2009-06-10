import time

from scrapy.core.exceptions import NotConfigured
from scrapy.store.db import DomainDataHistory
from scrapy.conf import settings

class LessScrapedPrioritizer(object):
    """
    A spider prioritizer based on these few simple rules:
    1. if spider was never scraped, it has top priority
    2. if spider was scraped before, then the less recently the spider
       has been scraped, the more priority it has
    """
    def __init__(self):
        # FIXME this prioritizer must be refactored
        raise NotImplemented

        if not settings['SCRAPING_DB']:
            raise NotConfigured("SCRAPING_DB setting is required")

        self.ddh = DomainDataHistory(settings['SCRAPING_DB'], 'domain_data_history')
        domains_to_scrape = set(elements)

        self.priorities = {}
        
        for domain in domains_to_scrape:
            stat = self.ddh.getlast(domain, path="start_time")
            if stat and stat[1]:
                last_started = stat[1]
                # spider is the timestamp of last start time
                self.priorities[domain] = time.mktime(last_started.timetuple())  
            else:
                # if domain was never scraped, it has top priority
                self.priorities[domain] = 1

    def get_priority(self, element):
        return self.priorities[element]
