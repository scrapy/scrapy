from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy.exceptions import DownloadFailedError
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
    """Response to a WebSocket handshake request, with methods to send and
    receive messages over the connection that the handshake established.

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

    attributes: tuple[str, ...] = (*Response.attributes, "_connection")

    __slots__ = ("_connection", "_connection_closed")

    def __init__(self, *args: Any, _connection: ClientConnection, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._connection: ClientConnection = _connection
        # The downloader reads this to know when the connection stops
        # occupying its slot.
        self._connection_closed: Deferred[None] = deferred_from_coro(
            _connection.wait_closed()
        )

    async def send(self, message: str | bytes) -> None:
        """Send *message* to the server."""
        await self._connection.send(message)

    async def receive(self) -> str | bytes:
        """Return the next message from the server.

        Raises :exc:`~scrapy.exceptions.DownloadFailedError` if the
        connection is closed, e.g. because a message went over
        :setting:`DOWNLOAD_MAXSIZE`.
        """
        from websockets.exceptions import ConnectionClosed  # noqa: PLC0415

        try:
            return await self._connection.recv()
        except ConnectionClosed as e:
            raise DownloadFailedError(str(e)) from e

    async def close(self) -> None:
        """Close the connection."""
        await self._connection.close()

    async def _release(self) -> None:
        await self.close()

    def __aiter__(self) -> AsyncIterator[str | bytes]:
        return self._iter_messages()

    async def _iter_messages(self) -> AsyncIterator[str | bytes]:
        from websockets.exceptions import ConnectionClosedError  # noqa: PLC0415

        try:
            async for message in self._connection:
                yield message
        except ConnectionClosedError as e:
            raise DownloadFailedError(str(e)) from e

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()
