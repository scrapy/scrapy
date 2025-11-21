import contextlib
import zlib
from io import BytesIO

with contextlib.suppress(ImportError):
    import brotli

with contextlib.suppress(ImportError):
    import zstandard


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
    while decompressor.unconsumed_tail:
        output_chunk = decompressor.decompress(
            decompressor.unconsumed_tail, max_length=_CHUNK_SIZE
        )
        decompressed_size += len(output_chunk)
        _check_max_size(decompressed_size, max_size)
        output_stream.write(output_chunk)
    if tail := decompressor.flush():
        decompressed_size += len(tail)
        _check_max_size(decompressed_size, max_size)
        output_stream.write(tail)
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
    decompressor = zstandard.ZstdDecompressor()
    stream_reader = decompressor.stream_reader(BytesIO(data))
    output_stream = BytesIO()
    output_chunk = b"."
    decompressed_size = 0
    while output_chunk:
        output_chunk = stream_reader.read(_CHUNK_SIZE)
        decompressed_size += len(output_chunk)
        _check_max_size(decompressed_size, max_size)
        output_stream.write(output_chunk)
    return output_stream.getvalue()
