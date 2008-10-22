"""
Scrapy extension for collecting scraping stats
"""
import os
import getpass
import socket
import datetime

from pydispatch import dispatcher

from scrapy.core import signals
from scrapy.stats import stats
from scrapy.conf import settings

class CoreStats(object):
    """Scrapy core stats collector"""

    def __init__(self):
        stats.setpath('_envinfo/user', getpass.getuser())
        stats.setpath('_envinfo/host', socket.gethostname())
        stats.setpath('_envinfo/logfile', settings['LOGFILE'])
        stats.setpath('_envinfo/pid', os.getpid())

        dispatcher.connect(self.stats_domain_open, signal=stats.domain_open)
        dispatcher.connect(self.stats_domain_closing, signal=stats.domain_closing)
        dispatcher.connect(self.item_scraped, signal=signals.item_scraped)
        dispatcher.connect(self.item_passed, signal=signals.item_passed)
        dispatcher.connect(self.item_dropped, signal=signals.item_dropped)
        dispatcher.connect(self.response_downloaded, signal=signals.response_downloaded)
        dispatcher.connect(self.request_uploaded, signal=signals.request_uploaded)

    def stats_domain_open(self, domain, spider):
        stats.setpath('%s/start_time' % domain, datetime.datetime.now())
        stats.setpath('%s/envinfo' % domain, stats.getpath('_envinfo'))
        stats.incpath('_global/domain_count/opened')

    def stats_domain_closing(self, domain, spider, status):
        stats.setpath('%s/finish_time' % domain, datetime.datetime.now())
        stats.setpath('%s/finish_status' % domain, 'OK' if status == 'finished' else status)
        stats.incpath('_global/domain_count/%s' % status)

    def item_scraped(self, item, spider):
        stats.incpath('%s/item_scraped_count' % spider.domain_name)
        stats.incpath('_global/item_scraped_count')

    def item_passed(self, item, spider, pipe_output):
        stats.incpath('%s/item_passed_count' % spider.domain_name)
        stats.incpath('_global/item_passed_count')

    def item_dropped(self, item, spider, exception):
        reason = exception.__class__.__name__
        stats.incpath('%s/item_dropped_count' % spider.domain_name)
        stats.incpath('%s/item_dropped_reasons_count/%s' % (spider.domain_name, reason))
        stats.incpath('_global/item_dropped_count')

    def response_downloaded(self, response, spider):
        stats.incpath('%s/response_count' % spider.domain_name)
        stats.incpath('%s/response_status_count/%s' % (spider.domain_name, response.status))
        stats.incpath('_global/response_downloaded_count')

        reslen = len(response)
        stats.incpath('%s/transfer/downloaded_bytes' % spider.domain_name, reslen)
        stats.incpath('_global/transfer/downloaded_bytes', reslen)

    def request_uploaded(self, request, spider):
        reqlen = len(request)
        stats.incpath('%s/transfer/uploaded_bytes' % spider.domain_name, reqlen)
        stats.incpath('_global/transfer/uploaded_bytes', reqlen)
        
