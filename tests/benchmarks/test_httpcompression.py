from __future__ import annotations

import sys
from gzip import GzipFile
from io import BytesIO
from typing import TYPE_CHECKING, Any

import pytest

from scrapy import Request, Spider
from scrapy.http import Response
from scrapy.utils.gz import gunzip
from tests import get_testdata
from tests.benchmarks import crawl

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pytest_codspeed import BenchmarkFixture  # type: ignore[import-not-found]

    from scrapy.crawler import Crawler

pytest.importorskip("pytest_codspeed", reason="Benchmarks require pytest-codspeed")

try:
    import brotli
except ImportError:
    import brotlicffi as brotli

if sys.version_info >= (3, 14):
    from compression import zstd
else:
    from backports import zstd

# Concurrent responses per crawl, high enough that decoding several of them
# in threads can overlap with the reactor doing other work.
DOMAINS = 32

# A real page, so that tiling it to reach a target size keeps a realistic
# compression ratio (unlike, say, a repeated short string).
_PAGE = gunzip(get_testdata("compressed", "html-gzip.bin"))


def _html(size: int) -> bytes:
    """A real HTML payload of exactly *size* bytes."""
    return (_PAGE * (size // len(_PAGE) + 1))[:size]


def _compress(codec: str, data: bytes) -> bytes:
    if codec == "gzip":
        buf = BytesIO()
        with GzipFile(fileobj=buf, mode="wb") as f:
            f.write(data)
        return buf.getvalue()
    if codec == "br":
        compressed: bytes = brotli.compress(data)
        return compressed
    if codec == "zstd":
        zstd_compressed: bytes = zstd.compress(data)
        return zstd_compressed
    raise ValueError(codec)  # pragma: no cover


def _handler_for(body: bytes, codec: str) -> type:
    """Build a download handler class that returns *body* for every request.

    Mirrors :class:`tests.benchmarks.NullDownloadHandler`'s concurrency
    tracking, but returns a real compressed body so
    :class:`~scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware`
    has real decompression work to do.
    """

    class _CompressedDownloadHandler:
        lazy = False

        def __init__(self, crawler: Crawler):
            self._crawler = crawler
            self._active = 0

        @classmethod
        def from_crawler(cls, crawler: Crawler) -> _CompressedDownloadHandler:
            return cls(crawler)

        async def download_request(self, request: Request) -> Response:
            self._active += 1
            self._crawler.stats.max_value("benchmark/peak_concurrency", self._active)
            try:
                return Response(
                    request.url,
                    request=request,
                    body=body,
                    headers={"Content-Encoding": codec},
                )
            finally:
                self._active -= 1

        async def close(self) -> None:
            pass

    return _CompressedDownloadHandler


class _CompressedSpider(Spider):
    name = "benchmark-compression"
    domains: int = DOMAINS

    async def start(self) -> AsyncIterator[Any]:
        for domain in range(self.domains):
            yield Request(f"http://d{domain}.example.com/")

    def parse(self, response: Response) -> None:
        return None


def _crawl_compressed(codec: str, size: int) -> Crawler:
    body = _compress(codec, _html(size))
    settings = {
        "DOWNLOAD_HANDLERS": {"http": _handler_for(body, codec)},
        "CONCURRENT_REQUESTS": DOMAINS,
        "LOG_ENABLED": False,
    }
    crawler = crawl(_CompressedSpider, settings, domains=DOMAINS)
    assert crawler.stats.get_value("httpcompression/response_count") == DOMAINS
    return crawler


# (codec, decompressed size). gzip gets the full sweep, since it is the most
# common encoding; br and zstd only bracket a couple of representative sizes.
# Sizes span small (a typical API response) to large (a big page or file), so
# that a change affecting only large responses shows up on some of these and
# not others.
_CASES = [
    *(
        pytest.param("gzip", size, id=f"gzip-{size}")
        for size in (
            4 * 1024,
            20 * 1024,
            100 * 1024,
            1024 * 1024,
            4 * 1024 * 1024,
        )
    ),
    *(
        pytest.param(codec, size, id=f"{codec}-{size}")
        for codec in ("br", "zstd")
        for size in (20 * 1024, 200 * 1024)
    ),
]


@pytest.mark.walltime
@pytest.mark.parametrize(("codec", "size"), _CASES)
def test_decode_concurrency(
    benchmark: BenchmarkFixture,
    codec: str,
    size: int,
) -> None:
    """Wall-clock cost of decoding many concurrent compressed responses.

    Tracks whatever :class:`HttpCompressionMiddleware
    <scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware>`
    currently does under concurrency, at a range of sizes, so that a change
    to how (or whether) it decodes off the reactor thread shows up as a
    regression or improvement here, size by size.
    """
    benchmark(lambda: _crawl_compressed(codec, size))


def test_decode_typical(benchmark: BenchmarkFixture) -> None:
    """Overhead of decoding a typical, small gzip-compressed API response.

    Uses the real (not monkeypatched) threshold: most responses stay under
    it and are decoded inline, so this guards that common case against added
    overhead.
    """
    benchmark(lambda: _crawl_compressed("gzip", 8 * 1024))
