from gzip import GzipFile
from io import BytesIO
import re
import struct

from scrapy.utils.decorators import deprecated


# - Python>=3.5 GzipFile's read() has issues returning leftover
#   uncompressed data when input is corrupted
#   (regression or bug-fix compared to Python 3.4)
# - read1(), which fetches data before raising EOFError on next call
#   works here but is only available from Python>=3.3
@deprecated('GzipFile.read1')
def read1(gzf, size=-1):
    return gzf.read1(size)


def gunzip(data):
    """Gunzip the given data and return as much data as possible.

    This is resilient to CRC checksum errors.
    """
    f = GzipFile(fileobj=BytesIO(data))
    output_list = []
    chunk = b'.'
    while chunk:
        try:
            chunk = f.read1(8196)
            output_list.append(chunk)
        except (IOError, EOFError, struct.error):
            # complete only if there is some data, otherwise re-raise
            # see issue 87 about catching struct.error
            # some pages are quite small so output_list is empty and f.extrabuf
            # contains the whole page content
            if output_list or getattr(f, 'extrabuf', None):
                try:
                    output_list.append(f.extrabuf[-f.extrasize:])
                finally:
                    break
            else:
                raise
    return b''.join(output_list)


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
