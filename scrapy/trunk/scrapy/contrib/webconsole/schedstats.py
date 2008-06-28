"""
Scheduler information module for Scrapy webconsole
"""
from pydispatch import dispatcher
from scrapy.core import signals
from scrapy.core.engine import scrapyengine
from scrapy.spider import spiders
from scrapy.management.web import banner

class SchedulerStats(object):
    webconsole_id = 'scheduler'
    webconsole_name = 'Scheduler queue'

    def __init__(self):
        from scrapy.management.web import webconsole_discover_module
        dispatcher.connect(self.webconsole_discover_module, signal=webconsole_discover_module)

    def webconsole_render(self, wc_request):
        s = banner(self)
        s += "<ul>\n"
        for domain, requests in scrapyengine.scheduler.pending_requests.iteritems():
            s += "<li>\n"
            s += "%s (<b>%s</b> pages)\n" % (domain, len(requests))
            s += "<ul>\n"
            # requests is a tuple of request and deffered now, as I understand
            for r, d in requests:
                if hasattr(r, 'url'):
                    s += "<li><a href='%s'>%s</a></li>\n" % (r.url, r.url)
                #else:
                #    s += "<li>%s</li>\n" % (repr(r))
            s += "</ul>\n"
            s += "</li>\n" 
        s += "</ul>\n"

        s += "</body>\n"
        s += "</html>\n"

        return s

    def webconsole_discover_module(self):
        return self
