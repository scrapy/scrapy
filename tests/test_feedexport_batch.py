from __future__ import annotations

import csv
import json
import marshal
import pickle
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

import lxml.etree
import pytest
from packaging.version import Version
from zope.interface.verify import verifyObject

import scrapy
from scrapy import Spider
from scrapy.exceptions import NotConfigured
from scrapy.extensions.feedexport import FeedExporter, IFeedStorage, S3FeedStorage
from scrapy.settings import Settings
from scrapy.utils.python import to_unicode
from scrapy.utils.test import get_crawler
from tests.spiders import ItemSpider
from tests.test_feedexport import TestFeedExportBase
from tests.utils.decorators import coroutine_test, inline_callbacks_test

if TYPE_CHECKING:
    from os import PathLike


def build_url(path: str | PathLike) -> str:
    path_str = str(path)
    if path_str[0] != "/":
        path_str = "/" + path_str
    return urljoin("file:", path_str)


class TestBatchDeliveries(TestFeedExportBase):
    _file_mark = "_%(batch_time)s_#%(batch_id)02d_"

    async def run_and_export(
        self, spider_cls: type[Spider], settings: dict[str, Any]
    ) -> dict[str, list[bytes]]:
        """Run spider with specified settings; return exported data."""

        FEEDS = settings.get("FEEDS") or {}
        settings["FEEDS"] = {
            build_url(file_path): feed for file_path, feed in FEEDS.items()
        }
        content: defaultdict[str, list[bytes]] = defaultdict(list)
        spider_cls.start_urls = [self.mockserver.url("/")]
        crawler = get_crawler(spider_cls, settings)
        await crawler.crawl_async()

        for path, feed in FEEDS.items():
            dir_name = Path(path).parent
            if not dir_name.exists():
                content[feed["format"]] = []
                continue
            for file in sorted(dir_name.iterdir()):
                content[feed["format"]].append(file.read_bytes())
        return content

    async def assertExportedJsonLines(self, items, rows, settings=None):
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename() / "jl" / self._file_mark: {
                        "format": "jl"
                    },
                },
            }
        )
        batch_size = Settings(settings).getint("FEED_EXPORT_BATCH_ITEM_COUNT")
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        data = await self.exported_data(items, settings)
        for batch in data["jl"]:
            got_batch = [
                json.loads(to_unicode(batch_item)) for batch_item in batch.splitlines()
            ]
            expected_batch, rows = rows[:batch_size], rows[batch_size:]
            assert got_batch == expected_batch

    async def assertExportedCsv(self, items, header, rows, settings=None):
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename() / "csv" / self._file_mark: {
                        "format": "csv"
                    },
                },
            }
        )
        batch_size = Settings(settings).getint("FEED_EXPORT_BATCH_ITEM_COUNT")
        data = await self.exported_data(items, settings)
        for batch in data["csv"]:
            got_batch = csv.DictReader(to_unicode(batch).splitlines())
            assert list(header) == got_batch.fieldnames
            expected_batch, rows = rows[:batch_size], rows[batch_size:]
            assert list(got_batch) == expected_batch

    async def assertExportedXml(self, items, rows, settings=None):
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename() / "xml" / self._file_mark: {
                        "format": "xml"
                    },
                },
            }
        )
        batch_size = Settings(settings).getint("FEED_EXPORT_BATCH_ITEM_COUNT")
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        data = await self.exported_data(items, settings)
        for batch in data["xml"]:
            root = lxml.etree.fromstring(batch)
            got_batch = [{e.tag: e.text for e in it} for it in root.findall("item")]
            expected_batch, rows = rows[:batch_size], rows[batch_size:]
            assert got_batch == expected_batch

    async def assertExportedMultiple(self, items, rows, settings=None):
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename() / "xml" / self._file_mark: {
                        "format": "xml"
                    },
                    self._random_temp_filename() / "json" / self._file_mark: {
                        "format": "json"
                    },
                },
            }
        )
        batch_size = Settings(settings).getint("FEED_EXPORT_BATCH_ITEM_COUNT")
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        data = await self.exported_data(items, settings)
        # XML
        xml_rows = rows.copy()
        for batch in data["xml"]:
            root = lxml.etree.fromstring(batch)
            got_batch = [{e.tag: e.text for e in it} for it in root.findall("item")]
            expected_batch, xml_rows = xml_rows[:batch_size], xml_rows[batch_size:]
            assert got_batch == expected_batch
        # JSON
        json_rows = rows.copy()
        for batch in data["json"]:
            got_batch = json.loads(batch.decode("utf-8"))
            expected_batch, json_rows = json_rows[:batch_size], json_rows[batch_size:]
            assert got_batch == expected_batch

    async def assertExportedPickle(self, items, rows, settings=None):
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename() / "pickle" / self._file_mark: {
                        "format": "pickle"
                    },
                },
            }
        )
        batch_size = Settings(settings).getint("FEED_EXPORT_BATCH_ITEM_COUNT")
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        data = await self.exported_data(items, settings)

        for batch in data["pickle"]:
            got_batch = self._load_until_eof(batch, load_func=pickle.load)
            expected_batch, rows = rows[:batch_size], rows[batch_size:]
            assert got_batch == expected_batch

    async def assertExportedMarshal(self, items, rows, settings=None):
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename() / "marshal" / self._file_mark: {
                        "format": "marshal"
                    },
                },
            }
        )
        batch_size = Settings(settings).getint("FEED_EXPORT_BATCH_ITEM_COUNT")
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        data = await self.exported_data(items, settings)

        for batch in data["marshal"]:
            got_batch = self._load_until_eof(batch, load_func=marshal.load)
            expected_batch, rows = rows[:batch_size], rows[batch_size:]
            assert got_batch == expected_batch

    @coroutine_test
    async def test_export_items(self):
        """Test partial deliveries in all supported formats"""
        items = [
            self.MyItem({"foo": "bar1", "egg": "spam1"}),
            self.MyItem({"foo": "bar2", "egg": "spam2", "baz": "quux2"}),
            self.MyItem({"foo": "bar3", "baz": "quux3"}),
        ]
        rows = [
            {"egg": "spam1", "foo": "bar1", "baz": ""},
            {"egg": "spam2", "foo": "bar2", "baz": "quux2"},
            {"foo": "bar3", "baz": "quux3", "egg": ""},
        ]
        settings = {"FEED_EXPORT_BATCH_ITEM_COUNT": 2}
        header = self.MyItem.fields.keys()
        await self.assertExported(items, header, rows, settings=settings)

    def test_wrong_path(self):
        """If path is without %(batch_time)s and %(batch_id) an exception must be raised"""
        settings = {
            "FEEDS": {
                self._random_temp_filename(): {"format": "xml"},
            },
            "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
        }
        crawler = get_crawler(settings_dict=settings)
        with pytest.raises(NotConfigured):
            FeedExporter(crawler)

    @coroutine_test
    async def test_export_no_items_not_store_empty(self):
        for fmt in ("json", "jsonlines", "xml", "csv"):
            settings = {
                "FEEDS": {
                    self._random_temp_filename() / fmt / self._file_mark: {
                        "format": fmt
                    },
                },
                "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
                "FEED_STORE_EMPTY": False,
            }
            data = await self.exported_no_data(settings)
            data = dict(data)
            assert len(data[fmt]) == 0

    @coroutine_test
    async def test_export_no_items_store_empty(self):
        formats = (
            ("json", b"[]"),
            ("jsonlines", b""),
            ("xml", b'<?xml version="1.0" encoding="utf-8"?>\n<items></items>'),
            ("csv", b""),
        )

        for fmt, expctd in formats:
            settings = {
                "FEEDS": {
                    self._random_temp_filename() / fmt / self._file_mark: {
                        "format": fmt
                    },
                },
                "FEED_STORE_EMPTY": True,
                "FEED_EXPORT_INDENT": None,
                "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
            }
            data = await self.exported_no_data(settings)
            data = dict(data)
            assert data[fmt][0] == expctd

    @coroutine_test
    async def test_export_multiple_configs(self):
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
                self._random_temp_filename() / "json" / self._file_mark: {
                    "format": "json",
                    "indent": 0,
                    "fields": ["bar"],
                    "encoding": "utf-8",
                },
                self._random_temp_filename() / "xml" / self._file_mark: {
                    "format": "xml",
                    "indent": 2,
                    "fields": ["foo"],
                    "encoding": "latin-1",
                },
                self._random_temp_filename() / "csv" / self._file_mark: {
                    "format": "csv",
                    "indent": None,
                    "fields": ["foo", "bar"],
                    "encoding": "utf-8",
                },
            },
            "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
        }
        data = await self.exported_data(items, settings)
        for fmt, expected in formats.items():
            for expected_batch, got_batch in zip(expected, data[fmt], strict=False):
                assert got_batch == expected_batch

    @coroutine_test
    async def test_batch_item_count_feeds_setting(self):
        items = [{"foo": "FOO"}, {"foo": "FOO1"}]
        formats = {
            "json": [
                b'[{"foo": "FOO"}]',
                b'[{"foo": "FOO1"}]',
            ],
        }
        settings = {
            "FEEDS": {
                self._random_temp_filename() / "json" / self._file_mark: {
                    "format": "json",
                    "indent": None,
                    "encoding": "utf-8",
                    "batch_item_count": 1,
                },
            },
        }
        data = await self.exported_data(items, settings)
        for fmt, expected in formats.items():
            for expected_batch, got_batch in zip(expected, data[fmt], strict=False):
                assert got_batch == expected_batch

    @coroutine_test
    async def test_batch_path_differ(self):
        """
        Test that the name of all batch files differ from each other.
        So %(batch_id)d replaced with the current id.
        """
        items = [
            self.MyItem({"foo": "bar1", "egg": "spam1"}),
            self.MyItem({"foo": "bar2", "egg": "spam2", "baz": "quux2"}),
            self.MyItem({"foo": "bar3", "baz": "quux3"}),
        ]
        settings = {
            "FEEDS": {
                self._random_temp_filename() / "%(batch_id)d": {
                    "format": "json",
                },
            },
            "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
        }
        data = await self.exported_data(items, settings)
        assert len(items) == len(data["json"])

    @inline_callbacks_test
    def test_stats_batch_file_success(self):
        settings = {
            "FEEDS": {
                build_url(
                    str(self._random_temp_filename() / "json" / self._file_mark)
                ): {
                    "format": "json",
                }
            },
            "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
        }
        crawler = get_crawler(ItemSpider, settings)
        yield crawler.crawl(total=2, mockserver=self.mockserver)
        assert "feedexport/success_count/FileFeedStorage" in crawler.stats.get_stats()
        assert crawler.stats.get_value("feedexport/success_count/FileFeedStorage") == 12

    @pytest.mark.requires_boto3
    @inline_callbacks_test
    def test_s3_export(self):
        bucket = "mybucket"
        items = [
            self.MyItem({"foo": "bar1", "egg": "spam1"}),
            self.MyItem({"foo": "bar2", "egg": "spam2", "baz": "quux2"}),
            self.MyItem({"foo": "bar3", "baz": "quux3"}),
        ]

        class CustomS3FeedStorage(S3FeedStorage):
            stubs = []

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
        crawler = get_crawler(settings_dict=settings)
        storage = S3FeedStorage.from_crawler(crawler, uri)
        verifyObject(IFeedStorage, storage)

        class TestSpider(scrapy.Spider):
            name = "testspider"

            def parse(self, response):
                yield from items

        TestSpider.start_urls = [self.mockserver.url("/")]
        crawler = get_crawler(TestSpider, settings)
        yield crawler.crawl()

        assert len(CustomS3FeedStorage.stubs) == len(items)
        for stub in CustomS3FeedStorage.stubs[:-1]:
            stub.assert_no_pending_responses()
        assert (
            "feedexport/success_count/CustomS3FeedStorage" in crawler.stats.get_stats()
        )
        assert (
            crawler.stats.get_value("feedexport/success_count/CustomS3FeedStorage") == 3
        )
