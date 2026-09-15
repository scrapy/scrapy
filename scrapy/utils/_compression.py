from __future__ import annotations

import struct
import sys
import zlib
from gzip import GzipFile
from io import BytesIO
from typing import TYPE_CHECKING

try:
    import brotli
except ImportError:
    import brotlicffi as brotli

if sys.version_info >= (3, 14):
    from compression import zstd
else:
    from backports import zstd

if TYPE_CHECKING:
    from scrapy.http import Response


_CHUNK_SIZE = 65536  # 64 KiB


class _DecompressionMaxSizeExceeded(ValueError):
    def __init__(self, decompressed_size: int, max_size: int) -> None:
        self.decompressed_size = decompressed_size
        self.max_size = max_size

    def __str__(self) -> str:
        return (
            f"The number of bytes decompressed so far "
            f"({self.decompressed_size} B) exceeded the specified maximum "
            f"({self.max_size} B)."
        )


def _check_max_size(decompressed_size: int, max_size: int) -> None:
    if max_size and decompressed_size > max_size:
        raise _DecompressionMaxSizeExceeded(decompressed_size, max_size)


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


def _inflate(data: bytes, *, max_size: int = 0) -> bytes:
    decompressor = zlib.decompressobj()
    try:
        first_chunk = decompressor.decompress(data, max_length=_CHUNK_SIZE)
    except zlib.error:
        # to work with raw deflate content that may be sent by microsoft servers.
        decompressor = zlib.decompressobj(wbits=-15)
        first_chunk = decompressor.decompress(data, max_length=_CHUNK_SIZE)
    decompressed_size = len(first_chunk)
    _check_max_size(decompressed_size, max_size)
    output_stream = BytesIO()
    output_stream.write(first_chunk)
    # Anything left in unconsumed_tail once the stream has ended is not part of
    # it, and feeding it back would neither consume it nor produce output.
    while decompressor.unconsumed_tail and not decompressor.eof:
        output_chunk = decompressor.decompress(
            decompressor.unconsumed_tail, max_length=_CHUNK_SIZE
        )
        decompressed_size += len(output_chunk)
        _check_max_size(decompressed_size, max_size)
        output_stream.write(output_chunk)
    return output_stream.getvalue()


def _unbrotli(data: bytes, *, max_size: int = 0) -> bytes:
    decompressor = brotli.Decompressor()
    first_chunk = decompressor.process(data, output_buffer_limit=_CHUNK_SIZE)
    decompressed_size = len(first_chunk)
    _check_max_size(decompressed_size, max_size)
    output_stream = BytesIO()
    output_stream.write(first_chunk)
    while not decompressor.is_finished():
        output_chunk = decompressor.process(b"", output_buffer_limit=_CHUNK_SIZE)
        if not output_chunk:
            break
        decompressed_size += len(output_chunk)
        _check_max_size(decompressed_size, max_size)
        output_stream.write(output_chunk)
    return output_stream.getvalue()


def _unzstd(data: bytes, *, max_size: int = 0) -> bytes:
    stream_reader = zstd.ZstdFile(BytesIO(data))
    output_stream = BytesIO()
    output_chunk = b"."
    decompressed_size = 0
    while output_chunk:
        try:
            output_chunk = stream_reader.read(_CHUNK_SIZE)
        except EOFError:
            # Return as much data as possible out of a truncated response.
            break
        decompressed_size += len(output_chunk)
        _check_max_size(decompressed_size, max_size)
        output_stream.write(output_chunk)
    return output_stream.getvalue()
