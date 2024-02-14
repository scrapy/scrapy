import warnings
from logging import getLogger

from scrapy import signals
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Response, TextResponse
from scrapy.responsetypes import responsetypes
from scrapy.utils._compression import (
    _DecompressionMaxSizeExceeded,
    _inflate,
    _unbrotli,
    _unzstd,
)
from scrapy.utils.deprecate import ScrapyDeprecationWarning
from scrapy.utils.gz import gunzip

logger = getLogger(__name__)

ACCEPTED_ENCODINGS = [b"gzip", b"deflate"]

try:
    import brotli  # noqa: F401
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


class HttpCompressionMiddleware(object):
    """This middleware allows compressed (gzip, deflate) traffic to be
    sent/received from web sites"""

    def __init__(self, crawler=None):
        if not crawler:
            self._max_size = 1073741824
            self._warn_size = 33554432
            return
        self._max_size = crawler.settings.getint("DOWNLOAD_MAXSIZE")
        self._warn_size = crawler.settings.getint("DOWNLOAD_WARNSIZE")
        crawler.signals.connect(self.open_spider, signals.spider_opened)

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('COMPRESSION_ENABLED'):
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
            mw._max_size = crawler.settings.getint("DOWNLOAD_MAXSIZE")
            mw._warn_size = crawler.settings.getint("DOWNLOAD_WARNSIZE")
            crawler.signals.connect(mw.open_spider, signals.spider_opened)
            return mw

    def open_spider(self, spider):
        if hasattr(spider, "download_maxsize"):
            self._max_size = spider.download_maxsize
        if hasattr(spider, "download_warnsize"):
            self._warn_size = spider.download_warnsize

    def process_request(self, request, spider):
        request.headers.setdefault('Accept-Encoding',
                                   b",".join(ACCEPTED_ENCODINGS))

    def process_response(self, request, response, spider):

        if request.method == 'HEAD':
            return response
        if isinstance(response, Response):
            content_encoding = response.headers.getlist('Content-Encoding')
            if content_encoding:
                encoding = content_encoding.pop()
                max_size = request.meta.get("download_maxsize", self._max_size)
                warn_size = request.meta.get("download_warnsize", self._warn_size)
                try:
                    decoded_body = self._decode(
                        response.body, encoding.lower(), max_size
                    )
                except _DecompressionMaxSizeExceeded:
                    raise IgnoreRequest(
                        "Ignored response {response} because its body "
                        "({body_size} B) exceeded DOWNLOAD_MAXSIZE "
                        "({max_size} B) during decompression.".format(
                            response=response,
                            body_size=len(response.body),
                            max_size=max_size,
                        )
                    )
                if len(response.body) < warn_size <= len(decoded_body):
                    logger.warning(
                        "%(response)s body size after decompression "
                        "(%(body_size)s B) is larger than the "
                        "download warning size (%(warn_size)s B).",
                        {
                            "response": response,
                            "body_size": len(decoded_body),
                            "warn_size": warn_size,
                        },
                    )
                respcls = responsetypes.from_args(
                    headers=response.headers, url=response.url, body=decoded_body
                )
                kwargs = dict(cls=respcls, body=decoded_body)
                if issubclass(respcls, TextResponse):
                    # force recalculating the encoding until we make sure the
                    # responsetypes guessing is reliable
                    kwargs['encoding'] = None
                response = response.replace(**kwargs)
                if not content_encoding:
                    del response.headers['Content-Encoding']

        return response

    def _decode(self, body, encoding, max_size):
        if encoding == b"gzip" or encoding == b"x-gzip":
            return gunzip(body, max_size=max_size)
        if encoding == b"deflate":
            return _inflate(body, max_size=max_size)
        if encoding == b"br" and b"br" in ACCEPTED_ENCODINGS:
            return _unbrotli(body, max_size=max_size)
        if encoding == b"zstd" and b"zstd" in ACCEPTED_ENCODINGS:
            return _unzstd(body, max_size=max_size)
        return body
