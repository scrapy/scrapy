from __future__ import annotations

import io
import zlib
from itertools import chain
from typing import TYPE_CHECKING, List, Optional, Union

from scrapy import Request, Spider
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.http import Response, TextResponse
from scrapy.responsetypes import responsetypes
from scrapy.statscollectors import StatsCollector
from scrapy.utils.gz import gunzip

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

ACCEPTED_ENCODINGS: List[bytes] = [b"gzip", b"deflate"]

try:
    import brotli

    ACCEPTED_ENCODINGS.append(b"br")
except ImportError:
    pass

try:
    import zstandard

    ACCEPTED_ENCODINGS.append(b"zstd")
except ImportError:
    pass


class HttpCompressionMiddleware:
    """This middleware allows compressed (gzip, deflate) traffic to be
    sent/received from web sites"""

    def __init__(self, stats: Optional[StatsCollector] = None):
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        if not crawler.settings.getbool("COMPRESSION_ENABLED"):
            raise NotConfigured
        return cls(stats=crawler.stats)

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
                decoded_body, content_encoding = self._handle_encoding(
                    response.body, content_encoding
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
                kwargs = dict(cls=respcls, body=decoded_body)
                if issubclass(respcls, TextResponse):
                    # force recalculating the encoding until we make sure the
                    # responsetypes guessing is reliable
                    kwargs["encoding"] = None
                response = response.replace(**kwargs)
                if not content_encoding:
                    del response.headers["Content-Encoding"]

        return response

    def _handle_encoding(self, body, content_encoding):
        to_decode, to_keep = self._split_encodings(content_encoding)
        for encoding in to_decode:
            body = self._decode(body, encoding)
        return body, to_keep

    def _split_encodings(self, content_encoding):
        to_keep = [
            encoding.strip().lower()
            for encoding in chain.from_iterable(
                encodings.split(b",") for encodings in content_encoding
            )
        ]
        to_decode = []
        while to_keep:
            encoding = to_keep.pop()
            if encoding not in ACCEPTED_ENCODINGS:
                to_keep.append(encoding)
                return to_decode, to_keep
            to_decode.append(encoding)
        return to_decode, to_keep

    def _decode(self, body: bytes, encoding: bytes) -> bytes:
        if encoding == b"gzip" or encoding == b"x-gzip":
            body = gunzip(body)

        if encoding == b"deflate":
            try:
                body = zlib.decompress(body)
            except zlib.error:
                # ugly hack to work with raw deflate content that may
                # be sent by microsoft servers. For more information, see:
                # http://carsten.codimi.de/gzip.yaws/
                # http://www.port80software.com/200ok/archive/2005/10/31/868.aspx
                # http://www.gzip.org/zlib/zlib_faq.html#faq38
                body = zlib.decompress(body, -15)
        if encoding == b"br" and b"br" in ACCEPTED_ENCODINGS:
            body = brotli.decompress(body)
        if encoding == b"zstd" and b"zstd" in ACCEPTED_ENCODINGS:
            # Using its streaming API since its simple API could handle only cases
            # where there is content size data embedded in the frame
            reader = zstandard.ZstdDecompressor().stream_reader(io.BytesIO(body))
            body = reader.read()
        return body
