from __future__ import annotations

import re
import warnings

import pytest
from w3lib.url import safe_url_string

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import HtmlResponse, Request, TextResponse
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule, Spider
from scrapy.utils.test import get_crawler
from tests.test_spider import TestSpider


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

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
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

    def test_parse_response_use(self):
        class _CrawlSpider(CrawlSpider):
            name = "test"
            start_urls = "https://www.example.com"
            _follow_links = False

        with warnings.catch_warnings():
            warnings.simplefilter("error", category=ScrapyDeprecationWarning)
            spider = _CrawlSpider()
        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"CrawlSpider\._parse_response method is deprecated",
        ):
            spider._parse_response(
                TextResponse(spider.start_urls, body=b""), None, None
            )

    def test_parse_response_override(self):
        class _CrawlSpider(CrawlSpider):
            def _parse_response(self, response, callback, cb_kwargs, follow=True):
                pass

            name = "test"
            start_urls = "https://www.example.com"
            _follow_links = False

        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"CrawlSpider\._parse_response method, which the",
        ):
            spider = _CrawlSpider()
        with warnings.catch_warnings():
            warnings.simplefilter("error", category=ScrapyDeprecationWarning)
            spider._parse_response(
                TextResponse(spider.start_urls, body=b""), None, None
            )

    def test_parse_with_rules(self):
        class _CrawlSpider(CrawlSpider):
            name = "test"
            start_urls = "https://www.example.com"

        with warnings.catch_warnings():
            warnings.simplefilter("error", category=ScrapyDeprecationWarning)
            spider = _CrawlSpider()
            spider.parse_with_rules(
                TextResponse(spider.start_urls, body=b""), None, None
            )


class TestDeprecation:
    def test_crawl_spider(self):
        assert issubclass(CrawlSpider, Spider)
        assert isinstance(CrawlSpider(name="foo"), Spider)
