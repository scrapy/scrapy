from __future__ import annotations

import csv
import json
import marshal
import pickle
import random
import shutil
import tempfile
import warnings
from abc import ABC, abstractmethod
from collections import defaultdict
from logging import getLogger
from pathlib import Path
from string import ascii_letters, digits
from typing import TYPE_CHECKING, Any
from unittest import mock
from urllib.parse import urljoin
from urllib.request import pathname2url

import lxml.etree
import pytest
from packaging.version import Version
from testfixtures import LogCapture
from w3lib.url import file_uri_to_path
from zope.interface import implementer
from zope.interface.verify import verifyObject

import scrapy
from scrapy import Spider, signals
from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.exporters import CsvItemExporter, JsonItemExporter
from scrapy.extensions.feedexport import (
    BlockingFeedStorage,
    FeedExporter,
    FeedSlot,
    FileFeedStorage,
    IFeedStorage,
    S3FeedStorage,
)
from scrapy.settings import Settings
from scrapy.utils.python import to_unicode
from scrapy.utils.test import get_crawler
from tests.mockserver.http import MockServer
from tests.spiders import ItemSpider
from tests.utils.decorators import coroutine_test, inline_callbacks_test

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from os import PathLike


def path_to_url(path):
    return urljoin("file:", pathname2url(str(path)))


def printf_escape(string):
    return string.replace("%", "%%")


def build_url(path: str | PathLike) -> str:
    path_str = str(path)
    if path_str[0] != "/":
        path_str = "/" + path_str
    return urljoin("file:", path_str)


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
        raise OSError("Cannot store")


@implementer(IFeedStorage)
class LogOnStoreFileStorage:
    """
    This storage logs inside `store` method.
    It can be used to make sure `store` method is invoked.
    """

    def __init__(self, uri, feed_options=None):
        self.path = file_uri_to_path(uri)
        self.logger = getLogger()

    def open(self, spider):
        return tempfile.NamedTemporaryFile(prefix="feed-")

    def store(self, file):
        self.logger.info("Storage.store is called")
        file.close()


