"""
Extension for persistent statistics by domain
"""
import re
import pprint

from pydispatch import dispatcher

from scrapy.spider import spiders
from scrapy.core.exceptions import NotConfigured
from scrapy.management.web import banner
from scrapy.conf import settings

class SpiderStats(object):
    webconsole_id = 'spiderstats'
    webconsole_name = 'Spider stats (all-time)'

    stats_mainpage = [
        ('item_scraped_count', "Items scraped <br>(last run)"),
        ('item_passed_count', "Items passed <br>(last run)"),
        ('response_count', "Pages crawled <br>(last run)"),
        ('start_time', "Start time <br>(last run)"),
        ('finish_time', "Finish time <br>(last run)"),
        ('finish_status', "Finish status<br>(last run)"),
        ]

    PATH_RE = re.compile("/spiderstats/([^/]+)")
    
    def __init__(self):
        if not settings['SCRAPING_DB']:
            raise NotConfigured("Requires SCRAPING_DB setting")

        from scrapy.store.db import DomainDataHistory
        self.ddh = DomainDataHistory(settings['SCRAPING_DB'], 'domain_data_history')

        from scrapy.management.web import webconsole_discover_module
        dispatcher.connect(self.webconsole_discover_module, signal=webconsole_discover_module)

    def webconsole_render(self, wc_request):
        m = self.PATH_RE.search(wc_request.path)
        if m:
            return self.render_domain(m.group(1))
        else:
            return self.render_main()

    def render_main(self):
        s = banner(self)
        s += "<table border='1'>\n"
        s += "<tr>\n"
        s += "<th>Domain</th>"
        for path, title in self.stats_mainpage:
            s += "<th>%s</th>" % title
        s += "</tr>\n"
        for domain in spiders.asdict().keys():
            s += "<tr>\n"
            s += "<td><a href='%s'>%s</a></td>" % (domain, domain)
            for path, title in self.stats_mainpage:
                stat = self.ddh.getlast(domain, path=path)
                value = stat[1] if stat else "None"
                s += "<td>%s</td>" % value
            s += "</tr>\n"
        s += "</table>\n"
        s += "</body>\n"
        s += "</html>\n"

        return str(s)

    def render_domain(self, domain):
        s = banner(self)
        stats = self.ddh.getall(domain)
        s += "<pre>\n"
        s += pprint.pformat(list(stats))
        s += "</pre>\n"
        s += "</body>\n"
        s += "</html>\n"

        return str(s)
        
    def webconsole_discover_module(self):
        return self
