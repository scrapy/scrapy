import struct

try:
    from cStringIO import StringIO as BytesIO
except ImportError:
    from io import BytesIO
from io import UnsupportedOperation
from gzip import GzipFile

class ReadOneGzipFile(GzipFile):
    def readone(self, size=-1):
        try:
            return self.read1(size)
        except UnsupportedOperation:
            return self.read(size)

def gunzip(data):
    """Gunzip the given data and return as much data as possible.

    This is resilient to CRC checksum errors.
    """
    f = ReadOneGzipFile(fileobj=BytesIO(data))
    output = b''
    chunk = b'.'
    while chunk:
        try:
            chunk = f.readone(8196)
            output += chunk
        except (IOError, EOFError, struct.error):
            # complete only if there is some data, otherwise re-raise
            # see issue 87 about catching struct.error
            # some pages are quite small so output is '' and f.extrabuf
            # contains the whole page content
            if output or getattr(f, 'extrabuf', None):
                try:
                    output += f.extrabuf
                finally:
                    break
            else:
                raise
    return output


def is_gzipped(response):
    """Return True if the response is gzipped, or False otherwise"""
    ctype = response.headers.get('Content-Type', b'')
    return ctype in (b'application/x-gzip', b'application/gzip')
