"""
Scrapy web services extension

See docs/topics/ws.rst
"""

from twisted.internet import reactor
from twisted.web import server, resource, error

from scrapy.core.exceptions import NotConfigured
from scrapy.utils.jsonrpc import jsonrpc_server_call
from scrapy.utils.serialize import ScrapyJSONEncoder, ScrapyJSONDecoder
from scrapy.utils.misc import load_object
from scrapy.utils.conf import build_component_list
from scrapy.conf import settings


class JsonResource(resource.Resource):

    ws_name = None
    json_encoder = ScrapyJSONEncoder()

    def render(self, txrequest):
        r = resource.Resource.render(self, txrequest)
        r = self.json_encoder.encode(r)
        txrequest.setHeader('Content-Type', 'application/json')
        txrequest.setHeader('Content-Length', len(r))
        return r


class JsonRpcResource(JsonResource):

    json_decoder = ScrapyJSONDecoder()

    def __init__(self, target=None):
        JsonResource.__init__(self)
        self._target = target

    def render_GET(self, txrequest):
        return self.get_target()

    def render_POST(self, txrequest):
        reqstr = txrequest.content.read()
        target = self.get_target()
        return jsonrpc_server_call(target, reqstr, self.json_decoder)

    def getChild(self, name, txrequest):
        target = self.get_target()
        try:
            newtarget = getattr(target, name)
            return JsonRpcResource(newtarget)
        except AttributeError:
            return error.NoResource("No such child resource.")

    def get_target(self):
        return self._target


class RootResource(JsonResource):

    def render_GET(self, txrequest):
        return {'resources': self.children.keys()}

    def getChild(self, name, txrequest):
        if name == '':
            return self
        return JsonResource.getChild(self, name, txrequest)


class WebService(server.Site):

    def __init__(self):
        if not settings.getbool('WEBSERVICE_ENABLED'):
            raise NotConfigured
        logfile = settings['WEBSERVICE_LOGFILE']
        port = settings.getint('WEBSERVICE_PORT')
        root = RootResource()
        reslist = build_component_list(settings['WEBSERVICE_RESOURCES_BASE'], \
            settings['WEBSERVICE_RESOURCES'])
        for res_cls in map(load_object, reslist):
            res = res_cls()
            root.putChild(res.ws_name, res)
        server.Site.__init__(self, root, logPath=logfile)
        self.noisy = False
        reactor.callWhenRunning(reactor.listenTCP, port, self)

