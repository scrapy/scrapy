"""
Scrapy web services extension

See docs/topics/webservice.rst
"""

from twisted.web import server, error

from scrapy.xlib.pydispatch import dispatcher
from scrapy.exceptions import NotConfigured
from scrapy import log, signals
from scrapy.utils.jsonrpc import jsonrpc_server_call
from scrapy.utils.serialize import ScrapyJSONEncoder, ScrapyJSONDecoder
from scrapy.utils.misc import load_object
from scrapy.utils.txweb import JsonResource as JsonResource_
from scrapy.utils.reactor import listen_tcp
from scrapy.utils.conf import build_component_list
from scrapy.conf import settings


class JsonResource(JsonResource_):

    json_encoder = ScrapyJSONEncoder()

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
        self.portrange = map(int, settings.getlist('WEBSERVICE_PORT'))
        self.host = settings['WEBSERVICE_HOST']
        root = RootResource()
        reslist = build_component_list(settings['WEBSERVICE_RESOURCES_BASE'], \
            settings['WEBSERVICE_RESOURCES'])
        for res_cls in map(load_object, reslist):
            res = res_cls()
            root.putChild(res.ws_name, res)
        server.Site.__init__(self, root, logPath=logfile)
        self.noisy = False
        dispatcher.connect(self.start_listening, signals.engine_started)
        dispatcher.connect(self.stop_listening, signals.engine_stopped)

    def start_listening(self):
        self.port = listen_tcp(self.portrange, self.host, self)
        h = self.port.getHost()
        log.msg("Web service listening on %s:%d" % (h.host, h.port), log.DEBUG)

    def stop_listening(self):
        self.port.stopListening()

