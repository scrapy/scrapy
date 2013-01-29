import posixpath
from datetime import datetime

from jinja2 import Template

from twisted.web import resource, static
from twisted.application.service import IServiceCollection

from scrapy.utils.misc import load_object

from .interfaces import IPoller, IEggStorage, ISpiderScheduler

class Root(resource.Resource):

    def __init__(self, config, app):
        resource.Resource.__init__(self)
        self.debug = config.getboolean('debug', False)
        self.runner = config.get('runner')

        self.htdocsdir = posixpath.join(posixpath.split(__file__)[0], "htdocs")

        logsdir = config.get('logs_dir')
        itemsdir = config.get('items_dir')
        
        self.app = app
        self.putChild('', Home(self))
        self.putChild('old', OldHome(self))

        self.putChild('logs', static.File(logsdir, 'text/plain'))
        self.putChild('items', static.File(itemsdir, 'text/plain'))
        self.putChild('jobs', Jobs(self))

        for path in ['css', 'js', 'img']:
            fullpath = posixpath.join(self.htdocsdir, path)
            self.putChild(path, static.File(fullpath))

        services = config.items('services', ())
        for servName, servClsName in services:
          servCls = load_object(servClsName)
          self.putChild(servName, servCls(self))
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


class OldHome(resource.Resource):
    def __init__(self, root):
        resource.Resource.__init__(self)
        self.root = root

    def render_GET(self, txrequest):
        vars = {
            'projects': ', '.join(self.root.scheduler.list_projects()),
        }
        return """
<html>
<head><title>Scrapyd</title></head>
<body>
<a href="/">New Front-End</a>
<h1>Scrapyd</h1>
<p>Available projects: <b>%(projects)s</b></p>
<ul>
<li><a href="/jobs">Jobs</a></li>
<li><a href="/items/">Items</li>
<li><a href="/logs/">Logs</li>
<li><a href="http://doc.scrapy.org/en/latest/topics/scrapyd.html">Documentation</a></li>
</ul>

<h2>How to schedule a spider?</h2>

<p>To schedule a spider you need to use the API (this web UI is only for
monitoring)</p>

<p>Example using <a href="http://curl.haxx.se/">curl</a>:</p>
<p><code>curl http://localhost:6800/schedule.json -d project=default -d spider=somespider</code></p>

<p>For more information about the API, see the <a href="http://doc.scrapy.org/en/latest/topics/scrapyd.html">Scrapyd documentation</a></p>
</body>
</html>
""" % vars
    

class Home(resource.Resource):

    def __init__(self, root):
        resource.Resource.__init__(self)
        self.root = root

    def render_GET(self, txrequest):

        tasks = []
        now = datetime.now()
        for project, queue in self.root.poller.queues.items():
            for m in queue.list():
                tasks.append(
                    dict(project=project, 
                        spider=str(m['name']),
                        job=str(m['_job']),
                        status="pending"))

        for p in self.root.launcher.processes.values():
            elapsed = now - p.start_time
            tasks.append(
                dict(project=p.project, 
                    spider=p.spider,
                    job=p.job,
                    elapsed=elapsed,
                    start_time=p.start_time,
                    end_time=None,
                    status="started"))

        for p in self.root.launcher.finished:
            elapsed = p.end_time - p.start_time
            tasks.append(
                dict(project=p.project, 
                    spider=p.spider,
                    job=p.job,
                    elapsed=elapsed,
                    start_time=p.start_time,
                    end_time=p.end_time,
                    status="finished"))

        ctx = {
            'appname': "Scrapy",
            'projects': self.root.scheduler.list_projects(),
            'queues': self.root.poller.queues,
            'launcher': self.root.launcher,
            'tasks': tasks,
        }

        full_path = posixpath.join(self.root.htdocsdir, "index.html")

        raw_data = open(full_path).read().decode("utf-8")
        template = Template(raw_data)
        response = template.render(**ctx)
        return response.encode("utf-8")

class Jobs(resource.Resource):

    def __init__(self, root):
        resource.Resource.__init__(self)
        self.root = root

    def render(self, txrequest):
        s = "<html><head><title>Scrapyd</title></title>"
        s += "<body>"
        s += "<h1>Jobs</h1>"
        s += "<p><a href='/'>New Front-end</a> <a href='/old'>Go back</a></p>"
        s += "<table border='1'>"
        s += "<th>Project</th><th>Spider</th><th>Job</th><th>PID</th><th>Runtime</th><th>Log</th><th>Items</th>"
        s += "<tr><th colspan='7' style='background-color: #ddd'>Pending</th></tr>"
        for project, queue in self.root.poller.queues.items():
            for m in queue.list():
                s += "<tr>"
                s += "<td>%s</td>" % project
                s += "<td>%s</td>" % str(m['name'])
                s += "<td>%s</td>" % str(m['_job'])
                s += "</tr>"
        s += "<tr><th colspan='7' style='background-color: #ddd'>Running</th></tr>"
        for p in self.root.launcher.processes.values():
            s += "<tr>"
            for a in ['project', 'spider', 'job', 'pid']:
                s += "<td>%s</td>" % getattr(p, a)
            s += "<td>%s</td>" % (datetime.now() - p.start_time)
            s += "<td><a href='/logs/%s/%s/%s.log'>Log</a></td>" % (p.project, p.spider, p.job)
            s += "<td><a href='/items/%s/%s/%s.jl'>Items</a></td>" % (p.project, p.spider, p.job)
            s += "</tr>"
        s += "<tr><th colspan='7' style='background-color: #ddd'>Finished</th></tr>"
        for p in self.root.launcher.finished:
            s += "<tr>"
            for a in ['project', 'spider', 'job']:
                s += "<td>%s</td>" % getattr(p, a)
            s += "<td></td>"
            s += "<td>%s</td>" % (p.end_time - p.start_time)
            s += "<td><a href='/logs/%s/%s/%s.log'>Log</a></td>" % (p.project, p.spider, p.job)
            s += "<td><a href='/items/%s/%s/%s.jl'>Items</a></td>" % (p.project, p.spider, p.job)
            s += "</tr>"
        s += "</table>"
        s += "</body>"
        s += "</html>"
        return s
