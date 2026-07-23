from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest import mock
from urllib.parse import urlencode

import pytest
from testfixtures import LogCapture

from scrapy import signals
from scrapy.crawler import Crawler
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request, Response, TextResponse, XmlResponse
from scrapy.settings import Settings
from scrapy.spiders import CSVFeedSpider, Spider, XMLFeedSpider
from scrapy.utils.test import get_crawler, get_reactor_settings
from tests import get_testdata
from tests.spiders import MockServerSpider
from tests.utils.decorators import coroutine_test, inline_callbacks_test

if TYPE_CHECKING:
    from tests.mockserver.http import MockServer


class RawFeedSpider(MockServerSpider):
    """Serves ``feed_body`` from the mock server so that it reaches the spider
    through a regular crawl.

    This lets the feed-spider tests exercise the parsing logic through the
    public interface (the default callback that the engine picks) instead of
    calling internal methods directly.
    """

    name = "test"
    content_type = "text/xml"
    feed_body = ""

    async def start(self):
        raw = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: {self.content_type}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
            f"{self.feed_body}"
        )
        yield Request(self.mockserver.url("/raw?" + urlencode({"raw": raw})))


async def run_feed_crawl(spider_cls, mockserver):
    """Crawl a single feed with ``spider_cls`` and return the scraped items
    together with the crawler (for stats assertions)."""
    items = []

    def collect(item):
        items.append(item)

    crawler = get_crawler(spider_cls)
    crawler.signals.connect(collect, signals.item_scraped)
    await crawler.crawl_async(mockserver=mockserver)
    return items, crawler


class TestSpider:
    spider_class = Spider

    def test_base_spider(self):
        spider = self.spider_class("example.com")
        assert spider.name == "example.com"
        assert spider.start_urls == []

    def test_spider_args(self):
        """``__init__`` method arguments are assigned to spider attributes"""
        spider = self.spider_class("example.com", foo="bar")
        assert spider.foo == "bar"

    def test_spider_without_name(self):
        """``__init__`` raises when the name is not provided."""
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
        with (
            mock.patch("scrapy.spiders.Spider.logger") as mock_logger,
            pytest.warns(
                ScrapyDeprecationWarning, match=r"Spider.log\(\) is deprecated"
            ),
        ):
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

    @coroutine_test
    async def test_parse_node_uses_parse_item(self, mockserver: MockServer):
        # parse_node falls back to parse_item for backward compatibility.
        class _Spider(self.spider_class, RawFeedSpider):
            itertag = "item"
            feed_body = "<items><item><id>1</id></item></items>"

            def parse_item(self, response, selector):
                return {"id": selector.xpath("id/text()").get()}

        items, _ = await run_feed_crawl(_Spider, mockserver)
        assert items == [{"id": "1"}]

    @coroutine_test
    async def test_parse_node_not_defined(self, mockserver: MockServer):
        # Without parse_node (nor parse_item) parsing fails with NotImplementedError.
        class _Spider(self.spider_class, RawFeedSpider):
            itertag = "item"
            feed_body = "<items><item><id>1</id></item></items>"

        items, crawler = await run_feed_crawl(_Spider, mockserver)
        assert items == []
        assert crawler.stats.get_value("spider_exceptions/NotImplementedError") == 1

    @coroutine_test
    async def test_html_iterator(self, mockserver: MockServer):
        class _Spider(self.spider_class, RawFeedSpider):
            iterator = "html"
            itertag = "item"
            content_type = "text/html"
            feed_body = (
                "<html><body><item><id>1</id></item>"
                "<item><id>2</id></item></body></html>"
            )

            def parse_node(self, response, selector):
                return {"id": selector.xpath("id/text()").get()}

        items, _ = await run_feed_crawl(_Spider, mockserver)
        assert items == [{"id": "1"}, {"id": "2"}]

    @coroutine_test
    async def test_unsupported_iterator(self, mockserver: MockServer):
        class _Spider(self.spider_class, RawFeedSpider):
            iterator = "unsupported"
            feed_body = "<items><item/></items>"

            def parse_node(self, response, selector):
                return {}

        items, crawler = await run_feed_crawl(_Spider, mockserver)
        assert items == []
        assert crawler.stats.get_value("spider_exceptions/NotSupported") == 1

    @coroutine_test
    async def test_non_text_response(self, mockserver: MockServer):
        # The xml and html iterators require a text response.
        for iterator in ("xml", "html"):

            class _Spider(self.spider_class, RawFeedSpider):
                content_type = "application/octet-stream"
                # A binary (non-text) body so the response is a plain Response.
                feed_body = "\x00\x01\x02\x03"

                def parse_node(self, response, selector):
                    return {}

            _Spider.iterator = iterator
            items, crawler = await run_feed_crawl(_Spider, mockserver)
            assert items == []
            assert crawler.stats.get_value("spider_exceptions/ValueError") == 1


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

    @coroutine_test
    async def test_parse(self, mockserver: MockServer):
        class _Spider(self.spider_class, RawFeedSpider):
            content_type = "text/csv"
            delimiter = ","
            quotechar = "'"
            feed_body = get_testdata("feeds", "feed-sample6.csv").decode()

            def parse_row(self, response, row):
                return row

        items, _ = await run_feed_crawl(_Spider, mockserver)
        assert items[0] == {"id": "1", "name": "alpha", "value": "foobar"}
        assert len(items) == 4

    @coroutine_test
    async def test_parse_row_not_defined(self, mockserver: MockServer):
        # Without parse_row parsing fails with NotImplementedError.
        class _Spider(self.spider_class, RawFeedSpider):
            content_type = "text/csv"
            feed_body = "id\n1\n"

        items, crawler = await run_feed_crawl(_Spider, mockserver)
        assert items == []
        assert crawler.stats.get_value("spider_exceptions/NotImplementedError") == 1


class TestNoParseMethodSpider:
    spider_class = Spider

    def test_undefined_parse_method(self):
        spider = self.spider_class("example.com")
        text = b"Random text"
        resp = TextResponse(url="http://www.example.com/random_url", body=text)

        exc_msg = "Spider.parse callback is not defined"
        with pytest.raises(NotImplementedError, match=exc_msg):
            spider.parse(resp)
