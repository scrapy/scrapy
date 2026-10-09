from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

import scrapy
from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.exporters import CsvItemExporter
from scrapy.extensions.feedexport import FeedExporter, FileFeedStorage
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test
from tests.utils.feedexport import (
    export_by_format,
    path_to_url,
    printf_escape,
    unique_path,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from tests.mockserver.http import MockServer


class FromCrawlerMixin:
    init_with_crawler = False

    @classmethod
    def from_crawler(cls, crawler, *args, feed_options=None, **kwargs):
        cls.init_with_crawler = True
        return cls(*args, **kwargs)


class FromCrawlerCsvItemExporter(CsvItemExporter, FromCrawlerMixin):
    pass


class FromCrawlerFileFeedStorage(FileFeedStorage, FromCrawlerMixin):
    @classmethod
    def from_crawler(cls, crawler, *args, feed_options=None, **kwargs):
        cls.init_with_crawler = True
        return cls(*args, feed_options=feed_options, **kwargs)


@coroutine_test
async def test_init_exporters_storages_with_crawler(
    mockserver: MockServer, tmp_path: Path
) -> None:
    settings = {
        "FEED_EXPORTERS": {"csv": FromCrawlerCsvItemExporter},
        "FEED_STORAGES": {"file": FromCrawlerFileFeedStorage},
        "FEEDS": {
            unique_path(tmp_path): {"format": "csv"},
        },
    }
    await export_by_format(mockserver, [], settings)
    assert FromCrawlerCsvItemExporter.init_with_crawler
    assert FromCrawlerFileFeedStorage.init_with_crawler


@coroutine_test
async def test_str_uri(mockserver: MockServer, tmp_path: Path) -> None:
    settings = {
        "FEED_STORE_EMPTY": True,
        "FEEDS": {str(unique_path(tmp_path)): {"format": "csv"}},
    }
    data = await export_by_format(mockserver, [], settings)
    assert data["csv"] == b""


# Test that the FeedExporer sends the feed_exporter_closed and feed_slot_closed signals
class TestFeedExporterSignals:
    items = [
        {"foo": "bar1", "egg": "spam1"},
        {"foo": "bar2", "egg": "spam2", "baz": "quux2"},
        {"foo": "bar3", "baz": "quux3"},
    ]

    with tempfile.NamedTemporaryFile(suffix="json") as tmp:
        settings = {
            "FEEDS": {
                printf_escape(path_to_url(tmp.name)): {
                    "format": "json",
                },
            },
        }

    def feed_exporter_closed_signal_handler(self):
        self.feed_exporter_closed_received = True

    def feed_slot_closed_signal_handler(self, slot):
        self.feed_slot_closed_received = True

    async def feed_exporter_closed_signal_handler_async(self):
        self.feed_exporter_closed_received = True

    async def feed_slot_closed_signal_handler_async(self, slot):
        self.feed_slot_closed_received = True

    async def run_signaled_feed_exporter(
        self,
        feed_exporter_signal_handler: Callable[[], Awaitable[None] | None],
        feed_slot_signal_handler: Callable[[Any], Awaitable[None] | None],
    ) -> None:
        crawler = get_crawler(settings_dict=self.settings)
        feed_exporter = build_from_crawler(FeedExporter, crawler)
        spider = scrapy.Spider.from_crawler(crawler, "default")
        crawler.signals.connect(
            feed_exporter_signal_handler,
            signal=signals.feed_exporter_closed,
        )
        crawler.signals.connect(
            feed_slot_signal_handler, signal=signals.feed_slot_closed
        )
        feed_exporter.open_spider(spider)
        for item in self.items:
            await feed_exporter.item_scraped(item, spider)
        await feed_exporter.close_spider(spider)

    @coroutine_test
    async def test_feed_exporter_signals_sent(self) -> None:
        self.feed_exporter_closed_received = False
        self.feed_slot_closed_received = False

        await self.run_signaled_feed_exporter(
            self.feed_exporter_closed_signal_handler,
            self.feed_slot_closed_signal_handler,
        )
        assert self.feed_slot_closed_received
        assert self.feed_exporter_closed_received

    @coroutine_test
    async def test_feed_exporter_signals_sent_async(self) -> None:
        self.feed_exporter_closed_received = False
        self.feed_slot_closed_received = False

        await self.run_signaled_feed_exporter(
            self.feed_exporter_closed_signal_handler_async,
            self.feed_slot_closed_signal_handler_async,
        )
        assert self.feed_slot_closed_received
        assert self.feed_exporter_closed_received


class TestFeedExportInit:
    def test_unsupported_storage(self):
        settings: dict[str, Any] = {
            "FEEDS": {
                "unsupported://uri": {},
            },
        }
        crawler = get_crawler(settings_dict=settings)
        with pytest.raises(NotConfigured):
            build_from_crawler(FeedExporter, crawler)

    def test_disabled_storage(self, caplog: pytest.LogCaptureFixture) -> None:
        class DisabledFeedStorage:
            def __init__(self, uri, *, feed_options=None):
                raise NotConfigured("not today")

        settings = {
            "FEED_STORAGES": {"disabled": DisabledFeedStorage},
            "FEEDS": {
                "disabled://uri": {},
            },
        }
        crawler = get_crawler(settings_dict=settings)
        with caplog.at_level(logging.ERROR), pytest.raises(NotConfigured):
            build_from_crawler(FeedExporter, crawler)
        assert (
            "Disabled feed storage scheme: disabled. Reason: not today" in caplog.text
        )

    def test_unsupported_format(self):
        settings = {
            "FEEDS": {
                "file://path": {
                    "format": "unsupported_format",
                },
            },
        }
        crawler = get_crawler(settings_dict=settings)
        with pytest.raises(NotConfigured):
            build_from_crawler(FeedExporter, crawler)

    def test_format_inferred_from_uri(self):
        settings: dict[str, Any] = {
            "FEEDS": {
                "output.json": {},
            },
        }
        crawler = get_crawler(settings_dict=settings)
        exporter = build_from_crawler(FeedExporter, crawler)
        assert exporter.feeds["output.json"]["format"] == "json"

    def test_format_missing_and_not_inferable(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        settings: dict[str, Any] = {
            "FEEDS": {
                "stdout:": {},
            },
        }
        crawler = get_crawler(settings_dict=settings)
        with caplog.at_level(logging.ERROR), pytest.raises(NotConfigured):
            build_from_crawler(FeedExporter, crawler)
        assert "Feed format not set" in caplog.text

    def test_absolute_pathlib_as_uri(self):
        with tempfile.NamedTemporaryFile(suffix="json") as tmp:
            settings = {
                "FEEDS": {
                    Path(tmp.name).resolve(): {
                        "format": "json",
                    },
                },
            }
            crawler = get_crawler(settings_dict=settings)
            exporter = build_from_crawler(FeedExporter, crawler)
            assert isinstance(exporter, FeedExporter)

    def test_relative_pathlib_as_uri(self):
        settings = {
            "FEEDS": {
                Path("./items.json"): {
                    "format": "json",
                },
            },
        }
        crawler = get_crawler(settings_dict=settings)
        exporter = build_from_crawler(FeedExporter, crawler)
        assert isinstance(exporter, FeedExporter)
