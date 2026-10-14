from __future__ import annotations

import logging
from pathlib import Path
from typing import IO, TYPE_CHECKING
from unittest import mock

from w3lib.url import file_uri_to_path

from scrapy.extensions.feedexport import BlockingFeedStorage
from scrapy.utils.test import get_crawler
from tests.spiders import ItemSpider
from tests.utils.decorators import coroutine_test
from tests.utils.feedexport import (
    export_by_format,
    path_to_url,
    printf_escape,
    unique_path,
)

if TYPE_CHECKING:
    import pytest

    from tests.mockserver.http import MockServer


class DummyBlockingFeedStorage(BlockingFeedStorage):
    def __init__(self, uri, *args, feed_options=None):
        self.path = Path(file_uri_to_path(uri))

    def _store_in_thread(self, file):
        dirname = self.path.parent
        if dirname and not dirname.exists():
            dirname.mkdir(parents=True)
        with self.path.open("ab") as output_file:
            output_file.write(file.read())

        file.close()


class FailingBlockingFeedStorage(DummyBlockingFeedStorage):
    def _store_in_thread(self, file):
        file.close()
        raise OSError("Cannot store")


@coroutine_test
async def test_stats_file_success(mockserver: MockServer, tmp_path: Path) -> None:
    settings = {
        "FEEDS": {
            printf_escape(path_to_url(str(unique_path(tmp_path)))): {
                "format": "json",
            }
        },
    }
    crawler = get_crawler(ItemSpider, settings)
    await crawler.crawl_async(mockserver=mockserver)
    assert "feedexport/success_count/FileFeedStorage" in crawler.stats.get_stats()
    assert crawler.stats.get_value("feedexport/success_count/FileFeedStorage") == 1


@coroutine_test
async def test_stats_file_failed(mockserver: MockServer, tmp_path: Path) -> None:
    settings = {
        "FEEDS": {
            printf_escape(path_to_url(str(unique_path(tmp_path)))): {
                "format": "json",
            }
        },
    }
    crawler = get_crawler(ItemSpider, settings)

    def store(file: IO[bytes]) -> None:
        file.close()
        raise KeyError("foo")

    with mock.patch(
        "scrapy.extensions.feedexport.FileFeedStorage.store",
        side_effect=store,
    ):
        await crawler.crawl_async(mockserver=mockserver)
    assert "feedexport/failed_count/FileFeedStorage" in crawler.stats.get_stats()
    assert crawler.stats.get_value("feedexport/failed_count/FileFeedStorage") == 1


@coroutine_test
async def test_stats_multiple_file(mockserver: MockServer, tmp_path: Path) -> None:
    settings = {
        "FEEDS": {
            printf_escape(path_to_url(str(unique_path(tmp_path)))): {
                "format": "json",
            },
            "stdout:": {
                "format": "xml",
            },
        },
    }
    crawler = get_crawler(ItemSpider, settings)
    await crawler.crawl_async(mockserver=mockserver)
    assert "feedexport/success_count/FileFeedStorage" in crawler.stats.get_stats()
    assert "feedexport/success_count/StdoutFeedStorage" in crawler.stats.get_stats()
    assert crawler.stats.get_value("feedexport/success_count/FileFeedStorage") == 1
    assert crawler.stats.get_value("feedexport/success_count/StdoutFeedStorage") == 1


@coroutine_test
async def test_multiple_feeds_success_logs_blocking_feed_storage(
    caplog: pytest.LogCaptureFixture, mockserver: MockServer, tmp_path: Path
) -> None:
    settings = {
        "FEEDS": {
            unique_path(tmp_path): {"format": "json"},
            unique_path(tmp_path): {"format": "xml"},
            unique_path(tmp_path): {"format": "csv"},
        },
        "FEED_STORAGES": {"file": DummyBlockingFeedStorage},
    }
    items = [
        {"foo": "bar1", "baz": ""},
        {"foo": "bar2", "baz": "quux"},
    ]
    with caplog.at_level(logging.DEBUG):
        await export_by_format(mockserver, items, settings)

    for fmt in ["json", "xml", "csv"]:
        assert f"Stored {fmt} feed (2 items)" in caplog.text


@coroutine_test
async def test_multiple_feeds_failing_logs_blocking_feed_storage(
    caplog: pytest.LogCaptureFixture, mockserver: MockServer, tmp_path: Path
) -> None:
    settings = {
        "FEEDS": {
            unique_path(tmp_path): {"format": "json"},
            unique_path(tmp_path): {"format": "xml"},
            unique_path(tmp_path): {"format": "csv"},
        },
        "FEED_STORAGES": {"file": FailingBlockingFeedStorage},
    }
    items = [
        {"foo": "bar1", "baz": ""},
        {"foo": "bar2", "baz": "quux"},
    ]
    with caplog.at_level(logging.DEBUG):
        await export_by_format(mockserver, items, settings)

    for fmt in ["json", "xml", "csv"]:
        assert f"Error storing {fmt} feed (2 items)" in caplog.text
