"""An HTTP proxy that never answers ``CONNECT`` requests."""

from __future__ import annotations

import socket
import threading
from typing import TYPE_CHECKING

from scrapy.utils.asyncio import sleep

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self


class StallingProxyConnection:
    """A connection received by :class:`StallingProxy`."""

    def __init__(self, sock: socket.socket) -> None:
        self._socket = sock
        #: Bytes read from the client, i.e. its ``CONNECT`` request.
        self.request: bytes = b""
        #: Whether the client has closed the connection.
        self.closed: bool = False

    def close(self) -> None:
        self._socket.close()

    def _read(self) -> None:
        while True:
            try:
                data = self._socket.recv(4096)
            except OSError:
                break
            if not data:  # the client closed the connection
                break
            self.request += data
        self.closed = True

    async def wait_closed(self, timeout: float = 10.0) -> bool:
        """Wait for the client to close the connection, and return whether it
        did so within *timeout* seconds."""
        for _ in range(int(timeout / 0.05)):
            if self.closed:
                return True
            await sleep(0.05)
        return self.closed


class StallingProxy:
    """An HTTP proxy that reads requests and never answers them, so that
    downloads through it can only finish with a timeout.

    It is meant to be used with HTTPS targets, to stall the ``CONNECT``
    handshake, and it can tell whether the client closed the connection::

        with StallingProxy() as proxy:
            request = Request(
                "https://example.com", meta={"proxy": proxy.url, ...}
            )
            ...
            connection = await proxy.wait_for_connection()
            assert await connection.wait_closed()

    It uses blocking sockets on separate threads, instead of the Twisted-based
    approach of the other mock servers, so that it works with any reactor, and
    so that a client connection being closed is detected even while the reactor
    is busy.
    """

    def __init__(self) -> None:
        self._socket = socket.socket()
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.listen(10)
        self.host, self.port = self._socket.getsockname()
        self.connections: list[StallingProxyConnection] = []

    def __enter__(self) -> Self:
        threading.Thread(target=self._accept, daemon=True).start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._socket.close()
        for connection in self.connections:
            connection.close()

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _accept(self) -> None:
        while True:
            try:
                sock, _ = self._socket.accept()
            except OSError:  # the proxy was stopped
                return
            connection = StallingProxyConnection(sock)
            self.connections.append(connection)
            threading.Thread(target=connection._read, daemon=True).start()

    async def wait_for_connection(
        self, timeout: float = 10.0
    ) -> StallingProxyConnection:
        """Wait for a client connection with a complete request, and return it."""
        for _ in range(int(timeout / 0.05)):
            if self.connections and b"\r\n\r\n" in self.connections[0].request:
                return self.connections[0]
            await sleep(0.05)
        raise AssertionError(f"No request reached the proxy in {timeout} seconds")
