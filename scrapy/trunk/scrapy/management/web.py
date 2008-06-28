import re
import socket
from datetime import datetime

from twisted.internet import reactor
from twisted.web import server, resource
from pydispatch import dispatcher

from scrapy.core.engine import scrapyengine
from scrapy.conf import settings

# web management signals
webconsole_discover_module = object()

urlpath_re = re.compile(r"^/(\w+)/")

def banner(module=None):
    s  = "<html>\n"
    s += "<head><title>Scrapy</title></head>\n"
    s += "<body>\n"
    s += "<h1><a href='/'>Scrapy web console</a></h1>\n"
    now = datetime.now()
    uptime = now - scrapyengine.start_time
    s += "<p>Bot: <b>%s</b> | Host: <b>%s</b> | Uptime: <b>%s</b> | Time: <b>%s</b> </p>\n" % (settings['BOT_NAME'], socket.gethostname(), str(uptime), str(now))
    if module:
        s += "<h2><a href='/%s/'>%s</a></h2>\n" % (module.webconsole_id, module.webconsole_name)
    return s

class WebConsoleResource(resource.Resource):
    isLeaf = True

    @property
    def modules(self):
        if not hasattr(self, '_modules'):
            self._modules = {}
            for _, obj in dispatcher.send(signal=webconsole_discover_module, sender=self.__class__):
                self._modules[obj.webconsole_id] = obj
        return self._modules

    def render_GET(self, request):
        m = urlpath_re.search(request.path)
        if m:
            return self.modules[m.group(1)].webconsole_render(request)
        else:
            return self.module_list()

    render_POST = render_GET

    def module_list(self):
        s  = banner()
        s += "<p>Available modules:</p>\n"
        s += "<ul>\n"
        for name, obj in self.modules.iteritems():
            s += "<li><a href='/%s/'>%s</a></li>\n" % (name, obj.webconsole_name)
        s += "</ul>\n"
        s += "</body>\n"
        s += "</html>\n"
        return s

class WebConsole(server.Site):

    def __init__(self):
        if not settings.getbool('WEBCONSOLE_ENABLED'):
            return

        server.Site.__init__(self, WebConsoleResource())
        self.noisy = False
        port = settings.getint('WEBCONSOLE_PORT')
        scrapyengine.listenTCP(port, self)
