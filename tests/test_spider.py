from __future__ import annotations

from typing import Any
from unittest import mock

import pytest
from testfixtures import LogCapture

from scrapy import signals
from scrapy.crawler import Crawler
from scrapy.http import Response, TextResponse, XmlResponse
from scrapy.settings import Settings
from scrapy.spiders import CSVFeedSpider, Spider, XMLFeedSpider
from scrapy.utils.test import get_crawler, get_reactor_settings
from tests import get_testdata
from tests.utils.decorators import inline_callbacks_test


class TestSpider:
    spider_class = Spider

    def test_base_spider(self):
        spider = self.spider_class("example.com")
        assert spider.name == "example.com"
        assert spider.start_urls == []  # pylint: disable=use-implicit-booleaness-not-comparison

    def test_spider_args(self):
        """``__init__`` method arguments are assigned to spider attributes"""
        spider = self.spider_class("example.com", foo="bar")
        assert spider.foo == "bar"

    def test_spider_without_name(self):
        """``__init__`` method arguments are assigned to spider attributes"""
        msg = "must have a name"
        with pytest.raises(ValueError, match=msg):
            self.spider_class()
        with pytest.raises(ValueError, match=msg):
            self.spider_class(somearg="foo")

    def test_from_crawler_crawler_and_settings_population(self):
        crawler = get_crawler()
        spider = self.spider_class.from_crawler(crawler, "example.com")
        assert hasattr(spider, "crawler")
        assert spider.crawler is crawler
        assert hasattr(spider, "settings")
        assert spider.settings is crawler.settings

    def test_from_crawler_init_call(self):
        with mock.patch.object(
            self.spider_class, "__init__", return_value=None
        ) as mock_init:
            self.spider_class.from_crawler(get_crawler(), "example.com", foo="bar")
            mock_init.assert_called_once_with("example.com", foo="bar")

    def test_closed_signal_call(self):
        class TestSpider(self.spider_class):
            closed_called = False

            def closed(self, reason):
                self.closed_called = True

        crawler = get_crawler()
        spider = TestSpider.from_crawler(crawler, "example.com")
        crawler.signals.send_catch_log(signal=signals.spider_opened, spider=spider)
        crawler.signals.send_catch_log(
            signal=signals.spider_closed, spider=spider, reason=None
        )
        assert spider.closed_called

    def test_update_settings(self):
        spider_settings = {"TEST1": "spider", "TEST2": "spider"}
        project_settings = {"TEST1": "project", "TEST3": "project"}
        self.spider_class.custom_settings = spider_settings
        settings = Settings(project_settings, priority="project")

        self.spider_class.update_settings(settings)
        assert settings.get("TEST1") == "spider"
        assert settings.get("TEST2") == "spider"
        assert settings.get("TEST3") == "project"

    @inline_callbacks_test
    def test_settings_in_from_crawler(self):
        spider_settings = {"TEST1": "spider", "TEST2": "spider"}
        project_settings = {
            "TEST1": "project",
            "TEST3": "project",
            **get_reactor_settings(),
        }

        class TestSpider(self.spider_class):
            name = "test"
            custom_settings = spider_settings

            @classmethod
            def from_crawler(cls, crawler: Crawler, *args: Any, **kwargs: Any):
                spider = super().from_crawler(crawler, *args, **kwargs)
                spider.settings.set("TEST1", "spider_instance", priority="spider")
                return spider

        crawler = Crawler(TestSpider, project_settings)
        assert crawler.settings.get("TEST1") == "spider"
        assert crawler.settings.get("TEST2") == "spider"
        assert crawler.settings.get("TEST3") == "project"
        yield crawler.crawl()
        assert crawler.settings.get("TEST1") == "spider_instance"

    def test_logger(self):
        spider = self.spider_class("example.com")
        with LogCapture() as lc:
            spider.logger.info("test log msg")
        lc.check(("example.com", "INFO", "test log msg"))

        record = lc.records[0]
        assert "spider" in record.__dict__
        assert record.spider is spider

    def test_log(self):
        spider = self.spider_class("example.com")
        with mock.patch("scrapy.spiders.Spider.logger") as mock_logger:
            spider.log("test log msg", "INFO")
        mock_logger.log.assert_called_once_with("INFO", "test log msg")


class TestXMLFeedSpider(TestSpider):
    spider_class = XMLFeedSpider

    def test_register_namespace(self):
        body = b"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns:x="http://www.google.com/schemas/sitemap/0.84"
                xmlns:y="http://www.example.com/schemas/extras/1.0">
        <url><x:loc>http://www.example.com/Special-Offers.html</x:loc><y:updated>2009-08-16</y:updated>
            <other value="bar" y:custom="fuu"/>
        </url>
        <url><loc>http://www.example.com/</loc><y:updated>2009-08-16</y:updated><other value="foo"/></url>
        </urlset>"""
        response = XmlResponse(url="http://example.com/sitemap.xml", body=body)

        class _XMLSpider(self.spider_class):
            itertag = "url"
            namespaces = (
                ("a", "http://www.google.com/schemas/sitemap/0.84"),
                ("b", "http://www.example.com/schemas/extras/1.0"),
            )

            def parse_node(self, response, selector):
                yield {
                    "loc": selector.xpath("a:loc/text()").getall(),
                    "updated": selector.xpath("b:updated/text()").getall(),
                    "other": selector.xpath("other/@value").getall(),
                    "custom": selector.xpath("other/@b:custom").getall(),
                }

        for iterator in ("iternodes", "xml"):
            spider = _XMLSpider("example", iterator=iterator)
            output = list(spider._parse(response))
            assert len(output) == 2, iterator
            assert output == [
                {
                    "loc": ["http://www.example.com/Special-Offers.html"],
                    "updated": ["2009-08-16"],
                    "custom": ["fuu"],
                    "other": ["bar"],
                },
                {
                    "loc": [],
                    "updated": ["2009-08-16"],
                    "other": ["foo"],
                    "custom": [],
                },
            ], iterator


class TestCSVFeedSpider(TestSpider):
    spider_class = CSVFeedSpider

    def test_parse_rows(self):
        body = get_testdata("feeds", "feed-sample6.csv")
        response = Response("http://example.org/dummy.csv", body=body)

        class _CrawlSpider(self.spider_class):
            name = "test"
            delimiter = ","
            quotechar = "'"

            def parse_row(self, response, row):
                return row

        spider = _CrawlSpider()
        rows = list(spider.parse_rows(response))
        assert rows[0] == {"id": "1", "name": "alpha", "value": "foobar"}
        assert len(rows) == 4


class TestNoParseMethodSpider:
    spider_class = Spider

    def test_undefined_parse_method(self):
        spider = self.spider_class("example.com")
        text = b"Random text"
        resp = TextResponse(url="http://www.example.com/random_url", body=text)

        exc_msg = "Spider.parse callback is not defined"
        with pytest.raises(NotImplementedError, match=exc_msg):
            spider.parse(resp)
