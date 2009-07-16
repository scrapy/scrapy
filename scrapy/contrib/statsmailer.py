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
        dispatcher.connect(self.send_stats, signal=signals.stats_domain_closing)
        
    def send_stats(self, domain):
        mail = MailSender()
        body = "Global stats\n\n"
        body += "\n".join("%-50s : %s" % i for i in stats.get_stats().items())
        body += "\n\n%s stats\n\n" % domain
        body += "\n".join("%-50s : %s" % i for i in stats.get_stats(domain).items())
        mail.send(self.recipients, "Scrapy stats for: %s" % domain, body)
