# This is only used by tests.test_downloader_handlers_http_base.TestHttpProxyBase

from __future__ import annotations

import sys
from subprocess import PIPE, Popen
from urllib.parse import urlparse

from twisted.web.server import Site

from tests.mockserver.http_resources import UriResource
from tests.mockserver.utils import ssl_context_factory
from tests.utils import get_script_run_env


class ProxyEchoMockServer:
    def __enter__(self):
        self.proc = Popen(
            [sys.executable, "-u", "-m", "tests.mockserver.proxy_echo"],
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

    factory = Site(UriResource())
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
