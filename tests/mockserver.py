from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from shutil import rmtree
from subprocess import PIPE, Popen
from tempfile import mkdtemp
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from OpenSSL import SSL
from twisted.internet import defer, reactor, ssl
from twisted.internet.task import deferLater
from twisted.names import dns, error
from twisted.names.server import DNSServerFactory
from twisted.web import resource, server
from twisted.web.server import NOT_DONE_YET, GzipEncoderFactory, Site
from twisted.web.static import File
from twisted.web.util import redirectTo

from scrapy.utils.python import to_bytes, to_unicode

if TYPE_CHECKING:
    from twisted.internet.protocol import ServerFactory


def getarg(request, name, default=None, type=None):
    if name in request.args:
        value = request.args[name][0]
        if type is not None:
            value = type(value)
        return value
    return default


def get_mockserver_env() -> dict[str, str]:
    """Return a OS environment dict suitable to run mockserver processes."""

    tests_path = Path(__file__).parent.parent
    pythonpath = str(tests_path) + os.pathsep + os.environ.get("PYTHONPATH", "")
    env = os.environ.copy()
    env["PYTHONPATH"] = pythonpath
    return env


# most of the following resources are copied from twisted.web.test.test_webclient
class ForeverTakingResource(resource.Resource):
    """
    L{ForeverTakingResource} is a resource which never finishes responding
    to requests.
    """

    def __init__(self, write=False):
        resource.Resource.__init__(self)
        self._write = write

    def render(self, request):
        if self._write:
            request.write(b"some bytes")
        return server.NOT_DONE_YET


class ErrorResource(resource.Resource):
    def render(self, request):
        request.setResponseCode(401)
        if request.args.get(b"showlength"):
            request.setHeader(b"content-length", b"0")
        return b""


class NoLengthResource(resource.Resource):
    def render(self, request):
        return b"nolength"


class HostHeaderResource(resource.Resource):
    """
    A testing resource which renders itself as the value of the host header
    from the request.
    """

    def render(self, request):
        return request.requestHeaders.getRawHeaders(b"host")[0]


class PayloadResource(resource.Resource):
    """
    A testing resource which renders itself as the contents of the request body
    as long as the request body is 100 bytes long, otherwise which renders
    itself as C{"ERROR"}.
    """

    def render(self, request):
        data = request.content.read()
        contentLength = request.requestHeaders.getRawHeaders(b"content-length")[0]
        if len(data) != 100 or int(contentLength) != 100:
            return b"ERROR"
        return data


class BrokenDownloadResource(resource.Resource):
    def render(self, request):
        # only sends 3 bytes even though it claims to send 5
        request.setHeader(b"content-length", b"5")
        request.write(b"abc")
        return b""


class LeafResource(resource.Resource):
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
            s += f"<a href='/follow?{argstr}'>follow {nl}</a><br>"
        s += """</body>"""
        request.write(to_bytes(s))
        request.finish()


class Delay(LeafResource):
    def render_GET(self, request):
        n = getarg(request, b"n", 1, type=float)
        b = getarg(request, b"b", 1, type=int)
        if b:
            # send headers now and delay body
            request.write("")
        self.deferRequest(request, n, self._delayedRender, request, n)
        return NOT_DONE_YET

    def _delayedRender(self, request, n):
        request.write(to_bytes(f"Response delayed for {n:.3f} seconds\n"))
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
        raw = getarg(request, b"raw", b"HTTP 1.1 200 OK\n")
        request.startedWriting = 1
        request.write(raw)
        request.channel.transport.loseConnection()
        request.finish()


class Echo(LeafResource):
    def render_GET(self, request):
        output = {
            "headers": {
                to_unicode(k): [to_unicode(v) for v in vs]
                for k, vs in request.requestHeaders.getAllRawHeaders()
            },
            "body": to_unicode(request.content.read()),
        }
        return to_bytes(json.dumps(output))

    render_POST = render_GET


class RedirectTo(LeafResource):
    def render(self, request):
        goto = getarg(request, b"goto", b"/")
        # we force the body content, otherwise Twisted redirectTo()
        # returns HTML with <meta http-equiv="refresh"
        redirectTo(goto, request)
        return b"redirecting..."


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
            if abort and hasattr(tr, "abortConnection"):
                tr.abortConnection()
            else:
                tr.loseConnection()
        finally:
            request.finish()


class ArbitraryLengthPayloadResource(LeafResource):
    def render(self, request):
        return request.content.read()


