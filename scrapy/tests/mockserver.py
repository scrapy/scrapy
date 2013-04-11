import json, random, urllib
from time import time
from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.internet import reactor


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
        self.putChild("follow", Follow())
        self.putChild("log", Log(self.log))

    def getChild(self, request, name):
        return self

    def render(self, request):
        return 'Scrapy mock HTTP server\n'


root = Root()
factory = Site(root)
reactor.listenTCP(8998, factory)
reactor.run()
