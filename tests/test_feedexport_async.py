"""Tests for coroutine support in feed storages and item exporters."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from twisted.internet.defer import Deferred
from w3lib.url import file_uri_to_path

from scrapy.exporters import JsonLinesItemExporter
from scrapy.extensions.feedexport import FileFeedStorage
from scrapy.utils.asyncio import call_later
from scrapy.utils.defer import maybe_deferred_to_future
from tests.utils.decorators import coroutine_test
from tests.utils.feedexport import PARSERS, export_by_path, unique_path

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable

    from scrapy import Spider
    from tests.mockserver.http import MockServer


async def suspend() -> None:
    """Let other coroutines run before resuming the calling one.

    Unlike :func:`asyncio.sleep`, this works with any value of the
    :setting:`TWISTED_REACTOR` setting.
    """
    d: Deferred[None] = Deferred()
    call_later(0, d.callback, None)
    await maybe_deferred_to_future(d)


class CallTracker:
    """Base class for feed components that record their calls, and whether any
    of those calls overlap."""

    calls: dict[str, int] = {}
    active = 0
    max_active = 0

    @classmethod
    def reset(cls) -> None:
        CallTracker.calls = {}
        CallTracker.active = 0
        CallTracker.max_active = 0

    @asynccontextmanager
    async def tracked(self, name: str) -> AsyncIterator[None]:
        key = f"{type(self).__name__}.{name}"
        CallTracker.calls[key] = CallTracker.calls.get(key, 0) + 1
        CallTracker.active += 1
        CallTracker.max_active = max(CallTracker.max_active, CallTracker.active)
        try:
            await suspend()
            yield
        finally:
            CallTracker.active -= 1


class AsyncFeedStorage(CallTracker):
    """Feed storage that follows
    :class:`~scrapy.extensions.feedexport.FeedStorageProtocol` with coroutine
    ``open()`` and ``store()`` methods."""

    def __init__(self, uri: str, *, feed_options: dict[str, Any] | None = None):
        self.path: Path = Path(file_uri_to_path(uri))

    async def open(self, spider: Spider) -> IO[bytes]:
        async with self.tracked("open"):
            return self.path.open("wb")

    async def store(self, file: IO[bytes]) -> None:
        async with self.tracked("store"):
            file.close()


class DeferredFeedStorage(FileFeedStorage):
    """Feed storage whose ``store()`` method returns a
    :class:`~twisted.internet.defer.Deferred` object."""

    def store(self, file: IO[bytes]) -> Deferred[None]:
        d: Deferred[None] = Deferred()
        call_later(0, d.callback, None)
        return d.addCallback(lambda _: file.close())


class AsyncJsonLinesItemExporter(CallTracker, JsonLinesItemExporter):
    """Item exporter with coroutine ``start_exporting()``, ``export_item()``
    and ``finish_exporting()`` methods."""

    async def start_exporting(self) -> None:
        async with self.tracked("start_exporting"):
            super().start_exporting()

    async def export_item(self, item: Any) -> None:  # type: ignore[override]
        async with self.tracked("export_item"):
            super().export_item(item)

    async def finish_exporting(self) -> None:
        async with self.tracked("finish_exporting"):
            super().finish_exporting()


class TestAsyncFeedExport:
    items: list[dict[str, Any]] = [{"foo": f"bar{index}"} for index in range(10)]

    async def _export(
        self,
        mockserver: MockServer,
        tmp_path: Path,
        items: list[dict[str, Any]],
        settings: dict[str, Any],
    ) -> bytes:
        path = unique_path(tmp_path)
        settings = {**settings, "FEEDS": {path: {"format": "jl"}}}
        return (await export_by_path(mockserver, items, settings))[path]

    @staticmethod
    def _sorted(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(items, key=lambda item: item["foo"])

    def _parse_jsonlines(self, data: bytes) -> list[dict[str, Any]]:
        # Items are exported in scraping completion order, which is arbitrary.
        return self._sorted(PARSERS["jsonlines"](data))

    @coroutine_test
    async def test_storage(self, mockserver: MockServer, tmp_path: Path) -> None:
        CallTracker.reset()
        data = await self._export(
            mockserver,
            tmp_path,
            self.items,
            {"FEED_STORAGES": {"file": AsyncFeedStorage}},
        )
        assert CallTracker.calls == {
            "AsyncFeedStorage.open": 1,
            "AsyncFeedStorage.store": 1,
        }
        assert self._parse_jsonlines(data) == self._sorted(self.items)

    @coroutine_test
    async def test_storage_no_items(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        CallTracker.reset()
        data = await self._export(
            mockserver,
            tmp_path,
            [],
            {
                "FEED_STORAGES": {"file": AsyncFeedStorage},
                "FEED_STORE_EMPTY": True,
            },
        )
        assert CallTracker.calls == {
            "AsyncFeedStorage.open": 1,
            "AsyncFeedStorage.store": 1,
        }
        assert data == b""

    @coroutine_test
    async def test_storage_deferred_store(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        data = await self._export(
            mockserver,
            tmp_path,
            self.items,
            {"FEED_STORAGES": {"file": DeferredFeedStorage}},
        )
        assert self._parse_jsonlines(data) == self._sorted(self.items)

    @coroutine_test
    async def test_exporter(self, mockserver: MockServer, tmp_path: Path) -> None:
        CallTracker.reset()
        data = await self._export(
            mockserver,
            tmp_path,
            self.items,
            {"FEED_EXPORTERS": {"jl": AsyncJsonLinesItemExporter}},
        )
        assert CallTracker.calls == {
            "AsyncJsonLinesItemExporter.start_exporting": 1,
            "AsyncJsonLinesItemExporter.export_item": len(self.items),
            "AsyncJsonLinesItemExporter.finish_exporting": 1,
        }
        assert self._parse_jsonlines(data) == self._sorted(self.items)

    @coroutine_test
    async def test_exporter_no_items(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        CallTracker.reset()
        data = await self._export(
            mockserver,
            tmp_path,
            [],
            {
                "FEED_EXPORTERS": {"jl": AsyncJsonLinesItemExporter},
                "FEED_STORE_EMPTY": True,
            },
        )
        assert CallTracker.calls == {
            "AsyncJsonLinesItemExporter.start_exporting": 1,
            "AsyncJsonLinesItemExporter.finish_exporting": 1,
        }
        assert data == b""

    @coroutine_test
    async def test_calls_are_serialized(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        """Item export calls never overlap, even though items are scraped
        concurrently, so that components that keep state do not need to support
        concurrent calls."""
        CallTracker.reset()
        await self._export(
            mockserver,
            tmp_path,
            self.items,
            {
                "FEED_STORAGES": {"file": AsyncFeedStorage},
                "FEED_EXPORTERS": {"jl": AsyncJsonLinesItemExporter},
            },
        )
        assert CallTracker.max_active == 1
