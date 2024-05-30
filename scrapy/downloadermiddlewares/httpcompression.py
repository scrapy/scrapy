from __future__ import annotations

import warnings
from itertools import chain
from logging import getLogger
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

from scrapy import Request, Spider, signals
from scrapy.crawler import Crawler
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Response, TextResponse
from scrapy.responsetypes import responsetypes
from scrapy.statscollectors import StatsCollector
from scrapy.utils._compression import (
    _DecompressionMaxSizeExceeded,
    _inflate,
    _unbrotli,
    _unzstd,
)
from scrapy.utils.deprecate import ScrapyDeprecationWarning
from scrapy.utils.gz import gunzip

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

logger = getLogger(__name__)

ACCEPTED_ENCODINGS: List[bytes] = [b"gzip", b"deflate"]

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
    sent/received from web sites"""

    def __init__(
        self,
        stats: Optional[StatsCollector] = None,
        *,
        crawler: Optional[Crawler] = None,
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
        try:
            return cls(crawler=crawler)
        except TypeError:
            warnings.warn(
                "HttpCompressionMiddleware subclasses must either modify "
                "their '__init__' method to support a 'crawler' parameter or "
                "reimplement their 'from_crawler' method.",
                ScrapyDeprecationWarning,
            )
            mw = cls()
            mw.stats = crawler.stats
            mw._max_size = crawler.settings.getint("DOWNLOAD_MAXSIZE")
            mw._warn_size = crawler.settings.getint("DOWNLOAD_WARNSIZE")
            crawler.signals.connect(mw.open_spider, signals.spider_opened)
            return mw

    def open_spider(self, spider):
        if hasattr(spider, "download_maxsize"):
            self._max_size = spider.download_maxsize
        if hasattr(spider, "download_warnsize"):
            self._warn_size = spider.download_warnsize

    def process_request(
        self, request: Request, spider: Spider
    ) -> Union[Request, Response, None]:
        request.headers.setdefault("Accept-Encoding", b", ".join(ACCEPTED_ENCODINGS))
        return None

    def process_response(
        self, request: Request, response: Response, spider: Spider
    ) -> Union[Request, Response]:
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
                kwargs = {"cls": respcls, "body": decoded_body}
                if issubclass(respcls, TextResponse):
                    # force recalculating the encoding until we make sure the
                    # responsetypes guessing is reliable
                    kwargs["encoding"] = None
                response = response.replace(**kwargs)
                if not content_encoding:
                    del response.headers["Content-Encoding"]

        return response

    def _handle_encoding(
        self, body: bytes, content_encoding: List[bytes], max_size: int
    ) -> Tuple[bytes, List[bytes]]:
        to_decode, to_keep = self._split_encodings(content_encoding)
        for encoding in to_decode:
            body = self._decode(body, encoding, max_size)
        return body, to_keep

    def _split_encodings(
        self, content_encoding: List[bytes]
    ) -> Tuple[List[bytes], List[bytes]]:
        to_keep: List[bytes] = [
            encoding.strip().lower()
            for encoding in chain.from_iterable(
                encodings.split(b",") for encodings in content_encoding
            )
        ]
        to_decode: List[bytes] = []
        while to_keep:
            encoding = to_keep.pop()
            if encoding not in ACCEPTED_ENCODINGS:
                to_keep.append(encoding)
                return to_decode, to_keep
            to_decode.append(encoding)
        return to_decode, to_keep

    def _decode(self, body: bytes, encoding: bytes, max_size: int) -> bytes:
        if encoding in {b"gzip", b"x-gzip"}:
            return gunzip(body, max_size=max_size)
        if encoding == b"deflate":
            return _inflate(body, max_size=max_size)
        if encoding == b"br" and b"br" in ACCEPTED_ENCODINGS:
            return _unbrotli(body, max_size=max_size)
        if encoding == b"zstd" and b"zstd" in ACCEPTED_ENCODINGS:
            return _unzstd(body, max_size=max_size)
        return body
