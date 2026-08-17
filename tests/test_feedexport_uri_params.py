from __future__ import annotations

import warnings
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import pytest

import scrapy
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.extensions.feedexport import FeedExporter
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from collections.abc import Callable

    from scrapy.crawler import Crawler


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

    def test_empty_dict(self):
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
