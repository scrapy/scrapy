from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import pytest

from scrapy import signals
from scrapy.http import Request, Response, TextResponse, XmlResponse
from scrapy.spiders import CSVFeedSpider, Spider, XMLFeedSpider
from scrapy.utils.test import get_crawler
from tests import get_testdata
from tests.spiders import MockServerSpider
from tests.utils.bases.spider import TestSpiderBase
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from scrapy.crawler import Crawler
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


async def run_feed_crawl(
    spider_cls: type[Spider], mockserver: MockServer
) -> tuple[list[Any], Crawler]:
    """Crawl a single feed with ``spider_cls`` and return the scraped items
    together with the crawler (for stats assertions)."""
    items = []

    def collect(item):
        items.append(item)

    crawler = get_crawler(spider_cls)
    crawler.signals.connect(collect, signals.item_scraped)
    await crawler.crawl_async(mockserver=mockserver)
    return items, crawler


class TestSpider(TestSpiderBase):
    spider_class = Spider


class TestXMLFeedSpider(TestSpiderBase):
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
        class _Spider(self.spider_class, RawFeedSpider):  # type: ignore[name-defined,misc]
            itertag = "item"
            feed_body = "<items><item><id>1</id></item></items>"

            def parse_item(self, response, selector):
                return {"id": selector.xpath("id/text()").get()}

        items, _ = await run_feed_crawl(_Spider, mockserver)
        assert items == [{"id": "1"}]

    @coroutine_test
    async def test_parse_node_not_defined(self, mockserver: MockServer):
        # Without parse_node (nor parse_item) parsing fails with NotImplementedError.
        class _Spider(self.spider_class, RawFeedSpider):  # type: ignore[name-defined,misc]
            itertag = "item"
            feed_body = "<items><item><id>1</id></item></items>"

        items, crawler = await run_feed_crawl(_Spider, mockserver)
        assert items == []
        assert crawler.stats
        assert crawler.stats.get_value("spider_exceptions/NotImplementedError") == 1

    @coroutine_test
    async def test_html_iterator(self, mockserver: MockServer):
        class _Spider(self.spider_class, RawFeedSpider):  # type: ignore[name-defined,misc]
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
        class _Spider(self.spider_class, RawFeedSpider):  # type: ignore[name-defined,misc]
            iterator = "unsupported"
            feed_body = "<items><item/></items>"

            def parse_node(self, response, selector):
                return {}

        items, crawler = await run_feed_crawl(_Spider, mockserver)
        assert items == []
        assert crawler.stats
        assert crawler.stats.get_value("spider_exceptions/NotSupported") == 1

    @coroutine_test
    async def test_non_text_response(self, mockserver: MockServer):
        # The xml and html iterators require a text response.
        for iterator in ("xml", "html"):

            class _Spider(self.spider_class, RawFeedSpider):  # type: ignore[name-defined,misc]
                content_type = "application/octet-stream"
                # A binary (non-text) body so the response is a plain Response.
                feed_body = "\x00\x01\x02\x03"

                def parse_node(self, response, selector):
                    return {}

            _Spider.iterator = iterator
            items, crawler = await run_feed_crawl(_Spider, mockserver)
            assert items == []
            assert crawler.stats
            assert crawler.stats.get_value("spider_exceptions/ValueError") == 1


class TestCSVFeedSpider(TestSpiderBase):
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
        class _Spider(self.spider_class, RawFeedSpider):  # type: ignore[name-defined,misc]
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
        class _Spider(self.spider_class, RawFeedSpider):  # type: ignore[name-defined,misc]
            content_type = "text/csv"
            feed_body = "id\n1\n"

        items, crawler = await run_feed_crawl(_Spider, mockserver)
        assert items == []
        assert crawler.stats
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
