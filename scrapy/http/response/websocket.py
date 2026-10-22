from __future__ import annotations

import logging
import weakref
from typing import TYPE_CHECKING, Any, Self

from scrapy.exceptions import DownloadFailedError
from scrapy.http.response import Response
from scrapy.utils.defer import deferred_from_coro

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from types import TracebackType

    from twisted.internet.defer import Deferred
    from websockets.asyncio.client import ClientConnection


logger = logging.getLogger(__name__)


class _ConnectionOwner:
    """Object that every response of a connection holds, which closes the
    connection once none of those responses is left."""

    __slots__ = ("__weakref__",)


# Copies of a response, e.g. from Response.replace(), share the owner of the
# original response, so the connection stays open while any of them is in use.
_owners: weakref.WeakValueDictionary[ClientConnection, _ConnectionOwner] = (
    weakref.WeakValueDictionary()
)


def _get_owner(connection: ClientConnection) -> _ConnectionOwner:
    owner = _owners.get(connection)
    if owner is None:
        owner = _owners[connection] = _ConnectionOwner()
        weakref.finalize(owner, _close_soon, connection).atexit = False
    return owner


def _close_soon(connection: ClientConnection) -> None:
    # The handler closes every connection when the crawl ends, so there is
    # nothing left to close once the loop is closed.
    if not connection.loop.is_closed():
        # Garbage collection may happen in any thread.
        connection.loop.call_soon_threadsafe(_close, connection)


def _close(connection: ClientConnection) -> None:
    connection.loop.create_task(connection.close())


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

    attributes: tuple[str, ...] = (*Response.attributes, "_connection", "_warnsize")

    __slots__ = ("_connection", "_connection_closed", "_owner", "_warnsize")

    def __init__(
        self,
        *args: Any,
        _connection: ClientConnection,
        _warnsize: int = 0,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self._connection: ClientConnection = _connection
        self._owner: _ConnectionOwner = _get_owner(_connection)
        # Set to 0 after the first warning, to warn once per connection.
        self._warnsize: int = _warnsize
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
            message = await self._connection.recv()
        except ConnectionClosed as e:
            raise DownloadFailedError(str(e)) from e
        self._check_warnsize(message)
        return message

    def _check_warnsize(self, message: str | bytes) -> None:
        if not self._warnsize:
            return
        size = len(message.encode() if isinstance(message, str) else message)
        if size > self._warnsize:
            logger.warning(
                f"Received a {size}-byte message, larger than the download"
                f" warn size ({self._warnsize}), from {self.url}."
            )
            self._warnsize = 0

    async def close(self) -> None:
        """Close the connection."""
        await self._connection.close()

    def __aiter__(self) -> AsyncIterator[str | bytes]:
        return self._iter_messages()

    async def _iter_messages(self) -> AsyncIterator[str | bytes]:
        from websockets.exceptions import ConnectionClosedError  # noqa: PLC0415

        try:
            async for message in self._connection:
                self._check_warnsize(message)
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
