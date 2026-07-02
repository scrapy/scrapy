from __future__ import annotations

import warnings
from abc import ABC, abstractmethod

import pytest

import scrapy
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.extensions.feedexport import FeedExporter, _format_uri_template
from scrapy.utils.test import get_crawler


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

    def test_percent_encoded_characters(self):
        """Percent-encoded characters in the URI (e.g. in an FTP password)
        must not be interpreted as printf-style format specifiers (#5794)."""
        settings = self.build_settings(
            uri="ftp://user:2%23um25%21M%23JZ@ftp.example.com/%(name)s.csv",
        )
        crawler, feed_exporter = self._crawler_feed_exporter(settings)
        spider = scrapy.Spider(self.spider_name)
        spider.crawler = crawler
        with warnings.catch_warnings():
            warnings.simplefilter("error", ScrapyDeprecationWarning)
            feed_exporter.open_spider(spider)

        assert (
            feed_exporter.slots[0].uri
            == f"ftp://user:2%23um25%21M%23JZ@ftp.example.com/{self.spider_name}.csv"
        )


class TestFormatURITemplate:
    params = {
        "time": "2026-07-02T00-00-00",
        "batch_id": 3,
        "name": "myspider",
    }

    @pytest.mark.parametrize(
        ("template", "expected"),
        [
            # percent-encoded characters are left untouched (#5794)
            (
                "ftp://user:2%23um25%21M%23JZ@ftp.example.com/file.csv",
                "ftp://user:2%23um25%21M%23JZ@ftp.example.com/file.csv",
            ),
            # named placeholders are substituted as before
            (
                "s3://bucket/%(name)s/%(time)s.json",
                "s3://bucket/myspider/2026-07-02T00-00-00.json",
            ),
            # conversion specs of named placeholders keep working
            (
                "file:///tmp/batch-%(batch_id)05d.csv",
                "file:///tmp/batch-00003.csv",
            ),
            # the %% printf escape keeps working
            (
                "file:///tmp/100%%-%(name)s.csv",
                "file:///tmp/100%-myspider.csv",
            ),
            # %25s is no longer read as a width-25 %s specifier, which used
            # to silently inject the whole params dict into the URI
            (
                "ftp://user:pa%25ss@host/file-%(name)s.csv",
                "ftp://user:pa%25ss@host/file-myspider.csv",
            ),
        ],
    )
    def test_substitution(self, template, expected):
        assert _format_uri_template(template, self.params) == expected

    def test_missing_key_raises(self):
        with pytest.raises(KeyError):
            _format_uri_template("file:///tmp/%(missing)s.csv", self.params)


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
