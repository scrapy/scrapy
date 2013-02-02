import json
import posixpath
from datetime import datetime

from jinja2 import Template, Environment, FileSystemLoader

from twisted.web import resource, static
from twisted.application.service import IServiceCollection

from scrapy.utils.misc import load_object

from .interfaces import IPoller, IEggStorage, ISpiderScheduler

class Root(resource.Resource):

    def __init__(self, config, app):
        resource.Resource.__init__(self)
        self.debug = config.getboolean('debug', False)
        self.runner = config.get('runner')

        
        self.htdocsdir = (config.get('htdocs_dir') or 
            posixpath.join(posixpath.split(__file__)[0], "htdocs"))

        self.environ = Environment(loader=FileSystemLoader(self.htdocsdir))

        logsdir = config.get('logs_dir')
        itemsdir = config.get('items_dir')
        
        self.app = app

        self.putChild('logs', static.File(logsdir, 'text/plain'))
        self.putChild('items', static.File(itemsdir, 'text/plain'))
        self.putChild('d', Data(self))

        for path in ['css', 'js', 'img']:
            fullpath = posixpath.join(self.htdocsdir, path)
            self.putChild(path, static.File(fullpath))

        services = config.items('services', ())
        for servName, servClsName in services:
          servCls = load_object(servClsName)
          self.putChild(servName, servCls(self))
        self.update_projects()

    def getChild(self, name, request):
        return Renderer(self, name)
        
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

def get_tasks(root):
    tasks = []
    now = datetime.now()

    for project, queue in root.poller.queues.items():
        for m in queue.list():
            tasks.append(
                dict(project=project, 
                    spider=str(m['name']),
                    job=str(m['_job']),
                    status="pending"))

    for p in root.launcher.processes.values():
        elapsed = now - p.start_time
        tasks.append(
            dict(project=p.project, 
                spider=p.spider,
                job=p.job,
                elapsed=elapsed,
                start_time=p.start_time,
                end_time=None,
                status="started"))

    for p in root.launcher.finished:
        elapsed = p.end_time - p.start_time
        tasks.append(
            dict(project=p.project, 
                spider=p.spider,
                job=p.job,
                elapsed=elapsed,
                start_time=p.start_time,
                end_time=p.end_time,
                status="finished"))
    return tasks
    
class Data(resource.Resource):
    def __init__(self, root):
        resource.Resource.__init__(self)
        self.root = root

    def render_GET(self, txrequest):
        tasks = get_tasks(self.root)
        dthandler = lambda obj: obj.isoformat() if isinstance(obj, datetime) else None
        return json.dumps(tasks, default=dthandler)

class Renderer(resource.Resource):

    def __init__(self, root, name, document_root='index.html'):
        resource.Resource.__init__(self)
        self.root = root
        self.name = name or document_root

    def render_GET(self, txrequest):
        tasks = get_tasks(self.root)
        ctx = {
            'appname': "Scrapy",
            'projects': self.root.scheduler.list_projects(),
            'queues': self.root.poller.queues,
            'launcher': self.root.launcher,
            'tasks': tasks,
        }

        template = self.root.environ.get_template(self.name)
        response = template.render(**ctx)
        return response.encode("utf-8")

