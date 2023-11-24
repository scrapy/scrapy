import struct

try:
    from cStringIO import StringIO as BytesIO
except ImportError:
    from io import BytesIO

import re
from gzip import GzipFile

import six

from scrapy.utils.decorators import deprecated

from ._compression import _CHUNK_SIZE, _DecompressionMaxSizeExceeded

# - Python>=3.5 GzipFile's read() has issues returning leftover
#   uncompressed data when input is corrupted
#   (regression or bug-fix compared to Python 3.4)
# - read1(), which fetches data before raising EOFError on next call
#   works here but is only available from Python>=3.3
# - scrapy does not support Python 3.2
# - Python 2.7 GzipFile works fine with standard read() + extrabuf
if six.PY2:
    def read1(gzf, size=-1):
        return gzf.read(size)
else:
    def read1(gzf, size=-1):
        return gzf.read1(size)


def gunzip(data, max_size=0):
    """Gunzip the given data and return as much data as possible.

    This is resilient to CRC checksum errors.
    """
    f = GzipFile(fileobj=BytesIO(data))
    output_stream = BytesIO()
    output_chunk = b"."
    decompressed_size = 0
    while output_chunk:
        try:
            output_chunk = read1(f, _CHUNK_SIZE)
        except (IOError, EOFError, struct.error):
            # complete only if there is some data, otherwise re-raise
            # see issue 87 about catching struct.error
            # some pages are quite small so output_list is empty and f.extrabuf
            # contains the whole page content
            if decompressed_size or getattr(f, 'extrabuf', None):
                try:
                    output_stream.write(f.extrabuf[-f.extrasize:])
                finally:
                    break
            else:
                raise
        decompressed_size += len(output_chunk)
        if max_size and decompressed_size > max_size:
            raise _DecompressionMaxSizeExceeded(
                "The number of bytes decompressed so far "
                "({decompressed_size} B) exceed the specified maximum "
                "({max_size} B).".format(
                    decompressed_size=decompressed_size,
                    max_size=max_size,
                )
            )
        output_stream.write(output_chunk)
    output_stream.seek(0)
    return output_stream.read()

_is_gzipped = re.compile(br'^application/(x-)?gzip\b', re.I).search
_is_octetstream = re.compile(br'^(application|binary)/octet-stream\b', re.I).search

@deprecated
def is_gzipped(response):
    """Return True if the response is gzipped, or False otherwise"""
    ctype = response.headers.get('Content-Type', b'')
    cenc = response.headers.get('Content-Encoding', b'').lower()
    return (_is_gzipped(ctype) or
            (_is_octetstream(ctype) and cenc in (b'gzip', b'x-gzip')))


def gzip_magic_number(response):
    return response.body[:3] == b'\x1f\x8b\x08'