class TestFeedExportBase(ABC):
    mockserver: MockServer

    class MyItem(scrapy.Item):
        foo = scrapy.Field()
        egg = scrapy.Field()
        baz = scrapy.Field()

    class MyItem2(scrapy.Item):
        foo = scrapy.Field()
        hello = scrapy.Field()

    def _random_temp_filename(self, inter_dir="") -> Path:
        chars = [random.choice(ascii_letters + digits) for _ in range(15)]
        filename = "".join(chars)
        return Path(self.temp_dir, inter_dir, filename)

    @classmethod
    def setup_class(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def teardown_class(cls):
        cls.mockserver.__exit__(None, None, None)

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def exported_data(
        self, items: Iterable[Any], settings: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Return exported data which a spider yielding ``items`` would return.
        """

        class TestSpider(scrapy.Spider):
            name = "testspider"

            def parse(self, response):
                yield from items

        return await self.run_and_export(TestSpider, settings)

    async def exported_no_data(self, settings: dict[str, Any]) -> dict[str, Any]:
        """
        Return exported data which a spider yielding no ``items`` would return.
        """

        class TestSpider(scrapy.Spider):
            name = "testspider"

            def parse(self, response):
                pass

        return await self.run_and_export(TestSpider, settings)

    async def assertExported(
        self,
        items: Iterable[Any],
        header: Iterable[str],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        await self.assertExportedCsv(items, header, rows, settings)
        await self.assertExportedJsonLines(items, rows, settings)
        await self.assertExportedXml(items, rows, settings)
        await self.assertExportedPickle(items, rows, settings)
        await self.assertExportedMarshal(items, rows, settings)
        await self.assertExportedMultiple(items, rows, settings)

    async def assertExportedCsv(  # noqa: B027
        self,
        items: Iterable[Any],
        header: Iterable[str],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        pass

    async def assertExportedJsonLines(  # noqa: B027
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        pass

    async def assertExportedXml(  # noqa: B027
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        pass

    async def assertExportedMultiple(  # noqa: B027
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        pass

    async def assertExportedPickle(  # noqa: B027
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        pass

    async def assertExportedMarshal(  # noqa: B027
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        pass

    @abstractmethod
    async def run_and_export(
        self, spider_cls: type[Spider], settings: dict[str, Any]
    ) -> dict[str, Any]:
        pass

    def _load_until_eof(self, data, load_func):
        result = []
        with tempfile.TemporaryFile() as temp:
            temp.write(data)
            temp.seek(0)
            while True:
                try:
                    result.append(load_func(temp))
                except EOFError:
                    break
        return result


class InstrumentedFeedSlot(FeedSlot):
    """Instrumented FeedSlot subclass for keeping track of calls to
    start_exporting and finish_exporting."""

    def start_exporting(self):
        self.update_listener("start")
        super().start_exporting()

    def finish_exporting(self):
        self.update_listener("finish")
        super().finish_exporting()

    @classmethod
    def subscribe__listener(cls, listener):
        cls.update_listener = listener.update


class IsExportingListener:
    """When subscribed to InstrumentedFeedSlot, keeps track of when
    a call to start_exporting has been made without a closing call to
    finish_exporting and when a call to finish_exporting has been made
    before a call to start_exporting."""

    def __init__(self):
        self.start_without_finish = False
        self.finish_without_start = False

    def update(self, method):
        if method == "start":
            self.start_without_finish = True
        elif method == "finish":
            if self.start_without_finish:
                self.start_without_finish = False
            else:
                self.finish_before_start = True


class ExceptionJsonItemExporter(JsonItemExporter):
    """JsonItemExporter that throws an exception every time export_item is called."""

    def export_item(self, _):
        raise RuntimeError("foo")


class TestFeedExport(TestFeedExportBase):
    async def run_and_export(
        self, spider_cls: type[Spider], settings: dict[str, Any]
    ) -> dict[str, Any]:
        """Run spider with specified settings; return exported data."""

        FEEDS = settings.get("FEEDS") or {}
        settings["FEEDS"] = {
            printf_escape(path_to_url(file_path)): feed_options
            for file_path, feed_options in FEEDS.items()
        }

        content: dict[str, Any] = {}
        try:
            spider_cls.start_urls = [self.mockserver.url("/")]
            crawler = get_crawler(spider_cls, settings)
            await crawler.crawl_async()

            for file_path, feed_options in FEEDS.items():
                content[feed_options["format"]] = (
                    Path(file_path).read_bytes() if Path(file_path).exists() else None
                )

        finally:
            for file_path in FEEDS:
                if not Path(file_path).exists():
                    continue

                Path(file_path).unlink()

        return content

    async def assertExportedCsv(
        self,
        items: Iterable[Any],
        header: Iterable[str],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename(): {"format": "csv"},
                },
            }
        )
        data = await self.exported_data(items, settings)
        reader = csv.DictReader(to_unicode(data["csv"]).splitlines())
        assert reader.fieldnames == list(header)
        assert rows == list(reader)

    async def assertExportedJsonLines(
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename(): {"format": "jl"},
                },
            }
        )
        data = await self.exported_data(items, settings)
        parsed = [json.loads(to_unicode(line)) for line in data["jl"].splitlines()]
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        assert rows == parsed

    async def assertExportedXml(
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename(): {"format": "xml"},
                },
            }
        )
        data = await self.exported_data(items, settings)
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        root = lxml.etree.fromstring(data["xml"])
        got_rows = [{e.tag: e.text for e in it} for it in root.findall("item")]
        assert rows == got_rows

    async def assertExportedMultiple(
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename(): {"format": "xml"},
                    self._random_temp_filename(): {"format": "json"},
                },
            }
        )
        data = await self.exported_data(items, settings)
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        # XML
        root = lxml.etree.fromstring(data["xml"])
        xml_rows = [{e.tag: e.text for e in it} for it in root.findall("item")]
        assert rows == xml_rows
        # JSON
        json_rows = json.loads(to_unicode(data["json"]))
        assert rows == json_rows

    async def assertExportedPickle(
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename(): {"format": "pickle"},
                },
            }
        )
        data = await self.exported_data(items, settings)
        expected = [{k: v for k, v in row.items() if v} for row in rows]

        result = self._load_until_eof(data["pickle"], load_func=pickle.load)
        assert result == expected

    async def assertExportedMarshal(
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename(): {"format": "marshal"},
                },
            }
        )
        data = await self.exported_data(items, settings)
        expected = [{k: v for k, v in row.items() if v} for row in rows]

        result = self._load_until_eof(data["marshal"], load_func=marshal.load)
        assert result == expected

    @inline_callbacks_test
    def test_stats_file_success(self):
        settings = {
            "FEEDS": {
                printf_escape(path_to_url(str(self._random_temp_filename()))): {
                    "format": "json",
                }
            },
        }
        crawler = get_crawler(ItemSpider, settings)
        yield crawler.crawl(mockserver=self.mockserver)
        assert "feedexport/success_count/FileFeedStorage" in crawler.stats.get_stats()
        assert crawler.stats.get_value("feedexport/success_count/FileFeedStorage") == 1

    @inline_callbacks_test
    def test_stats_file_failed(self):
        settings = {
            "FEEDS": {
                printf_escape(path_to_url(str(self._random_temp_filename()))): {
                    "format": "json",
                }
            },
        }
        crawler = get_crawler(ItemSpider, settings)
        with mock.patch(
            "scrapy.extensions.feedexport.FileFeedStorage.store",
            side_effect=KeyError("foo"),
        ):
            yield crawler.crawl(mockserver=self.mockserver)
        assert "feedexport/failed_count/FileFeedStorage" in crawler.stats.get_stats()
        assert crawler.stats.get_value("feedexport/failed_count/FileFeedStorage") == 1

    @inline_callbacks_test
    def test_stats_multiple_file(self):
        settings = {
            "FEEDS": {
                printf_escape(path_to_url(str(self._random_temp_filename()))): {
                    "format": "json",
                },
                "stdout:": {
                    "format": "xml",
                },
            },
        }
        crawler = get_crawler(ItemSpider, settings)
        with mock.patch.object(S3FeedStorage, "store"):
            yield crawler.crawl(mockserver=self.mockserver)
        assert "feedexport/success_count/FileFeedStorage" in crawler.stats.get_stats()
        assert "feedexport/success_count/StdoutFeedStorage" in crawler.stats.get_stats()
        assert crawler.stats.get_value("feedexport/success_count/FileFeedStorage") == 1
        assert (
            crawler.stats.get_value("feedexport/success_count/StdoutFeedStorage") == 1
        )

    @coroutine_test
    async def test_export_items(self):
        # feed exporters use field names from Item
        items = [
            self.MyItem({"foo": "bar1", "egg": "spam1"}),
            self.MyItem({"foo": "bar2", "egg": "spam2", "baz": "quux2"}),
        ]
        rows = [
            {"egg": "spam1", "foo": "bar1", "baz": ""},
            {"egg": "spam2", "foo": "bar2", "baz": "quux2"},
        ]
        header = self.MyItem.fields.keys()
        await self.assertExported(items, header, rows)

    @coroutine_test
    async def test_export_no_items_not_store_empty(self):
        for fmt in ("json", "jsonlines", "xml", "csv"):
            settings = {
                "FEEDS": {
                    self._random_temp_filename(): {"format": fmt},
                },
                "FEED_STORE_EMPTY": False,
            }
            data = await self.exported_no_data(settings)
            assert data[fmt] is None

    @coroutine_test
    async def test_start_finish_exporting_items(self):
        items = [
            self.MyItem({"foo": "bar1", "egg": "spam1"}),
        ]
        settings = {
            "FEEDS": {
                self._random_temp_filename(): {"format": "json"},
            },
            "FEED_EXPORT_INDENT": None,
        }

        listener = IsExportingListener()
        InstrumentedFeedSlot.subscribe__listener(listener)

        with mock.patch("scrapy.extensions.feedexport.FeedSlot", InstrumentedFeedSlot):
            await self.exported_data(items, settings)
            assert not listener.start_without_finish
            assert not listener.finish_without_start

    @coroutine_test
    async def test_start_finish_exporting_no_items(self):
        items = []
        settings = {
            "FEEDS": {
                self._random_temp_filename(): {"format": "json"},
            },
            "FEED_EXPORT_INDENT": None,
        }

        listener = IsExportingListener()
        InstrumentedFeedSlot.subscribe__listener(listener)

        with mock.patch("scrapy.extensions.feedexport.FeedSlot", InstrumentedFeedSlot):
            await self.exported_data(items, settings)
            assert not listener.start_without_finish
            assert not listener.finish_without_start

    @coroutine_test
    async def test_start_finish_exporting_items_exception(self):
        items = [
            self.MyItem({"foo": "bar1", "egg": "spam1"}),
        ]
        settings = {
            "FEEDS": {
                self._random_temp_filename(): {"format": "json"},
            },
            "FEED_EXPORTERS": {"json": ExceptionJsonItemExporter},
            "FEED_EXPORT_INDENT": None,
        }

        listener = IsExportingListener()
        InstrumentedFeedSlot.subscribe__listener(listener)

        with mock.patch("scrapy.extensions.feedexport.FeedSlot", InstrumentedFeedSlot):
            await self.exported_data(items, settings)
            assert not listener.start_without_finish
            assert not listener.finish_without_start

    @coroutine_test
    async def test_start_finish_exporting_no_items_exception(self):
        items = []
        settings = {
            "FEEDS": {
                self._random_temp_filename(): {"format": "json"},
            },
            "FEED_EXPORTERS": {"json": ExceptionJsonItemExporter},
            "FEED_EXPORT_INDENT": None,
        }

        listener = IsExportingListener()
        InstrumentedFeedSlot.subscribe__listener(listener)

        with mock.patch("scrapy.extensions.feedexport.FeedSlot", InstrumentedFeedSlot):
            await self.exported_data(items, settings)
            assert not listener.start_without_finish
            assert not listener.finish_without_start

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
                    self._random_temp_filename(): {"format": fmt},
                },
                "FEED_STORE_EMPTY": True,
                "FEED_EXPORT_INDENT": None,
            }
            data = await self.exported_no_data(settings)
            assert expctd == data[fmt]

    @coroutine_test
    async def test_export_no_items_multiple_feeds(self):
        """Make sure that `storage.store` is called for every feed."""
        settings = {
            "FEEDS": {
                self._random_temp_filename(): {"format": "json"},
                self._random_temp_filename(): {"format": "xml"},
                self._random_temp_filename(): {"format": "csv"},
            },
            "FEED_STORAGES": {"file": LogOnStoreFileStorage},
            "FEED_STORE_EMPTY": False,
        }

        with LogCapture() as log:
            await self.exported_no_data(settings)

        assert str(log).count("Storage.store is called") == 0

    @coroutine_test
    async def test_export_multiple_item_classes(self):
        items = [
            self.MyItem({"foo": "bar1", "egg": "spam1"}),
            self.MyItem2({"hello": "world2", "foo": "bar2"}),
            self.MyItem({"foo": "bar3", "egg": "spam3", "baz": "quux3"}),
            {"hello": "world4", "egg": "spam4"},
        ]

        # by default, Scrapy uses fields of the first Item for CSV and
        # all fields for JSON Lines
        header = self.MyItem.fields.keys()
        rows_csv = [
            {"egg": "spam1", "foo": "bar1", "baz": ""},
            {"egg": "", "foo": "bar2", "baz": ""},
            {"egg": "spam3", "foo": "bar3", "baz": "quux3"},
            {"egg": "spam4", "foo": "", "baz": ""},
        ]
        rows_jl = [dict(row) for row in items]
        await self.assertExportedCsv(items, header, rows_csv)
        await self.assertExportedJsonLines(items, rows_jl)

    @coroutine_test
    async def test_export_items_empty_field_list(self):
        # FEED_EXPORT_FIELDS==[] means the same as default None
        items = [{"foo": "bar"}]
        header = ["foo"]
        rows = [{"foo": "bar"}]
        settings = {"FEED_EXPORT_FIELDS": []}
        await self.assertExportedCsv(items, header, rows)
        await self.assertExportedJsonLines(items, rows, settings)

    @coroutine_test
    async def test_export_items_field_list(self):
        items = [{"foo": "bar"}]
        header = ["foo", "baz"]
        rows = [{"foo": "bar", "baz": ""}]
        settings = {"FEED_EXPORT_FIELDS": header}
        await self.assertExported(items, header, rows, settings=settings)

    @coroutine_test
    async def test_export_items_comma_separated_field_list(self):
        items = [{"foo": "bar"}]
        header = ["foo", "baz"]
        rows = [{"foo": "bar", "baz": ""}]
        settings = {"FEED_EXPORT_FIELDS": ",".join(header)}
        await self.assertExported(items, header, rows, settings=settings)

    @coroutine_test
    async def test_export_items_json_field_list(self):
        items = [{"foo": "bar"}]
        header = ["foo", "baz"]
        rows = [{"foo": "bar", "baz": ""}]
        settings = {"FEED_EXPORT_FIELDS": json.dumps(header)}
        await self.assertExported(items, header, rows, settings=settings)

    @coroutine_test
    async def test_export_items_field_names(self):
        items = [{"foo": "bar"}]
        header = {"foo": "Foo"}
        rows = [{"Foo": "bar"}]
        settings = {"FEED_EXPORT_FIELDS": header}
        await self.assertExported(items, list(header.values()), rows, settings=settings)

    @coroutine_test
    async def test_export_items_dict_field_names(self):
        items = [{"foo": "bar"}]
        header = {
            "baz": "Baz",
            "foo": "Foo",
        }
        rows = [{"Baz": "", "Foo": "bar"}]
        settings = {"FEED_EXPORT_FIELDS": header}
        await self.assertExported(items, ["Baz", "Foo"], rows, settings=settings)

    @coroutine_test
    async def test_export_items_json_field_names(self):
        items = [{"foo": "bar"}]
        header = {"foo": "Foo"}
        rows = [{"Foo": "bar"}]
        settings = {"FEED_EXPORT_FIELDS": json.dumps(header)}
        await self.assertExported(items, list(header.values()), rows, settings=settings)

    @coroutine_test
    async def test_export_based_on_item_classes(self):
        items = [
            self.MyItem({"foo": "bar1", "egg": "spam1"}),
            self.MyItem2({"hello": "world2", "foo": "bar2"}),
            {"hello": "world3", "egg": "spam3"},
        ]

        formats = {
            "csv": b"baz,egg,foo\r\n,spam1,bar1\r\n",
            "json": b'[\n{"hello": "world2", "foo": "bar2"}\n]',
            "jsonlines": (
                b'{"foo": "bar1", "egg": "spam1"}\n{"hello": "world2", "foo": "bar2"}\n'
            ),
            "xml": (
                b'<?xml version="1.0" encoding="utf-8"?>\n<items>\n<item>'
                b"<foo>bar1</foo><egg>spam1</egg></item>\n<item><hello>"
                b"world2</hello><foo>bar2</foo></item>\n<item><hello>world3"
                b"</hello><egg>spam3</egg></item>\n</items>"
            ),
        }

        settings = {
            "FEEDS": {
                self._random_temp_filename(): {
                    "format": "csv",
                    "item_classes": [self.MyItem],
                },
                self._random_temp_filename(): {
                    "format": "json",
                    "item_classes": [self.MyItem2],
                },
                self._random_temp_filename(): {
                    "format": "jsonlines",
                    "item_classes": [self.MyItem, self.MyItem2],
                },
                self._random_temp_filename(): {
                    "format": "xml",
                },
            },
        }

        data = await self.exported_data(items, settings)
        for fmt, expected in formats.items():
            assert data[fmt] == expected

    @coroutine_test
    async def test_export_based_on_custom_filters(self):
        items = [
            self.MyItem({"foo": "bar1", "egg": "spam1"}),
            self.MyItem2({"hello": "world2", "foo": "bar2"}),
            {"hello": "world3", "egg": "spam3"},
        ]

        MyItem = self.MyItem

        class CustomFilter1:
            def __init__(self, feed_options):
                pass

            def accepts(self, item):
                return isinstance(item, MyItem)

        class CustomFilter2(scrapy.extensions.feedexport.ItemFilter):
            def accepts(self, item):
                return "foo" in item.fields

        class CustomFilter3(scrapy.extensions.feedexport.ItemFilter):
            def accepts(self, item):
                return (
                    isinstance(item, tuple(self.item_classes)) and item["foo"] == "bar1"
                )

        formats = {
            "json": b'[\n{"foo": "bar1", "egg": "spam1"}\n]',
            "xml": (
                b'<?xml version="1.0" encoding="utf-8"?>\n<items>\n<item>'
                b"<foo>bar1</foo><egg>spam1</egg></item>\n<item><hello>"
                b"world2</hello><foo>bar2</foo></item>\n</items>"
            ),
            "jsonlines": b'{"foo": "bar1", "egg": "spam1"}\n',
        }

        settings = {
            "FEEDS": {
                self._random_temp_filename(): {
                    "format": "json",
                    "item_filter": CustomFilter1,
                },
                self._random_temp_filename(): {
                    "format": "xml",
                    "item_filter": CustomFilter2,
                },
                self._random_temp_filename(): {
                    "format": "jsonlines",
                    "item_classes": [self.MyItem, self.MyItem2],
                    "item_filter": CustomFilter3,
                },
            },
        }

        data = await self.exported_data(items, settings)
        for fmt, expected in formats.items():
            assert data[fmt] == expected

    @coroutine_test
    async def test_export_dicts(self):
        # When dicts are used, only keys from the first row are used as
        # a header for CSV, and all fields are used for JSON Lines.
        items = [
            {"foo": "bar", "egg": "spam"},
            {"foo": "bar", "egg": "spam", "baz": "quux"},
        ]
        rows_csv = [{"egg": "spam", "foo": "bar"}, {"egg": "spam", "foo": "bar"}]
        rows_jl = items
        await self.assertExportedCsv(items, ["foo", "egg"], rows_csv)
        await self.assertExportedJsonLines(items, rows_jl)

    @coroutine_test
    async def test_export_tuple(self):
        items = [
            {"foo": "bar1", "egg": "spam1"},
            {"foo": "bar2", "egg": "spam2", "baz": "quux"},
        ]

        settings = {"FEED_EXPORT_FIELDS": ("foo", "baz")}
        rows = [{"foo": "bar1", "baz": ""}, {"foo": "bar2", "baz": "quux"}]
        await self.assertExported(items, ["foo", "baz"], rows, settings=settings)

    @coroutine_test
    async def test_export_feed_export_fields(self):
        # FEED_EXPORT_FIELDS option allows to order export fields
        # and to select a subset of fields to export, both for Items and dicts.

        for item_cls in [self.MyItem, dict]:
            items = [
                item_cls({"foo": "bar1", "egg": "spam1"}),
                item_cls({"foo": "bar2", "egg": "spam2", "baz": "quux2"}),
            ]

            # export all columns
            settings = {"FEED_EXPORT_FIELDS": "foo,baz,egg"}
            rows = [
                {"egg": "spam1", "foo": "bar1", "baz": ""},
                {"egg": "spam2", "foo": "bar2", "baz": "quux2"},
            ]
            await self.assertExported(
                items, ["foo", "baz", "egg"], rows, settings=settings
            )

            # export a subset of columns
            settings = {"FEED_EXPORT_FIELDS": "egg,baz"}
            rows = [{"egg": "spam1", "baz": ""}, {"egg": "spam2", "baz": "quux2"}]
            await self.assertExported(items, ["egg", "baz"], rows, settings=settings)

    @coroutine_test
    async def test_export_encoding(self):
        items = [{"foo": "Test\xd6"}]

        formats = {
            "json": b'[{"foo": "Test\\u00d6"}]',
            "jsonlines": b'{"foo": "Test\\u00d6"}\n',
            "xml": (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                "<items><item><foo>Test\xd6</foo></item></items>"
            ).encode(),
            "csv": "foo\r\nTest\xd6\r\n".encode(),
        }

        for fmt, expected in formats.items():
            settings = {
                "FEEDS": {
                    self._random_temp_filename(): {"format": fmt},
                },
                "FEED_EXPORT_INDENT": None,
            }
            data = await self.exported_data(items, settings)
            assert data[fmt] == expected

        formats = {
            "json": b'[{"foo": "Test\xd6"}]',
            "jsonlines": b'{"foo": "Test\xd6"}\n',
            "xml": (
                b'<?xml version="1.0" encoding="latin-1"?>\n'
                b"<items><item><foo>Test\xd6</foo></item></items>"
            ),
            "csv": b"foo\r\nTest\xd6\r\n",
        }

        for fmt, expected in formats.items():
            settings = {
                "FEEDS": {
                    self._random_temp_filename(): {"format": fmt},
                },
                "FEED_EXPORT_INDENT": None,
                "FEED_EXPORT_ENCODING": "latin-1",
            }
            data = await self.exported_data(items, settings)
            assert data[fmt] == expected

    @coroutine_test
    async def test_export_multiple_configs(self):
        items = [{"foo": "FOO", "bar": "BAR"}]

        formats = {
            "json": b'[\n{"bar": "BAR"}\n]',
            "xml": (
                b'<?xml version="1.0" encoding="latin-1"?>\n'
                b"<items>\n  <item>\n    <foo>FOO</foo>\n  </item>\n</items>"
            ),
            "csv": b"bar,foo\r\nBAR,FOO\r\n",
        }

        settings = {
            "FEEDS": {
                self._random_temp_filename(): {
                    "format": "json",
                    "indent": 0,
                    "fields": ["bar"],
                    "encoding": "utf-8",
                },
                self._random_temp_filename(): {
                    "format": "xml",
                    "indent": 2,
                    "fields": ["foo"],
                    "encoding": "latin-1",
                },
                self._random_temp_filename(): {
                    "format": "csv",
                    "indent": None,
                    "fields": ["bar", "foo"],
                    "encoding": "utf-8",
                },
            },
        }

        data = await self.exported_data(items, settings)
        for fmt, expected in formats.items():
            assert data[fmt] == expected

    @coroutine_test
    async def test_export_indentation(self):
        items = [
            {"foo": ["bar"]},
            {"key": "value"},
        ]

        test_cases = [
            # JSON
            {
                "format": "json",
                "indent": None,
                "expected": b'[{"foo": ["bar"]},{"key": "value"}]',
            },
            {
                "format": "json",
                "indent": -1,
                "expected": b"""[
{"foo": ["bar"]},
{"key": "value"}
]""",
            },
            {
                "format": "json",
                "indent": 0,
                "expected": b"""[
{"foo": ["bar"]},
{"key": "value"}
]""",
            },
            {
                "format": "json",
                "indent": 2,
                "expected": b"""[
{
  "foo": [
    "bar"
  ]
},
{
  "key": "value"
}
]""",
            },
            {
                "format": "json",
                "indent": 4,
                "expected": b"""[
{
    "foo": [
        "bar"
    ]
},
{
    "key": "value"
}
]""",
            },
            {
                "format": "json",
                "indent": 5,
                "expected": b"""[
{
     "foo": [
          "bar"
     ]
},
{
     "key": "value"
}
]""",
            },
            # XML
            {
                "format": "xml",
                "indent": None,
                "expected": b"""<?xml version="1.0" encoding="utf-8"?>
<items><item><foo><value>bar</value></foo></item><item><key>value</key></item></items>""",
            },
            {
                "format": "xml",
                "indent": -1,
                "expected": b"""<?xml version="1.0" encoding="utf-8"?>
<items>
<item><foo><value>bar</value></foo></item>
<item><key>value</key></item>
</items>""",
            },
            {
                "format": "xml",
                "indent": 0,
                "expected": b"""<?xml version="1.0" encoding="utf-8"?>
<items>
<item><foo><value>bar</value></foo></item>
<item><key>value</key></item>
</items>""",
            },
            {
                "format": "xml",
                "indent": 2,
                "expected": b"""<?xml version="1.0" encoding="utf-8"?>
<items>
  <item>
    <foo>
      <value>bar</value>
    </foo>
  </item>
  <item>
    <key>value</key>
  </item>
</items>""",
            },
            {
                "format": "xml",
                "indent": 4,
                "expected": b"""<?xml version="1.0" encoding="utf-8"?>
<items>
    <item>
        <foo>
            <value>bar</value>
        </foo>
    </item>
    <item>
        <key>value</key>
    </item>
</items>""",
            },
            {
                "format": "xml",
                "indent": 5,
                "expected": b"""<?xml version="1.0" encoding="utf-8"?>
<items>
     <item>
          <foo>
               <value>bar</value>
          </foo>
     </item>
     <item>
          <key>value</key>
     </item>
</items>""",
            },
        ]

        for row in test_cases:
            settings = {
                "FEEDS": {
                    self._random_temp_filename(): {
                        "format": row["format"],
                        "indent": row["indent"],
                    },
                },
            }
            data = await self.exported_data(items, settings)
            assert data[row["format"]] == row["expected"]

    @coroutine_test
    async def test_init_exporters_storages_with_crawler(self):
        settings = {
            "FEED_EXPORTERS": {"csv": FromCrawlerCsvItemExporter},
            "FEED_STORAGES": {"file": FromCrawlerFileFeedStorage},
            "FEEDS": {
                self._random_temp_filename(): {"format": "csv"},
            },
        }
        await self.exported_data(items=[], settings=settings)
        assert FromCrawlerCsvItemExporter.init_with_crawler
        assert FromCrawlerFileFeedStorage.init_with_crawler

    @coroutine_test
    async def test_str_uri(self):
        settings = {
            "FEED_STORE_EMPTY": True,
            "FEEDS": {str(self._random_temp_filename()): {"format": "csv"}},
        }
        data = await self.exported_no_data(settings)
        assert data["csv"] == b""

    @pytest.mark.requires_reactor  # needs a reactor for BlockingFeedStorage
    @coroutine_test
    async def test_multiple_feeds_success_logs_blocking_feed_storage(self):
        settings = {
            "FEEDS": {
                self._random_temp_filename(): {"format": "json"},
                self._random_temp_filename(): {"format": "xml"},
                self._random_temp_filename(): {"format": "csv"},
            },
            "FEED_STORAGES": {"file": DummyBlockingFeedStorage},
        }
        items = [
            {"foo": "bar1", "baz": ""},
            {"foo": "bar2", "baz": "quux"},
        ]
        with LogCapture() as log:
            await self.exported_data(items, settings)

        for fmt in ["json", "xml", "csv"]:
            assert f"Stored {fmt} feed (2 items)" in str(log)

    @coroutine_test
    async def test_multiple_feeds_failing_logs_blocking_feed_storage(self):
        settings = {
            "FEEDS": {
                self._random_temp_filename(): {"format": "json"},
                self._random_temp_filename(): {"format": "xml"},
                self._random_temp_filename(): {"format": "csv"},
            },
            "FEED_STORAGES": {"file": FailingBlockingFeedStorage},
        }
        items = [
            {"foo": "bar1", "baz": ""},
            {"foo": "bar2", "baz": "quux"},
        ]
        with LogCapture() as log:
            await self.exported_data(items, settings)

        for fmt in ["json", "xml", "csv"]:
            assert f"Error storing {fmt} feed (2 items)" in str(log)

    @coroutine_test
    async def test_extend_kwargs(self):
        items = [{"foo": "FOO", "bar": "BAR"}]

        expected_with_title_csv = b"foo,bar\r\nFOO,BAR\r\n"
        expected_without_title_csv = b"FOO,BAR\r\n"
        test_cases = [
            # with title
            {
                "options": {
                    "format": "csv",
                    "item_export_kwargs": {"include_headers_line": True},
                },
                "expected": expected_with_title_csv,
            },
            # without title
            {
                "options": {
                    "format": "csv",
                    "item_export_kwargs": {"include_headers_line": False},
                },
                "expected": expected_without_title_csv,
            },
        ]

        for row in test_cases:
            feed_options = row["options"]
            settings = {
                "FEEDS": {
                    self._random_temp_filename(): feed_options,
                },
                "FEED_EXPORT_INDENT": None,
            }

            data = await self.exported_data(items, settings)
            assert data[feed_options["format"]] == row["expected"]

    @coroutine_test
    async def test_storage_file_no_postprocessing(self):
        @implementer(IFeedStorage)
        class Storage:
            def __init__(self, uri, *, feed_options=None):
                pass

            def open(self, spider):
                Storage.open_file = tempfile.NamedTemporaryFile(prefix="feed-")
                return Storage.open_file

            def store(self, file):
                Storage.store_file = file
                file.close()

        settings = {
            "FEEDS": {self._random_temp_filename(): {"format": "jsonlines"}},
            "FEED_STORAGES": {"file": Storage},
        }
        await self.exported_no_data(settings)
        assert Storage.open_file is Storage.store_file

    @coroutine_test
    async def test_storage_file_postprocessing(self):
        @implementer(IFeedStorage)
        class Storage:
            def __init__(self, uri, *, feed_options=None):
                pass

            def open(self, spider):
                Storage.open_file = tempfile.NamedTemporaryFile(prefix="feed-")
                return Storage.open_file

            def store(self, file):
                Storage.store_file = file
                Storage.file_was_closed = file.closed
                file.close()

        settings = {
            "FEEDS": {
                self._random_temp_filename(): {
                    "format": "jsonlines",
                    "postprocessing": [
                        "scrapy.extensions.postprocessing.GzipPlugin",
                    ],
                },
            },
            "FEED_STORAGES": {"file": Storage},
        }
        await self.exported_no_data(settings)
        assert Storage.open_file is Storage.store_file
        assert not Storage.file_was_closed


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
                f"file:///{tmp.name}": {
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
        self, feed_exporter_signal_handler: Callable, feed_slot_signal_handler: Callable
    ) -> None:
        crawler = get_crawler(settings_dict=self.settings)
        feed_exporter = FeedExporter.from_crawler(crawler)
        spider = scrapy.Spider("default")
        spider.crawler = crawler
        crawler.signals.connect(
            feed_exporter_signal_handler,
            signal=signals.feed_exporter_closed,
        )
        crawler.signals.connect(
            feed_slot_signal_handler, signal=signals.feed_slot_closed
        )
        feed_exporter.open_spider(spider)
        for item in self.items:
            feed_exporter.item_scraped(item, spider)
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
        settings = {
            "FEEDS": {
                "unsupported://uri": {},
            },
        }
        crawler = get_crawler(settings_dict=settings)
        with pytest.raises(NotConfigured):
            FeedExporter.from_crawler(crawler)

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
            FeedExporter.from_crawler(crawler)

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
            exporter = FeedExporter.from_crawler(crawler)
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
        exporter = FeedExporter.from_crawler(crawler)
        assert isinstance(exporter, FeedExporter)


class TestURIParams(ABC):
    spider_name = "uri_params_spider"
    deprecated_options = False

    @abstractmethod
    def build_settings(self, uri="file:///tmp/foobar", uri_params=None):
        raise NotImplementedError

    def _crawler_feed_exporter(self, settings):
        if self.deprecated_options:
            with pytest.warns(
                ScrapyDeprecationWarning,
                match="The `FEED_URI` and `FEED_FORMAT` settings have been deprecated",
            ):
                crawler = get_crawler(settings_dict=settings)
        else:
            crawler = get_crawler(settings_dict=settings)
        feed_exporter = crawler.get_extension(FeedExporter)
        return crawler, feed_exporter

    def test_default(self):
        settings = self.build_settings(
            uri="file:///tmp/%(name)s",
        )
        crawler, feed_exporter = self._crawler_feed_exporter(settings)
        spider = scrapy.Spider(self.spider_name)
        spider.crawler = crawler

        with warnings.catch_warnings():
            warnings.simplefilter("error", ScrapyDeprecationWarning)
            feed_exporter.open_spider(spider)

        assert feed_exporter.slots[0].uri == f"file:///tmp/{self.spider_name}"

    def test_none(self):
        def uri_params(params, spider):
            pass

        settings = self.build_settings(
            uri="file:///tmp/%(name)s",
            uri_params=uri_params,
        )
        crawler, feed_exporter = self._crawler_feed_exporter(settings)
        spider = scrapy.Spider(self.spider_name)
        spider.crawler = crawler

        feed_exporter.open_spider(spider)

        assert feed_exporter.slots[0].uri == f"file:///tmp/{self.spider_name}"

    def test_empty_dict(self):
        def uri_params(params, spider):
            return {}

        settings = self.build_settings(
            uri="file:///tmp/%(name)s",
            uri_params=uri_params,
        )
        crawler, feed_exporter = self._crawler_feed_exporter(settings)
        spider = scrapy.Spider(self.spider_name)
        spider.crawler = crawler

        with warnings.catch_warnings():
            warnings.simplefilter("error", ScrapyDeprecationWarning)
            with pytest.raises(KeyError):
                feed_exporter.open_spider(spider)

    def test_params_as_is(self):
        def uri_params(params, spider):
            return params

        settings = self.build_settings(
            uri="file:///tmp/%(name)s",
            uri_params=uri_params,
        )
        crawler, feed_exporter = self._crawler_feed_exporter(settings)
        spider = scrapy.Spider(self.spider_name)
        spider.crawler = crawler
        with warnings.catch_warnings():
            warnings.simplefilter("error", ScrapyDeprecationWarning)
            feed_exporter.open_spider(spider)

        assert feed_exporter.slots[0].uri == f"file:///tmp/{self.spider_name}"

    def test_custom_param(self):
        def uri_params(params, spider):
            return {**params, "foo": self.spider_name}

        settings = self.build_settings(
            uri="file:///tmp/%(foo)s",
            uri_params=uri_params,
        )
        crawler, feed_exporter = self._crawler_feed_exporter(settings)
        spider = scrapy.Spider(self.spider_name)
        spider.crawler = crawler
        with warnings.catch_warnings():
            warnings.simplefilter("error", ScrapyDeprecationWarning)
            feed_exporter.open_spider(spider)

        assert feed_exporter.slots[0].uri == f"file:///tmp/{self.spider_name}"


class TestURIParamsSetting(TestURIParams):
    deprecated_options = True

    def build_settings(self, uri="file:///tmp/foobar", uri_params=None):
        extra_settings = {}
        if uri_params:
            extra_settings["FEED_URI_PARAMS"] = uri_params
        return {
            "FEED_URI": uri,
            **extra_settings,
        }


class TestURIParamsFeedOption(TestURIParams):
    deprecated_options = False

    def build_settings(self, uri="file:///tmp/foobar", uri_params=None):
        options = {
            "format": "jl",
        }
        if uri_params:
            options["uri_params"] = uri_params
        return {
            "FEEDS": {
                uri: options,
            },
        }
