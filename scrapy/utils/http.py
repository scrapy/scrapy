"""
Transitional module for moving to the w3lib library.

For new code, always import from w3lib.http instead of this module
"""

from w3lib.http import *

def decode_chunked_transfer(chunked_body):
    """Parsed body received with chunked transfer encoding, and return the
    decoded body.

    For more info see:
    http://en.wikipedia.org/wiki/Chunked_transfer_encoding

    """
    body_parts = []
    pos = 0
    while pos < len(chunked_body):
        separator_pos = chunked_body.find(b'\r\n', pos)
        if separator_pos == -1:
            separator_pos = len(chunked_body)

        chunk_size = chunked_body[pos:separator_pos]
        if chunk_size == b'0':
            break
        size = int(chunk_size, 16)
        pos = separator_pos + 2
        chunk_data = chunked_body[pos:pos+size]
        body_parts.append(chunk_data)
        pos += size + 2

    return b''.join(body_parts)
