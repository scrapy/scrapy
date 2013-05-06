import json, random, urllib
from time import time
from twisted.web.server import Site, NOT_DONE_YET
from twisted.web.resource import Resource
from twisted.internet import reactor
from twisted.internet.task import deferLater


_id = lambda x: x
_request_args = {
    "args": _id,
    "clientproto": _id,
    "requestHeaders": lambda x: x._rawHeaders,
    "responseHeaders": lambda x: x._rawHeaders,
    "method": _id,
    "path": _id,
    "uri": _id,
}

def encode_request(request):
    """Encode request into a JSON-serializable type"""
    d = {"time": time()}
    for k, func in _request_args.iteritems():
        d[k] = func(getattr(request, k))
    return d

def getarg(request, name, default=None, type=str):
    if name in request.args:
        return type(request.args[name][0])
    else:
        return default

class Follow(Resource):

    isLeaf = True

    def render(self, request):
        total = getarg(request, "total", 100, type=int)
        show = getarg(request, "show", 1, type=int)
        order = getarg(request, "order", "desc")
        n = getarg(request, "n", total, type=int)
        if order == "rand":
            nlist = [random.randint(1, total) for _ in range(show)]
        else: # order == "desc"
            nlist = range(n, max(n-show, 0), -1)

        s = """<html> <head></head> <body>"""
        args = request.args.copy()
        for nl in nlist:
            args["n"] = [str(nl)]
            argstr = urllib.urlencode(args, doseq=True)
            s += "<a href='/follow?%s'>follow %d</a><br>" % (argstr, nl)
        s += """</body>"""
        return s

class Delay(Resource):

    isLeaf = True

    def render_GET(self, request):
        n = getarg(request, "n", 1, type=float)
        d = deferLater(reactor, n, lambda: (request, n))
        d.addCallback(self._delayedRender)
        return NOT_DONE_YET

    def _delayedRender(self, (request, n)):
        request.write("Response delayed for %0.3f seconds\n" % n)
        request.finish()

class Status(Resource):

    isLeaf = True

    def render_GET(self, request):
        n = getarg(request, "n", 200, type=int)
        request.setResponseCode(n)
        return ""

class Partial(Resource):

    isLeaf = True

    def render_GET(self, request):
        request.setHeader("Content-Length", "1024")
        d = deferLater(reactor, 0, lambda: request)
        d.addCallback(self._delayedRender)
        return NOT_DONE_YET

    def _delayedRender(self, request):
        request.write("partial content\n")
        request.finish()

class Drop(Partial):

    def _delayedRender(self, request):
        request.write("this connection will be dropped\n")
        request.channel.transport.loseConnection()
        request.finish()

class Log(Resource):

    isLeaf = True

    def __init__(self, log):
        self.log = log

    def render(self, request):
        return json.dumps(self.log)

class Root(Resource):

    def __init__(self):
        Resource.__init__(self)
        self.log = []
        self.putChild("status", Status())
        self.putChild("follow", Follow())
        self.putChild("delay", Delay())
        self.putChild("partial", Partial())
        self.putChild("drop", Drop())
        self.putChild("log", Log(self.log))

    def getChild(self, request, name):
        return self

    def render(self, request):
        return 'Scrapy mock HTTP server\n'


if __name__ == "__main__":
    root = Root()
    factory = Site(root)
    port = reactor.listenTCP(8998, factory)
    def print_listening():
        h = port.getHost()
        print "Mock server running at http://%s:%d" % (h.host, h.port)
    reactor.callWhenRunning(print_listening)
    reactor.run()
