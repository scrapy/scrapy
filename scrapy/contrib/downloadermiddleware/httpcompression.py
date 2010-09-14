import zlib
from gzip import GzipFile
from cStringIO import StringIO

from scrapy.http import Response
from scrapy.core.downloader.responsetypes import responsetypes


class HttpCompressionMiddleware(object):
    """This middleware allows compressed (gzip, deflate) traffic to be
    sent/received from web sites"""

    def process_request(self, request, spider):
        request.headers.setdefault('Accept-Encoding', 'gzip,deflate')

    def process_response(self, request, response, spider):
        if isinstance(response, Response):
            content_encoding = response.headers.getlist('Content-Encoding')
            if content_encoding:
                encoding = content_encoding.pop()
                decoded_body = self._decode(response.body, encoding.lower())
                respcls = responsetypes.from_args(headers=response.headers, \
                    url=response.url)
                response = response.replace(cls=respcls, body=decoded_body)
                if not content_encoding:
                    del response.headers['Content-Encoding']

        return response

    def _decode(self, body, encoding):
        if encoding == 'gzip':
            body = GzipFile(fileobj=StringIO(body)).read()

        if encoding == 'deflate':
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

