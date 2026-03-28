from __future__ import annotations

import gzip
import warnings
from datetime import datetime
from io import BytesIO
from logging import WARNING
from pathlib import Path

import pytest
from testfixtures import LogCapture

from scrapy.http import HtmlResponse, Request, Response, TextResponse, XmlResponse
from scrapy.spiders import SitemapSpider
from scrapy.utils.test import get_crawler
from tests import tests_datadir
from tests.test_spider import TestSpider
from tests.utils.decorators import coroutine_test


class TestSitemapSpider(TestSpider):
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
        r = XmlResponse(url="http://www.example.com/", body=self.BODY)
        self.assertSitemapBody(r, self.BODY)

        r = HtmlResponse(url="http://www.example.com/", body=self.BODY)
        self.assertSitemapBody(r, None)

        r = Response(url="http://www.example.com/favicon.ico", body=self.BODY)
        self.assertSitemapBody(r, None)

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

        class FilteredSitemapSpider(self.spider_class):
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

        class FilteredSitemapSpider(self.spider_class):
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

        class FilteredSitemapSpider(self.spider_class):
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
        class DownloadMaxSizeSpider(self.spider_class):
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

    def test_download_warnsize_setting(self):
        settings = {"DOWNLOAD_WARNSIZE": 10_000_000}
        crawler = get_crawler(settings_dict=settings)
        spider = self.spider_class.from_crawler(crawler, "example.com")
        body_path = Path(tests_datadir, "compressed", "bomb-gzip.bin")
        body = body_path.read_bytes()
        request = Request(url="https://example.com")
        response = Response(url="https://example.com", body=body, request=request)
        with LogCapture(
            "scrapy.spiders.sitemap", propagate=False, level=WARNING
        ) as log:
            spider._get_sitemap_body(response)
        log.check(
            (
                "scrapy.spiders.sitemap",
                "WARNING",
                (
                    "<200 https://example.com> body size after decompression "
                    "(11511612 B) is larger than the download warning size "
                    "(10000000 B)."
                ),
            ),
        )

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_download_warnsize_spider_attr(self):
        class DownloadWarnSizeSpider(self.spider_class):
            download_warnsize = 10_000_000

        crawler = get_crawler()
        spider = DownloadWarnSizeSpider.from_crawler(crawler, "example.com")
        body_path = Path(tests_datadir, "compressed", "bomb-gzip.bin")
        body = body_path.read_bytes()
        request = Request(
            url="https://example.com", meta={"download_warnsize": 10_000_000}
        )
        response = Response(url="https://example.com", body=body, request=request)
        with LogCapture(
            "scrapy.spiders.sitemap", propagate=False, level=WARNING
        ) as log:
            spider._get_sitemap_body(response)
        log.check(
            (
                "scrapy.spiders.sitemap",
                "WARNING",
                (
                    "<200 https://example.com> body size after decompression "
                    "(11511612 B) is larger than the download warning size "
                    "(10000000 B)."
                ),
            ),
        )

    def test_download_warnsize_request_meta(self):
        crawler = get_crawler()
        spider = self.spider_class.from_crawler(crawler, "example.com")
        body_path = Path(tests_datadir, "compressed", "bomb-gzip.bin")
        body = body_path.read_bytes()
        request = Request(
            url="https://example.com", meta={"download_warnsize": 10_000_000}
        )
        response = Response(url="https://example.com", body=body, request=request)
        with LogCapture(
            "scrapy.spiders.sitemap", propagate=False, level=WARNING
        ) as log:
            spider._get_sitemap_body(response)
        log.check(
            (
                "scrapy.spiders.sitemap",
                "WARNING",
                (
                    "<200 https://example.com> body size after decompression "
                    "(11511612 B) is larger than the download warning size "
                    "(10000000 B)."
                ),
            ),
        )

    @coroutine_test
    async def test_sitemap_urls(self):
        class TestSpider(self.spider_class):
            name = "test"
            sitemap_urls = ["https://toscrape.com/sitemap.xml"]

        crawler = get_crawler(TestSpider)
        spider = TestSpider.from_crawler(crawler)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            requests = [request async for request in spider.start()]

        assert len(requests) == 1
        request = requests[0]
        assert request.url == "https://toscrape.com/sitemap.xml"
        assert request.dont_filter is False
        assert request.callback == spider._parse_sitemap
