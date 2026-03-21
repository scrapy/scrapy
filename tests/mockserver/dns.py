from __future__ import annotations

import sys
from subprocess import PIPE, Popen

from twisted.internet import defer
from twisted.names import dns, error
from twisted.names.server import DNSServerFactory

from tests.utils import get_script_run_env


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
            [sys.executable, "-u", "-m", "tests.mockserver.dns"],
            stdout=PIPE,
            env=get_script_run_env(),
        )
        self.host = "127.0.0.1"
        self.port = int(
            self.proc.stdout.readline().strip().decode("ascii").split(":")[1]
        )
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.proc.kill()
        self.proc.communicate()


def main() -> None:
    from twisted.internet import reactor

    clients = [MockDNSResolver()]
    factory = DNSServerFactory(clients=clients)
    protocol = dns.DNSDatagramProtocol(controller=factory)
    listener = reactor.listenUDP(0, protocol)

    def print_listening():
        host = listener.getHost()
        print(f"{host.host}:{host.port}")

    reactor.callWhenRunning(print_listening)
    reactor.run()


if __name__ == "__main__":
    main()
