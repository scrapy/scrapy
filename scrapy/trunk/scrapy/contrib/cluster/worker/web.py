import os
import datetime

from pydispatch import dispatcher

from scrapy.spider import spiders
from scrapy.management.web import banner, webconsole_discover_module
from scrapy.utils.serialization import serialize
from scrapy.contrib.cluster.worker import ClusterWorker

class ClusterWorkerWeb(ClusterWorker):
    webconsole_id = 'cluster_worker'
    webconsole_name = 'Cluster worker'

    def __init__(self):
        ClusterWorker.__init__(self)

        dispatcher.connect(self.webconsole_discover_module, signal=webconsole_discover_module)

    def webconsole_render(self, wc_request):
        changes = ""
        if wc_request.path == '/cluster_worker/ws/':
            return self.webconsole_control(wc_request, ws=True)
        elif wc_request.args:
            changes = self.webconsole_control(wc_request)

        now = datetime.datetime.utcnow()

        s = banner(self)

        # running processes
        s += "<h2>Running processes</h2>\n"
        if self.running:
            s += "<form method='post' action='.'>\n"
            s += "<table border='1'>\n"
            s += "<tr><th>&nbsp;</th><th>PID</th><th>Domain</th><th>Status</th><th>Log file</th><th>Running time</th></tr>\n"
            for domain, proc in self.running.iteritems():
                chkbox = "<input type='checkbox' name='stop' value='%s' />" % domain if proc.status == "running" else "&nbsp;"
                elapsed = now - proc.start_time
                s += "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>\n" % \
                     (chkbox, proc.pid, domain, proc.status, proc.logfile, elapsed)
            s += "</table>\n"
            s += "<p><input type='submit' value='Stop selected domains'></p>\n"
            s += "</form>\n"
        else:
            s += "<p>No running processes</p>\n"

        # pending domains
        s += "<h2>Pending domains</h2>\n"
        if self.pending:
            s += "<form method='post' action='.'>\n"
            s += "<select name='remove' multiple='multiple' size='10'>\n"
            for domain in self.pending:
                s += "<option>%s</option>\n" % domain
            s += "</select>\n"
            s += "<p><input type='submit' value='Remove selected pending domains'></p>\n"
            s += "</form>\n"
        else:
            s += "<p>No pending domains</p>\n"

        # schedule domains
        enabled_domains = spiders.asdict(include_disabled=False).keys()
        s += "<h2>Schedule domains</h2>\n"
        s += "<form method='post' action='.'>\n"
        s += "<select name='schedule' multiple='multiple' size='10'>\n"
        for domain in sorted(enabled_domains):
            s += "<option>%s</option>\n" % domain
        s += "</select>\n"
        s += "<p><input type='submit' value='Schedule selected domains'></p>\n"
        s += "</form>\n"

        s += changes

        s += "</body>\n"
        s += "</html>\n"

        return s

    def webconsole_control(self, wc_request, ws=False):
        args = wc_request.args

        if "schedule" in args:
            for domain in args["schedule"]:
                self.schedule(domain)
            if ws:
                return self.ws_status(wc_request)
            else:
                return "<p>Scheduled domains: <ul><li>%s</li></ul>" % "</li><li>".join(args["schedule"]) + "</p>\n"

        if "stop" in args:
            for domain in args["stop"]:
                self.stop(domain)
            if ws:
                return self.ws_status(wc_request)
            else:
                return "<p>Stopped running processes: <ul><li>%s</li></ul>" % "</li><li>".join(args["stop"]) + "</p>\n"

        if "remove" in args:
            for domain in args["remove"]:
                self.remove(domain)
            if ws:
                return self.ws_status(wc_request)
            else:
                return "<p>Removed pending domains: <ul><li>%s</li></ul>" % "</li><li>".join(args["remove"]) + "</p>\n"
        
        if ws:
            return self.ws_status(wc_request)
        else:
            return ""

    def ws_status(self, wc_request):
        format = wc_request.args['format'][0] if 'format' in wc_request.args else 'json'
        wc_request.setHeader('content-type', 'text/plain')
        exported_proc_attrs = ['pid', 'status', 'start_time', 'logfile']
        d = {'maxproc': self.maxproc, 'running': {}, 'pending': []}
        for domain, proc in self.running.iteritems():
            d2 = {}
            for a in exported_proc_attrs:
                d2[a] = getattr(proc, a)
            d['running'][domain] = d2
        d['pending'] = self.pending
        d['loadavg'] = os.getloadavg()
        content = serialize(d, format)
        return content

    def webconsole_discover_module(self):
        return self
