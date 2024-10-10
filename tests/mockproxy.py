"""A basic authenticated HTTP proxy supporting CONNECT."""

# based on https://github.com/fmoo/twisted-connect-proxy by Peter Ruibal
from __future__ import annotations

import binascii
import sys
from typing import Optional, Tuple

from twisted.internet import reactor
from twisted.internet.protocol import ClientFactory, Protocol
from twisted.web.http import HTTPFactory
from twisted.web.proxy import Proxy, ProxyRequest


class ConnectProxyRequest(ProxyRequest):
    """HTTP ProxyRequest handler (factory) that supports CONNECT"""

    def process(self) -> None:
        if not self.check_auth():
            self.return_407()
            return

        if self.method == b"CONNECT":
            self.process_connect_request()
        else:
            super().process()

    def check_auth(self) -> bool:
        auth_header = self.getHeader(b"Proxy-Authorization")
        if not auth_header:
            return False
        self.requestHeaders.removeHeader(b"Proxy-Authorization")
        scheme, authinfo = auth_header.split(None, 1)
        if scheme.lower() != b"basic":
            return False
        try:
            user, password = binascii.a2b_base64(authinfo).split(b":", 1)
        except binascii.Error:
            return False
        assert isinstance(self.channel.factory, HTTPFactoryWithCreds)
        return (
            user == self.channel.factory.auth_user
            and password == self.channel.factory.auth_pass
        )

    def return_407(self):
        self.setResponseCode(407, b"Proxy Authentication Required")
        self.finish()

    @staticmethod
    def split_host_port(target: bytes) -> Tuple[bytes, int]:
        parts = target.split(b":", 1)
        port = int(parts[1])
        return parts[0], port

    def process_connect_request(self) -> None:
        host, port = self.split_host_port(self.uri)
        client_factory = ConnectProxyClientFactory(host, port, self)
        self.reactor.connectTCP(host, port, client_factory)


class ConnectProxy(Proxy):
    """HTTP Server Protocol that supports CONNECT"""

    requestFactory = ConnectProxyRequest
    connected_remote: Optional[ConnectProxyClient] = None

    def requestDone(self, request):
        if request.method == b"CONNECT" and self.connected_remote is not None:
            self.connected_remote.connectedClient = self
            self._handlingRequest = False
            self._networkProducer.resumeProducing()
            if self._savedTimeOut:
                self.setTimeout(self._savedTimeOut)
            data = b"".join(self._dataBuffer)
            self._dataBuffer = []
            self.setLineMode(data)
        else:
            super().requestDone(request)

    def connectionLost(self, reason):
        if self.connected_remote is not None:
            self.connected_remote.transport.loseConnection()
        super().connectionLost(reason)

    def dataReceived(self, data):
        if self.connected_remote is None:
            super().dataReceived(data)
        else:
            # Once proxy is connected, forward all bytes received
            # from the original client to the remote server.
            self.connected_remote.transport.write(data)


class ConnectProxyClient(Protocol):
    connectedClient = None

    def connectionMade(self):
        self.factory.request.channel.connected_remote = self
        self.factory.request.setResponseCode(200, b"CONNECT OK")
        self.factory.request.setHeader("X-Connected-IP", self.transport.realAddress[0])
        self.factory.request.setHeader("Content-Length", "0")
        self.factory.request.finish()

    def connectionLost(self, reason):
        if self.connectedClient is not None:
            self.connectedClient.transport.loseConnection()

    def dataReceived(self, data):
        if self.connectedClient is not None:
            # Forward all bytes from the remote server back to the
            # original connected client
            self.connectedClient.transport.write(data)


class ConnectProxyClientFactory(ClientFactory):
    protocol = ConnectProxyClient

    def __init__(self, host, port, request):
        self.request = request
        self.host = host
        self.port = port

    def clientConnectionFailed(self, connector, reason):
        self.request.fail("Gateway Error", str(reason))


class HTTPFactoryWithCreds(HTTPFactory):
    auth_user = auth_pass = b""


if __name__ == "__main__":
    factory = HTTPFactoryWithCreds()
    factory.protocol = ConnectProxy  # type: ignore[has-type]
    if len(sys.argv) > 1:
        factory.auth_user = sys.argv[1].encode()
    if len(sys.argv) > 2:
        factory.auth_pass = sys.argv[2].encode()

    listener = reactor.listenTCP(0, factory, interface="127.0.0.1")

    def print_listening():
        host = listener.getHost()
        print(f"{host.host}:{host.port}")

    reactor.callWhenRunning(print_listening)
    reactor.run()
