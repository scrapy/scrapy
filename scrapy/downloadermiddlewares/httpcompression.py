from __future__ import annotations

import io
import warnings
import zlib
from typing import TYPE_CHECKING, List, Optional, Union

from scrapy import Request, Spider
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
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

    def __init__(self, stats: Optional[StatsCollector] = None, settings=None):
        self.stats = stats
        if settings:
            self.keep_encoding_header = settings.getbool(
                "COMPRESSION_KEEP_ENCODING_HEADER"
            )
            if not self.keep_encoding_header:
                warnings.warn(
                    "Setting COMPRESSION_KEEP_ENCODING_HEADER=False is deprecated",
                    ScrapyDeprecationWarning,
                )
        else:
            self.keep_encoding_header = False
            warnings.warn(
                "The default value of COMPRESSION_KEEP_ENCODING_HEADER, "
                "False, is deprecated, and will stop working and stop "
                "being its default value in a future version of Scrapy. "
                "Set COMPRESSION_KEEP_ENCODING_HEADER=True in your "
                "settings to remove this warning.",
                ScrapyDeprecationWarning,
                stacklevel=2,
            )

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        if not crawler.settings.getbool("COMPRESSION_ENABLED"):
            raise NotConfigured
        try:
            return cls(stats=crawler.stats, settings=crawler.settings)
        except TypeError:
            warnings.warn(
                "HttpCompressionMiddleware subclasses must either modify "
                "their '__init__' method to support 'stats' and 'settings' parameters or "
                "reimplement the 'from_crawler' method.",
                ScrapyDeprecationWarning,
            )
            result = cls()
            result.stats = crawler.stats
            result.keep_encoding_header = False
            return result

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
        if b"decoded" in response.flags:
            return response
        content_encoding = response.headers.getlist("Content-Encoding")
        if not content_encoding:
            return response

        encoding = content_encoding[0]
        decoded_body = self._decode(response.body, encoding.lower())
        if self.stats:
            self.stats.inc_value(
                "httpcompression/response_bytes", len(decoded_body), spider=spider
            )
            self.stats.inc_value("httpcompression/response_count", spider=spider)
        respcls = responsetypes.from_args(
            headers=response.headers, url=response.url, body=decoded_body
        )
        kwargs = dict(cls=respcls, body=decoded_body)
        if issubclass(respcls, TextResponse):
            # force recalculating the encoding until we make sure the
            # responsetypes guessing is reliable
            kwargs["encoding"] = None

        kwargs["flags"] = response.flags + [b"decoded"]
        response = response.replace(**kwargs)
        if not self.keep_encoding_header:
            del response.headers["Content-Encoding"]
        return response

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
