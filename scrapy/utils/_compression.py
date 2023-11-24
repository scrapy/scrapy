import zlib
from io import BytesIO

try:
    import brotli
except ImportError:
    pass

try:
    import zstandard
except ImportError:
    pass


_CHUNK_SIZE = 65536  # 64 KiB


class _DecompressionMaxSizeExceeded(ValueError):
    pass


def _inflate(data, max_size=0):
    decompressor = zlib.decompressobj()
    raw_decompressor = zlib.decompressobj(-15)
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
                "The number of bytes decompressed so far "
                "({decompressed_size} B) exceed the specified maximum "
                "({max_size} B).".format(
                    decompressed_size=decompressed_size,
                    max_size=max_size,
                )
            )
        output_stream.write(output_chunk)
    output_stream.seek(0)
    return output_stream.read()


def _unbrotli(data, max_size=0):
    decompressor = brotli.Decompressor()
    input_stream = BytesIO(data)
    output_stream = BytesIO()
    output_chunk = b"."
    decompressed_size = 0
    while output_chunk:
        input_chunk = input_stream.read(_CHUNK_SIZE)
        output_chunk = decompressor.decompress(input_chunk)
        decompressed_size += len(output_chunk)
        if max_size and decompressed_size > max_size:
            raise _DecompressionMaxSizeExceeded(
                "The number of bytes decompressed so far "
                "({decompressed_size} B) exceed the specified maximum "
                "({max_size} B).".format(
                    decompressed_size=decompressed_size,
                    max_size=max_size,
                )
            )
        output_stream.write(output_chunk)
    output_stream.seek(0)
    return output_stream.read()


def _unzstd(data, max_size=0):
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
                "The number of bytes decompressed so far "
                "({decompressed_size} B) exceed the specified maximum "
                "({max_size} B).".format(
                    decompressed_size=decompressed_size,
                    max_size=max_size,
                )
            )
        output_stream.write(output_chunk)
    output_stream.seek(0)
    return output_stream.read()
