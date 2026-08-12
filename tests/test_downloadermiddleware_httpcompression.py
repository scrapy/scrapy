from gzip import GzipFile
from importlib.util import find_spec
from io import BytesIO
from logging import WARNING
from pathlib import Path
from typing import Any

import pytest
from w3lib.encoding import resolve_encoding

from scrapy.downloadermiddlewares.httpcompression import (
    ACCEPTED_ENCODINGS,
    HttpCompressionMiddleware,
)
from scrapy.exceptions import IgnoreRequest, NotConfigured, ScrapyDeprecationWarning
from scrapy.http import HtmlResponse, Request, Response
from scrapy.responsetypes import responsetypes
from scrapy.spiders import Spider
from scrapy.utils._compression import _DecompressionMaxSizeExceeded
from scrapy.utils.gz import gunzip
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
from tests import tests_datadir

SAMPLEDIR = Path(tests_datadir, "compressed")

FORMAT = {
    "gzip": ("html-gzip.bin", "gzip"),
    "x-gzip": ("html-gzip.bin", "x-gzip"),
    "rawdeflate": ("html-rawdeflate.bin", "deflate"),
    "zlibdeflate": ("html-zlibdeflate.bin", "deflate"),
    "gzip-deflate": ("html-gzip-deflate.bin", "gzip, deflate"),
    "gzip-deflate-gzip": ("html-gzip-deflate-gzip.bin", "gzip, deflate, gzip"),
    "br": ("html-br.bin", "br"),
    # $ zstd raw.html --content-size -o html-zstd-static-content-size.bin
    "zstd-static-content-size": ("html-zstd-static-content-size.bin", "zstd"),
    # $ zstd raw.html --no-content-size -o html-zstd-static-no-content-size.bin
    "zstd-static-no-content-size": ("html-zstd-static-no-content-size.bin", "zstd"),
    # $ cat raw.html | zstd -o html-zstd-streaming-no-content-size.bin
    "zstd-streaming-no-content-size": (
        "html-zstd-streaming-no-content-size.bin",
        "zstd",
    ),
    **{
        f"bomb-{format_id}": (f"bomb-{format_id}.bin", format_id)
        for format_id in (
            "br",  # 34 → 11 511 612
            "deflate",  # 27 968 → 11 511 612
            "gzip",  # 27 988 → 11 511 612
            "zstd",  # 1 096 → 11 511 612
        )
    },
}


def _skip_if_no_zstd() -> None:
    pytest.importorskip("zstandard")


