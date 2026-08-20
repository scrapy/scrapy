from __future__ import annotations

import asyncio
import json
import ssl
from pathlib import Path
from typing import TYPE_CHECKING

from websockets.asyncio.server import serve

from .http_base import BaseMockServer

if TYPE_CHECKING:
    from websockets.asyncio.server import ServerConnection
    from websockets.http11 import Request, Response


async def handler(connection: ServerConnection) -> None:
    assert connection.request is not None
    path = connection.request.path
    if path == "/echo":
        async for message in connection:
            await connection.send(message)
    elif path == "/headers":
        await connection.send(
            json.dumps(dict(connection.request.headers.raw_items())),
        )
        await connection.wait_closed()
    elif path == "/push":
        # Server push: messages arrive without the client asking for them.
        for index in range(3):
            await connection.send(f"push {index}")
    elif path == "/binary":
        await connection.send(b"\x00\x01\x02")
        await connection.wait_closed()
    elif path == "/large":
        await connection.send("x" * 1000)
        await connection.wait_closed()
    else:
        await connection.close(1011, f"unknown path: {path}")


def process_request(connection: ServerConnection, request: Request) -> Response | None:
    """Reject the handshake for the paths that test non-101 responses."""
    if request.path == "/unavailable":
        return connection.respond(503, "Service Unavailable")
    if request.path == "/redirect":
        response = connection.respond(301, "Moved Permanently")
        response.headers["Location"] = "/echo"
        return response
    return None


async def serve_forever() -> None:
    keys = Path(__file__).parent.parent / "keys"
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(keys / "localhost.crt", keys / "localhost.key")

    async with (
        serve(handler, "127.0.0.1", 0, process_request=process_request) as plain,
        serve(
            handler, "127.0.0.1", 0, ssl=ssl_context, process_request=process_request
        ) as secure,
    ):
        for scheme, server in (("ws", plain), ("wss", secure)):
            port = server.sockets[0].getsockname()[1]
            print(f"{scheme}://127.0.0.1:{port}", flush=True)
        await asyncio.gather(plain.serve_forever(), secure.serve_forever())


class WebSocketMockServer(BaseMockServer):
    module_name = "tests.mockserver.websocket"

    def url(self, path: str, is_secure: bool = False) -> str:
        port = self.port(is_secure)
        scheme = "wss" if is_secure else "ws"
        return f"{scheme}://{self.host}:{port}{path}"


def main() -> None:
    asyncio.run(serve_forever())


if __name__ == "__main__":
    main()
