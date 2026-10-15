from __future__ import annotations

import logging
import tempfile
import warnings
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import pytest

import scrapy
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.extensions.feedexport import FeedExporter, apply_uri_params
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test
from tests.utils.feedexport import MyItem, crawl_items, path_to_url, printf_escape

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from scrapy.crawler import Crawler
    from tests.mockserver.http import MockServer


class TestURIParams(ABC):
    spider_name = "uri_params_spider"
    deprecated_options = False

    @abstractmethod
    def build_settings(
        self,
        uri: str = "file:///tmp/foobar",
        uri_params: Callable[..., dict[str, Any] | None] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _crawler_feed_exporter(
        self, settings: dict[str, Any]
    ) -> tuple[Crawler, FeedExporter]:
        if self.deprecated_options:
            with pytest.warns(
                ScrapyDeprecationWarning,
                match="The `FEED_URI` and `FEED_FORMAT` settings have been deprecated",
            ):
                crawler = get_crawler(settings_dict=settings)
        else:
            crawler = get_crawler(settings_dict=settings)
        feed_exporter = crawler.get_extension(FeedExporter)
        assert feed_exporter is not None
        return crawler, feed_exporter

    def test_default(self):
        settings = self.build_settings(
            uri="file:///tmp/%(name)s",
        )
        crawler, feed_exporter = self._crawler_feed_exporter(settings)
        spider = scrapy.Spider.from_crawler(crawler, self.spider_name)

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
        spider = scrapy.Spider.from_crawler(crawler, self.spider_name)

        feed_exporter.open_spider(spider)

        assert feed_exporter.slots[0].uri == f"file:///tmp/{self.spider_name}"

    def test_empty_dict(self, caplog: pytest.LogCaptureFixture) -> None:
        def uri_params(params, spider):
            return {}

        settings = self.build_settings(
            uri="file:///tmp/%(name)s",
            uri_params=uri_params,
        )
        crawler, feed_exporter = self._crawler_feed_exporter(settings)
        spider = scrapy.Spider.from_crawler(crawler, self.spider_name)

        with warnings.catch_warnings():
            warnings.simplefilter("error", ScrapyDeprecationWarning)
            with caplog.at_level(logging.ERROR):
                feed_exporter.open_spider(spider)

        assert feed_exporter.slots == []
        assert "'name'" in caplog.text

    def test_params_as_is(self):
        def uri_params(params, spider):
            return params

        settings = self.build_settings(
            uri="file:///tmp/%(name)s",
            uri_params=uri_params,
        )
        crawler, feed_exporter = self._crawler_feed_exporter(settings)
        spider = scrapy.Spider.from_crawler(crawler, self.spider_name)
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
        spider = scrapy.Spider.from_crawler(crawler, self.spider_name)
        with warnings.catch_warnings():
            warnings.simplefilter("error", ScrapyDeprecationWarning)
            feed_exporter.open_spider(spider)

        assert feed_exporter.slots[0].uri == f"file:///tmp/{self.spider_name}"


class TestURIParamsSetting(TestURIParams):
    deprecated_options = True

    def build_settings(
        self,
        uri: str = "file:///tmp/foobar",
        uri_params: Callable[..., dict[str, Any] | None] | None = None,
    ) -> dict[str, Any]:
        extra_settings: dict[str, Any] = {}
        if uri_params:
            extra_settings["FEED_URI_PARAMS"] = uri_params
        return {
            "FEED_URI": uri,
            **extra_settings,
        }


class TestURIParamsFeedOption(TestURIParams):
    deprecated_options = False

    def build_settings(
        self,
        uri: str = "file:///tmp/foobar",
        uri_params: Callable[..., dict[str, Any] | None] | None = None,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "format": "jl",
        }
        if uri_params:
            options["uri_params"] = uri_params
        return {
            "FEEDS": {
                uri: options,
            },
        }


class TestApplyUriParams:
    params = {
        "name": "myspider",
        "time": "2020-01-01T00-00-00",
        "batch_id": 2,
        "batch_time": "2020-01-01T00-00-00",
    }

    @pytest.mark.parametrize(
        ("uri_template", "expected"),
        [
            # Placeholders are substituted, including width/flags.
            ("/data/%(name)s/%(time)s.json", "/data/myspider/2020-01-01T00-00-00.json"),
            ("/data/%(batch_id)05d.json", "/data/00002.json"),
            # Percent-encoding is kept verbatim (#6425, #5794).
            (
                "file:///path%20with%20spaces/%(name)s.json",
                "file:///path%20with%20spaces/myspider.json",
            ),
            (
                "ftp://user:2%23um25%21M%23JZ@ftp.example.com/%(name)s.csv",
                "ftp://user:2%23um25%21M%23JZ@ftp.example.com/myspider.csv",
            ),
            # A lone percent character next to a placeholder stays literal.
            ("/100%/%(name)s.json", "/100%/myspider.json"),
        ],
    )
    def test_apply_uri_params(self, uri_template: str, expected: str) -> None:
        assert apply_uri_params(uri_template, self.params) == expected


@coroutine_test
async def test_pathlib_uri_with_placeholders(
    mockserver: MockServer, tmp_path: Path
) -> None:
    feed_dir = tmp_path / "pathlib_placeholders"
    feed_dir.mkdir()
    items = [MyItem({"foo": "bar1", "egg": "spam1"})]

    settings = {
        "FEEDS": {
            feed_dir / "%(time)s.json": {"format": "json"},
        },
    }
    await crawl_items(mockserver, items, settings)

    files = list(feed_dir.iterdir())
    assert len(files) == 1
    assert "%(time)s" not in files[0].name
    assert files[0].suffix == ".json"


@coroutine_test
async def test_pathlib_uri_with_spaces_and_unicode(
    mockserver: MockServer, tmp_path: Path
) -> None:
    # A pathlib.Path key with spaces and non-ASCII characters must be kept
    # verbatim (not percent-encoded), while %()s placeholders are still
    # substituted. %(name)s resolves to the spider name deterministically,
    # so the resulting file name can be asserted exactly.
    feed_dir = tmp_path / "pathlib_spaces_unicode"
    feed_dir.mkdir()
    items = [MyItem({"foo": "bar1", "egg": "spam1"})]

    settings = {
        "FEEDS": {
            feed_dir / "out %(name)s ünïcode.json": {"format": "json"},
        },
    }
    await crawl_items(mockserver, items, settings)

    files = list(feed_dir.iterdir())
    assert len(files) == 1
    assert files[0].name == "out testspider ünïcode.json"


@coroutine_test
async def test_str_uri_with_percent_encoding_and_placeholder(
    mockserver: MockServer, tmp_path: Path
) -> None:
    # A percent-encoded string URI (e.g. %20 for a space) must reach
    # storage verbatim rather than being misinterpreted as a printf
    # directive, while %()s placeholders are still substituted. See #6425
    # and #5794.
    feed_dir = tmp_path / "dir with spaces"
    feed_dir.mkdir()
    items = [MyItem({"foo": "bar1", "egg": "spam1"})]

    settings = {
        "FEEDS": {
            f"{feed_dir.as_uri()}/%(time)s.json": {"format": "json"},
        },
    }
    await crawl_items(mockserver, items, settings)

    files = list(feed_dir.iterdir())
    assert len(files) == 1
    assert "%(time)s" not in files[0].name
    assert files[0].suffix == ".json"


@coroutine_test
async def test_bad_uri_placeholder_skips_only_that_feed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.NamedTemporaryFile(suffix="json") as tmp:
        settings = {
            "FEEDS": {
                printf_escape(path_to_url(tmp.name)): {"format": "json"},
                "file:///nonexistent/%(undefined_attr)s.json": {"format": "json"},
            },
        }
        crawler = get_crawler(settings_dict=settings)
        feed_exporter = build_from_crawler(FeedExporter, crawler)
        spider = scrapy.Spider.from_crawler(crawler, "default")
        with caplog.at_level(logging.ERROR):
            feed_exporter.open_spider(spider)
        assert len(feed_exporter.slots) == 1
        assert "undefined_attr" in caplog.text
        await feed_exporter.close_spider(spider)
