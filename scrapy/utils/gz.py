import struct
from gzip import GzipFile
from io import BytesIO
from typing import List

from scrapy.http import Response


def gunzip(data: bytes) -> bytes:
    """Gunzip the given data and return as much data as possible.

    This is resilient to CRC checksum errors.
    """
    f = GzipFile(fileobj=BytesIO(data))
    output_list: List[bytes] = []
    chunk = b"."
    while chunk:
        try:
            chunk = f.read1(8196)
            output_list.append(chunk)
        except (OSError, EOFError, struct.error):
            # complete only if there is some data, otherwise re-raise
            # see issue 87 about catching struct.error
            # some pages are quite small so output_list is empty
            if output_list:
                break
            raise
    return b"".join(output_list)


def gzip_magic_number(response: Response) -> bool:
    return response.body[:3] == b"\x1f\x8b\x08"
