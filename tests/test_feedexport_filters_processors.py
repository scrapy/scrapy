from __future__ import annotations

from typing import TYPE_CHECKING

from scrapy.extensions.feedexport import ItemFilter
from tests.utils.decorators import coroutine_test
from tests.utils.feedexport import (
    MyItem,
    MyItem2,
    crawl_items,
    export_by_format,
    path_to_url,
    unique_path,
)

if TYPE_CHECKING:
    from pathlib import Path

    from tests.mockserver.http import MockServer


@coroutine_test
async def test_export_based_on_item_classes(
    mockserver: MockServer, tmp_path: Path
) -> None:
    items = [
        MyItem({"foo": "bar1", "egg": "spam1"}),
        MyItem2({"hello": "world2", "foo": "bar2"}),
        {"hello": "world3", "egg": "spam3"},
    ]

    formats = {
        "csv": b"foo,egg,baz\r\nbar1,spam1,\r\n",
        "json": b'[\n{"foo": "bar2", "hello": "world2"}\n]',
        "jsonlines": (
            b'{"foo": "bar1", "egg": "spam1"}\n{"foo": "bar2", "hello": "world2"}\n'
        ),
        "xml": (
            b'<?xml version="1.0" encoding="utf-8"?>\n<items>\n<item>'
            b"<foo>bar1</foo><egg>spam1</egg></item>\n<item><foo>"
            b"bar2</foo><hello>world2</hello></item>\n<item><hello>world3"
            b"</hello><egg>spam3</egg></item>\n</items>"
        ),
    }

    settings = {
        "FEEDS": {
            unique_path(tmp_path): {
                "format": "csv",
                "item_classes": [MyItem],
            },
            unique_path(tmp_path): {
                "format": "json",
                "item_classes": [MyItem2],
            },
            unique_path(tmp_path): {
                "format": "jsonlines",
                "item_classes": [MyItem, MyItem2],
            },
            unique_path(tmp_path): {
                "format": "xml",
            },
        },
    }

    data = await export_by_format(mockserver, items, settings)
    for fmt, expected in formats.items():
        assert data[fmt] == expected


@coroutine_test
async def test_export_based_on_custom_filters(
    mockserver: MockServer, tmp_path: Path
) -> None:
    items = [
        MyItem({"foo": "bar1", "egg": "spam1"}),
        MyItem2({"hello": "world2", "foo": "bar2"}),
        {"hello": "world3", "egg": "spam3"},
    ]

    class CustomFilter1:
        def __init__(self, feed_options):
            pass

        def accepts(self, item):
            return isinstance(item, MyItem)

    class CustomFilter2(ItemFilter):
        def accepts(self, item):
            return "foo" in item.fields

    class CustomFilter3(ItemFilter):
        def accepts(self, item):
            return (
                isinstance(item, tuple(self.item_classes)) and item["foo"] == "bar1"  # type: ignore[index]
            )

    formats = {
        "json": b'[\n{"foo": "bar1", "egg": "spam1"}\n]',
        "xml": (
            b'<?xml version="1.0" encoding="utf-8"?>\n<items>\n<item>'
            b"<foo>bar1</foo><egg>spam1</egg></item>\n<item><foo>"
            b"bar2</foo><hello>world2</hello></item>\n</items>"
        ),
        "jsonlines": b'{"foo": "bar1", "egg": "spam1"}\n',
    }

    settings = {
        "FEEDS": {
            unique_path(tmp_path): {
                "format": "json",
                "item_filter": CustomFilter1,
            },
            unique_path(tmp_path): {
                "format": "xml",
                "item_filter": CustomFilter2,
            },
            unique_path(tmp_path): {
                "format": "jsonlines",
                "item_classes": [MyItem, MyItem2],
                "item_filter": CustomFilter3,
            },
        },
    }

    data = await export_by_format(mockserver, items, settings)
    for fmt, expected in formats.items():
        assert data[fmt] == expected


class TestItemFilter:
    def test_no_feed_options(self):
        item_filter = ItemFilter(None)
        assert item_filter.item_classes == ()
        assert item_filter.accepts(MyItem({"foo": "bar"}))


def split_foo(item):
    for value in item["foo"].split(","):
        yield {"foo": value}


def drop_item(item):
    return []


@coroutine_test
async def test_export_based_on_item_processors(
    mockserver: MockServer, tmp_path: Path
) -> None:
    items = [
        MyItem({"foo": "bar1,bar2"}),
        {"foo": "bar3"},
    ]

    formats = {
        "jsonlines": b'{"foo": "bar1"}\n{"foo": "bar2"}\n{"foo": "bar3"}\n',
        "json": b'[\n{"foo": "bar1"},\n{"foo": "bar2"},\n{"foo": "bar3"}\n]',
        "xml": (
            b'<?xml version="1.0" encoding="utf-8"?>\n<items>\n'
            b"<item><foo>bar1</foo></item>\n<item><foo>bar2</foo></item>\n</items>"
        ),
        "csv": b"",
    }

    settings = {
        "FEEDS": {
            unique_path(tmp_path): {
                "format": "jsonlines",
                "item_processor": split_foo,
            },
            unique_path(tmp_path): {
                "format": "json",
                "item_processor": "tests.test_feedexport_filters_processors.split_foo",
            },
            unique_path(tmp_path): {
                "format": "xml",
                "item_classes": [MyItem],
                "item_processor": split_foo,
            },
            unique_path(tmp_path): {
                "format": "csv",
                "item_processor": drop_item,
            },
        },
    }

    data = await export_by_format(mockserver, items, settings)
    for fmt, expected in formats.items():
        assert data[fmt] == expected


@coroutine_test
async def test_item_processor_stats(mockserver: MockServer, tmp_path: Path) -> None:
    settings = {
        "FEEDS": {
            path_to_url(unique_path(tmp_path)): {
                "format": "jsonlines",
                "item_processor": split_foo,
            },
        },
    }
    crawler = await crawl_items(mockserver, [{"foo": "bar1,bar2"}], settings)

    assert crawler.stats.get_value("item_scraped_count") == 1
    assert crawler.stats.get_value("feedexport/item_count/FileFeedStorage") == 2
