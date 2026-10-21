from __future__ import annotations

import socketserver
import threading
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from collections.abc import Iterable


class _RawHttpHandler(socketserver.BaseRequestHandler):
    server: RawHttpServer

    def handle(self) -> None:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = self.request.recv(65536)
            if not chunk:
                return
            data += chunk
        self.server.request_heads.append(data.partition(b"\r\n\r\n")[0])
        header_lines = b"".join(
            name + b": " + value + b"\r\n"
            for name, value in self.server.response_headers
        )
        self.request.sendall(
            b"HTTP/1.1 200 OK\r\n"
            + header_lines
            + b"Content-Length: 0\r\nConnection: close\r\n\r\n"
        )


class RawHttpServer(socketserver.ThreadingTCPServer):
    """An HTTP/1.1 server that keeps the bytes of the request heads it
    receives and answers every request with *response_headers* as they are.

    Unlike the Twisted-based mock servers, it does not change the case of
    header names, so tests can check them as they are on the wire.

    It runs on a separate thread, so it works with and without a reactor.
    """

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, response_headers: Iterable[tuple[bytes, bytes]] = ()) -> None:
        super().__init__(("127.0.0.1", 0), _RawHttpHandler)
        self.response_headers: list[tuple[bytes, bytes]] = list(response_headers)
        #: Request lines and header lines of the received requests.
        self.request_heads: list[bytes] = []
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.shutdown()
        self.server_close()
        self._thread.join()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    def request_header_names(self) -> list[bytes]:
        """Return the header names of the last received request, as sent."""
        return [
            line.partition(b":")[0]
            for line in self.request_heads[-1].split(b"\r\n")[1:]
        ]
