from __future__ import print_function
import sys, time, random, urllib, os, json
from subprocess import Popen, PIPE
from twisted.web.server import Site, NOT_DONE_YET
from twisted.web.resource import Resource
from twisted.internet import reactor, defer, ssl
from scrapy import twisted_version


if twisted_version < (11, 0, 0):
    def deferLater(clock, delay, func, *args, **kw):
        def _cancel_method():
            _cancel_cb(None)
            d.errback(Exception())

        def _cancel_cb(result):
            if cl.active():
                cl.cancel()
            return result

        d = defer.Deferred()
        d.cancel = _cancel_method
        d.addCallback(lambda ignored: func(*args, **kw))
        d.addBoth(_cancel_cb)
        cl = clock.callLater(delay, d.callback, None)
        return d
else:
    from twisted.internet.task import deferLater


def getarg(request, name, default=None, type=str):
    if name in request.args:
        return type(request.args[name][0])
    else:
        return default


class LeafResource(Resource):

    isLeaf = True

    def deferRequest(self, request, delay, f, *a, **kw):
        def _cancelrequest(_):
            # silence CancelledError
            d.addErrback(lambda _: None)
            d.cancel()

        d = deferLater(reactor, delay, f, *a, **kw)
        request.notifyFinish().addErrback(_cancelrequest)
        return d


class Follow(LeafResource):

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


class Delay(LeafResource):

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


class Status(LeafResource):

    def render_GET(self, request):
        n = getarg(request, "n", 200, type=int)
        request.setResponseCode(n)
        return ""


class Raw(LeafResource):

    def render_GET(self, request):
        request.startedWriting = 1
        self.deferRequest(request, 0, self._delayedRender, request)
        return NOT_DONE_YET
    render_POST = render_GET

    def _delayedRender(self, request):
        raw = getarg(request, 'raw', 'HTTP 1.1 200 OK\n')
        request.startedWriting = 1
        request.write(raw)
        request.channel.transport.loseConnection()
        request.finish()


class Echo(LeafResource):

    def render_GET(self, request):
        output = {
            'headers': dict(request.requestHeaders.getAllRawHeaders()),
            'body': request.content.read(),
        }
        return json.dumps(output)


class Partial(LeafResource):

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
        tr = request.channel.transport
        try:
            if abort and hasattr(tr, 'abortConnection'):
                tr.abortConnection()
            else:
                tr.loseConnection()
        finally:
            request.finish()


class Root(Resource):

    def __init__(self):
        Resource.__init__(self)
        self.putChild("status", Status())
        self.putChild("follow", Follow())
        self.putChild("delay", Delay())
        self.putChild("partial", Partial())
        self.putChild("drop", Drop())
        self.putChild("raw", Raw())
        self.putChild("echo", Echo())

    def getChild(self, name, request):
        return self

    def render(self, request):
        return 'Scrapy mock HTTP server\n'


class MockServer():

    def __enter__(self):
        from scrapy.utils.test import get_testenv
        self.proc = Popen([sys.executable, '-u', '-m', 'tests.mockserver'],
                          stdout=PIPE, env=get_testenv())
        self.proc.stdout.readline()

    def __exit__(self, exc_type, exc_value, traceback):
        self.proc.kill()
        self.proc.wait()
        time.sleep(0.2)


if __name__ == "__main__":
    root = Root()
    factory = Site(root)
    httpPort = reactor.listenTCP(8998, factory)
    contextFactory = ssl.DefaultOpenSSLContextFactory(
         os.path.join(os.path.dirname(__file__), 'keys/cert.pem'),
         os.path.join(os.path.dirname(__file__), 'keys/cert.pem'),
         )
    httpsPort = reactor.listenSSL(8999, factory, contextFactory)

    def print_listening():
        httpHost = httpPort.getHost()
        httpsHost = httpsPort.getHost()
        print("Mock server running at http://%s:%d and https://%s:%d" % (
            httpHost.host, httpHost.port, httpsHost.host, httpsHost.port))
    reactor.callWhenRunning(print_listening)
    reactor.run()