class TestHttpCompression:
    def setup_method(self):
        self.crawler = get_crawler(Spider)
        self.mw = build_from_crawler(HttpCompressionMiddleware, self.crawler)
        assert self.crawler.stats
        self.crawler.stats.open_spider()

    def _getresponse(self, coding: str) -> Response:
        if coding not in FORMAT:
            raise ValueError

        samplefile, contentencoding = FORMAT[coding]

        body = (SAMPLEDIR / samplefile).read_bytes()

        headers = {
            "Server": "Yaws/1.49 Yet Another Web Server",
            "Date": "Sun, 08 Mar 2009 00:41:03 GMT",
            "Content-Length": len(body),
            "Content-Type": "text/html",
            "Content-Encoding": contentencoding,
        }

        response = Response("http://scrapytest.org/", body=body, headers=headers)
        response.request = Request(
            "http://scrapytest.org", headers={"Accept-Encoding": "gzip, deflate"}
        )
        return response

    def assertStatsEqual(self, key: str, value: Any) -> None:
        assert self.crawler.stats
        assert self.crawler.stats.get_value(key) == value, str(
            self.crawler.stats.get_stats()
        )

    def test_setting_false_compression_enabled(self):
        with pytest.raises(NotConfigured):
            build_from_crawler(
                HttpCompressionMiddleware,
                get_crawler(settings_dict={"COMPRESSION_ENABLED": False}),
            )

    def test_setting_default_compression_enabled(self):
        assert isinstance(
            build_from_crawler(HttpCompressionMiddleware, get_crawler()),
            HttpCompressionMiddleware,
        )

    def test_setting_true_compression_enabled(self):
        assert isinstance(
            build_from_crawler(
                HttpCompressionMiddleware,
                get_crawler(settings_dict={"COMPRESSION_ENABLED": True}),
            ),
            HttpCompressionMiddleware,
        )

    def test_no_crawler_constructor(self):
        with pytest.warns(ScrapyDeprecationWarning, match="HttpCompressionMiddleware"):
            mw = HttpCompressionMiddleware()
        buf = BytesIO()
        with GzipFile(fileobj=buf, mode="wb") as f:
            f.write(b"hello")
        body = buf.getvalue()
        request = Request("http://scrapytest.org")
        response = Response(
            "http://scrapytest.org",
            body=body,
            headers={"Content-Encoding": "gzip"},
        )
        newresponse = mw.process_response(request, response)
        assert newresponse.body == b"hello"

    def test_process_request(self):
        request = Request("http://scrapytest.org")
        assert "Accept-Encoding" not in request.headers
        self.mw.process_request(request)
        assert request.headers.get("Accept-Encoding") == b", ".join(ACCEPTED_ENCODINGS)

    def test_process_request_body_file(self):
        request = Request("https://example.com", meta={"body_file": "body"})
        self.mw.process_request(request)
        assert "Accept-Encoding" not in request.headers

    def test_process_response_gzip(self):
        response = self._getresponse("gzip")
        assert response.request
        request = response.request

        assert response.headers["Content-Encoding"] == b"gzip"
        newresponse = self.mw.process_response(request, response)
        assert newresponse is not response
        assert newresponse.body.startswith(b"<!DOCTYPE")
        assert "Content-Encoding" not in newresponse.headers
        self.assertStatsEqual("httpcompression/response_count", 1)
        self.assertStatsEqual("httpcompression/response_bytes", 74837)

    def test_process_response_br(self):
        response = self._getresponse("br")
        assert response.request
        request = response.request
        assert response.headers["Content-Encoding"] == b"br"
        newresponse = self.mw.process_response(request, response)
        assert newresponse is not response
        assert newresponse.body.startswith(b"<!DOCTYPE")
        assert "Content-Encoding" not in newresponse.headers
        self.assertStatsEqual("httpcompression/response_count", 1)
        self.assertStatsEqual("httpcompression/response_bytes", 74837)

    def test_process_response_zstd(self):
        _skip_if_no_zstd()

        raw_content = None
        for check_key in FORMAT:
            if not check_key.startswith("zstd-"):
                continue
            response = self._getresponse(check_key)
            assert response.request
            request = response.request
            assert response.headers["Content-Encoding"] == b"zstd"
            newresponse = self.mw.process_response(request, response)
            if raw_content is None:
                raw_content = newresponse.body
            else:
                assert raw_content == newresponse.body
            assert newresponse is not response
            assert newresponse.body.startswith(b"<!DOCTYPE")
            assert "Content-Encoding" not in newresponse.headers

    def test_process_response_zstd_unsupported(self, caplog: pytest.LogCaptureFixture):
        if find_spec("zstandard") is not None:
            pytest.skip("Requires not having zstandard support")
        response = self._getresponse("zstd-static-content-size")
        assert response.request
        request = response.request
        assert response.headers["Content-Encoding"] == b"zstd"
        caplog.clear()
        with caplog.at_level(
            WARNING, logger="scrapy.downloadermiddlewares.httpcompression"
        ):
            newresponse = self.mw.process_response(request, response)
        assert caplog.record_tuples == [
            (
                "scrapy.downloadermiddlewares.httpcompression",
                WARNING,
                (
                    "HttpCompressionMiddleware cannot decode the response for"
                    " http://scrapytest.org/ from unsupported encoding(s) 'zstd'."
                    " You need to install zstandard to decode 'zstd'."
                ),
            ),
        ]
        assert newresponse is not response
        assert newresponse.headers.getlist("Content-Encoding") == [b"zstd"]

    def test_process_response_rawdeflate(self):
        response = self._getresponse("rawdeflate")
        assert response.request
        request = response.request

        assert response.headers["Content-Encoding"] == b"deflate"
        newresponse = self.mw.process_response(request, response)
        assert newresponse is not response
        assert newresponse.body.startswith(b"<!DOCTYPE")
        assert "Content-Encoding" not in newresponse.headers
        self.assertStatsEqual("httpcompression/response_count", 1)
        self.assertStatsEqual("httpcompression/response_bytes", 74840)

    def test_process_response_zlibdelate(self):
        response = self._getresponse("zlibdeflate")
        assert response.request
        request = response.request

        assert response.headers["Content-Encoding"] == b"deflate"
        newresponse = self.mw.process_response(request, response)
        assert newresponse is not response
        assert newresponse.body.startswith(b"<!DOCTYPE")
        assert "Content-Encoding" not in newresponse.headers
        self.assertStatsEqual("httpcompression/response_count", 1)
        self.assertStatsEqual("httpcompression/response_bytes", 74840)

    def test_process_response_plain(self):
        response = Response("http://scrapytest.org", body=b"<!DOCTYPE...")
        request = Request("http://scrapytest.org")

        assert not response.headers.get("Content-Encoding")
        newresponse = self.mw.process_response(request, response)
        assert newresponse is response
        assert newresponse.body.startswith(b"<!DOCTYPE")
        self.assertStatsEqual("httpcompression/response_count", None)
        self.assertStatsEqual("httpcompression/response_bytes", None)

    def test_multipleencodings(self):
        response = self._getresponse("gzip")
        response.headers["Content-Encoding"] = ["uuencode", "gzip"]
        assert response.request
        request = response.request
        newresponse = self.mw.process_response(request, response)
        assert newresponse is not response
        assert newresponse.headers.getlist("Content-Encoding") == [b"uuencode"]

    def test_multi_compression_single_header(self):
        response = self._getresponse("gzip-deflate")
        assert response.request
        request = response.request
        newresponse = self.mw.process_response(request, response)
        assert newresponse is not response
        assert "Content-Encoding" not in newresponse.headers
        assert newresponse.body.startswith(b"<!DOCTYPE")

    def test_multi_compression_single_header_invalid_compression(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        response = self._getresponse("gzip-deflate")
        response.headers["Content-Encoding"] = [b"gzip, foo, deflate"]
        assert response.request
        request = response.request
        caplog.clear()
        with caplog.at_level(
            WARNING, logger="scrapy.downloadermiddlewares.httpcompression"
        ):
            newresponse = self.mw.process_response(request, response)
        assert caplog.record_tuples == [
            (
                "scrapy.downloadermiddlewares.httpcompression",
                WARNING,
                (
                    "HttpCompressionMiddleware cannot decode the response for"
                    " http://scrapytest.org/ from unsupported encoding(s) 'gzip,foo'."
                ),
            ),
        ]
        assert newresponse is not response
        assert newresponse.headers.getlist("Content-Encoding") == [b"gzip", b"foo"]

    def test_multi_compression_multiple_header(self):
        response = self._getresponse("gzip-deflate")
        response.headers["Content-Encoding"] = ["gzip", "deflate"]
        assert response.request
        request = response.request
        newresponse = self.mw.process_response(request, response)
        assert newresponse is not response
        assert "Content-Encoding" not in newresponse.headers
        assert newresponse.body.startswith(b"<!DOCTYPE")

    def test_multi_compression_multiple_header_invalid_compression(self):
        response = self._getresponse("gzip-deflate")
        response.headers["Content-Encoding"] = ["gzip", "foo", "deflate"]
        assert response.request
        request = response.request
        newresponse = self.mw.process_response(request, response)
        assert newresponse is not response
        assert newresponse.headers.getlist("Content-Encoding") == [b"gzip", b"foo"]

    def test_multi_compression_single_and_multiple_header(self):
        response = self._getresponse("gzip-deflate-gzip")
        response.headers["Content-Encoding"] = ["gzip", "deflate, gzip"]
        assert response.request
        request = response.request
        newresponse = self.mw.process_response(request, response)
        assert newresponse is not response
        assert "Content-Encoding" not in newresponse.headers
        assert newresponse.body.startswith(b"<!DOCTYPE")

    def test_multi_compression_single_and_multiple_header_invalid_compression(self):
        response = self._getresponse("gzip-deflate")
        response.headers["Content-Encoding"] = ["gzip", "foo,deflate"]
        assert response.request
        request = response.request
        newresponse = self.mw.process_response(request, response)
        assert newresponse is not response
        assert newresponse.headers.getlist("Content-Encoding") == [b"gzip", b"foo"]

    def test_process_response_encoding_inside_body(self):
        headers = {
            "Content-Type": "text/html",
            "Content-Encoding": "gzip",
        }
        f = BytesIO()
        plainbody = (
            b"<html><head><title>Some page</title>"
            b'<meta http-equiv="Content-Type" content="text/html; charset=gb2312">'
        )
        zf = GzipFile(fileobj=f, mode="wb")
        zf.write(plainbody)
        zf.close()
        response = Response(
            "http://www.example.com/", headers=headers, body=f.getvalue()
        )
        request = Request("http://www.example.com/")

        newresponse = self.mw.process_response(request, response)
        assert isinstance(newresponse, HtmlResponse)
        assert newresponse.body == plainbody
        assert newresponse.encoding == resolve_encoding("gb2312")
        self.assertStatsEqual("httpcompression/response_count", 1)
        self.assertStatsEqual("httpcompression/response_bytes", len(plainbody))

    def test_process_response_force_recalculate_encoding(self):
        headers = {
            "Content-Type": "text/html",
            "Content-Encoding": "gzip",
        }
        f = BytesIO()
        plainbody = (
            b"<html><head><title>Some page</title>"
            b'<meta http-equiv="Content-Type" content="text/html; charset=gb2312">'
        )
        zf = GzipFile(fileobj=f, mode="wb")
        zf.write(plainbody)
        zf.close()
        response = HtmlResponse(
            "http://www.example.com/page.html", headers=headers, body=f.getvalue()
        )
        request = Request("http://www.example.com/")

        newresponse = self.mw.process_response(request, response)
        assert isinstance(newresponse, HtmlResponse)
        assert newresponse.body == plainbody
        assert newresponse.encoding == resolve_encoding("gb2312")
        self.assertStatsEqual("httpcompression/response_count", 1)
        self.assertStatsEqual("httpcompression/response_bytes", len(plainbody))

    def test_process_response_no_content_type_header(self):
        headers = {b"Content-Encoding": b"identity"}
        plainbody = (
            b"<html><head><title>Some page</title>"
            b'<meta http-equiv="Content-Type" content="text/html; charset=gb2312">'
        )
        respcls = responsetypes.from_args(
            url="http://www.example.com/index", headers=headers, body=plainbody
        )
        response = respcls(
            "http://www.example.com/index", headers=headers, body=plainbody
        )
        request = Request("http://www.example.com/index")

        newresponse = self.mw.process_response(request, response)
        assert isinstance(newresponse, respcls)
        assert isinstance(newresponse, HtmlResponse)
        assert newresponse.body == plainbody
        assert newresponse.encoding == resolve_encoding("gb2312")
        self.assertStatsEqual("httpcompression/response_count", 1)
        self.assertStatsEqual("httpcompression/response_bytes", len(plainbody))

    def test_process_response_gzipped_contenttype(self):
        response = self._getresponse("gzip")
        response.headers["Content-Type"] = "application/gzip"
        assert response.request
        request = response.request

        newresponse = self.mw.process_response(request, response)
        assert newresponse is not response
        assert newresponse.body.startswith(b"<!DOCTYPE")
        assert "Content-Encoding" not in newresponse.headers
        self.assertStatsEqual("httpcompression/response_count", 1)
        self.assertStatsEqual("httpcompression/response_bytes", 74837)

    def test_process_response_gzip_app_octetstream_contenttype(self):
        response = self._getresponse("gzip")
        response.headers["Content-Type"] = "application/octet-stream"
        assert response.request
        request = response.request

        newresponse = self.mw.process_response(request, response)
        assert newresponse is not response
        assert newresponse.body.startswith(b"<!DOCTYPE")
        assert "Content-Encoding" not in newresponse.headers
        self.assertStatsEqual("httpcompression/response_count", 1)
        self.assertStatsEqual("httpcompression/response_bytes", 74837)

    def test_process_response_gzip_binary_octetstream_contenttype(self):
        response = self._getresponse("x-gzip")
        response.headers["Content-Type"] = "binary/octet-stream"
        assert response.request
        request = response.request

        newresponse = self.mw.process_response(request, response)
        assert newresponse is not response
        assert newresponse.body.startswith(b"<!DOCTYPE")
        assert "Content-Encoding" not in newresponse.headers
        self.assertStatsEqual("httpcompression/response_count", 1)
        self.assertStatsEqual("httpcompression/response_bytes", 74837)

    def test_process_response_gzipped_gzip_file(self):
        """Test that a gzip Content-Encoded .gz file is gunzipped
        only once by the middleware, leaving gunzipping of the file
        to upper layers.
        """
        headers = {
            "Content-Type": "application/gzip",
            "Content-Encoding": "gzip",
        }
        # build a gzipped file (here, a sitemap)
        f = BytesIO()
        plainbody = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.google.com/schemas/sitemap/0.84">
  <url>
    <loc>http://www.example.com/</loc>
    <lastmod>2009-08-16</lastmod>
    <changefreq>daily</changefreq>
    <priority>1</priority>
  </url>
  <url>
    <loc>http://www.example.com/Special-Offers.html</loc>
    <lastmod>2009-08-16</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
</urlset>"""
        gz_file = GzipFile(fileobj=f, mode="wb")
        gz_file.write(plainbody)
        gz_file.close()

        # build a gzipped response body containing this gzipped file
        r = BytesIO()
        gz_resp = GzipFile(fileobj=r, mode="wb")
        gz_resp.write(f.getvalue())
        gz_resp.close()

        response = Response(
            "http://www.example.com/", headers=headers, body=r.getvalue()
        )
        request = Request("http://www.example.com/")

        newresponse = self.mw.process_response(request, response)
        assert gunzip(newresponse.body) == plainbody
        self.assertStatsEqual("httpcompression/response_count", 1)
        self.assertStatsEqual("httpcompression/response_bytes", 230)

    def test_process_response_head_request_no_decode_required(self):
        response = self._getresponse("gzip")
        response.headers["Content-Type"] = "application/gzip"
        assert response.request
        request = response.request
        request.method = "HEAD"
        response = response.replace(body=None)
        newresponse = self.mw.process_response(request, response)
        assert newresponse is response
        assert response.body == b""
        self.assertStatsEqual("httpcompression/response_count", None)
        self.assertStatsEqual("httpcompression/response_bytes", None)

    def _test_compression_bomb_setting(self, compression_id: str) -> None:
        settings = {"DOWNLOAD_MAXSIZE": 1_000_000}
        crawler = get_crawler(Spider, settings_dict=settings)
        spider = crawler._create_spider("scrapytest.org")
        mw = build_from_crawler(HttpCompressionMiddleware, crawler)
        mw.open_spider(spider)

        response = self._getresponse(f"bomb-{compression_id}")  # 11_511_612 B
        assert response.request
        with pytest.raises(IgnoreRequest) as exc_info:
            mw.process_response(response.request, response)
        cause = exc_info.value.__cause__
        assert isinstance(cause, _DecompressionMaxSizeExceeded)
        assert cause.decompressed_size < 1_100_000

    def test_compression_bomb_setting_br(self):
        self._test_compression_bomb_setting("br")

    def test_compression_bomb_setting_deflate(self):
        self._test_compression_bomb_setting("deflate")

    def test_compression_bomb_setting_gzip(self):
        self._test_compression_bomb_setting("gzip")

    def test_compression_bomb_setting_zstd(self):
        _skip_if_no_zstd()

        self._test_compression_bomb_setting("zstd")

    def test_compression_bomb_setting_logs_warning(self, caplog):
        settings = {"DOWNLOAD_MAXSIZE": 1_000_000}
        crawler = get_crawler(Spider, settings_dict=settings)
        spider = crawler._create_spider("scrapytest.org")
        mw = build_from_crawler(HttpCompressionMiddleware, crawler)
        mw.open_spider(spider)

        response = self._getresponse("bomb-gzip")  # 11_511_612 B
        assert response.request
        caplog.clear()
        with (
            caplog.at_level(
                WARNING, logger="scrapy.downloadermiddlewares.httpcompression"
            ),
            pytest.raises(IgnoreRequest) as exc_info,
        ):
            mw.process_response(response.request, response)
        assert caplog.record_tuples == [
            (
                "scrapy.downloadermiddlewares.httpcompression",
                WARNING,
                str(exc_info.value),
            )
        ]

    def _test_compression_bomb_spider_attr(self, compression_id: str) -> None:
        class DownloadMaxSizeSpider(Spider):
            download_maxsize = 1_000_000

        crawler = get_crawler(DownloadMaxSizeSpider)
        spider = crawler._create_spider("scrapytest.org")
        mw = build_from_crawler(HttpCompressionMiddleware, crawler)
        mw.open_spider(spider)

        response = self._getresponse(f"bomb-{compression_id}")
        assert response.request
        with pytest.raises(IgnoreRequest) as exc_info:
            mw.process_response(response.request, response)
        cause = exc_info.value.__cause__
        assert isinstance(cause, _DecompressionMaxSizeExceeded)
        assert cause.decompressed_size < 1_100_000

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_compression_bomb_spider_attr_br(self):
        self._test_compression_bomb_spider_attr("br")

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_compression_bomb_spider_attr_deflate(self):
        self._test_compression_bomb_spider_attr("deflate")

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_compression_bomb_spider_attr_gzip(self):
        self._test_compression_bomb_spider_attr("gzip")

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_compression_bomb_spider_attr_zstd(self):
        _skip_if_no_zstd()

        self._test_compression_bomb_spider_attr("zstd")

    def _test_compression_bomb_request_meta(self, compression_id: str) -> None:
        crawler = get_crawler(Spider)
        spider = crawler._create_spider("scrapytest.org")
        mw = build_from_crawler(HttpCompressionMiddleware, crawler)
        mw.open_spider(spider)

        response = self._getresponse(f"bomb-{compression_id}")
        response.meta["download_maxsize"] = 1_000_000
        assert response.request
        with pytest.raises(IgnoreRequest) as exc_info:
            mw.process_response(response.request, response)
        cause = exc_info.value.__cause__
        assert isinstance(cause, _DecompressionMaxSizeExceeded)
        assert cause.decompressed_size < 1_100_000

    def test_compression_bomb_request_meta_br(self):
        self._test_compression_bomb_request_meta("br")

    def test_compression_bomb_request_meta_deflate(self):
        self._test_compression_bomb_request_meta("deflate")

    def test_compression_bomb_request_meta_gzip(self):
        self._test_compression_bomb_request_meta("gzip")

    def test_compression_bomb_request_meta_zstd(self):
        _skip_if_no_zstd()

        self._test_compression_bomb_request_meta("zstd")

    def _test_download_warnsize_setting(
        self, caplog: pytest.LogCaptureFixture, compression_id: str
    ) -> None:
        settings = {"DOWNLOAD_WARNSIZE": 10_000_000}
        crawler = get_crawler(Spider, settings_dict=settings)
        spider = crawler._create_spider("scrapytest.org")
        mw = build_from_crawler(HttpCompressionMiddleware, crawler)
        mw.open_spider(spider)
        response = self._getresponse(f"bomb-{compression_id}")

        assert response.request
        caplog.clear()
        with caplog.at_level(
            WARNING, logger="scrapy.downloadermiddlewares.httpcompression"
        ):
            mw.process_response(response.request, response)
        assert caplog.record_tuples == [
            (
                "scrapy.downloadermiddlewares.httpcompression",
                WARNING,
                (
                    "<200 http://scrapytest.org/> body size after "
                    "decompression (11511612 B) is larger than the download "
                    "warning size (10000000 B)."
                ),
            ),
        ]

    def test_download_warnsize_setting_br(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        self._test_download_warnsize_setting(caplog, "br")

    def test_download_warnsize_setting_deflate(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        self._test_download_warnsize_setting(caplog, "deflate")

    def test_download_warnsize_setting_gzip(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        self._test_download_warnsize_setting(caplog, "gzip")

    def test_download_warnsize_setting_zstd(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        _skip_if_no_zstd()

        self._test_download_warnsize_setting(caplog, "zstd")

    def _test_download_warnsize_spider_attr(
        self, caplog: pytest.LogCaptureFixture, compression_id: str
    ) -> None:
        class DownloadWarnSizeSpider(Spider):
            download_warnsize = 10_000_000

        crawler = get_crawler(DownloadWarnSizeSpider)
        spider = crawler._create_spider("scrapytest.org")
        mw = build_from_crawler(HttpCompressionMiddleware, crawler)
        mw.open_spider(spider)
        response = self._getresponse(f"bomb-{compression_id}")

        assert response.request
        caplog.clear()
        with caplog.at_level(
            WARNING, logger="scrapy.downloadermiddlewares.httpcompression"
        ):
            mw.process_response(response.request, response)
        assert caplog.record_tuples == [
            (
                "scrapy.downloadermiddlewares.httpcompression",
                WARNING,
                (
                    "<200 http://scrapytest.org/> body size after "
                    "decompression (11511612 B) is larger than the download "
                    "warning size (10000000 B)."
                ),
            ),
        ]

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_download_warnsize_spider_attr_br(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        self._test_download_warnsize_spider_attr(caplog, "br")

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_download_warnsize_spider_attr_deflate(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        self._test_download_warnsize_spider_attr(caplog, "deflate")

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_download_warnsize_spider_attr_gzip(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        self._test_download_warnsize_spider_attr(caplog, "gzip")

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_download_warnsize_spider_attr_zstd(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        _skip_if_no_zstd()

        self._test_download_warnsize_spider_attr(caplog, "zstd")

    def _test_download_warnsize_request_meta(
        self, caplog: pytest.LogCaptureFixture, compression_id: str
    ) -> None:
        crawler = get_crawler(Spider)
        spider = crawler._create_spider("scrapytest.org")
        mw = build_from_crawler(HttpCompressionMiddleware, crawler)
        mw.open_spider(spider)
        response = self._getresponse(f"bomb-{compression_id}")
        response.meta["download_warnsize"] = 10_000_000

        assert response.request
        caplog.clear()
        with caplog.at_level(
            WARNING, logger="scrapy.downloadermiddlewares.httpcompression"
        ):
            mw.process_response(response.request, response)
        assert caplog.record_tuples == [
            (
                "scrapy.downloadermiddlewares.httpcompression",
                WARNING,
                (
                    "<200 http://scrapytest.org/> body size after "
                    "decompression (11511612 B) is larger than the download "
                    "warning size (10000000 B)."
                ),
            ),
        ]

    def test_download_warnsize_request_meta_br(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        self._test_download_warnsize_request_meta(caplog, "br")

    def test_download_warnsize_request_meta_deflate(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        self._test_download_warnsize_request_meta(caplog, "deflate")

    def test_download_warnsize_request_meta_gzip(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        self._test_download_warnsize_request_meta(caplog, "gzip")

    def test_download_warnsize_request_meta_zstd(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        _skip_if_no_zstd()

        self._test_download_warnsize_request_meta(caplog, "zstd")

    def _get_truncated_response(self, compression_id: str) -> Response:
        crawler = get_crawler(Spider)
        spider = crawler._create_spider("scrapytest.org")
        mw = build_from_crawler(HttpCompressionMiddleware, crawler)
        mw.open_spider(spider)
        response = self._getresponse(compression_id)
        truncated_body = response.body[: len(response.body) // 2]
        response = response.replace(body=truncated_body)
        assert response.request
        new_response = mw.process_response(response.request, response)
        assert isinstance(new_response, Response)
        return new_response

    def test_process_truncated_response_br(self):
        resp = self._get_truncated_response("br")
        assert resp.body.startswith(b"<!DOCTYPE")

    def test_process_truncated_response_zlibdeflate(self):
        resp = self._get_truncated_response("zlibdeflate")
        assert resp.body.startswith(b"<!DOCTYPE")

    def test_process_truncated_response_gzip(self):
        resp = self._get_truncated_response("gzip")
        assert resp.body.startswith(b"<!DOCTYPE")

    def test_process_truncated_response_zstd(self):
        _skip_if_no_zstd()
        for check_key in FORMAT:
            if not check_key.startswith("zstd-"):
                continue
            resp = self._get_truncated_response(check_key)
            assert len(resp.body) == 0
