"""
Transitional module for moving to the w3lib library.

For new code, always import from w3lib.http instead of this module
"""

import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.decorators import deprecated
from w3lib.http import *


warnings.warn("Module `scrapy.utils.http` is deprecated, "
              "Please import from `w3lib.http` instead.",
              ScrapyDeprecationWarning, stacklevel=2)


@deprecated
def decode_chunked_transfer(chunked_body):
    """Parsed body received with chunked transfer encoding, and return the
    decoded body.

    For more info see:
    https://en.wikipedia.org/wiki/Chunked_transfer_encoding

    """
    body, h, t = '', '', chunked_body
    while t:
        h, t = t.split('\r\n', 1)
        if h == '0':
            break
        size = int(h, 16)
        body += t[:size]
        t = t[size+2:]
    return body

