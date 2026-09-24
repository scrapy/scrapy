"""A plain-socket HTTP/1.1 server that records the raw request heads it
receives, to check the exact header names, case and order sent on the wire.

It runs in a thread, so it works with and without a Twisted reactor.
"""

from __future__ import annotations

import socketserver
import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


class _CapturingHandler(socketserver.BaseRequestHandler):
    server: _CapturingServer

    def handle(self) -> None:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = self.request.recv(65536)
            if not chunk:
                return
            data += chunk
        head, _, body = data.partition(b"\r\n\r\n")
        self.server.heads.append(head)
        content_length = next(
            (
                int(line.split(b":", 1)[1])
                for line in head.split(b"\r\n")[1:]
                if line.lower().startswith(b"content-length:")
            ),
            0,
        )
        while len(body) < content_length:
            chunk = self.request.recv(65536)
            if not chunk:
                break
            body += chunk
        self.request.sendall(
            b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        )


class _CapturingServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _CapturingHandler)
        self.heads: list[bytes] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    def request_line(self, index: int = -1) -> bytes:
        return self.heads[index].split(b"\r\n")[0]

    def header_lines(self, index: int = -1) -> list[tuple[bytes, bytes]]:
        """``(name, value)`` pairs of a received request, as sent."""
        result = []
        for line in self.heads[index].split(b"\r\n")[1:]:
            name, value = line.split(b":", 1)
            result.append((name, value.strip()))
        return result

    def header_names(self, index: int = -1) -> list[bytes]:
        return [name for name, _ in self.header_lines(index)]


@contextmanager
def capturing_server() -> Iterator[_CapturingServer]:
    server = _CapturingServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
