import struct
from cStringIO import StringIO
from gzip import GzipFile

def gunzip(data):
    """Gunzip the given data and return as much data as possible.

    This is resilient to CRC checksum errors.
    """
    f = GzipFile(fileobj=StringIO(data))
    output = ''
    chunk = '.'
    while chunk:
        try:
            chunk = f.read(8196)
            output += chunk
        except (IOError, EOFError, struct.error):
            # complete only if there is some data, otherwise re-raise
            # see issue 87 about catching struct.error
            # some pages are quite small so output is '' and f.extrabuf
            # contains the whole page content
            if output or f.extrabuf:
                output += f.extrabuf
                break
            else:
                raise
    return output

def is_gzipped(response):
    """Return True if the response is gzipped, or False otherwise"""
    ctype = response.headers.get('Content-Type', '')
    return ctype in ('application/x-gzip', 'application/gzip')
