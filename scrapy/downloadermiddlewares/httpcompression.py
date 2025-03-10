from __future__ import annotations

from itertools import chain
from logging import getLogger
from typing import TYPE_CHECKING, Any

from scrapy import Request, Spider, signals
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Response, TextResponse
from scrapy.responsetypes import responsetypes
from scrapy.utils._compression import (
    _DecompressionMaxSizeExceeded,
    _inflate,
    _unbrotli,
    _unzstd,
)
from scrapy.utils.gz import gunzip

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.statscollectors import StatsCollector


logger = getLogger(__name__)

ACCEPTED_ENCODINGS: list[bytes] = [b"gzip", b"deflate"]

try:
    try:
        import brotli  # noqa: F401
    except ImportError:
        import brotlicffi  # noqa: F401
except ImportError:
    pass
else:
    ACCEPTED_ENCODINGS.append(b"br")

try:
    import zstandard  # noqa: F401
except ImportError:
    pass
else:
    ACCEPTED_ENCODINGS.append(b"zstd")


class HttpCompressionMiddleware:
    """This middleware allows compressed (gzip, deflate) traffic to be
    sent/received from websites"""

    def __init__(
        self,
        stats: StatsCollector | None = None,
        *,
        crawler: Crawler | None = None,
    ):
        if not crawler:
            self.stats = stats
            self._max_size = 1073741824
            self._warn_size = 33554432
            return
        self.stats = crawler.stats
        self._max_size = crawler.settings.getint("DOWNLOAD_MAXSIZE")
        self._warn_size = crawler.settings.getint("DOWNLOAD_WARNSIZE")
        crawler.signals.connect(self.open_spider, signals.spider_opened)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        if not crawler.settings.getbool("COMPRESSION_ENABLED"):
            raise NotConfigured
        return cls(crawler=crawler)

    def open_spider(self, spider: Spider) -> None:
        if hasattr(spider, "download_maxsize"):
            self._max_size = spider.download_maxsize
        if hasattr(spider, "download_warnsize"):
            self._warn_size = spider.download_warnsize

    def process_request(
        self, request: Request, spider: Spider
    ) -> Request | Response | None:
        request.headers.setdefault("Accept-Encoding", b", ".join(ACCEPTED_ENCODINGS))
        return None

    def process_response(
        self, request: Request, response: Response, spider: Spider
    ) -> Request | Response:
        if request.method == "HEAD":
            return response
        if isinstance(response, Response):
            content_encoding = response.headers.getlist("Content-Encoding")
            if content_encoding:
                max_size = request.meta.get("download_maxsize", self._max_size)
                warn_size = request.meta.get("download_warnsize", self._warn_size)
                try:
                    decoded_body, content_encoding = self._handle_encoding(
                        response.body, content_encoding, max_size
                    )
                except _DecompressionMaxSizeExceeded:
                    raise IgnoreRequest(
                        f"Ignored response {response} because its body "
                        f"({len(response.body)} B compressed) exceeded "
                        f"DOWNLOAD_MAXSIZE ({max_size} B) during "
                        f"decompression."
                    )
                if len(response.body) < warn_size <= len(decoded_body):
                    logger.warning(
                        f"{response} body size after decompression "
                        f"({len(decoded_body)} B) is larger than the "
                        f"download warning size ({warn_size} B)."
                    )
                if content_encoding:
                    self._warn_unknown_encoding(response, content_encoding)
                response.headers["Content-Encoding"] = content_encoding
                if self.stats:
                    self.stats.inc_value(
                        "httpcompression/response_bytes",
                        len(decoded_body),
                        spider=spider,
                    )
                    self.stats.inc_value(
                        "httpcompression/response_count", spider=spider
                    )
                respcls = responsetypes.from_args(
                    headers=response.headers, url=response.url, body=decoded_body
                )
                kwargs: dict[str, Any] = {"body": decoded_body}
                if issubclass(respcls, TextResponse):
                    # force recalculating the encoding until we make sure the
                    # responsetypes guessing is reliable
                    kwargs["encoding"] = None
                response = response.replace(cls=respcls, **kwargs)
                if not content_encoding:
                    del response.headers["Content-Encoding"]

        return response

    def _handle_encoding(
        self, body: bytes, content_encoding: list[bytes], max_size: int
    ) -> tuple[bytes, list[bytes]]:
        to_decode, to_keep = self._split_encodings(content_encoding)
        for encoding in to_decode:
            body = self._decode(body, encoding, max_size)
        return body, to_keep

    @staticmethod
    def _split_encodings(
        content_encoding: list[bytes],
    ) -> tuple[list[bytes], list[bytes]]:
        supported_encodings = {*ACCEPTED_ENCODINGS, b"x-gzip"}
        to_keep: list[bytes] = [
            encoding.strip().lower()
            for encoding in chain.from_iterable(
                encodings.split(b",") for encodings in content_encoding
            )
        ]
        to_decode: list[bytes] = []
        while to_keep:
            encoding = to_keep.pop()
            if encoding not in supported_encodings:
                to_keep.append(encoding)
                return to_decode, to_keep
            to_decode.append(encoding)
        return to_decode, to_keep

    @staticmethod
    def _decode(body: bytes, encoding: bytes, max_size: int) -> bytes:
        if encoding in {b"gzip", b"x-gzip"}:
            return gunzip(body, max_size=max_size)
        if encoding == b"deflate":
            return _inflate(body, max_size=max_size)
        if encoding == b"br":
            return _unbrotli(body, max_size=max_size)
        if encoding == b"zstd":
            return _unzstd(body, max_size=max_size)
        # shouldn't be reached
        return body  # pragma: no cover

    def _warn_unknown_encoding(
        self, response: Response, encodings: list[bytes]
    ) -> None:
        encodings_str = b",".join(encodings).decode()
        msg = (
            f"{self.__class__.__name__} cannot decode the response for {response.url} "
            f"from unsupported encoding(s) '{encodings_str}'."
        )
        if b"br" in encodings:
            msg += " You need to install brotli or brotlicffi to decode 'br'."
        if b"zstd" in encodings:
            msg += " You need to install zstandard to decode 'zstd'."
        logger.warning(msg)
