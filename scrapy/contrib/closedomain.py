"""
CloseDomain is an extension that forces spiders to be closed after a given
time has expired.

"""
import datetime
import pprint

from pydispatch import dispatcher

from scrapy.core import signals
from scrapy import log
from scrapy.core.engine import scrapyengine
from scrapy.core.exceptions import NotConfigured
from scrapy.mail import MailSender
from scrapy.stats import stats
from scrapy.conf import settings

class CloseDomain(object):
    def __init__(self):
        self.timeout = settings.getint('CLOSEDOMAIN_TIMEOUT')
        if not self.timeout:
            raise NotConfigured

        self.tasks = {}
        self.mail = MailSender()
        self.notify = settings.getlist('CLOSEDOMAIN_NOTIFY')

        dispatcher.connect(self.domain_opened, signal=signals.domain_opened)
        dispatcher.connect(self.domain_closed, signal=signals.domain_closed)

    def domain_opened(self, domain):
        self.tasks[domain] = scrapyengine.addtask(self.close_domain, self.timeout, args=[domain])
        
    def close_domain(self, domain): 
        log.msg("Domain was opened for more than %d seconds, closing it..." % self.timeout, domain=domain)
        scrapyengine.close_domain(domain)
        if self.notify:
            body = "Closed domain %s because it remained opened for more than %s\n\n" % (domain, datetime.timedelta(seconds=self.timeout))
            body += "DOMAIN STATS ------------------------------------------------------\n\n"
            body += pprint.pformat(stats.get(domain, None))
            subj = "Closed domain by timeout: %s" % domain
            self.mail.send(self.notify, subj, body)

    def domain_closed(self, domain):
        if domain in self.tasks:
            scrapyengine.removetask(self.tasks[domain])