class Root(resource.Resource):
    def __init__(self):
        resource.Resource.__init__(self)
        self.putChild(b"status", Status())
        self.putChild(b"follow", Follow())
        self.putChild(b"delay", Delay())
        self.putChild(b"partial", Partial())
        self.putChild(b"drop", Drop())
        self.putChild(b"raw", Raw())
        self.putChild(b"echo", Echo())
        self.putChild(b"payload", PayloadResource())
        self.putChild(
            b"xpayload",
            resource.EncodingResourceWrapper(PayloadResource(), [GzipEncoderFactory()]),
        )
        self.putChild(b"alpayload", ArbitraryLengthPayloadResource())
        try:
            from tests import tests_datadir

            self.putChild(b"files", File(str(Path(tests_datadir, "test_site/files/"))))
        except Exception:
            pass
        self.putChild(b"redirect-to", RedirectTo())

    def getChild(self, name, request):
        return self

    def render(self, request):
        return b"Scrapy mock HTTP server\n"


class MockServer:
    def __enter__(self):
        self.proc = Popen(
            [sys.executable, "-u", "-m", "tests.mockserver", "-t", "http"],
            stdout=PIPE,
            env=get_mockserver_env(),
        )
        http_address = self.proc.stdout.readline().strip().decode("ascii")
        https_address = self.proc.stdout.readline().strip().decode("ascii")

        self.http_address = http_address
        self.https_address = https_address

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.proc.kill()
        self.proc.communicate()

    def url(self, path, is_secure=False):
        host = self.https_address if is_secure else self.http_address
        host = host.replace("0.0.0.0", "127.0.0.1")
        return host + path


class MockDNSResolver:
    """
    Implements twisted.internet.interfaces.IResolver partially
    """

    def _resolve(self, name):
        record = dns.Record_A(address=b"127.0.0.1")
        answer = dns.RRHeader(name=name, payload=record)
        return [answer], [], []

    def query(self, query, timeout=None):
        if query.type == dns.A:
            return defer.succeed(self._resolve(query.name.name))
        return defer.fail(error.DomainError())

    def lookupAllRecords(self, name, timeout=None):
        return defer.succeed(self._resolve(name))


class MockDNSServer:
    def __enter__(self):
        self.proc = Popen(
            [sys.executable, "-u", "-m", "tests.mockserver", "-t", "dns"],
            stdout=PIPE,
            env=get_mockserver_env(),
        )
        self.host = "127.0.0.1"
        self.port = int(
            self.proc.stdout.readline().strip().decode("ascii").split(":")[1]
        )
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.proc.kill()
        self.proc.communicate()


class MockFTPServer:
    """Creates an FTP server on port 2121 with a default passwordless user
    (anonymous) and a temporary root path that you can read from the
    :attr:`path` attribute."""

    def __enter__(self):
        self.path = Path(mkdtemp())
        self.proc = Popen(
            [sys.executable, "-u", "-m", "tests.ftpserver", "-d", str(self.path)],
            stderr=PIPE,
            env=get_mockserver_env(),
        )
        for line in self.proc.stderr:
            if b"starting FTP server" in line:
                break
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        rmtree(str(self.path))
        self.proc.kill()
        self.proc.communicate()

    def url(self, path):
        return "ftp://127.0.0.1:2121/" + path


def ssl_context_factory(
    keyfile="keys/localhost.key", certfile="keys/localhost.crt", cipher_string=None
):
    factory = ssl.DefaultOpenSSLContextFactory(
        str(Path(__file__).parent / keyfile),
        str(Path(__file__).parent / certfile),
    )
    if cipher_string:
        ctx = factory.getContext()
        # disabling TLS1.3 because it unconditionally enables some strong ciphers
        ctx.set_options(SSL.OP_CIPHER_SERVER_PREFERENCE | SSL.OP_NO_TLSv1_3)
        ctx.set_cipher_list(to_bytes(cipher_string))
    return factory


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-t", "--type", type=str, choices=("http", "dns"), default="http"
    )
    args = parser.parse_args()

    factory: ServerFactory

    if args.type == "http":
        root = Root()
        factory = Site(root)
        httpPort = reactor.listenTCP(0, factory)
        contextFactory = ssl_context_factory()
        httpsPort = reactor.listenSSL(0, factory, contextFactory)

        def print_listening():
            httpHost = httpPort.getHost()
            httpsHost = httpsPort.getHost()
            httpAddress = f"http://{httpHost.host}:{httpHost.port}"
            httpsAddress = f"https://{httpsHost.host}:{httpsHost.port}"
            print(httpAddress)
            print(httpsAddress)

    elif args.type == "dns":
        clients = [MockDNSResolver()]
        factory = DNSServerFactory(clients=clients)
        protocol = dns.DNSDatagramProtocol(controller=factory)
        listener = reactor.listenUDP(0, protocol)

        def print_listening():
            host = listener.getHost()
            print(f"{host.host}:{host.port}")

    reactor.callWhenRunning(print_listening)
    reactor.run()
