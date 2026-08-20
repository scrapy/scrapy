from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy.http.response import Response
from scrapy.utils.defer import deferred_from_coro

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from types import TracebackType

    from twisted.internet.defer import Deferred

    # typing.Self requires Python 3.11
    from typing_extensions import Self
    from websockets.asyncio.client import ClientConnection


class WebSocketResponse(Response):
    """Response to a WebSocket handshake request, which gives access to the
    WebSocket connection that the handshake established.

    .. versionadded:: VERSION

    Iterating a WebSocket response yields incoming messages, as :class:`str`
    for text messages and as :class:`bytes` for binary ones:

    .. code-block:: python

        async def parse(self, response):
            async with response:
                await response.send("subscribe")
                async for message in response:
                    yield {"message": message}

    See :ref:`websockets`.
    """

    attributes: tuple[str, ...] = (*Response.attributes, "connection")

    __slots__ = ("_connection_closed", "connection")

    def __init__(self, *args: Any, connection: ClientConnection, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.connection: ClientConnection = connection
        """The underlying :class:`websockets.asyncio.client.ClientConnection`
        object, for features that this class does not expose, such as
        :meth:`~websockets.asyncio.client.ClientConnection.recv_streaming` or
        :attr:`~websockets.asyncio.client.ClientConnection.subprotocol`."""
        # The downloader reads this to know when the connection stops
        # occupying its slot.
        self._connection_closed: Deferred[None] = deferred_from_coro(
            connection.wait_closed()
        )

    async def send(self, message: str | bytes) -> None:
        """Send *message* to the server."""
        await self.connection.send(message)

    async def receive(self) -> str | bytes:
        """Return the next message from the server."""
        return await self.connection.recv()

    async def close(self) -> None:
        """Close the connection."""
        await self.connection.close()

    async def _release(self) -> None:
        await self.close()

    def __aiter__(self) -> AsyncIterator[str | bytes]:
        return aiter(self.connection)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()
