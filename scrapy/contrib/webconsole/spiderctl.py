"""
Extensions for allowing spider control from web console
"""

from scrapy.xlib.pydispatch import dispatcher

from scrapy.core import signals
from scrapy.core.manager import scrapymanager
from scrapy.core.engine import scrapyengine
from scrapy.spider import spiders
from scrapy.management.web import banner
from scrapy.conf import settings

class Spiderctl(object):
    webconsole_id = 'spiderctl'
    webconsole_name = 'Spider control panel'

    def __init__(self):
        self.running = {}
        self.finished = set()
        dispatcher.connect(self.spider_opened, signal=signals.spider_opened)
        dispatcher.connect(self.spider_closed, signal=signals.spider_closed)

        from scrapy.management.web import webconsole_discover_module
        dispatcher.connect(self.webconsole_discover_module, signal=webconsole_discover_module)

    def spider_opened(self, spider):
        self.running[spider.domain_name] = spider

    def spider_closed(self, spider):
        del self.running[spider.domain_name]
        self.finished.add(spider.domain_name)

    def webconsole_render(self, wc_request):
        if wc_request.args:
            changes = self.webconsole_control(wc_request)

        self.scheduled = [s.domain_name for s in scrapyengine.spider_scheduler._pending_spiders]
        self.idle = [d for d in self.enabled_domains if d not in self.scheduled
                                                        and d not in self.running
                                                        and d not in self.finished]

        s = banner(self)
        s += '<table border=1">\n'
        s += "<tr><th>Idle (%d)</th><th>Scheduled (%d)</th><th>Running (%d/%d)</th><th>Finished (%d)</th></tr>\n" % \
                (len(self.idle),
                 len(self.scheduled),
                 len(self.running),
                 settings['CONCURRENT_SPIDERS'],
                 len(self.finished))
        s += "<tr>\n"

        # idle
        s += "<td valign='top'>\n"
        s += '<form method="post" action=".">\n'
        s += '<select name="add_pending_domains" multiple="multiple">\n'
        for domain in sorted(self.idle):
            s += "<option>%s</option>\n" % domain
        s += '</select><br>\n'
        s += '<br />'
        s += '<input type="submit" value="Schedule selected">\n'
        s += '</form>\n'
        s += "</td>\n"

        # scheduled
        s += "<td valign='top'>\n"
        s += '<form method="post" action=".">\n'
        s += '<select name="remove_pending_domains" multiple="multiple">\n'
        for domain in self.scheduled:
            s += "<option>%s</option>\n" % domain
        s += '</select><br>\n'
        s += '<br />'
        s += '<input type="submit" value="Remove selected">\n'
        s += '</form>\n'

        s += "</td>\n"

        # running
        s += "<td valign='top'>\n"
        s += '<form method="post" action=".">\n'
        s += '<select name="stop_running_domains" multiple="multiple">\n'
        for domain in sorted(self.running):
            s += "<option>%s</option>\n" % domain
        s += '</select><br>\n'
        s += '<br />'
        s += '<input type="submit" value="Stop selected">\n'
        s += '</form>\n'
        s += "</td>\n"

        # finished
        s += "<td valign='top'>\n"
        s += '<form method="post" action=".">\n'
        s += '<select name="rerun_finished_domains" multiple="multiple">\n'
        for domain in sorted(self.finished):
            s += "<option>%s</option>\n" % domain
        s += '</select><br>\n'
        s += '<br />'
        s += '<input type="submit" value="Re-schedule selected">\n'
        s += '</form>\n'
        s += "</td>\n"

        s += "</tr>\n"
        s += "</table>\n"

        if wc_request.args:
            s += changes

        s += "</body>\n"
        s += "</html>\n"

        return s

    def webconsole_control(self, wc_request):
        args = wc_request.args
        s = "<hr />\n"

        if "stop_running_domains" in args:
            s += "<p>"
            stopped_domains = []
            for domain in args["stop_running_domains"]:
                if domain in self.running:
                    scrapyengine.close_spider(self.running[domain])
                    stopped_domains.append(domain)
            s += "Stopped spiders: <ul><li>%s</li></ul>" % "</li><li>".join(stopped_domains)
            s += "</p>"
        if "remove_pending_domains" in args:
            removed = []
            for domain in args["remove_pending_domains"]:
                if scrapyengine.spider_scheduler.remove_pending_domain(domain):
                    removed.append(domain)
            if removed:
                s += "<p>"
                s += "Removed scheduled spiders: <ul><li>%s</li></ul>" % "</li><li>".join(args["remove_pending_domains"])
                s += "</p>"
        if "add_pending_domains" in args:
            for domain in args["add_pending_domains"]:
                if domain not in scrapyengine.scheduler.pending_requests:
                    scrapymanager.crawl_domain(domain)
            s += "<p>"
            s += "Scheduled spiders: <ul><li>%s</li></ul>" % "</li><li>".join(args["add_pending_domains"])
            s += "</p>"
        if "rerun_finished_domains" in args:
            for domain in args["rerun_finished_domains"]:
                if domain not in scrapyengine.scheduler.pending_requests:
                    scrapymanager.crawl_domain(domain)
                self.finished.remove(domain)
            s += "<p>"
            s += "Re-scheduled finished spiders: <ul><li>%s</li></ul>" % "</li><li>".join(args["rerun_finished_domains"])
            s += "</p>"

        return s
        
    def webconsole_discover_module(self):
        self.enabled_domains = spiders.list()
        return self
