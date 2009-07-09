"""
StatsMailer extension sends an email when a domain finishes scraping.

Use STATSMAILER_RCPTS setting to enable and give the recipient mail address
"""

import pprint

from scrapy.xlib.pydispatch import dispatcher

from scrapy.stats import stats
from scrapy.mail import MailSender
from scrapy.conf import settings
from scrapy.core import signals
from scrapy.core.exceptions import NotConfigured

class StatsMailer(object):

    def __init__(self):
        self.recipients = settings.getlist("STATSMAILER_RCPTS")
        if not self.recipients:
            raise NotConfigured
        dispatcher.connect(self.send_stats, signal=signals.domain_closed)
        
    def send_stats(self, domain):
        mail = MailSender()
        body = pprint.pformat(stats[domain])
        mail.send(self.recipients, "Scrapy stats for: %s" % domain, body)
