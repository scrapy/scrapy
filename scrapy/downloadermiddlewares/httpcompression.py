import io
import zlib
import logging

from scrapy.utils.gz import gunzip
from scrapy.http import Response, TextResponse
from scrapy.responsetypes import responsetypes
from scrapy.exceptions import NotConfigured


ACCEPTED_ENCODINGS = [b'gzip', b'deflate']
logger = logging.getLogger(__name__)

try:
    import brotli
    ACCEPTED_ENCODINGS.append(b'br')
except ImportError:
    logger.error("brotil not installed")

try:
    import zstandard
    ACCEPTED_ENCODINGS.append(b'zstd')
except ImportError:
    pass


class HttpCompressionMiddleware:
    """This middleware allows compressed (gzip, deflate) traffic to be
    sent/received from web sites"""
    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('COMPRESSION_ENABLED'):
            raise NotConfigured
        return cls()

    def process_request(self, request, spider):
        request.headers.setdefault('Accept-Encoding',
                                   b", ".join(ACCEPTED_ENCODINGS))

    def process_response(self, request, response, spider):

        if request.method == 'HEAD':
            return response
        if isinstance(response, Response):
            content_encoding = response.headers.getlist('Content-Encoding')
            if content_encoding:
                encoding = content_encoding.pop()
                decoded_body = self._decode(response.body, encoding.lower())
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

    def _decode(self, body, encoding):
        if encoding == b'gzip' or encoding == b'x-gzip':
            body = gunzip(body)

        if encoding == b'deflate':
            try:
                body = zlib.decompress(body)
            except zlib.error:
                # ugly hack to work with raw deflate content that may
                # be sent by microsoft servers. For more information, see:
                # http://carsten.codimi.de/gzip.yaws/
                # http://www.port80software.com/200ok/archive/2005/10/31/868.aspx
                # http://www.gzip.org/zlib/zlib_faq.html#faq38
                body = zlib.decompress(body, -15)
        if encoding == b'br' and b'br' in ACCEPTED_ENCODINGS:
            try:
                body = brotli.decompress(body)
            except ImportError:
                logger.error("brotil not installed")

        if encoding == b'zstd' and b'zstd' in ACCEPTED_ENCODINGS:
            # Using its streaming API since its simple API could handle only cases
            # where there is content size data embedded in the frame
            reader = zstandard.ZstdDecompressor().stream_reader(io.BytesIO(body))
            body = reader.read()
        return body
