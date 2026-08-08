from __future__ import annotations

import struct
from gzip import GzipFile
from io import BytesIO
from typing import TYPE_CHECKING

from ._compression import _CHUNK_SIZE, _check_max_size

if TYPE_CHECKING:
    from scrapy.http import Response


def gunzip(data: bytes, *, max_size: int = 0) -> bytes:
    """Gunzip the given data and return as much data as possible.

    This is resilient to CRC checksum errors.
    """
    f = GzipFile(fileobj=BytesIO(data))
    output_stream = BytesIO()
    chunk = b"."
    decompressed_size = 0
    while chunk:
        try:
            chunk = f.read1(_CHUNK_SIZE)
        except (OSError, EOFError, struct.error):
            # complete only if there is some data, otherwise re-raise
            # see issue 87 about catching struct.error
            # some pages are quite small so output_stream is empty
            if output_stream.getbuffer().nbytes > 0:
                break
            raise
        decompressed_size += len(chunk)
        _check_max_size(decompressed_size, max_size)
        output_stream.write(chunk)
    return output_stream.getvalue()


def gzip_magic_number(response: Response) -> bool:
    return response.body[:3] == b"\x1f\x8b\x08"
