from gzip import GzipFile
from io import BytesIO
from logging import WARNING
from pathlib import Path

import pytest
from testfixtures import LogCapture
from w3lib.encoding import resolve_encoding

from scrapy.downloadermiddlewares.httpcompression import (
    ACCEPTED_ENCODINGS,
    HttpCompressionMiddleware,
)
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import HtmlResponse, Request, Response
from scrapy.responsetypes import responsetypes
from scrapy.spiders import Spider
from scrapy.utils.gz import gunzip
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


def _skip_if_no_br() -> None:
    try:
        try:
            import brotli  # noqa: PLC0415

            brotli.Decompressor.can_accept_more_data
        except (ImportError, AttributeError):
            import brotlicffi  # noqa: PLC0415

            brotlicffi.Decompressor.can_accept_more_data
    except (ImportError, AttributeError):
        pytest.skip("no brotli support")


def _skip_if_no_zstd() -> None:
    try:
        import zstandard  # noqa: F401,PLC0415
    except ImportError:
        pytest.skip("no zstd support (zstandard)")


class TestHttpCompression:
    def setup_method(self):
        self.crawler = get_crawler(Spider)
        self.mw = HttpCompressionMiddleware.from_crawler(self.crawler)
        self.crawler.stats.open_spider()

    def _getresponse(self, coding):
        if coding not in FORMAT:
            raise ValueError

        samplefile, contentencoding = FORMAT[coding]

        body = (SAMPLEDIR / samplefile).read_bytes()

        headers = {
            "Server": "Yaws/1.49 Yet Another Web Server",
            "Date": "Sun, 08 Mar 2009 00:41:03 GMT",
            "Content-Type": "text/html",
            "Content-Encoding": contentencoding,
        }


        response = Response("http://scrapytest.org/", body=body, headers=headers)
        response.request = Request(
            "http://scrapytest.org", headers={"Accept-Encoding": "gzip, deflate"}
        )
        return response


    def assertStatsEqual(self, key, value):
        assert self.crawler.stats.get_value(key) == value, str(
            self.crawler.stats.get_stats()
        )


    def test_setting_false_compression_enabled(self):
        with pytest.raises(NotConfigured):
            HttpCompressionMiddleware.from_crawler(
                get_crawler(settings_dict={"COMPRESSION_ENABLED": False})
            )


    def test_setting_default_compression_enabled(self):
        assert isinstance(
            HttpCompressionMiddleware.from_crawler(get_crawler()),
            HttpCompressionMiddleware,
        )


    def test_setting_true_compression_enabled(self):
        assert isinstance(
            HttpCompressionMiddleware.from_crawler(
                get_crawler(settings_dict={"COMPRESSION_ENABLED": True})
            ),
            HttpCompressionMiddleware,
        )


    def test_process_request(self):
        request = Request("http://scrapytest.org")
        assert "Accept-Encoding" not in request.headers
        self.mw.process_request(request)
        assert request.headers.get("Accept-Encoding") == b", ".join(ACCEPTED_ENCODINGS)


    def test_process_response_gzip(self):
        response = self._getresponse("gzip")
        request = response.request


        assert response.headers["Content-Encoding"] == b"gzip"
        newresponse = self.mw.process_response(request, response)
        assert newresponse is not response
        assert newresponse.body.startswith(b"<!DOCTYPE")
        assert "Content-Encoding" not in newresponse.headers
        self.assertStatsEqual("httpcompression/response_count", 1)
        self.assertStatsEqual("httpcompression/response_bytes", 74837)

    def test_original_content_encoding_preserved_gzip(self):
        """After decompression, the original Content-Encoding should be
        accessible via response.meta['original_content_encoding'] (#1988)."""
        response = self._getresponse("gzip")
        request = response.request
        newresponse = self.mw.process_response(request, response)
        assert newresponse.meta["original_content_encoding"] == "gzip"

    def test_original_content_encoding_preserved_multi(self):
        """Multi-value Content-Encoding should be fully preserved in meta."""
        response = self._getresponse("gzip-deflate")
        request = response.request
        newresponse = self.mw.process_response(request, response)
        assert newresponse.meta["original_content_encoding"] == "gzip, deflate"

    def test_process_response_br(self):
        _skip_if_no_br()


        response = self._getresponse("br")
        request = response.request
        assert response.headers["Content-Encoding"] == b"br"
        newresponse = self.mw.process_response(request, response)
        assert newresponse is not response
        assert newresponse.body.startswith(b"<!DOCTYPE")
        assert "Content-Encoding" not in newresponse.headers
        self.assertStatsEqual("httpcompression/response_count", 1)
        self.assertStatsEqual("httpcompression/response_bytes", 74837)


    def test_process_response_br_unsupported(self):
        try:
            try:
                import brotli  # noqa: F401,PLC0415


                pytest.skip("Requires not having brotli support")
            except ImportError:
                import brotlicffi  # noqa: F401,PLC0415


                pytest.skip("Requires not having brotli support")
        except ImportError:
            pass
        response = self._getresponse("br")
        request = response.request
        assert response.headers["Content-Encoding"] == b"br"
        with LogCapture(
