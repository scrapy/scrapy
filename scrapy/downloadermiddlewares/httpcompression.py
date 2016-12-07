import zlib

from scrapy.utils.gz import gunzip, is_gzipped
from scrapy.http import Response, TextResponse
from scrapy.responsetypes import responsetypes
from scrapy.exceptions import NotConfigured


class HttpCompressionMiddleware(object):
    """This middleware allows compressed (gzip, deflate) traffic to be
    sent/received from web sites"""

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('COMPRESSION_ENABLED'):
            raise NotConfigured
        return cls()

    def process_request(self, request, spider):
        request.headers.setdefault('Accept-Encoding', 'gzip,deflate')

    def process_response(self, request, response, spider):

        if request.method == 'HEAD':
            return response
        if isinstance(response, Response):
            content_encoding = response.headers.getlist('Content-Encoding')
            if content_encoding and not is_gzipped(response):
                encoding = content_encoding.pop()
                try:
                    decoded_body = self._decode(response.body, encoding.lower())
                except (IOError, zlib.error):
                    # Propagate decompression failures of successful responses.
                    if 200 <= response.status < 300:
                        raise
                    # For unsuccessful responses, it's often because
                    # the body is plain text or HTML, wrongly advertized as gzipped.
                    # we make the bet it's ok to pass it as-is for redirects,
                    # 4xx's and 5xx's
                    decoded_body = response.body
                respcls = responsetypes.from_args(headers=response.headers, \
                    url=response.url)
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
        return body

