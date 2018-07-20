import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.http import decode_chunked_transfer


warnings.warn("Module `scrapy.downloadermiddlewares.chunked` is deprecated, "
              "chunked transfers are supported by default.",
              ScrapyDeprecationWarning, stacklevel=2)


class ChunkedTransferMiddleware(object):
    """This middleware adds support for chunked transfer encoding, as
    documented in: https://en.wikipedia.org/wiki/Chunked_transfer_encoding
    """

    def process_response(self, request, response, spider):
        if response.headers.get('Transfer-Encoding') == 'chunked':
            body = decode_chunked_transfer(response.body)
            return response.replace(body=body)
        return response
