import struct
from gzip import GzipFile
from io import BytesIO

from scrapy.utils.decorators import deprecated


# - GzipFile's read() has issues returning leftover uncompressed data when
#   input is corrupted
# - read1(), which fetches data before raising EOFError on next call
#   works here
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


def gzip_magic_number(response):
    return response.body[:3] == b'\x1f\x8b\x08'
