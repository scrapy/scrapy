from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

import pytest
from packaging.version import Version

import scrapy
from scrapy.exceptions import NotConfigured
from scrapy.extensions.feedexport import FeedExporter, S3FeedStorage
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
from tests.spiders import ItemSpider
from tests.utils.decorators import coroutine_test
from tests.utils.feedexport import PARSERS, MyItem, crawl_items, csv_header, unique_path

if TYPE_CHECKING:
    from collections.abc import Iterable
    from os import PathLike

    from tests.mockserver.http import MockServer


def build_url(path: str | PathLike[str]) -> str:
    path_str = str(path)
    if path_str[0] != "/":
        path_str = "/" + path_str
    return urljoin("file:", path_str)


async def export_batches(
    mockserver: MockServer, items: Iterable[Any], settings: dict[str, Any]
) -> dict[str, list[bytes]]:
    """Export *items* with *settings*, whose ``FEEDS`` are keyed by local
    batch paths with a separate parent directory for each feed, and return
    the contents of the batch files of each feed format, in file name order."""
    feeds = settings["FEEDS"]
    feed_urls = {build_url(path): options for path, options in feeds.items()}
    await crawl_items(mockserver, items, {**settings, "FEEDS": feed_urls})
    return {
        options["format"]: [
            file.read_bytes() for file in sorted(Path(path).parent.iterdir())
        ]
        if Path(path).parent.exists()
        else []
        for path, options in feeds.items()
    }


