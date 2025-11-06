import contextlib
import zlib
from io import BytesIO

try:
    import brotli
except ImportError:
    pass

with contextlib.suppress(ImportError):
    import zstandard


_CHUNK_SIZE = 65536  # 64 KiB


class _DecompressionMaxSizeExceeded(ValueError):
    pass


def _check_max_size(decompressed_size: int, max_size: int) -> None:
    if max_size and decompressed_size > max_size:
        raise _DecompressionMaxSizeExceeded(
            f"The number of bytes decompressed so far "
            f"({decompressed_size} B) exceeds the specified maximum "
            f"({max_size} B)."
        )


def _inflate(data: bytes, *, max_size: int = 0) -> bytes:
    decompressor = zlib.decompressobj()
    raw_decompressor = zlib.decompressobj(wbits=-15)
    input_stream = BytesIO(data)
    output_stream = BytesIO()
    output_chunk = b"."
    decompressed_size = 0
    while output_chunk:
        input_chunk = input_stream.read(_CHUNK_SIZE)
        try:
            output_chunk = decompressor.decompress(input_chunk)
        except zlib.error:
            if decompressor != raw_decompressor:
                # ugly hack to work with raw deflate content that may
                # be sent by microsoft servers. For more information, see:
                # http://carsten.codimi.de/gzip.yaws/
                # http://www.port80software.com/200ok/archive/2005/10/31/868.aspx
                # http://www.gzip.org/zlib/zlib_faq.html#faq38
                decompressor = raw_decompressor
                output_chunk = decompressor.decompress(input_chunk)
            else:
                raise
        decompressed_size += len(output_chunk)
        _check_max_size(decompressed_size, max_size)
        output_stream.write(output_chunk)
    output_stream.seek(0)
    return output_stream.read()


def _unbrotli(data: bytes, *, max_size: int = 0) -> bytes:
    decompressor = brotli.Decompressor()
    output_stream = BytesIO()
    output_chunk = decompressor.process(data, output_buffer_limit=_CHUNK_SIZE)
    decompressed_size = len(output_chunk)
    _check_max_size(decompressed_size, max_size)
    output_stream.write(output_chunk)
    while not decompressor.is_finished():
        output_chunk = decompressor.process(b"", output_buffer_limit=_CHUNK_SIZE)
        decompressed_size += len(output_chunk)
        _check_max_size(decompressed_size, max_size)
        output_stream.write(output_chunk)
    output_stream.seek(0)
    return output_stream.read()


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
    output_stream.seek(0)
    return output_stream.read()
