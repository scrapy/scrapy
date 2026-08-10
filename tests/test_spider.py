from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scrapy.http import Request, Response, TextResponse, XmlResponse
from scrapy.spiders import CSVFeedSpider, Spider, XMLFeedSpider
from tests import get_testdata
from tests.spiders import RawResponseSpider
from tests.utils.bases.spider import TestSpiderBase
from tests.utils.crawl import crawl_items
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from tests.mockserver.http import MockServer


class RawFeedSpider(RawResponseSpider):
    content_type = "text/xml"

    async def start(self):
        yield Request(self.raw_url)


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

        class _XMLSpider(self.spider_class):  # type: ignore[name-defined,misc]
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
        class _Spider(RawFeedSpider, self.spider_class):  # type: ignore[name-defined,misc]
            itertag = "item"

            def raw_body(self):
                return "<items><item><id>1</id></item></items>"

            def parse_item(self, response, selector):
                return {"id": selector.xpath("id/text()").get()}

        items, _ = await crawl_items(_Spider, mockserver)
        assert items == [{"id": "1"}]

    @coroutine_test
    async def test_parse_node_not_defined(self, mockserver: MockServer):
        class _Spider(RawFeedSpider, self.spider_class):  # type: ignore[name-defined,misc]
            itertag = "item"

            def raw_body(self):
                return "<items><item><id>1</id></item></items>"

        items, crawler = await crawl_items(_Spider, mockserver)
        assert items == []
        assert crawler.stats
        assert crawler.stats.get_value("spider_exceptions/NotImplementedError") == 1

    @coroutine_test
    async def test_html_iterator(self, mockserver: MockServer):
        class _Spider(RawFeedSpider, self.spider_class):  # type: ignore[name-defined,misc]
            iterator = "html"
            itertag = "item"
            content_type = "text/html"

            def raw_body(self):
                return (
                    "<html><body><item><id>1</id></item>"
                    "<item><id>2</id></item></body></html>"
                )

            def parse_node(self, response, selector):
                return {"id": selector.xpath("id/text()").get()}

        items, _ = await crawl_items(_Spider, mockserver)
        assert items == [{"id": "1"}, {"id": "2"}]

    @coroutine_test
    async def test_unsupported_iterator(self, mockserver: MockServer):
        class _Spider(RawFeedSpider, self.spider_class):  # type: ignore[name-defined,misc]
            iterator = "unsupported"

            def raw_body(self):
                return "<items><item/></items>"

            def parse_node(self, response, selector):
                return {}

        items, crawler = await crawl_items(_Spider, mockserver)
        assert items == []
        assert crawler.stats
        assert crawler.stats.get_value("spider_exceptions/NotSupported") == 1

    @pytest.mark.parametrize("feed_iterator", ["xml", "html"])
    @coroutine_test
    async def test_non_text_response(self, feed_iterator: str, mockserver: MockServer):
        # The xml and html iterators require a text response.
        class _Spider(RawFeedSpider, self.spider_class):  # type: ignore[name-defined,misc]
            content_type = "application/octet-stream"
            iterator = feed_iterator

            def raw_body(self):
                # A binary (non-text) body, so the response is a plain Response.
                return "\x00\x01\x02\x03"

            def parse_node(self, response, selector):
                return {}

        items, crawler = await crawl_items(_Spider, mockserver)
        assert items == []
        assert crawler.stats
        assert crawler.stats.get_value("spider_exceptions/ValueError") == 1


class TestCSVFeedSpider(TestSpiderBase):
    spider_class = CSVFeedSpider

    def test_parse_rows(self):
        body = get_testdata("feeds", "feed-sample6.csv")
        response = Response("http://example.org/dummy.csv", body=body)

        class _CrawlSpider(self.spider_class):  # type: ignore[name-defined,misc]
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
        class _Spider(RawFeedSpider, self.spider_class):  # type: ignore[name-defined,misc]
            content_type = "text/csv"
            delimiter = ","
            quotechar = "'"

            def raw_body(self):
                return get_testdata("feeds", "feed-sample6.csv").decode()

            def parse_row(self, response, row):
                return row

        items, _ = await crawl_items(_Spider, mockserver)
        assert items[0] == {"id": "1", "name": "alpha", "value": "foobar"}
        assert len(items) == 4

    @coroutine_test
    async def test_parse_row_not_defined(self, mockserver: MockServer):
        class _Spider(RawFeedSpider, self.spider_class):  # type: ignore[name-defined,misc]
            content_type = "text/csv"

            def raw_body(self):
                return "id\n1\n"

        items, crawler = await crawl_items(_Spider, mockserver)
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
