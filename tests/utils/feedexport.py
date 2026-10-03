from __future__ import annotations

import csv
import itertools
import json
import marshal
import pickle
from io import BytesIO
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any
from urllib.parse import urljoin
from urllib.request import pathname2url

import lxml.etree

from scrapy import Field, Item, Spider
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from scrapy.crawler import Crawler
    from tests.mockserver.http import MockServer


def path_to_url(path: str | Path) -> str:
    return urljoin("file:", pathname2url(str(path)))


def printf_escape(s: str) -> str:
    return s.replace("%", "%%")


class MyItem(Item):
    foo = Field()
    egg = Field()
    baz = Field()


class MyItem2(Item):
    foo = Field()
    hello = Field()


_path_ids = itertools.count()


def unique_path(tmp_path: Path) -> Path:
    """Return a path inside *tmp_path* that no previous call returned."""
    return tmp_path / f"feed{next(_path_ids)}"


async def crawl_items(
    mockserver: MockServer, items: Iterable[Any], settings: dict[str, Any]
) -> Crawler:
    """Run a spider that yields *items* from a single response with
    *settings*, and return its crawler."""

    class TestSpider(Spider):
        name = "testspider"
        start_urls = [mockserver.url("/")]

        def parse(self, response):
            yield from items

    crawler = get_crawler(TestSpider, settings)
    await crawler.crawl_async()
    return crawler


async def export_by_path(
    mockserver: MockServer, items: Iterable[Any], settings: dict[str, Any]
) -> dict[str | Path, bytes]:
    """Export *items* with *settings*, whose ``FEEDS`` are keyed by local
    paths, and return the contents of those paths that were written."""
    feeds = settings["FEEDS"]
    feed_urls = {
        printf_escape(path_to_url(path)): options for path, options in feeds.items()
    }
    await crawl_items(mockserver, items, {**settings, "FEEDS": feed_urls})
    return {path: Path(path).read_bytes() for path in feeds if Path(path).exists()}


def csv_header(data: bytes) -> list[str]:
    """Return the column names of the CSV feed *data*."""
    return next(csv.reader(data.decode().splitlines()))


def _parse_csv(data: bytes) -> list[Any]:
    # CSV cannot tell an empty field from a missing one, so empty fields are
    # left out, matching how the other formats export missing fields.
    return [
        {k: v for k, v in row.items() if v}
        for row in csv.DictReader(data.decode().splitlines())
    ]


def _parse_jsonlines(data: bytes) -> list[Any]:
    return [json.loads(line) for line in data.splitlines()]


def _parse_xml(data: bytes) -> list[Any]:
    root = lxml.etree.fromstring(data)
    return [{e.tag: e.text for e in item} for item in root.findall("item")]


def _load_until_eof(data: bytes, load: Callable[[IO[bytes]], Any]) -> list[Any]:
    file = BytesIO(data)
    result: list[Any] = []
    while True:
        try:
            result.append(load(file))
        except EOFError:
            return result


def _parse_pickle(data: bytes) -> list[Any]:
    return _load_until_eof(data, pickle.load)


def _parse_marshal(data: bytes) -> list[Any]:
    return _load_until_eof(data, marshal.load)


#: Functions that turn feed contents back into items, by feed format.
PARSERS: dict[str, Callable[[bytes], list[Any]]] = {
    "csv": _parse_csv,
    "json": json.loads,
    "jsonlines": _parse_jsonlines,
    "xml": _parse_xml,
    "pickle": _parse_pickle,
    "marshal": _parse_marshal,
}
