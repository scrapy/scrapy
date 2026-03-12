from __future__ import annotations

import re
import warnings
from logging import ERROR
from typing import Any
from unittest import mock

import pytest
from testfixtures import LogCapture
from w3lib.url import safe_url_string

from scrapy import signals
from scrapy.crawler import Crawler
from scrapy.http import HtmlResponse, Request, Response, TextResponse, XmlResponse
from scrapy.linkextractors import LinkExtractor
from scrapy.settings import Settings
from scrapy.spiders import CrawlSpider, CSVFeedSpider, Rule, Spider, XMLFeedSpider
from scrapy.spiders.init import InitSpider
from scrapy.utils.test import get_crawler, get_reactor_settings
from tests import get_testdata
from tests.utils.decorators import coroutine_test, inline_callbacks_test


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


@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
class TestInitSpider(TestSpider):
    spider_class = InitSpider

    @coroutine_test
    async def test_start_urls(self):
        responses = []

        class TestSpider(self.spider_class):
            name = "test"
            start_urls = ["data:,"]

            async def parse(self, response):
                responses.append(response)

        crawler = get_crawler(TestSpider)
        await crawler.crawl_async()
        assert len(responses) == 1
        assert responses[0].url == "data:,"


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


class TestCrawlSpider(TestSpider):
    test_body = b"""<html><head><title>Page title</title></head>
    <body>
    <p><a href="item/12.html">Item 12</a></p>
    <div class='links'>
    <p><a href="/about.html">About us</a></p>
    </div>
    <div>
    <p><a href="/nofollow.html">This shouldn't be followed</a></p>
    </div>
    </body></html>"""
    spider_class = CrawlSpider

    def test_rule_without_link_extractor(self):
        response = HtmlResponse(
            "http://example.org/somepage/index.html", body=self.test_body
        )

        class _CrawlSpider(self.spider_class):
            name = "test"
            allowed_domains = ["example.org"]
            rules = (Rule(),)

        spider = _CrawlSpider()
        output = list(spider._requests_to_follow(response))
        assert len(output) == 3
        assert all(isinstance(r, Request) for r in output)
        assert [r.url for r in output] == [
            "http://example.org/somepage/item/12.html",
            "http://example.org/about.html",
            "http://example.org/nofollow.html",
        ]

    def test_process_links(self):
        response = HtmlResponse(
            "http://example.org/somepage/index.html", body=self.test_body
        )

        class _CrawlSpider(self.spider_class):
            name = "test"
            allowed_domains = ["example.org"]
            rules = (Rule(LinkExtractor(), process_links="dummy_process_links"),)

            def dummy_process_links(self, links):
                return links

        spider = _CrawlSpider()
        output = list(spider._requests_to_follow(response))
        assert len(output) == 3
        assert all(isinstance(r, Request) for r in output)
        assert [r.url for r in output] == [
            "http://example.org/somepage/item/12.html",
            "http://example.org/about.html",
            "http://example.org/nofollow.html",
        ]

    def test_process_links_filter(self):
        response = HtmlResponse(
            "http://example.org/somepage/index.html", body=self.test_body
        )

        class _CrawlSpider(self.spider_class):
            name = "test"
            allowed_domains = ["example.org"]
            rules = (Rule(LinkExtractor(), process_links="filter_process_links"),)
            _test_regex = re.compile("nofollow")

            def filter_process_links(self, links):
                return [link for link in links if not self._test_regex.search(link.url)]

        spider = _CrawlSpider()
        output = list(spider._requests_to_follow(response))
        assert len(output) == 2
        assert all(isinstance(r, Request) for r in output)
        assert [r.url for r in output] == [
            "http://example.org/somepage/item/12.html",
            "http://example.org/about.html",
        ]

    def test_process_links_generator(self):
        response = HtmlResponse(
            "http://example.org/somepage/index.html", body=self.test_body
        )

        class _CrawlSpider(self.spider_class):
            name = "test"
            allowed_domains = ["example.org"]
            rules = (Rule(LinkExtractor(), process_links="dummy_process_links"),)

            def dummy_process_links(self, links):
                yield from links

        spider = _CrawlSpider()
        output = list(spider._requests_to_follow(response))
        assert len(output) == 3
        assert all(isinstance(r, Request) for r in output)
        assert [r.url for r in output] == [
            "http://example.org/somepage/item/12.html",
            "http://example.org/about.html",
            "http://example.org/nofollow.html",
        ]

    def test_process_request(self):
        response = HtmlResponse(
            "http://example.org/somepage/index.html", body=self.test_body
        )

        def process_request_change_domain(request, response):
            return request.replace(url=request.url.replace(".org", ".com"))

        class _CrawlSpider(self.spider_class):
            name = "test"
            allowed_domains = ["example.org"]
            rules = (
                Rule(LinkExtractor(), process_request=process_request_change_domain),
            )

        spider = _CrawlSpider()
        output = list(spider._requests_to_follow(response))
        assert len(output) == 3
        assert all(isinstance(r, Request) for r in output)
        assert [r.url for r in output] == [
            "http://example.com/somepage/item/12.html",
            "http://example.com/about.html",
            "http://example.com/nofollow.html",
        ]

    def test_process_request_with_response(self):
        response = HtmlResponse(
            "http://example.org/somepage/index.html", body=self.test_body
        )

        def process_request_meta_response_class(request, response):
            request.meta["response_class"] = response.__class__.__name__
            return request

        class _CrawlSpider(self.spider_class):
            name = "test"
            allowed_domains = ["example.org"]
            rules = (
                Rule(
                    LinkExtractor(), process_request=process_request_meta_response_class
                ),
            )

        spider = _CrawlSpider()
        output = list(spider._requests_to_follow(response))
        assert len(output) == 3
        assert all(isinstance(r, Request) for r in output)
        assert [r.url for r in output] == [
            "http://example.org/somepage/item/12.html",
            "http://example.org/about.html",
            "http://example.org/nofollow.html",
        ]
        assert [r.meta["response_class"] for r in output] == [
            "HtmlResponse",
            "HtmlResponse",
            "HtmlResponse",
        ]

    def test_process_request_instance_method(self):
        response = HtmlResponse(
            "http://example.org/somepage/index.html", body=self.test_body
        )

        class _CrawlSpider(self.spider_class):
            name = "test"
            allowed_domains = ["example.org"]
            rules = (Rule(LinkExtractor(), process_request="process_request_upper"),)

            def process_request_upper(self, request, response):
                return request.replace(url=request.url.upper())

        spider = _CrawlSpider()
        output = list(spider._requests_to_follow(response))
        assert len(output) == 3
        assert all(isinstance(r, Request) for r in output)
        assert [r.url for r in output] == [
            safe_url_string("http://EXAMPLE.ORG/SOMEPAGE/ITEM/12.HTML"),
            safe_url_string("http://EXAMPLE.ORG/ABOUT.HTML"),
            safe_url_string("http://EXAMPLE.ORG/NOFOLLOW.HTML"),
        ]

    def test_process_request_instance_method_with_response(self):
        response = HtmlResponse(
            "http://example.org/somepage/index.html", body=self.test_body
        )

        class _CrawlSpider(self.spider_class):
            name = "test"
            allowed_domains = ["example.org"]
            rules = (
                Rule(
                    LinkExtractor(),
                    process_request="process_request_meta_response_class",
                ),
            )

            def process_request_meta_response_class(self, request, response):
                request.meta["response_class"] = response.__class__.__name__
                return request

        spider = _CrawlSpider()
        output = list(spider._requests_to_follow(response))
        assert len(output) == 3
        assert all(isinstance(r, Request) for r in output)
        assert [r.url for r in output] == [
            "http://example.org/somepage/item/12.html",
            "http://example.org/about.html",
            "http://example.org/nofollow.html",
        ]
        assert [r.meta["response_class"] for r in output] == [
            "HtmlResponse",
            "HtmlResponse",
            "HtmlResponse",
        ]

    def test_follow_links_attribute_population(self):
        crawler = get_crawler()
        spider = self.spider_class.from_crawler(crawler, "example.com")
        assert hasattr(spider, "_follow_links")
        assert spider._follow_links

        settings_dict = {"CRAWLSPIDER_FOLLOW_LINKS": False}
        crawler = get_crawler(settings_dict=settings_dict)
        spider = self.spider_class.from_crawler(crawler, "example.com")
        assert hasattr(spider, "_follow_links")
        assert not spider._follow_links

    @inline_callbacks_test
    def test_start_url(self):
        class TestSpider(self.spider_class):
            name = "test"
            start_url = "https://www.example.com"

        crawler = get_crawler(TestSpider)
        with LogCapture("scrapy.core.engine", propagate=False, level=ERROR) as log:
            yield crawler.crawl()
        assert "Error while reading start items and requests" in str(log)
        assert "did you miss an 's'?" in str(log)

    def test_parse_response_use(self):
        class _CrawlSpider(CrawlSpider):
            name = "test"
            start_urls = "https://www.example.com"
            _follow_links = False

        with warnings.catch_warnings(record=True) as w:
            spider = _CrawlSpider()
            assert len(w) == 0
            spider._parse_response(
                TextResponse(spider.start_urls, body=b""), None, None
            )
            assert len(w) == 1

    def test_parse_response_override(self):
        class _CrawlSpider(CrawlSpider):
            def _parse_response(self, response, callback, cb_kwargs, follow=True):
                pass

            name = "test"
            start_urls = "https://www.example.com"
            _follow_links = False

        with warnings.catch_warnings(record=True) as w:
            assert len(w) == 0
            spider = _CrawlSpider()
            assert len(w) == 1
            spider._parse_response(
                TextResponse(spider.start_urls, body=b""), None, None
            )
            assert len(w) == 1

    def test_parse_with_rules(self):
        class _CrawlSpider(CrawlSpider):
            name = "test"
            start_urls = "https://www.example.com"

        with warnings.catch_warnings(record=True) as w:
            spider = _CrawlSpider()
            spider.parse_with_rules(
                TextResponse(spider.start_urls, body=b""), None, None
            )
            assert len(w) == 0


class TestDeprecation:
    def test_crawl_spider(self):
        assert issubclass(CrawlSpider, Spider)
        assert isinstance(CrawlSpider(name="foo"), Spider)


class TestNoParseMethodSpider:
    spider_class = Spider

    def test_undefined_parse_method(self):
        spider = self.spider_class("example.com")
        text = b"Random text"
        resp = TextResponse(url="http://www.example.com/random_url", body=text)

        exc_msg = "Spider.parse callback is not defined"
        with pytest.raises(NotImplementedError, match=exc_msg):
            spider.parse(resp)
