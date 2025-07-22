# This is only used by tests.test_downloader_handlers_http_base.TestSimpleHttpsBase

from __future__ import annotations

import sys
from subprocess import PIPE, Popen
from urllib.parse import urlparse

from twisted.web import resource
from twisted.web.server import Site
from twisted.web.static import Data

from tests.utils import get_script_run_env

from .utils import ssl_context_factory


class Root(resource.Resource):
    def __init__(self):
        resource.Resource.__init__(self)
        self.putChild(b"file", Data(b"0123456789", "text/plain"))

    def getChild(self, name, request):
        return self


class SimpleMockServer:
    def __init__(self, keyfile: str, certfile: str, cipher_string: str | None):
        self.keyfile: str = keyfile
        self.certfile: str = certfile
        self.cipher_string: str = cipher_string or ""

    def __enter__(self):
        self.proc = Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "tests.mockserver.simple_https",
                self.keyfile,
                self.certfile,
                self.cipher_string,
            ],
            stdout=PIPE,
            env=get_script_run_env(),
        )
        https_address = self.proc.stdout.readline().strip().decode("ascii")
        https_parsed = urlparse(https_address)
        self.host = "127.0.0.1"
        self.port = https_parsed.port
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.proc.kill()
        self.proc.communicate()

    def url(self, path: str) -> str:
        return f"https://{self.host}:{self.port}{path}"


def main() -> None:
    from twisted.internet import reactor

    keyfile, certfile, cipher_string = sys.argv[-3:]
    root = Root()
    factory = Site(root)
    contextFactory = ssl_context_factory(keyfile, certfile, cipher_string)
    httpsPort = reactor.listenSSL(0, factory, contextFactory)

    def print_listening():
        httpsHost = httpsPort.getHost()
        httpsAddress = f"https://{httpsHost.host}:{httpsHost.port}"
        print(httpsAddress)

    reactor.callWhenRunning(print_listening)
    reactor.run()


if __name__ == "__main__":
    main()