class TestBatchDeliveries:
    _file_mark = "_%(batch_time)s_%(batch_id)02d_"

    @pytest.mark.parametrize("fmt", list(PARSERS))
    @coroutine_test
    async def test_export_items(
        self, fmt: str, mockserver: MockServer, tmp_path: Path
    ) -> None:
        """Test partial deliveries in all supported formats"""
        items = [
            MyItem({"foo": "bar1", "egg": "spam1"}),
            MyItem({"foo": "bar2", "egg": "spam2", "baz": "quux2"}),
            MyItem({"foo": "bar3", "baz": "quux3"}),
        ]
        settings = {
            "FEEDS": {unique_path(tmp_path) / self._file_mark: {"format": fmt}},
            "FEED_EXPORT_BATCH_ITEM_COUNT": 2,
        }
        batches = (await export_batches(mockserver, items, settings))[fmt]
        if fmt == "csv":
            header = list(MyItem.fields)
            assert [csv_header(batch) for batch in batches] == [header, header]
        assert [PARSERS[fmt](batch) for batch in batches] == [
            [
                {"egg": "spam1", "foo": "bar1"},
                {"egg": "spam2", "foo": "bar2", "baz": "quux2"},
            ],
            [{"foo": "bar3", "baz": "quux3"}],
        ]

    @coroutine_test
    async def test_batch_delivered_when_full(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        """Full batches must be finalized and delivered as soon as they are
        full, instead of when the spider closes."""
        dir_path = unique_path(tmp_path)
        batch1_path = Path(dir_path, "1.json")
        mockserver_url = mockserver.url("/")
        batch1_contents: list[bytes | None] = []

        class TestSpider(scrapy.Spider):
            name = "testspider"
            start_urls = [mockserver_url]

            def parse(self, response):
                yield {"foo": "bar1"}
                yield {"foo": "bar2"}
                yield scrapy.Request(
                    mockserver_url, callback=self.parse2, dont_filter=True
                )

            def parse2(self, response):
                # the first batch was full after the second item, so it must
                # have been delivered by now
                batch1_contents.append(
                    batch1_path.read_bytes() if batch1_path.exists() else None
                )
                yield {"foo": "bar3"}

        settings = {
            "FEEDS": {
                build_url(dir_path / "%(batch_id)d.json"): {"format": "json"},
            },
            "FEED_EXPORT_BATCH_ITEM_COUNT": 2,
        }
        crawler = get_crawler(TestSpider, settings)
        await crawler.crawl_async()

        assert batch1_contents, "the second request was not processed"
        assert batch1_contents[0] is not None, "batch 1 was not stored during the crawl"
        assert json.loads(batch1_contents[0]) == [{"foo": "bar1"}, {"foo": "bar2"}]

    def test_wrong_path(self, tmp_path: Path) -> None:
        """If path is without %(batch_time)s and %(batch_id) an exception must be raised"""
        settings = {
            "FEEDS": {
                unique_path(tmp_path): {"format": "xml"},
            },
            "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
        }
        crawler = get_crawler(settings_dict=settings)
        with pytest.raises(NotConfigured):
            build_from_crawler(FeedExporter, crawler)

    @coroutine_test
    async def test_export_no_items_not_store_empty(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        for fmt in ("json", "jsonlines", "xml", "csv"):
            settings = {
                "FEEDS": {
                    unique_path(tmp_path) / self._file_mark: {"format": fmt},
                },
                "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
                "FEED_STORE_EMPTY": False,
            }
            data = await export_batches(mockserver, [], settings)
            assert len(data[fmt]) == 0

    @coroutine_test
    async def test_export_no_items_store_empty(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        formats = (
            ("json", b"[]"),
            ("jsonlines", b""),
            ("xml", b'<?xml version="1.0" encoding="utf-8"?>\n<items></items>'),
            ("csv", b""),
        )

        for fmt, expctd in formats:
            settings = {
                "FEEDS": {
                    unique_path(tmp_path) / self._file_mark: {"format": fmt},
                },
                "FEED_STORE_EMPTY": True,
                "FEED_EXPORT_INDENT": None,
                "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
            }
            data = await export_batches(mockserver, [], settings)
            assert data[fmt][0] == expctd

    @coroutine_test
    async def test_export_multiple_configs(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        items = [
            {"foo": "FOO", "bar": "BAR"},
            {"foo": "FOO1", "bar": "BAR1"},
        ]

        formats = {
            "json": [
                b'[\n{"bar": "BAR"}\n]',
                b'[\n{"bar": "BAR1"}\n]',
            ],
            "xml": [
                (
                    b'<?xml version="1.0" encoding="latin-1"?>\n'
                    b"<items>\n  <item>\n    <foo>FOO</foo>\n  </item>\n</items>"
                ),
                (
                    b'<?xml version="1.0" encoding="latin-1"?>\n'
                    b"<items>\n  <item>\n    <foo>FOO1</foo>\n  </item>\n</items>"
                ),
            ],
            "csv": [
                b"foo,bar\r\nFOO,BAR\r\n",
                b"foo,bar\r\nFOO1,BAR1\r\n",
            ],
        }

        settings = {
            "FEEDS": {
                unique_path(tmp_path) / self._file_mark: {
                    "format": "json",
                    "indent": 0,
                    "fields": ["bar"],
                    "encoding": "utf-8",
                },
                unique_path(tmp_path) / self._file_mark: {
                    "format": "xml",
                    "indent": 2,
                    "fields": ["foo"],
                    "encoding": "latin-1",
                },
                unique_path(tmp_path) / self._file_mark: {
                    "format": "csv",
                    "indent": None,
                    "fields": ["foo", "bar"],
                    "encoding": "utf-8",
                },
            },
            "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
        }
        data = await export_batches(mockserver, items, settings)
        for fmt, expected in formats.items():
            for expected_batch, got_batch in zip(expected, data[fmt], strict=True):
                assert got_batch == expected_batch

    @coroutine_test
    async def test_batch_item_count_feeds_setting(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        items = [{"foo": "FOO"}, {"foo": "FOO1"}]
        formats = {
            "json": [
                b'[{"foo": "FOO"}]',
                b'[{"foo": "FOO1"}]',
            ],
        }
        settings = {
            "FEEDS": {
                unique_path(tmp_path) / self._file_mark: {
                    "format": "json",
                    "indent": None,
                    "encoding": "utf-8",
                    "batch_item_count": 1,
                },
            },
        }
        data = await export_batches(mockserver, items, settings)
        for fmt, expected in formats.items():
            for expected_batch, got_batch in zip(expected, data[fmt], strict=True):
                assert got_batch == expected_batch

    @coroutine_test
    async def test_batch_item_count_with_item_processor(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        def split_foo(item):
            for value in item["foo"].split(","):
                yield {"foo": value}

        items = [{"foo": "FOO,FOO1"}, {"foo": "FOO2"}]
        formats = {
            "json": [
                b'[{"foo": "FOO"}]',
                b'[{"foo": "FOO1"}]',
                b'[{"foo": "FOO2"}]',
            ],
        }
        settings = {
            "FEEDS": {
                unique_path(tmp_path) / self._file_mark: {
                    "format": "json",
                    "indent": None,
                    "encoding": "utf-8",
                    "batch_item_count": 1,
                    "item_processor": split_foo,
                },
            },
        }
        data = await export_batches(mockserver, items, settings)
        for fmt, expected in formats.items():
            for expected_batch, got_batch in zip(expected, data[fmt], strict=True):
                assert got_batch == expected_batch

    @coroutine_test
    async def test_batch_path_differ(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        """
        Test that the name of all batch files differ from each other.
        So %(batch_id)d replaced with the current id.
        """
        items = [
            MyItem({"foo": "bar1", "egg": "spam1"}),
            MyItem({"foo": "bar2", "egg": "spam2", "baz": "quux2"}),
            MyItem({"foo": "bar3", "baz": "quux3"}),
        ]
        settings = {
            "FEEDS": {
                unique_path(tmp_path) / "%(batch_id)d": {
                    "format": "json",
                },
            },
            "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
        }
        data = await export_batches(mockserver, items, settings)
        assert len(items) == len(data["json"])

    @coroutine_test
    async def test_stats_batch_file_success(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        settings = {
            "FEEDS": {
                build_url(str(unique_path(tmp_path) / self._file_mark)): {
                    "format": "json",
                }
            },
            "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
        }
        crawler = get_crawler(ItemSpider, settings)
        await crawler.crawl_async(total=2, mockserver=mockserver)
        assert "feedexport/success_count/FileFeedStorage" in crawler.stats.get_stats()
        assert crawler.stats.get_value("feedexport/success_count/FileFeedStorage") == 12

    @pytest.mark.requires_boto3
    @coroutine_test
    async def test_s3_export(self, mockserver: MockServer) -> None:
        bucket = "mybucket"
        items = [
            MyItem({"foo": "bar1", "egg": "spam1"}),
            MyItem({"foo": "bar2", "egg": "spam2", "baz": "quux2"}),
            MyItem({"foo": "bar3", "baz": "quux3"}),
        ]

        class CustomS3FeedStorage(S3FeedStorage):
            from botocore.stub import Stubber  # noqa: PLC0415

            stubs: list[Stubber] = []

            def open(self, *args, **kwargs):
                from botocore import __version__ as botocore_version  # noqa: PLC0415
                from botocore.stub import ANY, Stubber  # noqa: PLC0415

                expected_params = {
                    "Body": ANY,
                    "Bucket": bucket,
                    "Key": ANY,
                }
                if Version(botocore_version) >= Version("1.36.0"):
                    expected_params["ChecksumAlgorithm"] = ANY

                stub = Stubber(self.s3_client)
                stub.activate()
                CustomS3FeedStorage.stubs.append(stub)
                stub.add_response(
                    "put_object",
                    expected_params=expected_params,
                    service_response={},
                )
                return super().open(*args, **kwargs)

        key = "export.csv"
        uri = f"s3://{bucket}/{key}/%(batch_id)d.json"
        batch_item_count = 1
        settings = {
            "AWS_ACCESS_KEY_ID": "access_key",
            "AWS_SECRET_ACCESS_KEY": "secret_key",
            "FEED_EXPORT_BATCH_ITEM_COUNT": batch_item_count,
            "FEED_STORAGES": {
                "s3": CustomS3FeedStorage,
            },
            "FEEDS": {
                uri: {
                    "format": "json",
                },
            },
        }

        crawler = await crawl_items(mockserver, items, settings)

        assert len(CustomS3FeedStorage.stubs) == len(items)
        for stub in CustomS3FeedStorage.stubs:
            stub.assert_no_pending_responses()
        assert (
            "feedexport/success_count/CustomS3FeedStorage" in crawler.stats.get_stats()
        )
        assert (
            crawler.stats.get_value("feedexport/success_count/CustomS3FeedStorage") == 3
        )
