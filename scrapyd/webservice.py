import cgi
import traceback
from cStringIO import StringIO

from twisted.web.resource import Resource

from scrapy.utils.txweb import JsonResource
from .interfaces import IPoller, IEggStorage, ISpiderScheduler
from .eggutils import get_spider_list_from_eggfile

class WsResource(JsonResource):

    def __init__(self, root):
        JsonResource.__init__(self)
        self.root = root

    def render(self, txrequest):
        try:
            return JsonResource.render(self, txrequest)
        except Exception, e:
            if self.root.debug:
                return traceback.format_exc()
            r = {"status": "error", "message": str(e)}
            return self.render_object(r, txrequest)

class Schedule(WsResource):

    def render_POST(self, txrequest):
        args = dict((k, v[0]) for k, v in txrequest.args.items())
        project = args.pop('project')
        spider = args.pop('spider')
        sched = self.root.app.getComponent(ISpiderScheduler)
        sched.schedule(project, spider, **args)
        return {"status": "ok"}

class AddVersion(WsResource):

    def render_POST(self, txrequest):
        ct = txrequest.requestHeaders.getRawHeaders('Content-Type')[0]
        boundary = ct.split('boundary=', 1)[1]
        d = cgi.parse_multipart(txrequest.content, {'boundary': boundary})
        project = d['project'][0]
        version = d['version'][0]
        eggf = StringIO(d['egg'][0])
        spiders = get_spider_list_from_eggfile(eggf, project)
        eggstorage = self.root.app.getComponent(IEggStorage)
        eggstorage.put(eggf, project, version)
        self.root.update_projects()
        return {"status": "ok", "spiders": spiders}

class ListProjects(WsResource):

    def render_GET(self, txrequest):
        projects = self.root.app.getComponent(ISpiderScheduler).list_projects()
        return {"status": "ok", "projects": projects}

class ListVersions(WsResource):

    def render_GET(self, txrequest):
        project = txrequest.args['project'][0]
        eggstorage = self.root.app.getComponent(IEggStorage)
        versions = eggstorage.list(project)
        return {"status": "ok", "versions": versions}

class ListSpiders(WsResource):

    def render_GET(self, txrequest):
        project = txrequest.args['project'][0]
        eggstorage = self.root.app.getComponent(IEggStorage)
        _, eggf = eggstorage.get(project)
        spiders = get_spider_list_from_eggfile(eggf, project, \
            eggrunner=self.root.egg_runner)
        return {"status": "ok", "spiders": spiders}

class DeleteProject(WsResource):

    def render_POST(self, txrequest):
        project = txrequest.args['project'][0]
        self._delete_version(project)
        return {"status": "ok"}

    def _delete_version(self, project, version=None):
        eggstorage = self.root.app.getComponent(IEggStorage)
        eggstorage.delete(project, version)
        self.root.update_projects()

class DeleteVersion(DeleteProject):

    def render_POST(self, txrequest):
        project = txrequest.args['project'][0]
        version = txrequest.args['version'][0]
        self._delete_version(project, version)
        return {"status": "ok"}

class Root(Resource):

    def __init__(self, config, app):
        Resource.__init__(self)
        self.debug = config.getboolean('debug', False)
        self.eggrunner = config.get('egg_runner')
        self.app = app
        self.putChild('schedule.json', Schedule(self))
        self.putChild('addversion.json', AddVersion(self))
        self.putChild('listprojects.json', ListProjects(self))
        self.putChild('listversions.json', ListVersions(self))
        self.putChild('listspiders.json', ListSpiders(self))
        self.putChild('delproject.json', DeleteProject(self))
        self.putChild('delversion.json', DeleteVersion(self))
        self.update_projects()

    def update_projects(self):
        self.app.getComponent(IPoller).update_projects()
        self.app.getComponent(ISpiderScheduler).update_projects()
