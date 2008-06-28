import datetime

from pydispatch import dispatcher

from scrapy.spider import spiders 
from scrapy.management.web import banner, webconsole_discover_module
from scrapy.utils.serialization import parse_jsondatetime
from scrapy.contrib.cluster.master import ClusterMaster

class ClusterMasterWeb(ClusterMaster):
    webconsole_id = 'cluster_master'
    webconsole_name = 'Cluster master'

    def __init__(self):
        ClusterMaster.__init__(self)

        dispatcher.connect(self.webconsole_discover_module, signal=webconsole_discover_module)

    def webconsole_render(self, wc_request):
        changes = ""
        if wc_request.path == '/cluster/nodes/':
            return self.render_nodes(wc_request)
        elif wc_request.path == '/cluster/domains/':
            return self.render_domains(wc_request)
        elif wc_request.args:
            changes = self.webconsole_control(wc_request)

        s = self.render_header()

        s += "<h2>Home</h2>\n"

        s += "<table border='1'>\n"
        s += "<tr><th>&nbsp;</th><th>Name</th><th>Status</th><th>Running</th><th>Pending</th><th>Load.avg</th></tr>\n"
        for node in self.nodes.itervalues():
            #chkbox = "<input type='checkbox' name='shutdown' value='%s' />" % domain if node.status in ["up", "idle"] else "&nbsp;"
            nodelink = "<a href='nodes/#%s'>%s</a>" % (node.name, node.name)
            chkbox = "&nbsp;"
            loadavg = "%.2f %.2f %.2f" % node.loadavg
            s += "<tr><td>%s</td><td>%s</td><td>%s</td><td>%d/%d</td><td>%d</td><td>%s</td></tr>\n" % \
                 (chkbox, nodelink, node.status, len(node.running), node.maxproc, len(node.pending), loadavg)
        s += "</table>\n"

        s += "</body>\n"
        s += "</html>\n"

        return str(s)

    def webconsole_control(self, wc_request):
        args = wc_request.args

        if "updatenodes" in args:
            self.update_nodes()

        if "schedule" in args:
            node = args["node"][0] if "node" in args else None
            self.schedule(args["schedule"], nodename=node)

        if "stop" in args:
            self.stop(args["stop"])

        if "remove" in args:
            self.remove(args["remove"])

        return ""

    def render_nodes(self, wc_request):
        if wc_request.args:
            self.webconsole_control(wc_request)

        now = datetime.datetime.utcnow()

        s = self.render_header()
        for node in self.nodes.itervalues():
            s += "<h2><a name='%s'>%s</h2>\n" % (node.name, node.name)

            s += "<h3>Running domains</h3>\n"
            if node.running:
                s += "<form method='post' action='.'>\n"
                s += "<table border='1'>\n"
                s += "<tr><th>&nbsp;</th><th>PID</th><th>Domain</th><th>Status</th><th>Running time</th><th>Log file</th></tr>\n"
                for domain, proc in node.running.iteritems():
                    chkbox = "<input type='checkbox' name='stop' value='%s' />" % domain if proc['status'] == "running" else "&nbsp;"
                    start_time = parse_jsondatetime(proc.get('start_time', None))
                    elapsed = now - start_time if start_time else None
                    s += "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>\n" % \
                         (chkbox, proc['pid'], domain, proc['status'], elapsed, proc['logfile'])
                s += "</table>\n"
                s += "<input type='hidden' name='node' value='%s'>\n" % node.name
                s += "<p><input type='submit' value='Stop selected domains on %s'></p>\n" % node.name
                s += "</form>\n"
            else:
                s += "<p>No running domains on %s</p>\n" % node.name

            # pending domains
            s += "<h3>Pending domains</h3>\n"
            if node.pending:
                s += "<form method='post' action='.'>\n"
                s += "<select name='remove' multiple='multiple' size='10'>\n"
                for domain in node.pending:
                    s += "<option>%s</option>\n" % domain
                s += "</select>\n"
                s += "<input type='hidden' name='node' value='%s'>\n" % node.name
                s += "<p><input type='submit' value='Remove selected pending domains on %s'></p>\n" % node.name
                s += "</form>\n"
            else:
                s += "<p>No pending domains on %s</p>\n" % node.name

        return str(s)

    def render_domains(self, wc_request):
        if wc_request.args:
            self.webconsole_control(wc_request)

        enabled_domains = set(spiders.asdict(include_disabled=False).keys())
        inactive_domains = enabled_domains - set(self.running.keys() + self.pending.keys())

        s = self.render_header()

        s += "<h2>Schedule domains</h2>\n"

        s += "Inactive domains (not running or pending)<br />"
        s += "<form method='post' action='.'>\n"
        s += "<select name='schedule' multiple='multiple' size='10'>\n"
        for domain in sorted(inactive_domains):
            s += "<option>%s</option>\n" % domain
        s += "</select>\n"
        s += "</br>\n"
        s += "Node (only available nodes shown):<br />\n"
        s += "<select name='node'>\n"
        s += "<option value='' selected='selected'>any</option>"
        for node in self.available_nodes:
            domcount = "%d/%d/%d" % (len(node.running), node.maxproc, len(node.pending))
            loadavg = "%.2f %.2f %.2f" % node.loadavg
            s += "<option value='%s'>%s [D: %s | LA: %s]</option>" % (node.name, node.name, domcount, loadavg)
        s += "</select>\n"
        s += "<p><input type='submit' value='Schedule selected domains'></p>\n"
        s += "</form>\n"

        s += "<h2>Domains</h2>\n"

        s += "<table border='1'>\n"
        s += "<tr><th>Domain</th><th>Status</th><th>Node</th></tr>\n"
        s += self._domains_table(self.running, '<b>running</b>')
        s += self._domains_table(self.pending, 'pending')
        s += "</table>\n"

        return str(s)

    def render_header(self):
        s = banner(self)
        s += "<p>Nav: "
        s += "<a href='/cluster/'>Home</a> | "
        s += "<a href='/cluster/domains/'>Domains</a> | "
        s += "<a href='/cluster/nodes/'>Nodes</a> (<a href='/cluster/nodes/?updatenodes=1'>update</a>)"
        s += "</p>"
        return s

    def _domains_table(self, dict_, status):
        s = ""
        for domain, node in dict_.iteritems():
            s += "<tr><td>%s</td><td>%s</td><td>%s</td></tr>\n" % (domain, status, node.name)
        return s

    def webconsole_discover_module(self):
        return self
