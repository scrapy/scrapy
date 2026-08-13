from __future__ import annotations

import sys
from subprocess import PIPE, Popen
from typing import TYPE_CHECKING

from twisted.internet import defer
from twisted.names import dns, error
from twisted.names.server import DNSServerFactory

from tests.utils import get_script_run_env

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType

    from twisted.internet.defer import Deferred

    # typing.Self requires Python 3.11
    from typing_extensions import Self


_Answers = tuple[list[dns.RRHeader], list[dns.RRHeader], list[dns.RRHeader]]


class MockDNSResolver:
    """
    Implements twisted.internet.interfaces.IResolver partially
    """

    def _resolve(self, name: bytes) -> _Answers:
        record = dns.Record_A(address=b"127.0.0.1")
        # zope.interface has no type hints, so mypy cannot tell that Record_A
        # provides the IEncodableRecord interface.
        answer = dns.RRHeader(name=name, payload=record)  # type: ignore[arg-type]
        return [answer], [], []

    def query(
        self, query: dns.Query, timeout: Sequence[int] | None = None
    ) -> Deferred[_Answers]:
        if query.type == dns.A:
            return defer.succeed(self._resolve(query.name.name))
        return defer.fail(error.DomainError())

    def lookupAllRecords(
        self, name: bytes, timeout: Sequence[int] | None = None
    ) -> Deferred[_Answers]:
        return defer.succeed(self._resolve(name))


class MockDNSServer:
    def __enter__(self) -> Self:
        self.proc = Popen(
            [sys.executable, "-u", "-m", "tests.mockserver.dns"],
            stdout=PIPE,
            env=get_script_run_env(),
            text=True,
        )
        assert self.proc.stdout is not None
        self.host = "127.0.0.1"
        self.port = int(self.proc.stdout.readline().strip().split(":")[1])
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.proc.kill()
        self.proc.communicate()


def main() -> None:
    from twisted.internet import reactor

    clients = [MockDNSResolver()]
    factory = DNSServerFactory(clients=clients)
    protocol = dns.DNSDatagramProtocol(controller=factory)
    listener = reactor.listenUDP(0, protocol)

    def print_listening() -> None:
        host = listener.getHost()
        print(f"{host.host}:{host.port}")

    reactor.callWhenRunning(print_listening)
    reactor.run()


if __name__ == "__main__":
    main()
