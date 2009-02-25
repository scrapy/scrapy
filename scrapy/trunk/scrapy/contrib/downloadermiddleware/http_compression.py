import zlib
from gzip import GzipFile
from cStringIO import StringIO

from scrapy.http import Response


class HTTPCompressionMiddleware(object):
    """This middleware allows compressed (gzip, deflate) traffic to be
    sent/received from web sites"""

    def process_request(self, request, spider):
        request.headers.setdefault('Accept-Encoding', 'gzip,deflate')

    def process_response(self, request, response, spider):
        if isinstance(response, Response):
            content_encoding = response.headers.get('Content-Encoding')
            if content_encoding:
                encoding = content_encoding[0].lower()
                raw_body = response.body
                decoded_body = self._decode(raw_body, encoding)
                response = response.replace(body=decoded_body)
                response.headers['Content-Encoding'] = content_encoding[1:]
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

