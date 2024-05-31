import zlib
from io import BytesIO
from warnings import warn

from scrapy.exceptions import ScrapyDeprecationWarning

try:
    try:
        import brotli
    except ImportError:
        import brotlicffi as brotli
except ImportError:
    pass
else:
    try:
        brotli.Decompressor.process
    except AttributeError:
        warn(
            (
                "You have brotlipy installed, and Scrapy will use it, but "
                "Scrapy support for brotlipy is deprecated and will stop "
                "working in a future version of Scrapy. brotlipy itself is "
                "deprecated, it has been superseded by brotlicffi. Please, "
                "uninstall brotlipy and install brotli or brotlicffi instead. "
                "brotlipy has the same import name as brotli, so keeping both "
                "installed is strongly discouraged."
            ),
            ScrapyDeprecationWarning,
        )

        def _brotli_decompress(decompressor, data):
            return decompressor.decompress(data)

    else:

        def _brotli_decompress(decompressor, data):
            return decompressor.process(data)


try:
    import zstandard
except ImportError:
    pass


_CHUNK_SIZE = 65536  # 64 KiB


class _DecompressionMaxSizeExceeded(ValueError):
    pass


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
        if max_size and decompressed_size > max_size:
            raise _DecompressionMaxSizeExceeded(
                f"The number of bytes decompressed so far "
                f"({decompressed_size} B) exceed the specified maximum "
                f"({max_size} B)."
            )
        output_stream.write(output_chunk)
    output_stream.seek(0)
    return output_stream.read()


def _unbrotli(data: bytes, *, max_size: int = 0) -> bytes:
    decompressor = brotli.Decompressor()
    input_stream = BytesIO(data)
    output_stream = BytesIO()
    output_chunk = b"."
    decompressed_size = 0
    while output_chunk:
        input_chunk = input_stream.read(_CHUNK_SIZE)
        output_chunk = _brotli_decompress(decompressor, input_chunk)
        decompressed_size += len(output_chunk)
        if max_size and decompressed_size > max_size:
            raise _DecompressionMaxSizeExceeded(
                f"The number of bytes decompressed so far "
                f"({decompressed_size} B) exceed the specified maximum "
                f"({max_size} B)."
            )
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
        if max_size and decompressed_size > max_size:
            raise _DecompressionMaxSizeExceeded(
                f"The number of bytes decompressed so far "
                f"({decompressed_size} B) exceed the specified maximum "
                f"({max_size} B)."
            )
        output_stream.write(output_chunk)
    output_stream.seek(0)
    return output_stream.read()
