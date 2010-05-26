"""
Extensions for allowing spider control from web console
"""

from scrapy.xlib.pydispatch import dispatcher

from scrapy.core import signals
from scrapy.core.manager import scrapymanager
from scrapy.core.engine import scrapyengine
from scrapy.spider import spiders
from scrapy.management.web import banner, webconsole_discover_module
from scrapy.conf import settings

class Spiderctl(object):
    webconsole_id = 'spiderctl'
    webconsole_name = 'Spider control panel'

    def __init__(self):
        self.running = {}
        self.finished = set()
        dispatcher.connect(self.spider_opened, signal=signals.spider_opened)
        dispatcher.connect(self.spider_closed, signal=signals.spider_closed)
        dispatcher.connect(self.webconsole_discover_module, signal=webconsole_discover_module)

    def spider_opened(self, spider):
        self.running[spider.name] = spider

    def spider_closed(self, spider):
        del self.running[spider.name]
        self.finished.add(spider.name)

    def webconsole_render(self, wc_request):
        if wc_request.args:
            changes = self.webconsole_control(wc_request)

        self.scheduled = [s[0].name for s in scrapymanager.queue.spider_requests]
        self.idle = [d for d in self.enabled_spiders if d not in self.scheduled
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
        s += '<select name="add_pending_spiders" multiple="multiple">\n'
        for name in sorted(self.idle):
            s += "<option>%s</option>\n" % name
        s += '</select><br>\n'
        s += '<br />'
        s += '<input type="submit" value="Schedule selected">\n'
        s += '</form>\n'
        s += "</td>\n"

        # scheduled
        s += "<td valign='top'>\n"
        s += '<form method="post" action=".">\n'
        s += '<select name="remove_pending_spiders" multiple="multiple">\n'
        for name in self.scheduled:
            s += "<option>%s</option>\n" % name
        s += '</select><br>\n'
        s += '<br />'
        s += '<input type="submit" value="Remove selected">\n'
        s += '</form>\n'

        s += "</td>\n"

        # running
        s += "<td valign='top'>\n"
        s += '<form method="post" action=".">\n'
        s += '<select name="stop_running_spiders" multiple="multiple">\n'
        for name in sorted(self.running):
            s += "<option>%s</option>\n" % name 
        s += '</select><br>\n'
        s += '<br />'
        s += '<input type="submit" value="Stop selected">\n'
        s += '</form>\n'
        s += "</td>\n"

        # finished
        s += "<td valign='top'>\n"
        s += '<form method="post" action=".">\n'
        s += '<select name="rerun_finished_spiders" multiple="multiple">\n'
        for name in sorted(self.finished):
            s += "<option>%s</option>\n" % name
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

        if "stop_running_spiders" in args:
            s += "<p>"
            stopped_spiders = []
            for name in args["stop_running_spiders"]:
                if name in self.running:
                    scrapyengine.close_spider(self.running[name])
                    stopped_spiders.append(name)
            s += "Stopped spiders: <ul><li>%s</li></ul>" % "</li><li>".join(stopped_spiders)
            s += "</p>"
        if "remove_pending_spiders" in args:
            removed = []
            for name in args["remove_pending_spiders"]:
                q = scrapymanager.queue
                q.spider_requests = [x for x in q.spider_requests if x[0].name != name]
            if removed:
                s += "<p>"
                s += "Removed scheduled spiders: <ul><li>%s</li></ul>" % "</li><li>".join(args["remove_pending_spiders"])
                s += "</p>"
        if "add_pending_spiders" in args:
            for name in args["add_pending_spiders"]:
                if name not in scrapyengine.scheduler.pending_requests:
                    scrapymanager.queue.append_spider_name(name)
            s += "<p>"
            s += "Scheduled spiders: <ul><li>%s</li></ul>" % "</li><li>".join(args["add_pending_spiders"])
            s += "</p>"
        if "rerun_finished_spiders" in args:
            for name in args["rerun_finished_spiders"]:
                if name not in scrapyengine.scheduler.pending_requests:
                    scrapymanager.queue.append_spider_name(name)
                self.finished.remove(name)
            s += "<p>"
            s += "Re-scheduled finished spiders: <ul><li>%s</li></ul>" % "</li><li>".join(args["rerun_finished_spiders"])
            s += "</p>"

        return s
        
    def webconsole_discover_module(self):
        self.enabled_spiders = spiders.list()
        return self
