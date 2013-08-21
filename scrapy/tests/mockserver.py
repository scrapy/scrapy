import sys, time, random, urllib
from subprocess import Popen, PIPE
from twisted.web.server import Site, NOT_DONE_YET
from twisted.web.resource import Resource
from twisted.internet import reactor
from twisted.internet.task import deferLater


def getarg(request, name, default=None, type=str):
    if name in request.args:
        return type(request.args[name][0])
    else:
        return default


class DeferMixin(object):

    def deferRequest(self, request, delay, f, *a, **kw):
        def _cancelrequest(_):
            # silence CancelledError
            d.addErrback(lambda _: None)
            d.cancel()
        d = deferLater(reactor, delay, f, *a, **kw)
        request.notifyFinish().addErrback(_cancelrequest)
        return d


class Follow(DeferMixin, Resource):

    isLeaf = True

    def render(self, request):
        total = getarg(request, "total", 100, type=int)
        show = getarg(request, "show", 1, type=int)
        order = getarg(request, "order", "desc")
        maxlatency = getarg(request, "maxlatency", 0, type=float)
        n = getarg(request, "n", total, type=int)
        if order == "rand":
            nlist = [random.randint(1, total) for _ in range(show)]
        else:  # order == "desc"
            nlist = range(n, max(n - show, 0), -1)

        lag = random.random() * maxlatency
        self.deferRequest(request, lag, self.renderRequest, request, nlist)
        return NOT_DONE_YET

    def renderRequest(self, request, nlist):
        s = """<html> <head></head> <body>"""
        args = request.args.copy()
        for nl in nlist:
            args["n"] = [str(nl)]
            argstr = urllib.urlencode(args, doseq=True)
            s += "<a href='/follow?%s'>follow %d</a><br>" % (argstr, nl)
        s += """</body>"""
        request.write(s)
        request.finish()


class Delay(DeferMixin, Resource):

    isLeaf = True

    def render_GET(self, request):
        n = getarg(request, "n", 1, type=float)
        b = getarg(request, "b", 1, type=int)
        if b:
            # send headers now and delay body
            request.write('')
        self.deferRequest(request, n, self._delayedRender, request, n)
        return NOT_DONE_YET

    def _delayedRender(self, request, n):
        request.write("Response delayed for %0.3f seconds\n" % n)
        request.finish()


class Status(Resource):

    isLeaf = True

    def render_GET(self, request):
        n = getarg(request, "n", 200, type=int)
        request.setResponseCode(n)
        return ""


class Partial(DeferMixin, Resource):

    isLeaf = True

    def render_GET(self, request):
        request.setHeader("Content-Length", "1024")
        self.deferRequest(request, 0, self._delayedRender, request)
        return NOT_DONE_YET

    def _delayedRender(self, request):
        request.write("partial content\n")
        request.finish()


class Drop(Partial):

    def _delayedRender(self, request):
        abort = getarg(request, "abort", 0, type=int)
        request.write("this connection will be dropped\n")
        if abort:
            request.channel.transport.abortConnection()
        else:
            request.channel.transport.loseConnection()
            request.finish()


class Root(Resource):

    def __init__(self):
        Resource.__init__(self)
        self.putChild("status", Status())
        self.putChild("follow", Follow())
        self.putChild("delay", Delay())
        self.putChild("partial", Partial())
        self.putChild("drop", Drop())

    def getChild(self, name, request):
        return self

    def render(self, request):
        return 'Scrapy mock HTTP server\n'


class MockServer():

    def __enter__(self):
        from scrapy.utils.test import get_testenv
        self.proc = Popen([sys.executable, '-u', '-m', 'scrapy.tests.mockserver'],
                          stdout=PIPE, env=get_testenv())
        self.proc.stdout.readline()

    def __exit__(self, exc_type, exc_value, traceback):
        self.proc.kill()
        self.proc.wait()
        time.sleep(0.2)


if __name__ == "__main__":
    root = Root()
    factory = Site(root)
    port = reactor.listenTCP(8998, factory)
    def print_listening():
        h = port.getHost()
        print "Mock server running at http://%s:%d" % (h.host, h.port)
    reactor.callWhenRunning(print_listening)
    reactor.run()
