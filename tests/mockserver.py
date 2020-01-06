import json
import os
import random
import sys
from subprocess import Popen, PIPE
from urllib.parse import urlencode

from OpenSSL import SSL
from twisted.web.server import Site, NOT_DONE_YET
from twisted.web.resource import Resource
from twisted.web.static import File
from twisted.web.test.test_webclient import PayloadResource
from twisted.web.server import GzipEncoderFactory
from twisted.web.resource import EncodingResourceWrapper
from twisted.web.util import redirectTo
from twisted.internet import reactor, ssl
from twisted.internet.task import deferLater

from scrapy.utils.python import to_bytes, to_unicode
from scrapy.utils.ssl import SSL_OP_NO_TLSv1_3


def getarg(request, name, default=None, type=None):
    if name in request.args:
        value = request.args[name][0]
        if type is not None:
            value = type(value)
        return value
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
        total = getarg(request, b"total", 100, type=int)
        show = getarg(request, b"show", 1, type=int)
        order = getarg(request, b"order", b"desc")
        maxlatency = getarg(request, b"maxlatency", 0, type=float)
        n = getarg(request, b"n", total, type=int)
        if order == b"rand":
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
            args[b"n"] = [to_bytes(str(nl))]
            argstr = urlencode(args, doseq=True)
            s += "<a href='/follow?%s'>follow %d</a><br>" % (argstr, nl)
        s += """</body>"""
        request.write(to_bytes(s))
        request.finish()


class Delay(LeafResource):

    def render_GET(self, request):
        n = getarg(request, b"n", 1, type=float)
        b = getarg(request, b"b", 1, type=int)
        if b:
            # send headers now and delay body
            request.write('')
        self.deferRequest(request, n, self._delayedRender, request, n)
        return NOT_DONE_YET

    def _delayedRender(self, request, n):
        request.write(to_bytes("Response delayed for %0.3f seconds\n" % n))
        request.finish()


class Status(LeafResource):

    def render_GET(self, request):
        n = getarg(request, b"n", 200, type=int)
        request.setResponseCode(n)
        return b""


class Raw(LeafResource):

    def render_GET(self, request):
        request.startedWriting = 1
        self.deferRequest(request, 0, self._delayedRender, request)
        return NOT_DONE_YET
    render_POST = render_GET

    def _delayedRender(self, request):
        raw = getarg(request, b'raw', b'HTTP 1.1 200 OK\n')
        request.startedWriting = 1
        request.write(raw)
        request.channel.transport.loseConnection()
        request.finish()


class Echo(LeafResource):

    def render_GET(self, request):
        output = {
            'headers': dict(
                (to_unicode(k), [to_unicode(v) for v in vs])
                for k, vs in request.requestHeaders.getAllRawHeaders()),
            'body': to_unicode(request.content.read()),
        }
        return to_bytes(json.dumps(output))
    render_POST = render_GET


class RedirectTo(LeafResource):

    def render(self, request):
        goto = getarg(request, b'goto', b'/')
        # we force the body content, otherwise Twisted redirectTo()
        # returns HTML with <meta http-equiv="refresh"
        redirectTo(goto, request)
        return b'redirecting...'


class Partial(LeafResource):

    def render_GET(self, request):
        request.setHeader(b"Content-Length", b"1024")
        self.deferRequest(request, 0, self._delayedRender, request)
        return NOT_DONE_YET

    def _delayedRender(self, request):
        request.write(b"partial content\n")
        request.finish()


class Drop(Partial):

    def _delayedRender(self, request):
        abort = getarg(request, b"abort", 0, type=int)
        request.write(b"this connection will be dropped\n")
        tr = request.channel.transport
        try:
            if abort and hasattr(tr, 'abortConnection'):
                tr.abortConnection()
            else:
                tr.loseConnection()
        finally:
            request.finish()


class ArbitraryLengthPayloadResource(LeafResource):

    def render(self, request):
        return request.content.read()


class Root(Resource):

    def __init__(self):
        Resource.__init__(self)
        self.putChild(b"status", Status())
        self.putChild(b"follow", Follow())
        self.putChild(b"delay", Delay())
        self.putChild(b"partial", Partial())
        self.putChild(b"drop", Drop())
        self.putChild(b"raw", Raw())
        self.putChild(b"echo", Echo())
        self.putChild(b"payload", PayloadResource())
        self.putChild(b"xpayload", EncodingResourceWrapper(PayloadResource(), [GzipEncoderFactory()]))
        self.putChild(b"alpayload", ArbitraryLengthPayloadResource())
        try:
            from tests import tests_datadir
            self.putChild(b"files", File(os.path.join(tests_datadir, 'test_site/files/')))
        except Exception:
            pass
        self.putChild(b"redirect-to", RedirectTo())

    def getChild(self, name, request):
        return self

    def render(self, request):
        return b'Scrapy mock HTTP server\n'


class MockServer():

    def __enter__(self):
        from scrapy.utils.test import get_testenv

        self.proc = Popen([sys.executable, '-u', '-m', 'tests.mockserver'],
                          stdout=PIPE, env=get_testenv())
        http_address = self.proc.stdout.readline().strip().decode('ascii')
        https_address = self.proc.stdout.readline().strip().decode('ascii')

        self.http_address = http_address
        self.https_address = https_address

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.proc.kill()
        self.proc.communicate()

    def url(self, path, is_secure=False):
        host = self.http_address.replace('0.0.0.0', '127.0.0.1')
        if is_secure:
            host = self.https_address
        return host + path


def ssl_context_factory(keyfile='keys/localhost.key', certfile='keys/localhost.crt', cipher_string=None):
    factory = ssl.DefaultOpenSSLContextFactory(
         os.path.join(os.path.dirname(__file__), keyfile),
         os.path.join(os.path.dirname(__file__), certfile),
         )
    if cipher_string:
        ctx = factory.getContext()
        # disabling TLS1.2+ because it unconditionally enables some strong ciphers
        ctx.set_options(SSL.OP_CIPHER_SERVER_PREFERENCE | SSL.OP_NO_TLSv1_2 | SSL_OP_NO_TLSv1_3)
        ctx.set_cipher_list(to_bytes(cipher_string))
    return factory


if __name__ == "__main__":
    root = Root()
    factory = Site(root)
    httpPort = reactor.listenTCP(0, factory)
    contextFactory = ssl_context_factory()
    httpsPort = reactor.listenSSL(0, factory, contextFactory)

    def print_listening():
        httpHost = httpPort.getHost()
        httpsHost = httpsPort.getHost()
        httpAddress = 'http://%s:%d' % (httpHost.host, httpHost.port)
        httpsAddress = 'https://%s:%d' % (httpsHost.host, httpsHost.port)
        print(httpAddress)
        print(httpsAddress)

    reactor.callWhenRunning(print_listening)
    reactor.run()
