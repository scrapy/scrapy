from __future__ import annotations

import sys
from pathlib import Path
from subprocess import PIPE, Popen
from urllib.parse import urlparse

from twisted.web import resource
from twisted.web.server import Site
from twisted.web.static import Data, File
from twisted.web.util import Redirect

from tests import tests_datadir
from tests.utils import get_script_run_env

from .http_resources import (
    ArbitraryLengthPayloadResource,
    BrokenChunkedResource,
    BrokenDownloadResource,
    ChunkedResource,
    ContentLengthHeaderResource,
    Delay,
    Drop,
    DuplicateHeaderResource,
    Echo,
    EmptyContentTypeHeaderResource,
    Follow,
    ForeverTakingResource,
    HostHeaderResource,
    LargeChunkedFileResource,
    NoMetaRefreshRedirect,
    Partial,
    PayloadResource,
    Raw,
    RedirectTo,
    Status,
)
from .utils import ssl_context_factory


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
        self.putChild(b"alpayload", ArbitraryLengthPayloadResource())
        self.putChild(b"static", File(str(Path(tests_datadir, "test_site/"))))
        self.putChild(b"redirect-to", RedirectTo())
        self.putChild(b"text", Data(b"Works", "text/plain"))
        self.putChild(
            b"html",
            Data(
                b"<body><p class='one'>Works</p><p class='two'>World</p></body>",
                "text/html",
            ),
        )
        self.putChild(
            b"enc-gb18030",
            Data(b"<p>gb18030 encoding</p>", "text/html; charset=gb18030"),
        )
        self.putChild(b"redirect", Redirect(b"/redirected"))
        self.putChild(
            b"redirect-no-meta-refresh", NoMetaRefreshRedirect(b"/redirected")
        )
        self.putChild(b"redirected", Data(b"Redirected here", "text/plain"))
        numbers = [str(x).encode("utf8") for x in range(2**18)]
        self.putChild(b"numbers", Data(b"".join(numbers), "text/plain"))
        self.putChild(b"wait", ForeverTakingResource())
        self.putChild(b"hang-after-headers", ForeverTakingResource(write=True))
        self.putChild(b"host", HostHeaderResource())
        self.putChild(b"broken", BrokenDownloadResource())
        self.putChild(b"chunked", ChunkedResource())
        self.putChild(b"broken-chunked", BrokenChunkedResource())
        self.putChild(b"contentlength", ContentLengthHeaderResource())
        self.putChild(b"nocontenttype", EmptyContentTypeHeaderResource())
        self.putChild(b"largechunkedfile", LargeChunkedFileResource())
        self.putChild(b"duplicate-header", DuplicateHeaderResource())

    def getChild(self, name, request):
        return self

    def render(self, request):
        return b"Scrapy mock HTTP server\n"


class MockServer:
    def __enter__(self):
        self.proc = Popen(
            [sys.executable, "-u", "-m", "tests.mockserver.http"],
            stdout=PIPE,
            env=get_script_run_env(),
        )
        http_address = self.proc.stdout.readline().strip().decode("ascii")
        https_address = self.proc.stdout.readline().strip().decode("ascii")

        http_parsed = urlparse(http_address)
        https_parsed = urlparse(https_address)
        self.host = "127.0.0.1"
        self.http_port = http_parsed.port
        self.https_port = https_parsed.port
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.proc.kill()
        self.proc.communicate()

    def port(self, is_secure: bool = False) -> int:
        return self.https_port if is_secure else self.http_port

    def url(self, path: str, is_secure: bool = False) -> str:
        port = self.port(is_secure)
        scheme = "https" if is_secure else "http"
        return f"{scheme}://{self.host}:{port}{path}"


def main() -> None:
    from twisted.internet import reactor

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

    reactor.callWhenRunning(print_listening)
    reactor.run()


if __name__ == "__main__":
    main()
