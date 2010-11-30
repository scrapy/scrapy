from datetime import datetime

from twisted.web import resource, static
from twisted.application.service import IServiceCollection
from .interfaces import IPoller, IEggStorage, ISpiderScheduler

from . import webservice

class Root(resource.Resource):

    def __init__(self, config, app):
        resource.Resource.__init__(self)
        self.debug = config.getboolean('debug', False)
        self.eggrunner = config.get('egg_runner')
        logsdir = config.get('logs_dir')
        self.app = app
        self.putChild('', Home())
        self.putChild('schedule.json', webservice.Schedule(self))
        self.putChild('addversion.json', webservice.AddVersion(self))
        self.putChild('listprojects.json', webservice.ListProjects(self))
        self.putChild('listversions.json', webservice.ListVersions(self))
        self.putChild('listspiders.json', webservice.ListSpiders(self))
        self.putChild('delproject.json', webservice.DeleteProject(self))
        self.putChild('delversion.json', webservice.DeleteVersion(self))
        self.putChild('logs', static.File(logsdir, 'text/plain'))
        self.putChild('procmon', ProcessMonitor(self))
        self.update_projects()

    def update_projects(self):
        self.poller.update_projects()
        self.scheduler.update_projects()

    @property
    def launcher(self):
        app = IServiceCollection(self.app, self.app)
        return app.getServiceNamed('launcher')

    @property
    def scheduler(self):
        return self.app.getComponent(ISpiderScheduler)

    @property
    def eggstorage(self):
        return self.app.getComponent(IEggStorage)

    @property
    def poller(self):
        return self.app.getComponent(IPoller)


class Home(resource.Resource):

    def render_GET(self, txrequest):
        return """
<html>
<head><title>Scrapyd</title></head>
<body>
<h1>Scrapyd</h1>
<ul>
<li><a href="/procmon">Process monitor</a></li>
<li><a href="/logs/">Logs</li>
<li><a href="http://doc.scrapy.org/topics/scrapyd.html">Documentation</a></li>
</ul>
</body>
</html>
"""


class ProcessMonitor(resource.Resource):

    def __init__(self, root):
        resource.Resource.__init__(self)
        self.root = root

    def render(self, txrequest):
        s = "<html><head><title>Scrapyd</title></title>"
        s += "<body>"
        s += "<h1>Process monitor</h1>"
        s += "<p><a href='..'>Go back</a></p>"
        s += "<table border='1'>"
        s += "<tr>"
        s += "<th>Project</th><th>Spider</th><th>Job</th><th>PID</th><th>Runtime</th><th>Log</th>"
        s += "</tr>"
        for p in self.root.launcher.processes.values():
            s += "<tr>"
            for a in ['project', 'spider', 'job', 'pid']:
                s += "<td>%s</td>" % getattr(p, a)
            s += "<td>%s</td>" % (datetime.now() - p.start_time)
            s += "<td><a href='/logs/%s/%s/%s.log'>Log</a></td>" % (p.project, p.spider, p.job)
            s += "</tr>"
        s += "</table>"
        s += "</body>"
        s += "</html>"
        return s

