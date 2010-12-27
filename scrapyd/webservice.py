import cgi
import traceback
import uuid
from cStringIO import StringIO

from scrapy.utils.txweb import JsonResource
from .utils import get_spider_list

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
        jobid = uuid.uuid1().hex
        args['_job'] = jobid
        self.root.scheduler.schedule(project, spider, **args)
        jobids = {spider: jobid}
        return {"status": "ok", "jobs": jobids}

class AddVersion(WsResource):

    def render_POST(self, txrequest):
        ct = txrequest.requestHeaders.getRawHeaders('Content-Type')[0]
        boundary = ct.split('boundary=', 1)[1]
        d = cgi.parse_multipart(txrequest.content, {'boundary': boundary})
        project = d['project'][0]
        version = d['version'][0]
        eggf = StringIO(d['egg'][0])
        self.root.eggstorage.put(eggf, project, version)
        spiders = get_spider_list(project)
        self.root.update_projects()
        return {"status": "ok", "project": project, "version": version, \
            "spiders": len(spiders)}

class ListProjects(WsResource):

    def render_GET(self, txrequest):
        projects = self.root.scheduler.list_projects()
        return {"status": "ok", "projects": projects}

class ListVersions(WsResource):

    def render_GET(self, txrequest):
        project = txrequest.args['project'][0]
        versions = self.root.eggstorage.list(project)
        return {"status": "ok", "versions": versions}

class ListSpiders(WsResource):

    def render_GET(self, txrequest):
        project = txrequest.args['project'][0]
        spiders = get_spider_list(project, runner=self.root.runner)
        return {"status": "ok", "spiders": spiders}

class DeleteProject(WsResource):

    def render_POST(self, txrequest):
        project = txrequest.args['project'][0]
        self._delete_version(project)
        return {"status": "ok"}

    def _delete_version(self, project, version=None):
        self.root.eggstorage.delete(project, version)
        self.root.update_projects()

class DeleteVersion(DeleteProject):

    def render_POST(self, txrequest):
        project = txrequest.args['project'][0]
        version = txrequest.args['version'][0]
        self._delete_version(project, version)
        return {"status": "ok"}

