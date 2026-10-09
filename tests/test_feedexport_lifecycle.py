from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from unittest import mock

from scrapy.exporters import JsonItemExporter
from scrapy.extensions.feedexport import FeedSlot
from tests.utils.decorators import coroutine_test
from tests.utils.feedexport import MyItem, export_by_format, unique_path

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest

    from tests.mockserver.http import MockServer


class InstrumentedFeedSlot(FeedSlot):
    """Instrumented FeedSlot subclass for keeping track of calls to
    start_exporting and finish_exporting."""

    update_listener: Callable[[str], None]

    async def start_exporting(self):
        self.update_listener("start")
        await super().start_exporting()

    async def finish_exporting(self):
        self.update_listener("finish")
        await super().finish_exporting()

    @classmethod
    def subscribe__listener(cls, listener: IsExportingListener) -> None:
        cls.update_listener = listener.update


class IsExportingListener:
    """When subscribed to InstrumentedFeedSlot, keeps track of when
    a call to start_exporting has been made without a closing call to
    finish_exporting and when a call to finish_exporting has been made
    before a call to start_exporting."""

    def __init__(self) -> None:
        self.start_without_finish = False
        self.finish_without_start = False

    def update(self, method):
        if method == "start":
            self.start_without_finish = True
        elif method == "finish":
            if self.start_without_finish:
                self.start_without_finish = False
            else:
                self.finish_without_start = True


class ExceptionJsonItemExporter(JsonItemExporter):
    """JsonItemExporter that throws an exception every time export_item is called."""

    def export_item(self, _):
        raise RuntimeError("foo")


@coroutine_test
async def test_start_finish_exporting_items(
    mockserver: MockServer, tmp_path: Path
) -> None:
    items = [
        MyItem({"foo": "bar1", "egg": "spam1"}),
    ]
    settings = {
        "FEEDS": {
            unique_path(tmp_path): {"format": "json"},
        },
        "FEED_EXPORT_INDENT": None,
    }

    listener = IsExportingListener()
    InstrumentedFeedSlot.subscribe__listener(listener)

    with mock.patch("scrapy.extensions.feedexport.FeedSlot", InstrumentedFeedSlot):
        await export_by_format(mockserver, items, settings)
        assert not listener.start_without_finish
        assert not listener.finish_without_start


@coroutine_test
async def test_start_finish_exporting_no_items(
    mockserver: MockServer, tmp_path: Path
) -> None:
    items: list[Any] = []
    settings = {
        "FEEDS": {
            unique_path(tmp_path): {"format": "json"},
        },
        "FEED_EXPORT_INDENT": None,
    }

    listener = IsExportingListener()
    InstrumentedFeedSlot.subscribe__listener(listener)

    with mock.patch("scrapy.extensions.feedexport.FeedSlot", InstrumentedFeedSlot):
        await export_by_format(mockserver, items, settings)
        assert not listener.start_without_finish
        assert not listener.finish_without_start


@coroutine_test
async def test_start_finish_exporting_items_exception(
    mockserver: MockServer, tmp_path: Path
) -> None:
    items = [
        MyItem({"foo": "bar1", "egg": "spam1"}),
    ]
    settings = {
        "FEEDS": {
            unique_path(tmp_path): {"format": "json"},
        },
        "FEED_EXPORTERS": {"json": ExceptionJsonItemExporter},
        "FEED_EXPORT_INDENT": None,
    }

    listener = IsExportingListener()
    InstrumentedFeedSlot.subscribe__listener(listener)

    with mock.patch("scrapy.extensions.feedexport.FeedSlot", InstrumentedFeedSlot):
        await export_by_format(mockserver, items, settings)
        assert not listener.start_without_finish
        assert not listener.finish_without_start


@coroutine_test
async def test_export_item_exception_mentions_item(
    caplog: pytest.LogCaptureFixture, mockserver: MockServer, tmp_path: Path
) -> None:
    items = [{"foo": {None: "bar"}}]
    settings = {
        "FEEDS": {
            unique_path(tmp_path): {"format": "json"},
        },
        "FEED_EXPORTERS": {"json": ExceptionJsonItemExporter},
    }
    with caplog.at_level(logging.ERROR):
        await export_by_format(mockserver, items, settings)
    assert "RuntimeError: foo" in caplog.text
    assert "Item: {'foo': {None: 'bar'}}" in caplog.text


@coroutine_test
async def test_start_finish_exporting_no_items_exception(
    mockserver: MockServer, tmp_path: Path
) -> None:
    items: list[Any] = []
    settings = {
        "FEEDS": {
            unique_path(tmp_path): {"format": "json"},
        },
        "FEED_EXPORTERS": {"json": ExceptionJsonItemExporter},
        "FEED_EXPORT_INDENT": None,
    }

    listener = IsExportingListener()
    InstrumentedFeedSlot.subscribe__listener(listener)

    with mock.patch("scrapy.extensions.feedexport.FeedSlot", InstrumentedFeedSlot):
        await export_by_format(mockserver, items, settings)
        assert not listener.start_without_finish
        assert not listener.finish_without_start
