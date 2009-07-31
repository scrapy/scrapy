"""
StatsMailer extension sends an email when a domain finishes scraping.

Use STATSMAILER_RCPTS setting to enable and give the recipient mail address
"""

from scrapy.xlib.pydispatch import dispatcher

from scrapy.stats import stats, signals
from scrapy.mail import MailSender
from scrapy.conf import settings
from scrapy.core.exceptions import NotConfigured

class StatsMailer(object):

    def __init__(self):
        self.recipients = settings.getlist("STATSMAILER_RCPTS")
        if not self.recipients:
            raise NotConfigured
        dispatcher.connect(self.stats_domain_closed, signal=signals.stats_domain_closed)
        
    def stats_domain_closed(self, domain, domain_stats):
        mail = MailSender()
        body = "Global stats\n\n"
        body += "\n".join("%-50s : %s" % i for i in stats.get_stats().items())
        body += "\n\n%s stats\n\n" % domain
        body += "\n".join("%-50s : %s" % i for i in domain_stats.items())
        mail.send(self.recipients, "Scrapy stats for: %s" % domain, body)
