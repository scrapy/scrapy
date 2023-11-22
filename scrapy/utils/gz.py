import struct
from gzip import GzipFile
from io import BytesIO
from typing import List

from scrapy.http import Response

from ._compression import _DecompressionMaxSizeExceeded


def gunzip(data: bytes, max_size: int = 0) -> bytes:
    """Gunzip the given data and return as much data as possible.

    This is resilient to CRC checksum errors.
    """
    f = GzipFile(fileobj=BytesIO(data))
    output_list: List[bytes] = []
    chunk = b"."
    decompressed_size = 0
    while chunk:
        try:
            chunk = f.read1(8196)
        except (OSError, EOFError, struct.error):
            # complete only if there is some data, otherwise re-raise
            # see issue 87 about catching struct.error
            # some pages are quite small so output_list is empty
            if output_list:
                break
            raise
        decompressed_size += len(chunk)
        if max_size and decompressed_size > max_size:
            raise _DecompressionMaxSizeExceeded(
                f"The number of bytes decompressed so far "
                f"({decompressed_size}B) exceed the specified maximum "
                f"({max_size}B)."
            )
        output_list.append(chunk)
    return b"".join(output_list)


def gzip_magic_number(response: Response) -> bool:
    return response.body[:3] == b"\x1f\x8b\x08"
