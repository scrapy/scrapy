"""
Scrapy Web Console extension

See docs/topics/webconsole.rst
"""

import re
import socket
from datetime import datetime

from twisted.internet import reactor
from twisted.web import server, resource
from scrapy.xlib.pydispatch import dispatcher

from scrapy.core.engine import scrapyengine
from scrapy.conf import settings

# web management signals
webconsole_discover_module = object()

urlpath_re = re.compile(r"^/(\w+)/")

def error404(module):
    return """
<html>
  <head><title>404 Not Found</title></head>
  <body>
    <h1>Not found</h1>
    <p>Web console module not found: <b>%s</b></p>
    <p><a href="/">Back to main menu</a></p>
  </body>
</html>
""" % module

def banner(module=None):
    s  = "<html>\n"
    s += "<head><title>Scrapy</title></head>\n"
    s += "<body>\n"
    s += "<h1><a href='/'>Scrapy web console</a></h1>\n"
    now = datetime.now()
    uptime = now - scrapyengine.start_time
    s += "<p>Bot: <b>%s</b> | Host: <b>%s</b> | Uptime: <b>%s</b> | Time: <b>%s</b> </p>\n" % (settings['BOT_NAME'], socket.gethostname(), str(uptime), str(now.replace(microsecond=0)))
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
            module = m.group(1)
            if module in self.modules:
                return self.modules[m.group(1)].webconsole_render(request)
            else:
                request.setResponseCode(404)
                return error404(module)
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

        logfile = settings['WEBCONSOLE_LOGFILE']
        server.Site.__init__(self, WebConsoleResource(), logPath=logfile)
        self.noisy = False
        port = settings.getint('WEBCONSOLE_PORT')
        reactor.callWhenRunning(reactor.listenTCP, port, self)
