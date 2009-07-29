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
        self.running = set()
        self.finished = set()
        dispatcher.connect(self.domain_open, signal=signals.domain_open)
        dispatcher.connect(self.domain_closed, signal=signals.domain_closed)

        from scrapy.management.web import webconsole_discover_module
        dispatcher.connect(self.webconsole_discover_module, signal=webconsole_discover_module)

    def domain_open(self, domain, spider):
        self.running.add(domain)

    def domain_closed(self, domain, spider):
        self.running.remove(domain)
        self.finished.add(domain)

    def webconsole_render(self, wc_request):
        if wc_request.args:
            changes = self.webconsole_control(wc_request)

        enabled_domains = spiders.asdict().keys()
        self.scheduled = scrapyengine.domain_scheduler.pending_domains
        self.idle = [d for d in enabled_domains if d not in self.scheduled
                                                        and d not in self.running
                                                        and d not in self.finished]

        s = banner(self)
        s += '<table border=1">\n'
        s += "<tr><th>Running (%d/%d)</th><th>Scheduled (%d)</th><th>Finished (%d)</th><th>Idle (%d)</th></tr>\n" % \
                (len(self.running),
                 settings['CONCURRENT_DOMAINS'],
                 len(self.scheduled),
                 len(self.finished),
                 len(self.idle))
        s += "<tr>\n"

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

        s += "</tr>\n"
        s += "<tr>\n"

        s += "<td>&nbsp;</td>\n"

        s += "<td>\n"
        s += '<form method="post" action=".">\n'
        s += "<textarea name='bulk_remove_domains' rows='10' cols='25'></textarea>\n"
        s += '<br>\n'
        s += '<input type="submit" value="Bulk remove domains"><br />\n'
        s += "<span style='font-size: small'>(enter one domain per line)</span>\n"
        s += '</form>\n'
        s += '</td>\n'

        s += "<td>&nbsp;</td>\n"

        s += "<td>\n"
        s += '<form method="post" action=".">\n'
        s += "<textarea name='bulk_schedule_domains' rows='10' cols='25'></textarea>\n"
        s += '<br>\n'
        s += '<input type="submit" value="Bulk schedule domains"><br/>\n'
        s += "<span style='font-size: small'>(enter one domain per line)</span>\n"
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
        enabled_domains = spiders.asdict().keys()
        s = "<hr />\n"

        if "stop_running_domains" in args:
            s += "<p>"
            s += "Stopped spiders: <ul><li>%s</li></ul>" % "</li><li>".join(args["stop_running_domains"])
            for domain in args["stop_running_domains"]:
                scrapyengine.close_domain(domain)
            s += "</p>"
        if "remove_pending_domains" in args:
            removed = []
            for domain in args["remove_pending_domains"]:
                if scrapyengine.domain_scheduler.remove_pending_domain(domain):
                    removed.append(domain)
            if removed:
                s += "<p>"
                s += "Removed scheduled spiders: <ul><li>%s</li></ul>" % "</li><li>".join(args["remove_pending_domains"])
                s += "</p>"
        if "bulk_remove_domains" in args:
            scheduled = []
            to_remove = set([d.strip() for d in args["bulk_remove_domains"][0].split("\n")])
            removed = set([d for d in scrapyengine.scheduler.pending_domains if d in to_remove])
            scrapyengine.scheduler.pending_domains = [d for d in scrapyengine.scheduler.pending_domains if d not in removed]
            if removed:
                s += "<p>"
                s += "Removed: <ul><li>%s</li></ul>" % "</li><li>".join(removed)
                s += "</p>"
                s += "<p>"
                s += "Not removed: <ul><li>%s</li></ul>" % "</li><li>".join(to_remove - removed)
                s += "</p>"
        if "add_pending_domains" in args:
            for domain in args["add_pending_domains"]:
                if domain not in scrapyengine.scheduler.pending_requests:
                    scrapymanager.crawl(domain)
            s += "<p>"
            s += "Scheduled spiders: <ul><li>%s</li></ul>" % "</li><li>".join(args["add_pending_domains"])
            s += "</p>"
        if "bulk_schedule_domains" in args:
            to_schedule = set([d.strip() for d in args["bulk_schedule_domains"][0].split("\n")])
            scheduled = set()
            for domain in to_schedule:
                if domain in enabled_domains and domain not in scrapyengine.scheduler.pending_requests:
                    scrapymanager.crawl(domain)
                    scheduled.add(domain)
            if scheduled:
                s += "<p>"
                s += "Scheduled: <ul><li>%s</li></ul>" % "</li><li>".join(scheduled)
                s += "</p>"
                s += "<p>"
                s += "Not scheduled: <ul><li>%s</li></ul>" % "</li><li>".join(to_schedule - scheduled)
                s += "</p>"
        if "rerun_finished_domains" in args:
            for domain in args["rerun_finished_domains"]:
                if domain not in scrapyengine.scheduler.pending_requests:
                    scrapymanager.crawl(domain)
                self.finished.remove(domain)
            s += "<p>"
            s += "Re-scheduled finished spiders: <ul><li>%s</li></ul>" % "</li><li>".join(args["rerun_finished_domains"])
            s += "</p>"

        return s
        
    def webconsole_discover_module(self):
        return self
