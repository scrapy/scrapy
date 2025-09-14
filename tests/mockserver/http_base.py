"""Base classes and functions for HTTP mockservers."""

from __future__ import annotations

import argparse
import sys
from abc import ABC, abstractmethod
from subprocess import PIPE, Popen
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from twisted.web.server import Site

from tests.utils import get_script_run_env

from .utils import ssl_context_factory

if TYPE_CHECKING:
    from collections.abc import Callable

    from twisted.web import resource


class BaseMockServer(ABC):
    listen_http: bool = True
    listen_https: bool = True

    @property
    @abstractmethod
    def module_name(self) -> str:
        raise NotImplementedError

    def __init__(self) -> None:
        if not self.listen_http and not self.listen_https:
            raise ValueError("At least one of listen_http and listen_https must be set")

        self.proc: Popen | None = None
        self.host: str = "127.0.0.1"
        self.http_port: int | None = None
        self.https_port: int | None = None

    def __enter__(self):
        self.proc = Popen(
            [sys.executable, "-u", "-m", self.module_name, *self.get_additional_args()],
            stdout=PIPE,
            env=get_script_run_env(),
        )
        if self.listen_http:
            http_address = self.proc.stdout.readline().strip().decode("ascii")
            http_parsed = urlparse(http_address)
            self.http_port = http_parsed.port
        if self.listen_https:
            https_address = self.proc.stdout.readline().strip().decode("ascii")
            https_parsed = urlparse(https_address)
            self.https_port = https_parsed.port
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.proc:
            self.proc.kill()
            self.proc.communicate()

    def get_additional_args(self) -> list[str]:
        return []

    def port(self, is_secure: bool = False) -> int:
        if not is_secure and not self.listen_http:
            raise ValueError("This server doesn't provide HTTP")
        if is_secure and not self.listen_https:
            raise ValueError("This server doesn't provide HTTPS")
        port = self.https_port if is_secure else self.http_port
        assert port is not None
        return port

    def url(self, path: str, is_secure: bool = False) -> str:
        port = self.port(is_secure)
        scheme = "https" if is_secure else "http"
        return f"{scheme}://{self.host}:{port}{path}"


def main_factory(
    resource_class: type[resource.Resource],
    *,
    listen_http: bool = True,
    listen_https: bool = True,
) -> Callable[[], None]:
    if not listen_http and not listen_https:
        raise ValueError("At least one of listen_http and listen_https must be set")

    def main() -> None:
        from twisted.internet import reactor

        root = resource_class()
        factory = Site(root)

        if listen_http:
            http_port = reactor.listenTCP(0, factory)

        if listen_https:
            parser = argparse.ArgumentParser()
            parser.add_argument("--keyfile", help="SSL key file")
            parser.add_argument("--certfile", help="SSL certificate file")
            parser.add_argument(
                "--cipher-string",
                default=None,
                help="SSL cipher string (optional)",
            )
            args = parser.parse_args()
            context_factory_kw = {}
            if args.keyfile:
                context_factory_kw["keyfile"] = args.keyfile
            if args.certfile:
                context_factory_kw["certfile"] = args.certfile
            if args.cipher_string:
                context_factory_kw["cipher_string"] = args.cipher_string
            context_factory = ssl_context_factory(**context_factory_kw)
            https_port = reactor.listenSSL(0, factory, context_factory)

        def print_listening():
            if listen_http:
                http_host = http_port.getHost()
                http_address = f"http://{http_host.host}:{http_host.port}"
                print(http_address)
            if listen_https:
                https_host = https_port.getHost()
                https_address = f"https://{https_host.host}:{https_host.port}"
                print(https_address)

        reactor.callWhenRunning(print_listening)
        reactor.run()

    return main
