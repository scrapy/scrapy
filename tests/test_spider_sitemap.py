from __future__ import annotations

import gzip
import re
from datetime import datetime
from io import BytesIO
from logging import WARNING
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

import pytest

from scrapy import signals
from scrapy.http import HtmlResponse, Request, Response, TextResponse, XmlResponse
from scrapy.spiders import SitemapSpider
from scrapy.utils.test import get_crawler
from tests import tests_datadir
from tests.spiders import RawResponseSpider
from tests.utils.bases.spider import TestSpiderBase
from tests.utils.crawl import crawl_items
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from tests.mockserver.http import MockServer


class RawSitemapSpider(RawResponseSpider):
    """Feeds :meth:`raw_body` to :class:`~scrapy.spiders.SitemapSpider` as a
    sitemap, so that it is fetched and followed through a regular crawl.

    Subclasses build the document in :meth:`raw_body`, typically using
    :attr:`mockserver` to point ``<loc>`` entries at real endpoints.
    """

    content_type = "application/xml"

    async def start(self):
        self.sitemap_urls = [self.raw_url]
        async for request in super().start():
            yield request


class TestSitemapSpider(TestSpiderBase):
    spider_class = SitemapSpider

    BODY = b"SITEMAP"
    f = BytesIO()
    g = gzip.GzipFile(fileobj=f, mode="w+b")
    g.write(BODY)
    g.close()
    GZBODY = f.getvalue()

    def assertSitemapBody(self, response: Response, body: bytes | None) -> None:
        crawler = get_crawler()
        spider = self.spider_class.from_crawler(crawler, "example.com")
        assert spider._get_sitemap_body(response) == body

    def test_get_sitemap_body(self):
        r: Response = XmlResponse(url="http://www.example.com/", body=self.BODY)
        self.assertSitemapBody(r, self.BODY)

        r = HtmlResponse(url="http://www.example.com/", body=self.BODY)
        self.assertSitemapBody(r, None)

        r = Response(url="http://www.example.com/favicon.ico", body=self.BODY)
        self.assertSitemapBody(r, None)

        r = XmlResponse(url="http://www.example.com/", body=b"")
        self.assertSitemapBody(r, b"")

    def test_get_sitemap_body_gzip_headers(self):
        r = Response(
            url="http://www.example.com/sitemap",
            body=self.GZBODY,
            headers={"content-type": "application/gzip"},
            request=Request("http://www.example.com/sitemap"),
        )
        self.assertSitemapBody(r, self.BODY)

    def test_get_sitemap_body_xml_url(self):
        r = TextResponse(url="http://www.example.com/sitemap.xml", body=self.BODY)
        self.assertSitemapBody(r, self.BODY)

    def test_get_sitemap_body_xml_url_compressed(self):
        r = Response(
            url="http://www.example.com/sitemap.xml.gz",
            body=self.GZBODY,
            request=Request("http://www.example.com/sitemap"),
        )
        self.assertSitemapBody(r, self.BODY)

        # .xml.gz but body decoded by HttpCompression middleware already
        r = Response(url="http://www.example.com/sitemap.xml.gz", body=self.BODY)
        self.assertSitemapBody(r, self.BODY)

    def test_get_sitemap_urls_from_robotstxt(self):
        robots = b"""# Sitemap files
Sitemap: http://example.com/sitemap.xml
Sitemap: http://example.com/sitemap-product-index.xml
Sitemap: HTTP://example.com/sitemap-uppercase.xml
Sitemap: /sitemap-relative-url.xml
"""

        r = TextResponse(url="http://www.example.com/robots.txt", body=robots)
        spider = self.spider_class("example.com")
        assert [req.url for req in spider._parse_sitemap(r)] == [
            "http://example.com/sitemap.xml",
            "http://example.com/sitemap-product-index.xml",
            "http://example.com/sitemap-uppercase.xml",
            "http://www.example.com/sitemap-relative-url.xml",
        ]

    def test_get_sitemap_urls_from_robotstxt_skips_invalid_utf8_urls(self):
        robots = (
            b"User-agent: *\n"
            b"Sitemap: http://example.com/\xff.xml\n"
            b"Sitemap: http://example.com/ok.xml\n"
        )

        r = TextResponse(url="http://www.example.com/robots.txt", body=robots)
        spider = self.spider_class("example.com")

        assert [req.url for req in spider._parse_sitemap(r)] == [
            "http://example.com/ok.xml",
        ]

    def test_get_sitemap_urls_from_robots_parsed_signal(self):
        crawler = get_crawler(self.spider_class, settings_dict={"ROBOTSTXT_OBEY": True})
        spider = self.spider_class.from_crawler(crawler, "example.com")

        class FakeRobotParser:
            def sitemaps(self):
                return [
                    "http://example.com/sitemap.xml",  # already found below
                    "/sitemap-from-parser.xml",  # only reported through the signal
                ]

        crawler.signals.send_catch_log(
            signal=signals.robots_parsed,
            robotparser=FakeRobotParser(),
            request=Request("http://www.example.com/robots.txt"),
        )

        robots = b"Sitemap: http://example.com/sitemap.xml\n"
        r = TextResponse(url="http://www.example.com/robots.txt", body=robots)
        assert [req.url for req in spider._parse_sitemap(r)] == [
            "http://example.com/sitemap.xml",
            "http://www.example.com/sitemap-from-parser.xml",
        ]

    def test_robots_parsed_signal_not_connected_without_robotstxt_obey(self):
        crawler = get_crawler(self.spider_class)
        spider = self.spider_class.from_crawler(crawler, "example.com")

        crawler.signals.send_catch_log(
            signal=signals.robots_parsed,
            robotparser=None,
            request=Request("http://www.example.com/robots.txt"),
        )

        assert spider._robots_sitemaps == {}

    def test_robots_parsed_signal_schedules_sitemaps_for_skipped_netloc(self):
        crawler = get_crawler(self.spider_class, settings_dict={"ROBOTSTXT_OBEY": True})
        spider = self.spider_class.from_crawler(crawler, "example.com")
        crawler.engine = mock.MagicMock()
        spider._signal_only_netlocs.add("www.example.com")

        class FakeRobotParser:
            def sitemaps(self):
                return ["/sitemap.xml"]

        # request is whatever other request to that host triggered the fetch,
        # not necessarily a request for robots.txt itself.
        crawler.signals.send_catch_log(
            signal=signals.robots_parsed,
            robotparser=FakeRobotParser(),
            request=Request("http://www.example.com/some/page"),
        )

        crawler.engine.crawl.assert_called_once()
        scheduled = crawler.engine.crawl.call_args[0][0]
        assert scheduled.url == "http://www.example.com/sitemap.xml"
        assert scheduled.callback == spider._parse_sitemap
        assert spider._signal_only_netlocs == set()
        assert spider._robots_sitemaps == {}

    def test_alternate_url_locs(self):
        sitemap = b"""<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
        <url>
            <loc>http://www.example.com/english/</loc>
            <xhtml:link rel="alternate" hreflang="de"
                href="http://www.example.com/deutsch/"/>
            <xhtml:link rel="alternate" hreflang="de-ch"
                href="http://www.example.com/schweiz-deutsch/"/>
            <xhtml:link rel="alternate" hreflang="it"
                href="http://www.example.com/italiano/"/>
            <xhtml:link rel="alternate" hreflang="it"/><!-- wrong tag without href -->
        </url>
    </urlset>"""
        r = TextResponse(url="http://www.example.com/sitemap.xml", body=sitemap)
        spider = self.spider_class("example.com")
        assert [req.url for req in spider._parse_sitemap(r)] == [
            "http://www.example.com/english/"
        ]

        spider.sitemap_alternate_links = True
        assert [req.url for req in spider._parse_sitemap(r)] == [
            "http://www.example.com/english/",
            "http://www.example.com/deutsch/",
            "http://www.example.com/schweiz-deutsch/",
            "http://www.example.com/italiano/",
        ]

    def test_sitemap_filter(self):
        sitemap = b"""<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
        <url>
            <loc>http://www.example.com/english/</loc>
            <lastmod>2010-01-01</lastmod>
        </url>
        <url>
            <loc>http://www.example.com/portuguese/</loc>
            <lastmod>2005-01-01</lastmod>
        </url>
    </urlset>"""

        class FilteredSitemapSpider(self.spider_class):  # type: ignore[name-defined,misc]
            def sitemap_filter(self, entries):
                for entry in entries:
                    date_time = datetime.strptime(entry["lastmod"], "%Y-%m-%d")
                    if date_time.year > 2008:
                        yield entry

        r = TextResponse(url="http://www.example.com/sitemap.xml", body=sitemap)
        spider = self.spider_class("example.com")
        assert [req.url for req in spider._parse_sitemap(r)] == [
            "http://www.example.com/english/",
            "http://www.example.com/portuguese/",
        ]

        spider = FilteredSitemapSpider("example.com")
        assert [req.url for req in spider._parse_sitemap(r)] == [
            "http://www.example.com/english/"
        ]

    def test_sitemap_filter_with_alternate_links(self):
        sitemap = b"""<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
        <url>
            <loc>http://www.example.com/english/article_1/</loc>
            <lastmod>2010-01-01</lastmod>
            <xhtml:link rel="alternate" hreflang="de"
                href="http://www.example.com/deutsch/article_1/"/>
        </url>
        <url>
            <loc>http://www.example.com/english/article_2/</loc>
            <lastmod>2015-01-01</lastmod>
        </url>
    </urlset>"""

        class FilteredSitemapSpider(self.spider_class):  # type: ignore[name-defined,misc]
            def sitemap_filter(self, entries):
                for entry in entries:
                    alternate_links = entry.get("alternate", ())
                    for link in alternate_links:
                        if "/deutsch/" in link:
                            entry["loc"] = link
                            yield entry

        r = TextResponse(url="http://www.example.com/sitemap.xml", body=sitemap)
        spider = self.spider_class("example.com")
        assert [req.url for req in spider._parse_sitemap(r)] == [
            "http://www.example.com/english/article_1/",
            "http://www.example.com/english/article_2/",
        ]

        spider = FilteredSitemapSpider("example.com")
        assert [req.url for req in spider._parse_sitemap(r)] == [
            "http://www.example.com/deutsch/article_1/"
        ]

    def test_sitemapindex_filter(self):
        sitemap = b"""<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <sitemap>
            <loc>http://www.example.com/sitemap1.xml</loc>
            <lastmod>2004-01-01T20:00:00+00:00</lastmod>
        </sitemap>
        <sitemap>
            <loc>http://www.example.com/sitemap2.xml</loc>
            <lastmod>2005-01-01</lastmod>
        </sitemap>
    </sitemapindex>"""

        class FilteredSitemapSpider(self.spider_class):  # type: ignore[name-defined,misc]
            def sitemap_filter(self, entries):
                for entry in entries:
                    date_time = datetime.strptime(
                        entry["lastmod"].split("T")[0], "%Y-%m-%d"
                    )
                    if date_time.year > 2004:
                        yield entry

        r = TextResponse(url="http://www.example.com/sitemap.xml", body=sitemap)
        spider = self.spider_class("example.com")
        assert [req.url for req in spider._parse_sitemap(r)] == [
            "http://www.example.com/sitemap1.xml",
            "http://www.example.com/sitemap2.xml",
        ]

        spider = FilteredSitemapSpider("example.com")
        assert [req.url for req in spider._parse_sitemap(r)] == [
            "http://www.example.com/sitemap2.xml"
        ]

    @pytest.mark.parametrize(
        ("rule", "result"),
        [(r"english", ["http://www.example.com/english/"]), (r"nonexistent", [])],
    )
    def test_sitemap_filter_with_rule(self, rule: str, result: list[str]):
        sitemap = b"""<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>http://www.example.com/english/</loc></url>
        <url><loc>http://www.example.com/portuguese/</loc></url>
    </urlset>"""
        r = TextResponse(url="http://www.example.com/sitemap.xml", body=sitemap)

        class _RuleSpider(self.spider_class):  # type: ignore[name-defined,misc]
            sitemap_rules = [(rule, "parse")]

        spider = _RuleSpider("example.com")
        urls = [req.url for req in spider._parse_sitemap(r)]
        assert urls == result

    @coroutine_test
    async def test_sitemap_rules_with_callable(self, mockserver: MockServer):
        # A sitemap_rules entry may hold a callable instead of a method name.
        def parse_item(response):
            yield {"url": response.url}

        class _Spider(RawSitemapSpider, self.spider_class):  # type: ignore[name-defined,misc]
            sitemap_rules = [("", parse_item)]

            def raw_body(self):
                assert self.mockserver
                loc = self.mockserver.url("/text")
                return (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    f"<url><loc>{loc}</loc></url>"
                    "</urlset>"
                )

        items, _ = await crawl_items(_Spider, mockserver)
        assert items == [{"url": mockserver.url("/text")}]

    @coroutine_test
    async def test_sitemap_empty_loc(self, mockserver: MockServer):
        class _Spider(RawSitemapSpider, self.spider_class):  # type: ignore[name-defined,misc]
            def parse(self, response):
                yield {"url": response.url}

            def raw_body(self):
                assert self.mockserver
                loc = self.mockserver.url("/text")
                return (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    "<url><loc></loc></url>"
                    f"<url><loc>{loc}</loc></url>"
                    "</urlset>"
                )

        items, _ = await crawl_items(_Spider, mockserver)
        assert items == [{"url": mockserver.url("/text")}]

    @coroutine_test
    async def test_robots_txt_requested_once(self, mockserver: MockServer):
        """robots.txt should be downloaded only once, even though both
        SitemapSpider and RobotsTxtMiddleware need its content: the spider
        requests it directly to look for sitemaps, while the middleware
        downloads it to know what the spider is allowed to crawl.
        """
        robots_url = mockserver.url("/robots.txt")

        class _Spider(self.spider_class):  # type: ignore[name-defined,misc]
            name = "robots_txt_requested_once"
            custom_settings = {"ROBOTSTXT_OBEY": True}
            sitemap_urls = [robots_url]

            @classmethod
            def from_crawler(cls, crawler, *args, **kwargs):
                spider = super().from_crawler(crawler, *args, **kwargs)
                spider.robots_txt_requests = []
                crawler.signals.connect(
                    spider._track_downloader_hit,
                    signals.request_reached_downloader,
                )
                return spider

            def _track_downloader_hit(self, request, spider):
                if request.url == robots_url:
                    self.robots_txt_requests.append(request)

        _, crawler = await crawl_items(_Spider, mockserver)
        assert isinstance(crawler.spider, _Spider)
        assert len(crawler.spider.robots_txt_requests) == 1

    @coroutine_test
    async def test_start_skips_robots_url_covered_by_another_sitemap_url(self):
        crawler = get_crawler(self.spider_class, settings_dict={"ROBOTSTXT_OBEY": True})
        spider = self.spider_class.from_crawler(
            crawler,
            "example.com",
            sitemap_urls=[
                "http://www.example.com/sitemap.xml",
                "http://www.example.com/robots.txt",
                "http://other.example.com/robots.txt",
            ],
        )

        urls = [request.url async for request in spider.start()]

        assert urls == [
            "http://www.example.com/sitemap.xml",
            "http://other.example.com/robots.txt",
        ]
        assert spider._signal_only_netlocs == {"www.example.com"}

    @coroutine_test
    async def test_robots_txt_requested_once_when_other_sitemap_url_goes_first(
        self, mockserver: MockServer
    ):
        """When another sitemap_urls entry targets the same host, the spider
        should not also request robots.txt itself: RobotsTxtMiddleware's own
        robots.txt request, triggered by that other entry, covers it.
        """
        robots_url = mockserver.url("/robots.txt")
        other_url = mockserver.url("/text")

        class _Spider(self.spider_class):  # type: ignore[name-defined,misc]
            name = "robots_txt_requested_once_other_first"
            custom_settings = {"ROBOTSTXT_OBEY": True}
            sitemap_urls = [other_url, robots_url]

            @classmethod
            def from_crawler(cls, crawler, *args, **kwargs):
                spider = super().from_crawler(crawler, *args, **kwargs)
                spider.robots_txt_requests = []
                crawler.signals.connect(
                    spider._track_downloader_hit,
                    signals.request_reached_downloader,
                )
                return spider

            def _track_downloader_hit(self, request, spider):
                if request.url == robots_url:
                    self.robots_txt_requests.append(request)

        _, crawler = await crawl_items(_Spider, mockserver)
        assert isinstance(crawler.spider, _Spider)
        assert len(crawler.spider.robots_txt_requests) == 1

    def test_parse_sitemap_empty_body(self, caplog: pytest.LogCaptureFixture) -> None:
        r = XmlResponse(url="http://www.example.com/sitemap.xml", body=b"")
        spider = self.spider_class("example.com")

        caplog.clear()
        with caplog.at_level(WARNING):
            results = list(spider._parse_sitemap(r))

        assert not results

        assert caplog.record_tuples == [
            (
                "scrapy.spiders.sitemap",
                WARNING,
                "Ignoring invalid sitemap: <200 http://www.example.com/sitemap.xml>",
            )
        ]

    def test_parse_sitemap_not_sitemap(self):
        body = b"""<?xml version="1.0" encoding="UTF-8"?>
    <some attr="string">
        <tag><tag3>sometext</tag3></tag>
        <tag2><tag4>sometext2</tag4></tag2>
    </some>"""
        r = XmlResponse(url="http://www.example.com/random.xml", body=body)
        spider = self.spider_class("example.com")

        results = list(spider._parse_sitemap(r))

        assert not results

    @pytest.mark.parametrize(
        ("follow", "result"),
        [
            (r"1.xml", ["http://www.example.com/sitemap1.xml"]),
            (re.compile(r"sitemap\d"), ["http://www.example.com/sitemap1.xml"]),
            (r"nonexistent", []),
        ],
    )
    def test_sitemap_follow(self, follow, result):
        sitemap = b"""<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <sitemap>
            <loc>http://www.example.com/sitemap1.xml</loc>
        </sitemap>
    </sitemapindex>"""
        r = TextResponse(url="http://www.example.com/sitemap.xml", body=sitemap)

        class _FollowSpider(self.spider_class):  # type: ignore[name-defined,misc]
            sitemap_follow = [follow]

        spider = _FollowSpider("example.com")
        urls = [req.url for req in spider._parse_sitemap(r)]
        assert urls == result

    def test_compression_bomb_setting(self):
        settings = {"DOWNLOAD_MAXSIZE": 10_000_000}
        crawler = get_crawler(settings_dict=settings)
        spider = self.spider_class.from_crawler(crawler, "example.com")
        body_path = Path(tests_datadir, "compressed", "bomb-gzip.bin")
        body = body_path.read_bytes()
        request = Request(url="https://example.com")
        response = Response(url="https://example.com", body=body, request=request)
        assert spider._get_sitemap_body(response) is None

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_compression_bomb_spider_attr(self):
        class DownloadMaxSizeSpider(self.spider_class):  # type: ignore[name-defined,misc]
            download_maxsize = 10_000_000

        crawler = get_crawler()
        spider = DownloadMaxSizeSpider.from_crawler(crawler, "example.com")
        body_path = Path(tests_datadir, "compressed", "bomb-gzip.bin")
        body = body_path.read_bytes()
        request = Request(url="https://example.com")
        response = Response(url="https://example.com", body=body, request=request)
        assert spider._get_sitemap_body(response) is None

    def test_compression_bomb_request_meta(self):
        crawler = get_crawler()
        spider = self.spider_class.from_crawler(crawler, "example.com")
        body_path = Path(tests_datadir, "compressed", "bomb-gzip.bin")
        body = body_path.read_bytes()
        request = Request(
            url="https://example.com", meta={"download_maxsize": 10_000_000}
        )
        response = Response(url="https://example.com", body=body, request=request)
        assert spider._get_sitemap_body(response) is None

    def test_download_warnsize_setting(self, caplog: pytest.LogCaptureFixture) -> None:
        settings = {"DOWNLOAD_WARNSIZE": 10_000_000}
        crawler = get_crawler(settings_dict=settings)
        spider = self.spider_class.from_crawler(crawler, "example.com")
        body_path = Path(tests_datadir, "compressed", "bomb-gzip.bin")
        body = body_path.read_bytes()
        request = Request(url="https://example.com")
        response = Response(url="https://example.com", body=body, request=request)
        caplog.clear()
        with caplog.at_level(WARNING, logger="scrapy.spiders.sitemap"):
            spider._get_sitemap_body(response)
        assert caplog.record_tuples == [
            (
                "scrapy.spiders.sitemap",
                WARNING,
                (
                    "<200 https://example.com> body size after decompression "
                    "(11511612 B) is larger than the download warning size "
                    "(10000000 B)."
                ),
            ),
        ]

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_download_warnsize_spider_attr(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        class DownloadWarnSizeSpider(self.spider_class):  # type: ignore[name-defined,misc]
            download_warnsize = 10_000_000

        crawler = get_crawler()
        spider = DownloadWarnSizeSpider.from_crawler(crawler, "example.com")
        body_path = Path(tests_datadir, "compressed", "bomb-gzip.bin")
        body = body_path.read_bytes()
        request = Request(
            url="https://example.com", meta={"download_warnsize": 10_000_000}
        )
        response = Response(url="https://example.com", body=body, request=request)
        caplog.clear()
        with caplog.at_level(WARNING, logger="scrapy.spiders.sitemap"):
            spider._get_sitemap_body(response)
        assert caplog.record_tuples == [
            (
                "scrapy.spiders.sitemap",
                WARNING,
                (
                    "<200 https://example.com> body size after decompression "
                    "(11511612 B) is larger than the download warning size "
                    "(10000000 B)."
                ),
            ),
        ]

    def test_download_warnsize_request_meta(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        crawler = get_crawler()
        spider = self.spider_class.from_crawler(crawler, "example.com")
        body_path = Path(tests_datadir, "compressed", "bomb-gzip.bin")
        body = body_path.read_bytes()
        request = Request(
            url="https://example.com", meta={"download_warnsize": 10_000_000}
        )
        response = Response(url="https://example.com", body=body, request=request)
        caplog.clear()
        with caplog.at_level(WARNING, logger="scrapy.spiders.sitemap"):
            spider._get_sitemap_body(response)
        assert caplog.record_tuples == [
            (
                "scrapy.spiders.sitemap",
                WARNING,
                (
                    "<200 https://example.com> body size after decompression "
                    "(11511612 B) is larger than the download warning size "
                    "(10000000 B)."
                ),
            ),
        ]

    @coroutine_test
    async def test_sitemap_urls(self):
        class TestSpider(self.spider_class):  # type: ignore[name-defined,misc]
            name = "test"
            sitemap_urls = ["https://toscrape.com/sitemap.xml"]

        crawler = get_crawler(TestSpider)
        spider = TestSpider.from_crawler(crawler)
        requests = [request async for request in spider.start()]

        assert len(requests) == 1
        request = requests[0]
        assert request.url == "https://toscrape.com/sitemap.xml"
        assert request.dont_filter is False
        assert request.callback == spider._parse_sitemap
