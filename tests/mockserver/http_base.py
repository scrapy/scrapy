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

    # typing.Self requires Python 3.11
    from typing_extensions import Self


class BaseMockServer(ABC):
    listen_http: bool = True
    listen_https: bool = True

    @property
    @abstractmethod
    def module_name(self) -> str:
        raise NotImplementedError

    def __init__(self, host: str | None = None) -> None:
        """Start a mockserver.

        *host* is the address to listen on; by default every interface is bound
        and requests are made to 127.0.0.1. Pass e.g. ``"::1"`` to test over
        IPv6.
        """
        if not self.listen_http and not self.listen_https:
            raise ValueError("At least one of listen_http and listen_https must be set")

        self.proc: Popen[str] | None = None
        self.host: str = host if host is not None else "127.0.0.1"
        self._listen_host: str | None = host
        self.http_port: int | None = None
        self.https_port: int | None = None

    def __enter__(self) -> Self:
        host_args = (
            ["--host", self._listen_host] if self._listen_host is not None else []
        )
        self.proc = Popen(
            [
                sys.executable,
                "-u",
                "-m",
                self.module_name,
                *host_args,
                *self.get_additional_args(),
            ],
            stdout=PIPE,
            env=get_script_run_env(),
            text=True,
        )
        assert self.proc.stdout is not None
        if self.listen_http:
            http_address = self.proc.stdout.readline().strip()
            http_parsed = urlparse(http_address)
            self.http_port = http_parsed.port
        if self.listen_https:
            https_address = self.proc.stdout.readline().strip()
            https_parsed = urlparse(https_address)
            self.https_port = https_parsed.port
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
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
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{scheme}://{host}:{port}{path}"


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

        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--host",
            default="",
            help="Address to listen on, e.g. ::1 for the IPv6 loopback. "
            "Every interface is bound by default.",
        )
        parser.add_argument("--keyfile", help="SSL key file")
        parser.add_argument("--certfile", help="SSL certificate file")
        parser.add_argument(
            "--cipher-string",
            default=None,
            help="SSL cipher string (optional)",
        )
        parser.add_argument(
            "--tls-min-version",
            default=None,
            help="Minimum accepted TLS version (optional)",
        )
        parser.add_argument(
            "--tls-max-version",
            default=None,
            help="Maximum accepted TLS version (optional)",
        )
        args = parser.parse_args()

        root = resource_class()
        factory = Site(root)

        if listen_http:
            http_port = reactor.listenTCP(0, factory, interface=args.host)

        if listen_https:
            context_factory_kw = {}
            if args.keyfile:
                context_factory_kw["keyfile"] = args.keyfile
            if args.certfile:
                context_factory_kw["certfile"] = args.certfile
            if args.cipher_string:
                context_factory_kw["cipher_string"] = args.cipher_string
            if args.tls_min_version:
                context_factory_kw["tls_min_version"] = args.tls_min_version
            if args.tls_max_version:
                context_factory_kw["tls_max_version"] = args.tls_max_version
            context_factory = ssl_context_factory(**context_factory_kw)
            https_port = reactor.listenSSL(
                0, factory, context_factory, interface=args.host
            )

        def print_listening():
            def address(scheme: str, listening_port) -> str:
                listening_host = listening_port.getHost()
                host = listening_host.host
                if ":" in host:  # IPv6 literal
                    host = f"[{host}]"
                return f"{scheme}://{host}:{listening_host.port}"

            if listen_http:
                print(address("http", http_port))
            if listen_https:
                print(address("https", https_port))

        reactor.callWhenRunning(print_listening)
        reactor.run()

    return main
