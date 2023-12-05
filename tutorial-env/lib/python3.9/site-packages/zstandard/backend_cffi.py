# Copyright (c) 2016-present, Gregory Szorc
# All rights reserved.
#
# This software may be modified and distributed under the terms
# of the BSD license. See the LICENSE file for details.

"""Python interface to the Zstandard (zstd) compression library."""

from __future__ import absolute_import, unicode_literals

# This should match what the C extension exports.
__all__ = [
    "BufferSegment",
    "BufferSegments",
    "BufferWithSegments",
    "BufferWithSegmentsCollection",
    "ZstdCompressionChunker",
    "ZstdCompressionDict",
    "ZstdCompressionObj",
    "ZstdCompressionParameters",
    "ZstdCompressionReader",
    "ZstdCompressionWriter",
    "ZstdCompressor",
    "ZstdDecompressionObj",
    "ZstdDecompressionReader",
    "ZstdDecompressionWriter",
    "ZstdDecompressor",
    "ZstdError",
    "FrameParameters",
    "backend_features",
    "estimate_decompression_context_size",
    "frame_content_size",
    "frame_header_size",
    "get_frame_parameters",
    "train_dictionary",
    # Constants.
    "FLUSH_BLOCK",
    "FLUSH_FRAME",
    "COMPRESSOBJ_FLUSH_FINISH",
    "COMPRESSOBJ_FLUSH_BLOCK",
    "ZSTD_VERSION",
    "FRAME_HEADER",
    "CONTENTSIZE_UNKNOWN",
    "CONTENTSIZE_ERROR",
    "MAX_COMPRESSION_LEVEL",
    "COMPRESSION_RECOMMENDED_INPUT_SIZE",
    "COMPRESSION_RECOMMENDED_OUTPUT_SIZE",
    "DECOMPRESSION_RECOMMENDED_INPUT_SIZE",
    "DECOMPRESSION_RECOMMENDED_OUTPUT_SIZE",
    "MAGIC_NUMBER",
    "BLOCKSIZELOG_MAX",
    "BLOCKSIZE_MAX",
    "WINDOWLOG_MIN",
    "WINDOWLOG_MAX",
    "CHAINLOG_MIN",
    "CHAINLOG_MAX",
    "HASHLOG_MIN",
    "HASHLOG_MAX",
    "MINMATCH_MIN",
    "MINMATCH_MAX",
    "SEARCHLOG_MIN",
    "SEARCHLOG_MAX",
    "SEARCHLENGTH_MIN",
    "SEARCHLENGTH_MAX",
    "TARGETLENGTH_MIN",
    "TARGETLENGTH_MAX",
    "LDM_MINMATCH_MIN",
    "LDM_MINMATCH_MAX",
    "LDM_BUCKETSIZELOG_MAX",
    "STRATEGY_FAST",
    "STRATEGY_DFAST",
    "STRATEGY_GREEDY",
    "STRATEGY_LAZY",
    "STRATEGY_LAZY2",
    "STRATEGY_BTLAZY2",
    "STRATEGY_BTOPT",
    "STRATEGY_BTULTRA",
    "STRATEGY_BTULTRA2",
    "DICT_TYPE_AUTO",
    "DICT_TYPE_RAWCONTENT",
    "DICT_TYPE_FULLDICT",
    "FORMAT_ZSTD1",
    "FORMAT_ZSTD1_MAGICLESS",
]

import io
import os

from ._cffi import (  # type: ignore
    ffi,
    lib,
)


backend_features = set()  # type: ignore

COMPRESSION_RECOMMENDED_INPUT_SIZE = lib.ZSTD_CStreamInSize()
COMPRESSION_RECOMMENDED_OUTPUT_SIZE = lib.ZSTD_CStreamOutSize()
DECOMPRESSION_RECOMMENDED_INPUT_SIZE = lib.ZSTD_DStreamInSize()
DECOMPRESSION_RECOMMENDED_OUTPUT_SIZE = lib.ZSTD_DStreamOutSize()

new_nonzero = ffi.new_allocator(should_clear_after_alloc=False)


MAX_COMPRESSION_LEVEL = lib.ZSTD_maxCLevel()
MAGIC_NUMBER = lib.ZSTD_MAGICNUMBER
FRAME_HEADER = b"\x28\xb5\x2f\xfd"
CONTENTSIZE_UNKNOWN = lib.ZSTD_CONTENTSIZE_UNKNOWN
CONTENTSIZE_ERROR = lib.ZSTD_CONTENTSIZE_ERROR
ZSTD_VERSION = (
    lib.ZSTD_VERSION_MAJOR,
    lib.ZSTD_VERSION_MINOR,
    lib.ZSTD_VERSION_RELEASE,
)

BLOCKSIZELOG_MAX = lib.ZSTD_BLOCKSIZELOG_MAX
BLOCKSIZE_MAX = lib.ZSTD_BLOCKSIZE_MAX
WINDOWLOG_MIN = lib.ZSTD_WINDOWLOG_MIN
WINDOWLOG_MAX = lib.ZSTD_WINDOWLOG_MAX
CHAINLOG_MIN = lib.ZSTD_CHAINLOG_MIN
CHAINLOG_MAX = lib.ZSTD_CHAINLOG_MAX
HASHLOG_MIN = lib.ZSTD_HASHLOG_MIN
HASHLOG_MAX = lib.ZSTD_HASHLOG_MAX
MINMATCH_MIN = lib.ZSTD_MINMATCH_MIN
MINMATCH_MAX = lib.ZSTD_MINMATCH_MAX
SEARCHLOG_MIN = lib.ZSTD_SEARCHLOG_MIN
SEARCHLOG_MAX = lib.ZSTD_SEARCHLOG_MAX
SEARCHLENGTH_MIN = lib.ZSTD_MINMATCH_MIN
SEARCHLENGTH_MAX = lib.ZSTD_MINMATCH_MAX
TARGETLENGTH_MIN = lib.ZSTD_TARGETLENGTH_MIN
TARGETLENGTH_MAX = lib.ZSTD_TARGETLENGTH_MAX
LDM_MINMATCH_MIN = lib.ZSTD_LDM_MINMATCH_MIN
LDM_MINMATCH_MAX = lib.ZSTD_LDM_MINMATCH_MAX
LDM_BUCKETSIZELOG_MAX = lib.ZSTD_LDM_BUCKETSIZELOG_MAX

STRATEGY_FAST = lib.ZSTD_fast
STRATEGY_DFAST = lib.ZSTD_dfast
STRATEGY_GREEDY = lib.ZSTD_greedy
STRATEGY_LAZY = lib.ZSTD_lazy
STRATEGY_LAZY2 = lib.ZSTD_lazy2
STRATEGY_BTLAZY2 = lib.ZSTD_btlazy2
STRATEGY_BTOPT = lib.ZSTD_btopt
STRATEGY_BTULTRA = lib.ZSTD_btultra
STRATEGY_BTULTRA2 = lib.ZSTD_btultra2

DICT_TYPE_AUTO = lib.ZSTD_dct_auto
DICT_TYPE_RAWCONTENT = lib.ZSTD_dct_rawContent
DICT_TYPE_FULLDICT = lib.ZSTD_dct_fullDict

FORMAT_ZSTD1 = lib.ZSTD_f_zstd1
FORMAT_ZSTD1_MAGICLESS = lib.ZSTD_f_zstd1_magicless

FLUSH_BLOCK = 0
FLUSH_FRAME = 1

COMPRESSOBJ_FLUSH_FINISH = 0
COMPRESSOBJ_FLUSH_BLOCK = 1


def _cpu_count():
    # os.cpu_count() was introducd in Python 3.4.
    try:
        return os.cpu_count() or 0
    except AttributeError:
        pass

    # Linux.
    try:
        return os.sysconf("SC_NPROCESSORS_ONLN")
    except (AttributeError, ValueError):
        pass

    # TODO implement on other platforms.
    return 0


class BufferSegment:
    """Represents a segment within a ``BufferWithSegments``.

    This type is essentially a reference to N bytes within a
    ``BufferWithSegments``.

    The object conforms to the buffer protocol.
    """

    @property
    def offset(self):
        """The byte offset of this segment within its parent buffer."""
        raise NotImplementedError()

    def __len__(self):
        """Obtain the length of the segment, in bytes."""
        raise NotImplementedError()

    def tobytes(self):
        """Obtain bytes copy of this segment."""
        raise NotImplementedError()


class BufferSegments:
    """Represents an array of ``(offset, length)`` integers.

    This type is effectively an index used by :py:class:`BufferWithSegments`.

    The array members are 64-bit unsigned integers using host/native bit order.

    Instances conform to the buffer protocol.
    """


class BufferWithSegments:
    """A memory buffer containing N discrete items of known lengths.

    This type is essentially a fixed size memory address and an array
    of 2-tuples of ``(offset, length)`` 64-bit unsigned native-endian
    integers defining the byte offset and length of each segment within
    the buffer.

    Instances behave like containers.

    Instances also conform to the buffer protocol. So a reference to the
    backing bytes can be obtained via ``memoryview(o)``. A *copy* of the
    backing bytes can be obtained via ``.tobytes()``.

    This type exists to facilitate operations against N>1 items without
    the overhead of Python object creation and management. Used with
    APIs like :py:meth:`ZstdDecompressor.multi_decompress_to_buffer`, it
    is possible to decompress many objects in parallel without the GIL
    held, leading to even better performance.
    """

    @property
    def size(self):
        """Total sizein bytes of the backing buffer."""
        raise NotImplementedError()

    def __len__(self):
        raise NotImplementedError()

    def __getitem__(self, i):
        """Obtains a segment within the buffer.

        The returned object references memory within this buffer.

        :param i:
           Integer index of segment to retrieve.
        :return:
           :py:class:`BufferSegment`
        """
        raise NotImplementedError()

    def segments(self):
        """Obtain the array of ``(offset, length)`` segments in the buffer.

        :return:
           :py:class:`BufferSegments`
        """
        raise NotImplementedError()

    def tobytes(self):
        """Obtain bytes copy of this instance."""
        raise NotImplementedError()


class BufferWithSegmentsCollection:
    """A virtual spanning view over multiple BufferWithSegments.

    Instances are constructed from 1 or more :py:class:`BufferWithSegments`
    instances. The resulting object behaves like an ordered sequence whose
    members are the segments within each ``BufferWithSegments``.

    If the object is composed of 2 ``BufferWithSegments`` instances with the
    first having 2 segments and the second have 3 segments, then ``b[0]``
    and ``b[1]`` access segments in the first object and ``b[2]``, ``b[3]``,
    and ``b[4]`` access segments from the second.
    """

    def __len__(self):
        """The number of segments within all ``BufferWithSegments``."""
        raise NotImplementedError()

    def __getitem__(self, i):
        """Obtain the ``BufferSegment`` at an offset."""
        raise NotImplementedError()


class ZstdError(Exception):
    pass


def _zstd_error(zresult):
    # Resolves to bytes on Python 2 and 3. We use the string for formatting
    # into error messages, which will be literal unicode. So convert it to
    # unicode.
    return ffi.string(lib.ZSTD_getErrorName(zresult)).decode("utf-8")


def _make_cctx_params(params):
    res = lib.ZSTD_createCCtxParams()
    if res == ffi.NULL:
        raise MemoryError()

    res = ffi.gc(res, lib.ZSTD_freeCCtxParams)

    attrs = [
        (lib.ZSTD_c_format, params.format),
        (lib.ZSTD_c_compressionLevel, params.compression_level),
        (lib.ZSTD_c_windowLog, params.window_log),
        (lib.ZSTD_c_hashLog, params.hash_log),
        (lib.ZSTD_c_chainLog, params.chain_log),
        (lib.ZSTD_c_searchLog, params.search_log),
        (lib.ZSTD_c_minMatch, params.min_match),
        (lib.ZSTD_c_targetLength, params.target_length),
        (lib.ZSTD_c_strategy, params.strategy),
        (lib.ZSTD_c_contentSizeFlag, params.write_content_size),
        (lib.ZSTD_c_checksumFlag, params.write_checksum),
        (lib.ZSTD_c_dictIDFlag, params.write_dict_id),
        (lib.ZSTD_c_nbWorkers, params.threads),
        (lib.ZSTD_c_jobSize, params.job_size),
        (lib.ZSTD_c_overlapLog, params.overlap_log),
        (lib.ZSTD_c_forceMaxWindow, params.force_max_window),
        (lib.ZSTD_c_enableLongDistanceMatching, params.enable_ldm),
        (lib.ZSTD_c_ldmHashLog, params.ldm_hash_log),
        (lib.ZSTD_c_ldmMinMatch, params.ldm_min_match),
        (lib.ZSTD_c_ldmBucketSizeLog, params.ldm_bucket_size_log),
        (lib.ZSTD_c_ldmHashRateLog, params.ldm_hash_rate_log),
    ]

    for param, value in attrs:
        _set_compression_parameter(res, param, value)

    return res


class ZstdCompressionParameters(object):
    """Low-level zstd compression parameters.

    This type represents a collection of parameters to control how zstd
    compression is performed.

    Instances can be constructed from raw parameters or derived from a
    base set of defaults specified from a compression level (recommended)
    via :py:meth:`ZstdCompressionParameters.from_level`.

    >>> # Derive compression settings for compression level 7.
    >>> params = zstandard.ZstdCompressionParameters.from_level(7)

    >>> # With an input size of 1MB
    >>> params = zstandard.ZstdCompressionParameters.from_level(7, source_size=1048576)

    Using ``from_level()``, it is also possible to override individual compression
    parameters or to define additional settings that aren't automatically derived.
    e.g.:

    >>> params = zstandard.ZstdCompressionParameters.from_level(4, window_log=10)
    >>> params = zstandard.ZstdCompressionParameters.from_level(5, threads=4)

    Or you can define low-level compression settings directly:

    >>> params = zstandard.ZstdCompressionParameters(window_log=12, enable_ldm=True)

    Once a ``ZstdCompressionParameters`` instance is obtained, it can be used to
    configure a compressor:

    >>> cctx = zstandard.ZstdCompressor(compression_params=params)

    Some of these are very low-level settings. It may help to consult the official
    zstandard documentation for their behavior. Look for the ``ZSTD_p_*`` constants
    in ``zstd.h`` (https://github.com/facebook/zstd/blob/dev/lib/zstd.h).
    """

    @staticmethod
    def from_level(level, source_size=0, dict_size=0, **kwargs):
        """Create compression parameters from a compression level.

        :param level:
           Integer compression level.
        :param source_size:
           Integer size in bytes of source to be compressed.
        :param dict_size:
           Integer size in bytes of compression dictionary to use.
        :return:
           :py:class:`ZstdCompressionParameters`
        """
        params = lib.ZSTD_getCParams(level, source_size, dict_size)

        args = {
            "window_log": "windowLog",
            "chain_log": "chainLog",
            "hash_log": "hashLog",
            "search_log": "searchLog",
            "min_match": "minMatch",
            "target_length": "targetLength",
            "strategy": "strategy",
        }

        for arg, attr in args.items():
            if arg not in kwargs:
                kwargs[arg] = getattr(params, attr)

        return ZstdCompressionParameters(**kwargs)

    def __init__(
        self,
        format=0,
        compression_level=0,
        window_log=0,
        hash_log=0,
        chain_log=0,
        search_log=0,
        min_match=0,
        target_length=0,
        strategy=-1,
        write_content_size=1,
        write_checksum=0,
        write_dict_id=0,
        job_size=0,
        overlap_log=-1,
        force_max_window=0,
        enable_ldm=0,
        ldm_hash_log=0,
        ldm_min_match=0,
        ldm_bucket_size_log=0,
        ldm_hash_rate_log=-1,
        threads=0,
    ):
        params = lib.ZSTD_createCCtxParams()
        if params == ffi.NULL:
            raise MemoryError()

        params = ffi.gc(params, lib.ZSTD_freeCCtxParams)

        self._params = params

        if threads < 0:
            threads = _cpu_count()

        # We need to set ZSTD_c_nbWorkers before ZSTD_c_jobSize and ZSTD_c_overlapLog
        # because setting ZSTD_c_nbWorkers resets the other parameters.
        _set_compression_parameter(params, lib.ZSTD_c_nbWorkers, threads)

        _set_compression_parameter(params, lib.ZSTD_c_format, format)
        _set_compression_parameter(
            params, lib.ZSTD_c_compressionLevel, compression_level
        )
        _set_compression_parameter(params, lib.ZSTD_c_windowLog, window_log)
        _set_compression_parameter(params, lib.ZSTD_c_hashLog, hash_log)
        _set_compression_parameter(params, lib.ZSTD_c_chainLog, chain_log)
        _set_compression_parameter(params, lib.ZSTD_c_searchLog, search_log)
        _set_compression_parameter(params, lib.ZSTD_c_minMatch, min_match)
        _set_compression_parameter(
            params, lib.ZSTD_c_targetLength, target_length
        )

        if strategy == -1:
            strategy = 0

        _set_compression_parameter(params, lib.ZSTD_c_strategy, strategy)
        _set_compression_parameter(
            params, lib.ZSTD_c_contentSizeFlag, write_content_size
        )
        _set_compression_parameter(
            params, lib.ZSTD_c_checksumFlag, write_checksum
        )
        _set_compression_parameter(params, lib.ZSTD_c_dictIDFlag, write_dict_id)
        _set_compression_parameter(params, lib.ZSTD_c_jobSize, job_size)

        if overlap_log == -1:
            overlap_log = 0

        _set_compression_parameter(params, lib.ZSTD_c_overlapLog, overlap_log)
        _set_compression_parameter(
            params, lib.ZSTD_c_forceMaxWindow, force_max_window
        )
        _set_compression_parameter(
            params, lib.ZSTD_c_enableLongDistanceMatching, enable_ldm
        )
        _set_compression_parameter(params, lib.ZSTD_c_ldmHashLog, ldm_hash_log)
        _set_compression_parameter(
            params, lib.ZSTD_c_ldmMinMatch, ldm_min_match
        )
        _set_compression_parameter(
            params, lib.ZSTD_c_ldmBucketSizeLog, ldm_bucket_size_log
        )

        if ldm_hash_rate_log == -1:
            ldm_hash_rate_log = 0

        _set_compression_parameter(
            params, lib.ZSTD_c_ldmHashRateLog, ldm_hash_rate_log
        )

    @property
    def format(self):
        return _get_compression_parameter(self._params, lib.ZSTD_c_format)

    @property
    def compression_level(self):
        return _get_compression_parameter(
            self._params, lib.ZSTD_c_compressionLevel
        )

    @property
    def window_log(self):
        return _get_compression_parameter(self._params, lib.ZSTD_c_windowLog)

    @property
    def hash_log(self):
        return _get_compression_parameter(self._params, lib.ZSTD_c_hashLog)

    @property
    def chain_log(self):
        return _get_compression_parameter(self._params, lib.ZSTD_c_chainLog)

    @property
    def search_log(self):
        return _get_compression_parameter(self._params, lib.ZSTD_c_searchLog)

    @property
    def min_match(self):
        return _get_compression_parameter(self._params, lib.ZSTD_c_minMatch)

    @property
    def target_length(self):
        return _get_compression_parameter(self._params, lib.ZSTD_c_targetLength)

    @property
    def strategy(self):
        return _get_compression_parameter(self._params, lib.ZSTD_c_strategy)

    @property
    def write_content_size(self):
        return _get_compression_parameter(
            self._params, lib.ZSTD_c_contentSizeFlag
        )

    @property
    def write_checksum(self):
        return _get_compression_parameter(self._params, lib.ZSTD_c_checksumFlag)

    @property
    def write_dict_id(self):
        return _get_compression_parameter(self._params, lib.ZSTD_c_dictIDFlag)

    @property
    def job_size(self):
        return _get_compression_parameter(self._params, lib.ZSTD_c_jobSize)

    @property
    def overlap_log(self):
        return _get_compression_parameter(self._params, lib.ZSTD_c_overlapLog)

    @property
    def force_max_window(self):
        return _get_compression_parameter(
            self._params, lib.ZSTD_c_forceMaxWindow
        )

    @property
    def enable_ldm(self):
        return _get_compression_parameter(
            self._params, lib.ZSTD_c_enableLongDistanceMatching
        )

    @property
    def ldm_hash_log(self):
        return _get_compression_parameter(self._params, lib.ZSTD_c_ldmHashLog)

    @property
    def ldm_min_match(self):
        return _get_compression_parameter(self._params, lib.ZSTD_c_ldmMinMatch)

    @property
    def ldm_bucket_size_log(self):
        return _get_compression_parameter(
            self._params, lib.ZSTD_c_ldmBucketSizeLog
        )

    @property
    def ldm_hash_rate_log(self):
        return _get_compression_parameter(
            self._params, lib.ZSTD_c_ldmHashRateLog
        )

    @property
    def threads(self):
        return _get_compression_parameter(self._params, lib.ZSTD_c_nbWorkers)

    def estimated_compression_context_size(self):
        """Estimated size in bytes needed to compress with these parameters."""
        return lib.ZSTD_estimateCCtxSize_usingCCtxParams(self._params)


def estimate_decompression_context_size():
    """Estimate the memory size requirements for a decompressor instance.

    :return:
       Integer number of bytes.
    """
    return lib.ZSTD_estimateDCtxSize()


def _set_compression_parameter(params, param, value):
    zresult = lib.ZSTD_CCtxParams_setParameter(params, param, value)
    if lib.ZSTD_isError(zresult):
        raise ZstdError(
            "unable to set compression context parameter: %s"
            % _zstd_error(zresult)
        )


def _get_compression_parameter(params, param):
    result = ffi.new("int *")

    zresult = lib.ZSTD_CCtxParams_getParameter(params, param, result)
    if lib.ZSTD_isError(zresult):
        raise ZstdError(
            "unable to get compression context parameter: %s"
            % _zstd_error(zresult)
        )

    return result[0]


class ZstdCompressionWriter(object):
    """Writable compressing stream wrapper.

    ``ZstdCompressionWriter`` is a write-only stream interface for writing
    compressed data to another stream.

    This type conforms to the ``io.RawIOBase`` interface and should be usable
    by any type that operates against a *file-object* (``typing.BinaryIO``
    in Python type hinting speak). Only methods that involve writing will do
    useful things.

    As data is written to this stream (e.g. via ``write()``), that data
    is sent to the compressor. As compressed data becomes available from
    the compressor, it is sent to the underlying stream by calling its
    ``write()`` method.

    Both ``write()`` and ``flush()`` return the number of bytes written to the
    object's ``write()``. In many cases, small inputs do not accumulate enough
    data to cause a write and ``write()`` will return ``0``.

    Calling ``close()`` will mark the stream as closed and subsequent I/O
    operations will raise ``ValueError`` (per the documented behavior of
    ``io.RawIOBase``). ``close()`` will also call ``close()`` on the underlying
    stream if such a method exists and the instance was constructed with
    ``closefd=True``

    Instances are obtained by calling :py:meth:`ZstdCompressor.stream_writer`.

    Typically usage is as follows:

    >>> cctx = zstandard.ZstdCompressor(level=10)
    >>> compressor = cctx.stream_writer(fh)
    >>> compressor.write(b"chunk 0\\n")
    >>> compressor.write(b"chunk 1\\n")
    >>> compressor.flush()
    >>> # Receiver will be able to decode ``chunk 0\\nchunk 1\\n`` at this point.
    >>> # Receiver is also expecting more data in the zstd *frame*.
    >>>
    >>> compressor.write(b"chunk 2\\n")
    >>> compressor.flush(zstandard.FLUSH_FRAME)
    >>> # Receiver will be able to decode ``chunk 0\\nchunk 1\\nchunk 2``.
    >>> # Receiver is expecting no more data, as the zstd frame is closed.
    >>> # Any future calls to ``write()`` at this point will construct a new
    >>> # zstd frame.

    Instances can be used as context managers. Exiting the context manager is
    the equivalent of calling ``close()``, which is equivalent to calling
    ``flush(zstandard.FLUSH_FRAME)``:

    >>> cctx = zstandard.ZstdCompressor(level=10)
    >>> with cctx.stream_writer(fh) as compressor:
    ...     compressor.write(b'chunk 0')
    ...     compressor.write(b'chunk 1')
    ...     ...

    .. important::

       If ``flush(FLUSH_FRAME)`` is not called, emitted data doesn't
       constitute a full zstd *frame* and consumers of this data may complain
       about malformed input. It is recommended to use instances as a context
       manager to ensure *frames* are properly finished.

    If the size of the data being fed to this streaming compressor is known,
    you can declare it before compression begins:

    >>> cctx = zstandard.ZstdCompressor()
    >>> with cctx.stream_writer(fh, size=data_len) as compressor:
    ...     compressor.write(chunk0)
    ...     compressor.write(chunk1)
    ...     ...

    Declaring the size of the source data allows compression parameters to
    be tuned. And if ``write_content_size`` is used, it also results in the
    content size being written into the frame header of the output data.

    The size of chunks being ``write()`` to the destination can be specified:

    >>> cctx = zstandard.ZstdCompressor()
    >>> with cctx.stream_writer(fh, write_size=32768) as compressor:
    ...     ...

    To see how much memory is being used by the streaming compressor:

    >>> cctx = zstandard.ZstdCompressor()
    >>> with cctx.stream_writer(fh) as compressor:
    ...     ...
    ...     byte_size = compressor.memory_size()

    Thte total number of bytes written so far are exposed via ``tell()``:

    >>> cctx = zstandard.ZstdCompressor()
    >>> with cctx.stream_writer(fh) as compressor:
    ...     ...
    ...     total_written = compressor.tell()

    ``stream_writer()`` accepts a ``write_return_read`` boolean argument to
    control the return value of ``write()``. When ``False`` (the default),
    ``write()`` returns the number of bytes that were ``write()``'en to the
    underlying object. When ``True``, ``write()`` returns the number of bytes
    read from the input that were subsequently written to the compressor.
    ``True`` is the *proper* behavior for ``write()`` as specified by the
    ``io.RawIOBase`` interface and will become the default value in a future
    release.
    """

    def __init__(
        self,
        compressor,
        writer,
        source_size,
        write_size,
        write_return_read,
        closefd=True,
    ):
        self._compressor = compressor
        self._writer = writer
        self._write_size = write_size
        self._write_return_read = bool(write_return_read)
        self._closefd = bool(closefd)
        self._entered = False
        self._closing = False
        self._closed = False
        self._bytes_compressed = 0

        self._dst_buffer = ffi.new("char[]", write_size)
        self._out_buffer = ffi.new("ZSTD_outBuffer *")
        self._out_buffer.dst = self._dst_buffer
        self._out_buffer.size = len(self._dst_buffer)
        self._out_buffer.pos = 0

        zresult = lib.ZSTD_CCtx_setPledgedSrcSize(compressor._cctx, source_size)
        if lib.ZSTD_isError(zresult):
            raise ZstdError(
                "error setting source size: %s" % _zstd_error(zresult)
            )

    def __enter__(self):
        if self._closed:
            raise ValueError("stream is closed")

        if self._entered:
            raise ZstdError("cannot __enter__ multiple times")

        self._entered = True
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self._entered = False
        self.close()
        self._compressor = None

        return False

    def __iter__(self):
        raise io.UnsupportedOperation()

    def __next__(self):
        raise io.UnsupportedOperation()

    def memory_size(self):
        return lib.ZSTD_sizeof_CCtx(self._compressor._cctx)

    def fileno(self):
        f = getattr(self._writer, "fileno", None)
        if f:
            return f()
        else:
            raise OSError("fileno not available on underlying writer")

    def close(self):
        if self._closed:
            return

        try:
            self._closing = True
            self.flush(FLUSH_FRAME)
        finally:
            self._closing = False
            self._closed = True

        # Call close() on underlying stream as well.
        f = getattr(self._writer, "close", None)
        if self._closefd and f:
            f()

    @property
    def closed(self):
        return self._closed

    def isatty(self):
        return False

    def readable(self):
        return False

    def readline(self, size=-1):
        raise io.UnsupportedOperation()

    def readlines(self, hint=-1):
        raise io.UnsupportedOperation()

    def seek(self, offset, whence=None):
        raise io.UnsupportedOperation()

    def seekable(self):
        return False

    def truncate(self, size=None):
        raise io.UnsupportedOperation()

    def writable(self):
        return True

    def writelines(self, lines):
        raise NotImplementedError("writelines() is not yet implemented")

    def read(self, size=-1):
        raise io.UnsupportedOperation()

    def readall(self):
        raise io.UnsupportedOperation()

    def readinto(self, b):
        raise io.UnsupportedOperation()

    def write(self, data):
        """Send data to the compressor and possibly to the inner stream."""
        if self._closed:
            raise ValueError("stream is closed")

        total_write = 0

        data_buffer = ffi.from_buffer(data)

        in_buffer = ffi.new("ZSTD_inBuffer *")
        in_buffer.src = data_buffer
        in_buffer.size = len(data_buffer)
        in_buffer.pos = 0

        out_buffer = self._out_buffer
        out_buffer.pos = 0

        while in_buffer.pos < in_buffer.size:
            zresult = lib.ZSTD_compressStream2(
                self._compressor._cctx,
                out_buffer,
                in_buffer,
                lib.ZSTD_e_continue,
            )
            if lib.ZSTD_isError(zresult):
                raise ZstdError(
                    "zstd compress error: %s" % _zstd_error(zresult)
                )

            if out_buffer.pos:
                self._writer.write(
                    ffi.buffer(out_buffer.dst, out_buffer.pos)[:]
                )
                total_write += out_buffer.pos
                self._bytes_compressed += out_buffer.pos
                out_buffer.pos = 0

        if self._write_return_read:
            return in_buffer.pos
        else:
            return total_write

    def flush(self, flush_mode=FLUSH_BLOCK):
        """Evict data from compressor's internal state and write it to inner stream.

        Calling this method may result in 0 or more ``write()`` calls to the
        inner stream.

        This method will also call ``flush()`` on the inner stream, if such a
        method exists.

        :param flush_mode:
           How to flush the zstd compressor.

           ``zstandard.FLUSH_BLOCK`` will flush data already sent to the
           compressor but not emitted to the inner stream. The stream is still
           writable after calling this. This is the default behavior.

           See documentation for other ``zstandard.FLUSH_*`` constants for more
           flushing options.
        :return:
           Integer number of bytes written to the inner stream.
        """

        if flush_mode == FLUSH_BLOCK:
            flush = lib.ZSTD_e_flush
        elif flush_mode == FLUSH_FRAME:
            flush = lib.ZSTD_e_end
        else:
            raise ValueError("unknown flush_mode: %r" % flush_mode)

        if self._closed:
            raise ValueError("stream is closed")

        total_write = 0

        out_buffer = self._out_buffer
        out_buffer.pos = 0

        in_buffer = ffi.new("ZSTD_inBuffer *")
        in_buffer.src = ffi.NULL
        in_buffer.size = 0
        in_buffer.pos = 0

        while True:
            zresult = lib.ZSTD_compressStream2(
                self._compressor._cctx, out_buffer, in_buffer, flush
            )
            if lib.ZSTD_isError(zresult):
                raise ZstdError(
                    "zstd compress error: %s" % _zstd_error(zresult)
                )

            if out_buffer.pos:
                self._writer.write(
                    ffi.buffer(out_buffer.dst, out_buffer.pos)[:]
                )
                total_write += out_buffer.pos
                self._bytes_compressed += out_buffer.pos
                out_buffer.pos = 0

            if not zresult:
                break

        f = getattr(self._writer, "flush", None)
        if f and not self._closing:
            f()

        return total_write

    def tell(self):
        return self._bytes_compressed


class ZstdCompressionObj(object):
    """A compressor conforming to the API in Python's standard library.

    This type implements an API similar to compression types in Python's
    standard library such as ``zlib.compressobj`` and ``bz2.BZ2Compressor``.
    This enables existing code targeting the standard library API to swap
    in this type to achieve zstd compression.

    .. important::

       The design of this API is not ideal for optimal performance.

       The reason performance is not optimal is because the API is limited to
       returning a single buffer holding compressed data. When compressing
       data, we don't know how much data will be emitted. So in order to
       capture all this data in a single buffer, we need to perform buffer
       reallocations and/or extra memory copies. This can add significant
       overhead depending on the size or nature of the compressed data how
       much your application calls this type.

       If performance is critical, consider an API like
       :py:meth:`ZstdCompressor.stream_reader`,
       :py:meth:`ZstdCompressor.stream_writer`,
       :py:meth:`ZstdCompressor.chunker`, or
       :py:meth:`ZstdCompressor.read_to_iter`, which result in less overhead
       managing buffers.

    Instances are obtained by calling :py:meth:`ZstdCompressor.compressobj`.

    Here is how this API should be used:

    >>> cctx = zstandard.ZstdCompressor()
    >>> cobj = cctx.compressobj()
    >>> data = cobj.compress(b"raw input 0")
    >>> data = cobj.compress(b"raw input 1")
    >>> data = cobj.flush()

    Or to flush blocks:

    >>> cctx.zstandard.ZstdCompressor()
    >>> cobj = cctx.compressobj()
    >>> data = cobj.compress(b"chunk in first block")
    >>> data = cobj.flush(zstandard.COMPRESSOBJ_FLUSH_BLOCK)
    >>> data = cobj.compress(b"chunk in second block")
    >>> data = cobj.flush()

    For best performance results, keep input chunks under 256KB. This avoids
    extra allocations for a large output object.

    It is possible to declare the input size of the data that will be fed
    into the compressor:

    >>> cctx = zstandard.ZstdCompressor()
    >>> cobj = cctx.compressobj(size=6)
    >>> data = cobj.compress(b"foobar")
    >>> data = cobj.flush()
    """

    def compress(self, data):
        """Send data to the compressor.

        This method receives bytes to feed to the compressor and returns
        bytes constituting zstd compressed data.

        The zstd compressor accumulates bytes and the returned bytes may be
        substantially smaller or larger than the size of the input data on
        any given call. The returned value may be the empty byte string
        (``b""``).

        :param data:
           Data to write to the compressor.
        :return:
           Compressed data.
        """
        if self._finished:
            raise ZstdError("cannot call compress() after compressor finished")

        data_buffer = ffi.from_buffer(data)
        source = ffi.new("ZSTD_inBuffer *")
        source.src = data_buffer
        source.size = len(data_buffer)
        source.pos = 0

        chunks = []

        while source.pos < len(data):
            zresult = lib.ZSTD_compressStream2(
                self._compressor._cctx, self._out, source, lib.ZSTD_e_continue
            )
            if lib.ZSTD_isError(zresult):
                raise ZstdError(
                    "zstd compress error: %s" % _zstd_error(zresult)
                )

            if self._out.pos:
                chunks.append(ffi.buffer(self._out.dst, self._out.pos)[:])
                self._out.pos = 0

        return b"".join(chunks)

    def flush(self, flush_mode=COMPRESSOBJ_FLUSH_FINISH):
        """Emit data accumulated in the compressor that hasn't been outputted yet.

        The ``flush_mode`` argument controls how to end the stream.

        ``zstandard.COMPRESSOBJ_FLUSH_FINISH`` (the default) ends the
        compression stream and finishes a zstd frame. Once this type of flush
        is performed, ``compress()`` and ``flush()`` can no longer be called.
        This type of flush **must** be called to end the compression context. If
        not called, the emitted data may be incomplete and may not be readable
        by a decompressor.

        ``zstandard.COMPRESSOBJ_FLUSH_BLOCK`` will flush a zstd block. This
        ensures that all data fed to this instance will have been omitted and
        can be decoded by a decompressor. Flushes of this type can be performed
        multiple times. The next call to ``compress()`` will begin a new zstd
        block.

        :param flush_mode:
           How to flush the zstd compressor.
        :return:
           Compressed data.
        """
        if flush_mode not in (
            COMPRESSOBJ_FLUSH_FINISH,
            COMPRESSOBJ_FLUSH_BLOCK,
        ):
            raise ValueError("flush mode not recognized")

        if self._finished:
            raise ZstdError("compressor object already finished")

        if flush_mode == COMPRESSOBJ_FLUSH_BLOCK:
            z_flush_mode = lib.ZSTD_e_flush
        elif flush_mode == COMPRESSOBJ_FLUSH_FINISH:
            z_flush_mode = lib.ZSTD_e_end
            self._finished = True
        else:
            raise ZstdError("unhandled flush mode")

        assert self._out.pos == 0

        in_buffer = ffi.new("ZSTD_inBuffer *")
        in_buffer.src = ffi.NULL
        in_buffer.size = 0
        in_buffer.pos = 0

        chunks = []

        while True:
            zresult = lib.ZSTD_compressStream2(
                self._compressor._cctx, self._out, in_buffer, z_flush_mode
            )
            if lib.ZSTD_isError(zresult):
                raise ZstdError(
                    "error ending compression stream: %s" % _zstd_error(zresult)
                )

            if self._out.pos:
                chunks.append(ffi.buffer(self._out.dst, self._out.pos)[:])
                self._out.pos = 0

            if not zresult:
                break

        return b"".join(chunks)


class ZstdCompressionChunker(object):
    """Compress data to uniformly sized chunks.

    This type allows you to iteratively feed chunks of data into a compressor
    and produce output chunks of uniform size.

    ``compress()``, ``flush()``, and ``finish()`` all return an iterator of
    ``bytes`` instances holding compressed data. The iterator may be empty.
    Callers MUST iterate through all elements of the returned iterator before
    performing another operation on the object or else the compressor's
    internal state may become confused. This can result in an exception being
    raised or malformed data being emitted.

    All chunks emitted by ``compress()`` will have a length of the configured
    chunk size.

    ``flush()`` and ``finish()`` may return a final chunk smaller than
    the configured chunk size.

    Instances are obtained by calling :py:meth:`ZstdCompressor.chunker`.

    Here is how the API should be used:

    >>> cctx = zstandard.ZstdCompressor()
    >>> chunker = cctx.chunker(chunk_size=32768)
    >>>
    >>> with open(path, 'rb') as fh:
    ...     while True:
    ...         in_chunk = fh.read(32768)
    ...         if not in_chunk:
    ...             break
    ...
    ...         for out_chunk in chunker.compress(in_chunk):
    ...             # Do something with output chunk of size 32768.
    ...
    ...     for out_chunk in chunker.finish():
    ...         # Do something with output chunks that finalize the zstd frame.

    This compressor type is often a better alternative to
    :py:class:`ZstdCompressor.compressobj` because it has better performance
    properties.

    ``compressobj()`` will emit output data as it is available. This results
    in a *stream* of output chunks of varying sizes. The consistency of the
    output chunk size with ``chunker()`` is more appropriate for many usages,
    such as sending compressed data to a socket.

    ``compressobj()`` may also perform extra memory reallocations in order
    to dynamically adjust the sizes of the output chunks. Since ``chunker()``
    output chunks are all the same size (except for flushed or final chunks),
    there is less memory allocation/copying overhead.
    """

    def __init__(self, compressor, chunk_size):
        self._compressor = compressor
        self._out = ffi.new("ZSTD_outBuffer *")
        self._dst_buffer = ffi.new("char[]", chunk_size)
        self._out.dst = self._dst_buffer
        self._out.size = chunk_size
        self._out.pos = 0

        self._in = ffi.new("ZSTD_inBuffer *")
        self._in.src = ffi.NULL
        self._in.size = 0
        self._in.pos = 0
        self._finished = False

    def compress(self, data):
        """Feed new input data into the compressor.

        :param data:
           Data to feed to compressor.
        :return:
           Iterator of ``bytes`` representing chunks of compressed data.
        """
        if self._finished:
            raise ZstdError("cannot call compress() after compression finished")

        if self._in.src != ffi.NULL:
            raise ZstdError(
                "cannot perform operation before consuming output "
                "from previous operation"
            )

        data_buffer = ffi.from_buffer(data)

        if not len(data_buffer):
            return

        self._in.src = data_buffer
        self._in.size = len(data_buffer)
        self._in.pos = 0

        while self._in.pos < self._in.size:
            zresult = lib.ZSTD_compressStream2(
                self._compressor._cctx, self._out, self._in, lib.ZSTD_e_continue
            )

            if self._in.pos == self._in.size:
                self._in.src = ffi.NULL
                self._in.size = 0
                self._in.pos = 0

            if lib.ZSTD_isError(zresult):
                raise ZstdError(
                    "zstd compress error: %s" % _zstd_error(zresult)
                )

            if self._out.pos == self._out.size:
                yield ffi.buffer(self._out.dst, self._out.pos)[:]
                self._out.pos = 0

    def flush(self):
        """Flushes all data currently in the compressor.

        :return:
           Iterator of ``bytes`` of compressed data.
        """
        if self._finished:
            raise ZstdError("cannot call flush() after compression finished")

        if self._in.src != ffi.NULL:
            raise ZstdError(
                "cannot call flush() before consuming output from "
                "previous operation"
            )

        while True:
            zresult = lib.ZSTD_compressStream2(
                self._compressor._cctx, self._out, self._in, lib.ZSTD_e_flush
            )
            if lib.ZSTD_isError(zresult):
                raise ZstdError(
                    "zstd compress error: %s" % _zstd_error(zresult)
                )

            if self._out.pos:
                yield ffi.buffer(self._out.dst, self._out.pos)[:]
                self._out.pos = 0

            if not zresult:
                return

    def finish(self):
        """Signals the end of input data.

        No new data can be compressed after this method is called.

        This method will flush buffered data and finish the zstd frame.

        :return:
           Iterator of ``bytes`` of compressed data.
        """
        if self._finished:
            raise ZstdError("cannot call finish() after compression finished")

        if self._in.src != ffi.NULL:
            raise ZstdError(
                "cannot call finish() before consuming output from "
                "previous operation"
            )

        while True:
            zresult = lib.ZSTD_compressStream2(
                self._compressor._cctx, self._out, self._in, lib.ZSTD_e_end
            )
            if lib.ZSTD_isError(zresult):
                raise ZstdError(
                    "zstd compress error: %s" % _zstd_error(zresult)
                )

            if self._out.pos:
                yield ffi.buffer(self._out.dst, self._out.pos)[:]
                self._out.pos = 0

            if not zresult:
                self._finished = True
                return


class ZstdCompressionReader(object):
    """Readable compressing stream wrapper.

    ``ZstdCompressionReader`` is a read-only stream interface for obtaining
    compressed data from a source.

    This type conforms to the ``io.RawIOBase`` interface and should be usable
    by any type that operates against a *file-object* (``typing.BinaryIO``
    in Python type hinting speak).

    Instances are neither writable nor seekable (even if the underlying
    source is seekable). ``readline()`` and ``readlines()`` are not implemented
    because they don't make sense for compressed data. ``tell()`` returns the
    number of compressed bytes emitted so far.

    Instances are obtained by calling :py:meth:`ZstdCompressor.stream_reader`.

    In this example, we open a file for reading and then wrap that file
    handle with a stream from which compressed data can be ``read()``.

    >>> with open(path, 'rb') as fh:
    ...     cctx = zstandard.ZstdCompressor()
    ...     reader = cctx.stream_reader(fh)
    ...     while True:
    ...         chunk = reader.read(16384)
    ...         if not chunk:
    ...             break
    ...
    ...         # Do something with compressed chunk.

    Instances can also be used as context managers:

    >>> with open(path, 'rb') as fh:
    ...     cctx = zstandard.ZstdCompressor()
    ...     with cctx.stream_reader(fh) as reader:
    ...         while True:
    ...             chunk = reader.read(16384)
    ...             if not chunk:
    ...                 break
    ...
    ...             # Do something with compressed chunk.

    When the context manager exits or ``close()`` is called, the stream is
    closed, underlying resources are released, and future operations against
    the compression stream will fail.

    ``stream_reader()`` accepts a ``size`` argument specifying how large the
    input stream is. This is used to adjust compression parameters so they are
    tailored to the source size. e.g.

    >>> with open(path, 'rb') as fh:
    ...     cctx = zstandard.ZstdCompressor()
    ...     with cctx.stream_reader(fh, size=os.stat(path).st_size) as reader:
    ...         ...

    If the ``source`` is a stream, you can specify how large ``read()``
    requests to that stream should be via the ``read_size`` argument.
    It defaults to ``zstandard.COMPRESSION_RECOMMENDED_INPUT_SIZE``. e.g.

    >>> with open(path, 'rb') as fh:
    ...     cctx = zstandard.ZstdCompressor()
    ...     # Will perform fh.read(8192) when obtaining data to feed into the
    ...     # compressor.
    ...     with cctx.stream_reader(fh, read_size=8192) as reader:
    ...         ...
    """

    def __init__(self, compressor, source, read_size, closefd=True):
        self._compressor = compressor
        self._source = source
        self._read_size = read_size
        self._closefd = closefd
        self._entered = False
        self._closed = False
        self._bytes_compressed = 0
        self._finished_input = False
        self._finished_output = False

        self._in_buffer = ffi.new("ZSTD_inBuffer *")
        # Holds a ref so backing bytes in self._in_buffer stay alive.
        self._source_buffer = None

    def __enter__(self):
        if self._entered:
            raise ValueError("cannot __enter__ multiple times")

        if self._closed:
            raise ValueError("stream is closed")

        self._entered = True
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self._entered = False
        self._compressor = None
        self.close()
        self._source = None

        return False

    def readable(self):
        return True

    def writable(self):
        return False

    def seekable(self):
        return False

    def readline(self):
        raise io.UnsupportedOperation()

    def readlines(self):
        raise io.UnsupportedOperation()

    def write(self, data):
        raise OSError("stream is not writable")

    def writelines(self, ignored):
        raise OSError("stream is not writable")

    def isatty(self):
        return False

    def flush(self):
        return None

    def close(self):
        if self._closed:
            return

        self._closed = True

        f = getattr(self._source, "close", None)
        if self._closefd and f:
            f()

    @property
    def closed(self):
        return self._closed

    def tell(self):
        return self._bytes_compressed

    def readall(self):
        chunks = []

        while True:
            chunk = self.read(1048576)
            if not chunk:
                break

            chunks.append(chunk)

        return b"".join(chunks)

    def __iter__(self):
        raise io.UnsupportedOperation()

    def __next__(self):
        raise io.UnsupportedOperation()

    next = __next__

    def _read_input(self):
        if self._finished_input:
            return

        if hasattr(self._source, "read"):
            data = self._source.read(self._read_size)

            if not data:
                self._finished_input = True
                return

            self._source_buffer = ffi.from_buffer(data)
            self._in_buffer.src = self._source_buffer
            self._in_buffer.size = len(self._source_buffer)
            self._in_buffer.pos = 0
        else:
            self._source_buffer = ffi.from_buffer(self._source)
            self._in_buffer.src = self._source_buffer
            self._in_buffer.size = len(self._source_buffer)
            self._in_buffer.pos = 0

    def _compress_into_buffer(self, out_buffer):
        if self._in_buffer.pos >= self._in_buffer.size:
            return

        old_pos = out_buffer.pos

        zresult = lib.ZSTD_compressStream2(
            self._compressor._cctx,
            out_buffer,
            self._in_buffer,
            lib.ZSTD_e_continue,
        )

        self._bytes_compressed += out_buffer.pos - old_pos

        if self._in_buffer.pos == self._in_buffer.size:
            self._in_buffer.src = ffi.NULL
            self._in_buffer.pos = 0
            self._in_buffer.size = 0
            self._source_buffer = None

            if not hasattr(self._source, "read"):
                self._finished_input = True

        if lib.ZSTD_isError(zresult):
            raise ZstdError("zstd compress error: %s", _zstd_error(zresult))

        return out_buffer.pos and out_buffer.pos == out_buffer.size

    def read(self, size=-1):
        if self._closed:
            raise ValueError("stream is closed")

        if size < -1:
            raise ValueError("cannot read negative amounts less than -1")

        if size == -1:
            return self.readall()

        if self._finished_output or size == 0:
            return b""

        # Need a dedicated ref to dest buffer otherwise it gets collected.
        dst_buffer = ffi.new("char[]", size)
        out_buffer = ffi.new("ZSTD_outBuffer *")
        out_buffer.dst = dst_buffer
        out_buffer.size = size
        out_buffer.pos = 0

        if self._compress_into_buffer(out_buffer):
            return ffi.buffer(out_buffer.dst, out_buffer.pos)[:]

        while not self._finished_input:
            self._read_input()

            if self._compress_into_buffer(out_buffer):
                return ffi.buffer(out_buffer.dst, out_buffer.pos)[:]

        # EOF
        old_pos = out_buffer.pos

        zresult = lib.ZSTD_compressStream2(
            self._compressor._cctx, out_buffer, self._in_buffer, lib.ZSTD_e_end
        )

        self._bytes_compressed += out_buffer.pos - old_pos

        if lib.ZSTD_isError(zresult):
            raise ZstdError(
                "error ending compression stream: %s", _zstd_error(zresult)
            )

        if zresult == 0:
            self._finished_output = True

        return ffi.buffer(out_buffer.dst, out_buffer.pos)[:]

    def read1(self, size=-1):
        if self._closed:
            raise ValueError("stream is closed")

        if size < -1:
            raise ValueError("cannot read negative amounts less than -1")

        if self._finished_output or size == 0:
            return b""

        # -1 returns arbitrary number of bytes.
        if size == -1:
            size = COMPRESSION_RECOMMENDED_OUTPUT_SIZE

        dst_buffer = ffi.new("char[]", size)
        out_buffer = ffi.new("ZSTD_outBuffer *")
        out_buffer.dst = dst_buffer
        out_buffer.size = size
        out_buffer.pos = 0

        # read1() dictates that we can perform at most 1 call to the
        # underlying stream to get input. However, we can't satisfy this
        # restriction with compression because not all input generates output.
        # It is possible to perform a block flush in order to ensure output.
        # But this may not be desirable behavior. So we allow multiple read()
        # to the underlying stream. But unlike read(), we stop once we have
        # any output.

        self._compress_into_buffer(out_buffer)
        if out_buffer.pos:
            return ffi.buffer(out_buffer.dst, out_buffer.pos)[:]

        while not self._finished_input:
            self._read_input()

            # If we've filled the output buffer, return immediately.
            if self._compress_into_buffer(out_buffer):
                return ffi.buffer(out_buffer.dst, out_buffer.pos)[:]

            # If we've populated the output buffer and we're not at EOF,
            # also return, as we've satisfied the read1() limits.
            if out_buffer.pos and not self._finished_input:
                return ffi.buffer(out_buffer.dst, out_buffer.pos)[:]

            # Else if we're at EOS and we have room left in the buffer,
            # fall through to below and try to add more data to the output.

        # EOF.
        old_pos = out_buffer.pos

        zresult = lib.ZSTD_compressStream2(
            self._compressor._cctx, out_buffer, self._in_buffer, lib.ZSTD_e_end
        )

        self._bytes_compressed += out_buffer.pos - old_pos

        if lib.ZSTD_isError(zresult):
            raise ZstdError(
                "error ending compression stream: %s" % _zstd_error(zresult)
            )

        if zresult == 0:
            self._finished_output = True

        return ffi.buffer(out_buffer.dst, out_buffer.pos)[:]

    def readinto(self, b):
        if self._closed:
            raise ValueError("stream is closed")

        if self._finished_output:
            return 0

        # TODO use writable=True once we require CFFI >= 1.12.
        dest_buffer = ffi.from_buffer(b)
        ffi.memmove(b, b"", 0)
        out_buffer = ffi.new("ZSTD_outBuffer *")
        out_buffer.dst = dest_buffer
        out_buffer.size = len(dest_buffer)
        out_buffer.pos = 0

        if self._compress_into_buffer(out_buffer):
            return out_buffer.pos

        while not self._finished_input:
            self._read_input()
            if self._compress_into_buffer(out_buffer):
                return out_buffer.pos

        # EOF.
        old_pos = out_buffer.pos
        zresult = lib.ZSTD_compressStream2(
            self._compressor._cctx, out_buffer, self._in_buffer, lib.ZSTD_e_end
        )

        self._bytes_compressed += out_buffer.pos - old_pos

        if lib.ZSTD_isError(zresult):
            raise ZstdError(
                "error ending compression stream: %s", _zstd_error(zresult)
            )

        if zresult == 0:
            self._finished_output = True

        return out_buffer.pos

    def readinto1(self, b):
        if self._closed:
            raise ValueError("stream is closed")

        if self._finished_output:
            return 0

        # TODO use writable=True once we require CFFI >= 1.12.
        dest_buffer = ffi.from_buffer(b)
        ffi.memmove(b, b"", 0)

        out_buffer = ffi.new("ZSTD_outBuffer *")
        out_buffer.dst = dest_buffer
        out_buffer.size = len(dest_buffer)
        out_buffer.pos = 0

        self._compress_into_buffer(out_buffer)
        if out_buffer.pos:
            return out_buffer.pos

        while not self._finished_input:
            self._read_input()

            if self._compress_into_buffer(out_buffer):
                return out_buffer.pos

            if out_buffer.pos and not self._finished_input:
                return out_buffer.pos

        # EOF.
        old_pos = out_buffer.pos

        zresult = lib.ZSTD_compressStream2(
            self._compressor._cctx, out_buffer, self._in_buffer, lib.ZSTD_e_end
        )

        self._bytes_compressed += out_buffer.pos - old_pos

        if lib.ZSTD_isError(zresult):
            raise ZstdError(
                "error ending compression stream: %s" % _zstd_error(zresult)
            )

        if zresult == 0:
            self._finished_output = True

        return out_buffer.pos


class ZstdCompressor(object):
    """
    Create an object used to perform Zstandard compression.

    Each instance is essentially a wrapper around a ``ZSTD_CCtx`` from
    zstd's C API.

    An instance can compress data various ways. Instances can be used
    multiple times. Each compression operation will use the compression
    parameters defined at construction time.

    .. note:

       When using a compression dictionary and multiple compression
       operations are performed, the ``ZstdCompressionParameters`` derived
       from an integer compression ``level`` and the first compressed data's
       size will be reused for all subsequent operations. This may not be
       desirable if source data sizes vary significantly.

    ``compression_params`` is mutually exclusive with ``level``,
    ``write_checksum``, ``write_content_size``, ``write_dict_id``, and
    ``threads``.

    Assume that each ``ZstdCompressor`` instance can only handle a single
    logical compression operation at the same time. i.e. if you call a method
    like ``stream_reader()`` to obtain multiple objects derived from the same
    ``ZstdCompressor`` instance and attempt to use them simultaneously, errors
    will likely occur.

    If you need to perform multiple logical compression operations and you
    can't guarantee those operations are temporally non-overlapping, you need
    to obtain multiple ``ZstdCompressor`` instances.

    Unless specified otherwise, assume that no two methods of
    ``ZstdCompressor`` instances can be called from multiple Python
    threads simultaneously. In other words, assume instances are not thread safe
    unless stated otherwise.

    :param level:
       Integer compression level. Valid values are all negative integers
       through 22. Lower values generally yield faster operations with lower
       compression ratios. Higher values are generally slower but compress
       better. The default is 3, which is what the ``zstd`` CLI uses. Negative
       levels effectively engage ``--fast`` mode from the ``zstd`` CLI.
    :param dict_data:
       A ``ZstdCompressionDict`` to be used to compress with dictionary
        data.
    :param compression_params:
       A ``ZstdCompressionParameters`` instance defining low-level compression
       parameters. If defined, this will overwrite the ``level`` argument.
    :param write_checksum:
       If True, a 4 byte content checksum will be written with the compressed
       data, allowing the decompressor to perform content verification.
    :param write_content_size:
       If True (the default), the decompressed content size will be included
       in the header of the compressed data. This data will only be written if
       the compressor knows the size of the input data.
    :param write_dict_id:
       Determines whether the dictionary ID will be written into the compressed
       data. Defaults to True. Only adds content to the compressed data if
       a dictionary is being used.
    :param threads:
       Number of threads to use to compress data concurrently. When set,
       compression operations are performed on multiple threads. The default
       value (0) disables multi-threaded compression. A value of ``-1`` means
       to set the number of threads to the number of detected logical CPUs.
    """

    def __init__(
        self,
        level=3,
        dict_data=None,
        compression_params=None,
        write_checksum=None,
        write_content_size=None,
        write_dict_id=None,
        threads=0,
    ):
        if level > lib.ZSTD_maxCLevel():
            raise ValueError(
                "level must be less than %d" % lib.ZSTD_maxCLevel()
            )

        if threads < 0:
            threads = _cpu_count()

        if compression_params and write_checksum is not None:
            raise ValueError(
                "cannot define compression_params and " "write_checksum"
            )

        if compression_params and write_content_size is not None:
            raise ValueError(
                "cannot define compression_params and " "write_content_size"
            )

        if compression_params and write_dict_id is not None:
            raise ValueError(
                "cannot define compression_params and " "write_dict_id"
            )

        if compression_params and threads:
            raise ValueError("cannot define compression_params and threads")

        if compression_params:
            self._params = _make_cctx_params(compression_params)
        else:
            if write_dict_id is None:
                write_dict_id = True

            params = lib.ZSTD_createCCtxParams()
            if params == ffi.NULL:
                raise MemoryError()

            self._params = ffi.gc(params, lib.ZSTD_freeCCtxParams)

            _set_compression_parameter(
                self._params, lib.ZSTD_c_compressionLevel, level
            )

            _set_compression_parameter(
                self._params,
                lib.ZSTD_c_contentSizeFlag,
                write_content_size if write_content_size is not None else 1,
            )

            _set_compression_parameter(
                self._params,
                lib.ZSTD_c_checksumFlag,
                1 if write_checksum else 0,
            )

            _set_compression_parameter(
                self._params, lib.ZSTD_c_dictIDFlag, 1 if write_dict_id else 0
            )

            if threads:
                _set_compression_parameter(
                    self._params, lib.ZSTD_c_nbWorkers, threads
                )

        cctx = lib.ZSTD_createCCtx()
        if cctx == ffi.NULL:
            raise MemoryError()

        self._cctx = cctx
        self._dict_data = dict_data

        # We defer setting up garbage collection until after calling
        # _setup_cctx() to ensure the memory size estimate is more accurate.
        try:
            self._setup_cctx()
        finally:
            self._cctx = ffi.gc(
                cctx, lib.ZSTD_freeCCtx, size=lib.ZSTD_sizeof_CCtx(cctx)
            )

    def _setup_cctx(self):
        zresult = lib.ZSTD_CCtx_setParametersUsingCCtxParams(
            self._cctx, self._params
        )
        if lib.ZSTD_isError(zresult):
            raise ZstdError(
                "could not set compression parameters: %s"
                % _zstd_error(zresult)
            )

        dict_data = self._dict_data

        if dict_data:
            if dict_data._cdict:
                zresult = lib.ZSTD_CCtx_refCDict(self._cctx, dict_data._cdict)
            else:
                zresult = lib.ZSTD_CCtx_loadDictionary_advanced(
                    self._cctx,
                    dict_data.as_bytes(),
                    len(dict_data),
                    lib.ZSTD_dlm_byRef,
                    dict_data._dict_type,
                )

            if lib.ZSTD_isError(zresult):
                raise ZstdError(
                    "could not load compression dictionary: %s"
                    % _zstd_error(zresult)
                )

    def memory_size(self):
        """Obtain the memory usage of this compressor, in bytes.

        >>> cctx = zstandard.ZstdCompressor()
        >>> memory = cctx.memory_size()
        """
        return lib.ZSTD_sizeof_CCtx(self._cctx)

    def compress(self, data):
        """
        Compress data in a single operation.

        This is the simplest mechanism to perform compression: simply pass in a
        value and get a compressed value back. It is almost the most prone to
        abuse.

        The input and output values must fit in memory, so passing in very large
        values can result in excessive memory usage. For this reason, one of the
        streaming based APIs is preferred for larger values.

        :param data:
           Source data to compress
        :return:
           Compressed data

        >>> cctx = zstandard.ZstdCompressor()
        >>> compressed = cctx.compress(b"data to compress")
        """
        lib.ZSTD_CCtx_reset(self._cctx, lib.ZSTD_reset_session_only)

        data_buffer = ffi.from_buffer(data)

        dest_size = lib.ZSTD_compressBound(len(data_buffer))
        out = new_nonzero("char[]", dest_size)

        zresult = lib.ZSTD_CCtx_setPledgedSrcSize(self._cctx, len(data_buffer))
        if lib.ZSTD_isError(zresult):
            raise ZstdError(
                "error setting source size: %s" % _zstd_error(zresult)
            )

        out_buffer = ffi.new("ZSTD_outBuffer *")
        in_buffer = ffi.new("ZSTD_inBuffer *")

        out_buffer.dst = out
        out_buffer.size = dest_size
        out_buffer.pos = 0

        in_buffer.src = data_buffer
        in_buffer.size = len(data_buffer)
        in_buffer.pos = 0

        zresult = lib.ZSTD_compressStream2(
            self._cctx, out_buffer, in_buffer, lib.ZSTD_e_end
        )

        if lib.ZSTD_isError(zresult):
            raise ZstdError("cannot compress: %s" % _zstd_error(zresult))
        elif zresult:
            raise ZstdError("unexpected partial frame flush")

        return ffi.buffer(out, out_buffer.pos)[:]

    def compressobj(self, size=-1):
        """
        Obtain a compressor exposing the Python standard library compression API.

        See :py:class:`ZstdCompressionObj` for the full documentation.

        :param size:
           Size in bytes of data that will be compressed.
        :return:
           :py:class:`ZstdCompressionObj`
        """
        lib.ZSTD_CCtx_reset(self._cctx, lib.ZSTD_reset_session_only)

        if size < 0:
            size = lib.ZSTD_CONTENTSIZE_UNKNOWN

        zresult = lib.ZSTD_CCtx_setPledgedSrcSize(self._cctx, size)
        if lib.ZSTD_isError(zresult):
            raise ZstdError(
                "error setting source size: %s" % _zstd_error(zresult)
            )

        cobj = ZstdCompressionObj()
        cobj._out = ffi.new("ZSTD_outBuffer *")
        cobj._dst_buffer = ffi.new(
            "char[]", COMPRESSION_RECOMMENDED_OUTPUT_SIZE
        )
        cobj._out.dst = cobj._dst_buffer
        cobj._out.size = COMPRESSION_RECOMMENDED_OUTPUT_SIZE
        cobj._out.pos = 0
        cobj._compressor = self
        cobj._finished = False

        return cobj

    def chunker(self, size=-1, chunk_size=COMPRESSION_RECOMMENDED_OUTPUT_SIZE):
        """
        Create an object for iterative compressing to same-sized chunks.

        This API is similar to :py:meth:`ZstdCompressor.compressobj` but has
        better performance properties.

        :param size:
           Size in bytes of data that will be compressed.
        :param chunk_size:
           Size of compressed chunks.
        :return:
           :py:class:`ZstdCompressionChunker`
        """
        lib.ZSTD_CCtx_reset(self._cctx, lib.ZSTD_reset_session_only)

        if size < 0:
            size = lib.ZSTD_CONTENTSIZE_UNKNOWN

        zresult = lib.ZSTD_CCtx_setPledgedSrcSize(self._cctx, size)
        if lib.ZSTD_isError(zresult):
            raise ZstdError(
                "error setting source size: %s" % _zstd_error(zresult)
            )

        return ZstdCompressionChunker(self, chunk_size=chunk_size)

    def copy_stream(
        self,
        ifh,
        ofh,
        size=-1,
        read_size=COMPRESSION_RECOMMENDED_INPUT_SIZE,
        write_size=COMPRESSION_RECOMMENDED_OUTPUT_SIZE,
    ):
        """
        Copy data between 2 streams while compressing it.

        Data will be read from ``ifh``, compressed, and written to ``ofh``.
        ``ifh`` must have a ``read(size)`` method. ``ofh`` must have a
        ``write(data)``
        method.

        >>> cctx = zstandard.ZstdCompressor()
        >>> with open(input_path, "rb") as ifh, open(output_path, "wb") as ofh:
        ...     cctx.copy_stream(ifh, ofh)

        It is also possible to declare the size of the source stream:

        >>> cctx = zstandard.ZstdCompressor()
        >>> cctx.copy_stream(ifh, ofh, size=len_of_input)

        You can also specify how large the chunks that are ``read()``
        and ``write()`` from and to the streams:

        >>> cctx = zstandard.ZstdCompressor()
        >>> cctx.copy_stream(ifh, ofh, read_size=32768, write_size=16384)

        The stream copier returns a 2-tuple of bytes read and written:

        >>> cctx = zstandard.ZstdCompressor()
        >>> read_count, write_count = cctx.copy_stream(ifh, ofh)

        :param ifh:
           Source stream to read from
        :param ofh:
           Destination stream to write to
        :param size:
           Size in bytes of the source stream. If defined, compression
           parameters will be tuned for this size.
        :param read_size:
           Chunk sizes that source stream should be ``read()`` from.
        :param write_size:
           Chunk sizes that destination stream should be ``write()`` to.
        :return:
           2-tuple of ints of bytes read and written, respectively.
        """

        if not hasattr(ifh, "read"):
            raise ValueError("first argument must have a read() method")
        if not hasattr(ofh, "write"):
            raise ValueError("second argument must have a write() method")

        lib.ZSTD_CCtx_reset(self._cctx, lib.ZSTD_reset_session_only)

        if size < 0:
            size = lib.ZSTD_CONTENTSIZE_UNKNOWN

        zresult = lib.ZSTD_CCtx_setPledgedSrcSize(self._cctx, size)
        if lib.ZSTD_isError(zresult):
            raise ZstdError(
                "error setting source size: %s" % _zstd_error(zresult)
            )

        in_buffer = ffi.new("ZSTD_inBuffer *")
        out_buffer = ffi.new("ZSTD_outBuffer *")

        dst_buffer = ffi.new("char[]", write_size)
        out_buffer.dst = dst_buffer
        out_buffer.size = write_size
        out_buffer.pos = 0

        total_read, total_write = 0, 0

        while True:
            data = ifh.read(read_size)
            if not data:
                break

            data_buffer = ffi.from_buffer(data)
            total_read += len(data_buffer)
            in_buffer.src = data_buffer
            in_buffer.size = len(data_buffer)
            in_buffer.pos = 0

            while in_buffer.pos < in_buffer.size:
                zresult = lib.ZSTD_compressStream2(
                    self._cctx, out_buffer, in_buffer, lib.ZSTD_e_continue
                )
                if lib.ZSTD_isError(zresult):
                    raise ZstdError(
                        "zstd compress error: %s" % _zstd_error(zresult)
                    )

                if out_buffer.pos:
                    ofh.write(ffi.buffer(out_buffer.dst, out_buffer.pos))
                    total_write += out_buffer.pos
                    out_buffer.pos = 0

        # We've finished reading. Flush the compressor.
        while True:
            zresult = lib.ZSTD_compressStream2(
                self._cctx, out_buffer, in_buffer, lib.ZSTD_e_end
            )
            if lib.ZSTD_isError(zresult):
                raise ZstdError(
                    "error ending compression stream: %s" % _zstd_error(zresult)
                )

            if out_buffer.pos:
                ofh.write(ffi.buffer(out_buffer.dst, out_buffer.pos))
                total_write += out_buffer.pos
                out_buffer.pos = 0

            if zresult == 0:
                break

        return total_read, total_write

    def stream_reader(
        self,
        source,
        size=-1,
        read_size=COMPRESSION_RECOMMENDED_INPUT_SIZE,
        closefd=True,
    ):
        """
        Wrap a readable source with a stream that can read compressed data.

        This will produce an object conforming to the ``io.RawIOBase``
        interface which can be ``read()`` from to retrieve compressed data
        from a source.

        The source object can be any object with a ``read(size)`` method
        or an object that conforms to the buffer protocol.

        See :py:class:`ZstdCompressionReader` for type documentation and usage
        examples.

        :param source:
           Object to read source data from
        :param size:
           Size in bytes of source object.
        :param read_size:
           How many bytes to request when ``read()``'ing from the source.
        :param closefd:
           Whether to close the source stream when the returned stream is
           closed.
        :return:
           :py:class:`ZstdCompressionReader`
        """
        lib.ZSTD_CCtx_reset(self._cctx, lib.ZSTD_reset_session_only)

        try:
            size = len(source)
        except Exception:
            pass

        if size < 0:
            size = lib.ZSTD_CONTENTSIZE_UNKNOWN

        zresult = lib.ZSTD_CCtx_setPledgedSrcSize(self._cctx, size)
        if lib.ZSTD_isError(zresult):
            raise ZstdError(
                "error setting source size: %s" % _zstd_error(zresult)
            )

        return ZstdCompressionReader(self, source, read_size, closefd=closefd)

    def stream_writer(
        self,
        writer,
        size=-1,
        write_size=COMPRESSION_RECOMMENDED_OUTPUT_SIZE,
        write_return_read=True,
        closefd=True,
    ):
        """
        Create a stream that will write compressed data into another stream.

        The argument to ``stream_writer()`` must have a ``write(data)`` method.
        As compressed data is available, ``write()`` will be called with the
        compressed data as its argument. Many common Python types implement
        ``write()``, including open file handles and ``io.BytesIO``.

        See :py:class:`ZstdCompressionWriter` for more documentation, including
        usage examples.

        :param writer:
           Stream to write compressed data to.
        :param size:
           Size in bytes of data to be compressed. If set, it will be used
           to influence compression parameter tuning and could result in the
           size being written into the header of the compressed data.
        :param write_size:
           How much data to ``write()`` to ``writer`` at a time.
        :param write_return_read:
           Whether ``write()`` should return the number of bytes that were
           consumed from the input.
        :param closefd:
           Whether to ``close`` the ``writer`` when this stream is closed.
        :return:
           :py:class:`ZstdCompressionWriter`
        """
        if not hasattr(writer, "write"):
            raise ValueError("must pass an object with a write() method")

        lib.ZSTD_CCtx_reset(self._cctx, lib.ZSTD_reset_session_only)

        if size < 0:
            size = lib.ZSTD_CONTENTSIZE_UNKNOWN

        return ZstdCompressionWriter(
            self, writer, size, write_size, write_return_read, closefd=closefd
        )

    def read_to_iter(
        self,
        reader,
        size=-1,
        read_size=COMPRESSION_RECOMMENDED_INPUT_SIZE,
        write_size=COMPRESSION_RECOMMENDED_OUTPUT_SIZE,
    ):
        """
        Read uncompressed data from a reader and return an iterator

        Returns an iterator of compressed data produced from reading from
        ``reader``.

        This method provides a mechanism to stream compressed data out of a
        source as an iterator of data chunks.

        Uncompressed data will be obtained from ``reader`` by calling the
        ``read(size)`` method of it or by reading a slice (if ``reader``
        conforms to the *buffer protocol*). The source data will be streamed
        into a compressor. As compressed data is available, it will be exposed
        to the iterator.

        Data is read from the source in chunks of ``read_size``. Compressed
        chunks are at most ``write_size`` bytes. Both values default to the
        zstd input and and output defaults, respectively.

        If reading from the source via ``read()``, ``read()`` will be called
        until it raises or returns an empty bytes (``b""``). It is perfectly
        valid for the source to deliver fewer bytes than were what requested
        by ``read(size)``.

        The caller is partially in control of how fast data is fed into the
        compressor by how it consumes the returned iterator. The compressor
        will not consume from the reader unless the caller consumes from the
        iterator.

        >>> cctx = zstandard.ZstdCompressor()
        >>> for chunk in cctx.read_to_iter(fh):
        ...     # Do something with emitted data.

        ``read_to_iter()`` accepts a ``size`` argument declaring the size of
        the input stream:

        >>> cctx = zstandard.ZstdCompressor()
        >>> for chunk in cctx.read_to_iter(fh, size=some_int):
        >>>     pass

        You can also control the size that data is ``read()`` from the source
        and the ideal size of output chunks:

        >>> cctx = zstandard.ZstdCompressor()
        >>> for chunk in cctx.read_to_iter(fh, read_size=16384, write_size=8192):
        >>>     pass

        ``read_to_iter()`` does not give direct control over the sizes of chunks
        fed into the compressor. Instead, chunk sizes will be whatever the object
        being read from delivers. These will often be of a uniform size.

        :param reader:
           Stream providing data to be compressed.
        :param size:
           Size in bytes of input data.
        :param read_size:
           Controls how many bytes are ``read()`` from the source.
        :param write_size:
           Controls the output size of emitted chunks.
        :return:
           Iterator of ``bytes``.
        """

        if hasattr(reader, "read"):
            have_read = True
        elif hasattr(reader, "__getitem__"):
            have_read = False
            buffer_offset = 0
            size = len(reader)
        else:
            raise ValueError(
                "must pass an object with a read() method or "
                "conforms to buffer protocol"
            )

        lib.ZSTD_CCtx_reset(self._cctx, lib.ZSTD_reset_session_only)

        if size < 0:
            size = lib.ZSTD_CONTENTSIZE_UNKNOWN

        zresult = lib.ZSTD_CCtx_setPledgedSrcSize(self._cctx, size)
        if lib.ZSTD_isError(zresult):
            raise ZstdError(
                "error setting source size: %s" % _zstd_error(zresult)
            )

        in_buffer = ffi.new("ZSTD_inBuffer *")
        out_buffer = ffi.new("ZSTD_outBuffer *")

        in_buffer.src = ffi.NULL
        in_buffer.size = 0
        in_buffer.pos = 0

        dst_buffer = ffi.new("char[]", write_size)
        out_buffer.dst = dst_buffer
        out_buffer.size = write_size
        out_buffer.pos = 0

        while True:
            # We should never have output data sitting around after a previous
            # iteration.
            assert out_buffer.pos == 0

            # Collect input data.
            if have_read:
                read_result = reader.read(read_size)
            else:
                remaining = len(reader) - buffer_offset
                slice_size = min(remaining, read_size)
                read_result = reader[buffer_offset : buffer_offset + slice_size]
                buffer_offset += slice_size

            # No new input data. Break out of the read loop.
            if not read_result:
                break

            # Feed all read data into the compressor and emit output until
            # exhausted.
            read_buffer = ffi.from_buffer(read_result)
            in_buffer.src = read_buffer
            in_buffer.size = len(read_buffer)
            in_buffer.pos = 0

            while in_buffer.pos < in_buffer.size:
                zresult = lib.ZSTD_compressStream2(
                    self._cctx, out_buffer, in_buffer, lib.ZSTD_e_continue
                )
                if lib.ZSTD_isError(zresult):
                    raise ZstdError(
                        "zstd compress error: %s" % _zstd_error(zresult)
                    )

                if out_buffer.pos:
                    data = ffi.buffer(out_buffer.dst, out_buffer.pos)[:]
                    out_buffer.pos = 0
                    yield data

            assert out_buffer.pos == 0

            # And repeat the loop to collect more data.
            continue

        # If we get here, input is exhausted. End the stream and emit what
        # remains.
        while True:
            assert out_buffer.pos == 0
            zresult = lib.ZSTD_compressStream2(
                self._cctx, out_buffer, in_buffer, lib.ZSTD_e_end
            )
            if lib.ZSTD_isError(zresult):
                raise ZstdError(
                    "error ending compression stream: %s" % _zstd_error(zresult)
                )

            if out_buffer.pos:
                data = ffi.buffer(out_buffer.dst, out_buffer.pos)[:]
                out_buffer.pos = 0
                yield data

            if zresult == 0:
                break

    def multi_compress_to_buffer(self, data, threads=-1):
        """
        Compress multiple pieces of data as a single function call.

        (Experimental. Not yet supported by CFFI backend.)

        This function is optimized to perform multiple compression operations
        as as possible with as little overhead as possible.

        Data to be compressed can be passed as a ``BufferWithSegmentsCollection``,
        a ``BufferWithSegments``, or a list containing byte like objects. Each
        element of the container will be compressed individually using the
        configured parameters on the ``ZstdCompressor`` instance.

        The ``threads`` argument controls how many threads to use for
        compression. The default is ``0`` which means to use a single thread.
        Negative values use the number of logical CPUs in the machine.

        The function returns a ``BufferWithSegmentsCollection``. This type
        represents N discrete memory allocations, each holding 1 or more
        compressed frames.

        Output data is written to shared memory buffers. This means that unlike
        regular Python objects, a reference to *any* object within the collection
        keeps the shared buffer and therefore memory backing it alive. This can
        have undesirable effects on process memory usage.

        The API and behavior of this function is experimental and will likely
        change. Known deficiencies include:

        * If asked to use multiple threads, it will always spawn that many
          threads, even if the input is too small to use them. It should
          automatically lower the thread count when the extra threads would
          just add overhead.
        * The buffer allocation strategy is fixed. There is room to make it
          dynamic, perhaps even to allow one output buffer per input,
          facilitating a variation of the API to return a list without the
          adverse effects of shared memory buffers.

        :param data:
           Source to read discrete pieces of data to compress.

           Can be a ``BufferWithSegmentsCollection``, a ``BufferWithSegments``,
           or a ``list[bytes]``.
        :return:
           BufferWithSegmentsCollection holding compressed data.
        """
        raise NotImplementedError()

    def frame_progression(self):
        """
        Return information on how much work the compressor has done.

        Returns a 3-tuple of (ingested, consumed, produced).

        >>> cctx = zstandard.ZstdCompressor()
        >>> (ingested, consumed, produced) = cctx.frame_progression()
        """
        progression = lib.ZSTD_getFrameProgression(self._cctx)

        return progression.ingested, progression.consumed, progression.produced


class FrameParameters(object):
    """Information about a zstd frame.

    Instances have the following attributes:

    ``content_size``
       Integer size of original, uncompressed content. This will be ``0`` if the
       original content size isn't written to the frame (controlled with the
       ``write_content_size`` argument to ``ZstdCompressor``) or if the input
       content size was ``0``.

    ``window_size``
       Integer size of maximum back-reference distance in compressed data.

    ``dict_id``
       Integer of dictionary ID used for compression. ``0`` if no dictionary
       ID was used or if the dictionary ID was ``0``.

    ``has_checksum``
       Bool indicating whether a 4 byte content checksum is stored at the end
       of the frame.
    """

    def __init__(self, fparams):
        self.content_size = fparams.frameContentSize
        self.window_size = fparams.windowSize
        self.dict_id = fparams.dictID
        self.has_checksum = bool(fparams.checksumFlag)


def frame_content_size(data):
    """Obtain the decompressed size of a frame.

    The returned value is usually accurate. But strictly speaking it should
    not be trusted.

    :return:
       ``-1`` if size unknown and a non-negative integer otherwise.
    """
    data_buffer = ffi.from_buffer(data)

    size = lib.ZSTD_getFrameContentSize(data_buffer, len(data_buffer))

    if size == lib.ZSTD_CONTENTSIZE_ERROR:
        raise ZstdError("error when determining content size")
    elif size == lib.ZSTD_CONTENTSIZE_UNKNOWN:
        return -1
    else:
        return size


def frame_header_size(data):
    """Obtain the size of a frame header.

    :return:
       Integer size in bytes.
    """
    data_buffer = ffi.from_buffer(data)

    zresult = lib.ZSTD_frameHeaderSize(data_buffer, len(data_buffer))
    if lib.ZSTD_isError(zresult):
        raise ZstdError(
            "could not determine frame header size: %s" % _zstd_error(zresult)
        )

    return zresult


def get_frame_parameters(data):
    """
    Parse a zstd frame header into frame parameters.

    Depending on which fields are present in the frame and their values, the
    length of the frame parameters varies. If insufficient bytes are passed
    in to fully parse the frame parameters, ``ZstdError`` is raised. To ensure
    frame parameters can be parsed, pass in at least 18 bytes.

    :param data:
       Data from which to read frame parameters.
    :return:
       :py:class:`FrameParameters`
    """
    params = ffi.new("ZSTD_frameHeader *")

    data_buffer = ffi.from_buffer(data)
    zresult = lib.ZSTD_getFrameHeader(params, data_buffer, len(data_buffer))
    if lib.ZSTD_isError(zresult):
        raise ZstdError(
            "cannot get frame parameters: %s" % _zstd_error(zresult)
        )

    if zresult:
        raise ZstdError(
            "not enough data for frame parameters; need %d bytes" % zresult
        )

    return FrameParameters(params[0])


class ZstdCompressionDict(object):
    """Represents a computed compression dictionary.

    Instances are obtained by calling :py:func:`train_dictionary` or by
    passing bytes obtained from another source into the constructor.

    Instances can be constructed from bytes:

    >>> dict_data = zstandard.ZstdCompressionDict(data)

    It is possible to construct a dictionary from *any* data. If the data
    doesn't begin with a magic header, it will be treated as a *prefix*
    dictionary. *Prefix* dictionaries allow compression operations to
    reference raw data within the dictionary.

    It is possible to force the use of *prefix* dictionaries or to require
    a dictionary header:

    >>> dict_data = zstandard.ZstdCompressionDict(data, dict_type=zstandard.DICT_TYPE_RAWCONTENT)
    >>> dict_data = zstandard.ZstdCompressionDict(data, dict_type=zstandard.DICT_TYPE_FULLDICT)

    You can see how many bytes are in the dictionary by calling ``len()``:

    >>> dict_data = zstandard.train_dictionary(size, samples)
    >>> dict_size = len(dict_data)  # will not be larger than ``size``

    Once you have a dictionary, you can pass it to the objects performing
    compression and decompression:

    >>> dict_data = zstandard.train_dictionary(131072, samples)
    >>> cctx = zstandard.ZstdCompressor(dict_data=dict_data)
    >>> for source_data in input_data:
    ...     compressed = cctx.compress(source_data)
    ...     # Do something with compressed data.
    ...
    >>> dctx = zstandard.ZstdDecompressor(dict_data=dict_data)
    >>> for compressed_data in input_data:
    ...     buffer = io.BytesIO()
    ...     with dctx.stream_writer(buffer) as decompressor:
    ...         decompressor.write(compressed_data)
    ...         # Do something with raw data in ``buffer``.

    Dictionaries have unique integer IDs. You can retrieve this ID via:

    >>> dict_id = zstandard.dictionary_id(dict_data)

    You can obtain the raw data in the dict (useful for persisting and constructing
    a ``ZstdCompressionDict`` later) via ``as_bytes()``:

    >>> dict_data = zstandard.train_dictionary(size, samples)
    >>> raw_data = dict_data.as_bytes()

    By default, when a ``ZstdCompressionDict`` is *attached* to a
    ``ZstdCompressor``, each ``ZstdCompressor`` performs work to prepare the
    dictionary for use. This is fine if only 1 compression operation is being
    performed or if the ``ZstdCompressor`` is being reused for multiple operations.
    But if multiple ``ZstdCompressor`` instances are being used with the dictionary,
    this can add overhead.

    It is possible to *precompute* the dictionary so it can readily be consumed
    by multiple ``ZstdCompressor`` instances:

    >>> d = zstandard.ZstdCompressionDict(data)
    >>> # Precompute for compression level 3.
    >>> d.precompute_compress(level=3)
    >>> # Precompute with specific compression parameters.
    >>> params = zstandard.ZstdCompressionParameters(...)
    >>> d.precompute_compress(compression_params=params)

    .. note::

       When a dictionary is precomputed, the compression parameters used to
       precompute the dictionary overwrite some of the compression parameters
       specified to ``ZstdCompressor``.

    :param data:
       Dictionary data.
    :param dict_type:
       Type of dictionary. One of the ``DICT_TYPE_*`` constants.
    """

    def __init__(self, data, dict_type=DICT_TYPE_AUTO, k=0, d=0):
        assert isinstance(data, bytes)
        self._data = data
        self.k = k
        self.d = d

        if dict_type not in (
            DICT_TYPE_AUTO,
            DICT_TYPE_RAWCONTENT,
            DICT_TYPE_FULLDICT,
        ):
            raise ValueError(
                "invalid dictionary load mode: %d; must use "
                "DICT_TYPE_* constants"
            )

        self._dict_type = dict_type
        self._cdict = None

    def __len__(self):
        return len(self._data)

    def dict_id(self):
        """Obtain the integer ID of the dictionary."""
        return int(lib.ZDICT_getDictID(self._data, len(self._data)))

    def as_bytes(self):
        """Obtain the ``bytes`` representation of the dictionary."""
        return self._data

    def precompute_compress(self, level=0, compression_params=None):
        """Precompute a dictionary os it can be used by multiple compressors.

        Calling this method on an instance that will be used by multiple
        :py:class:`ZstdCompressor` instances will improve performance.
        """
        if level and compression_params:
            raise ValueError(
                "must only specify one of level or " "compression_params"
            )

        if not level and not compression_params:
            raise ValueError("must specify one of level or compression_params")

        if level:
            cparams = lib.ZSTD_getCParams(level, 0, len(self._data))
        else:
            cparams = ffi.new("ZSTD_compressionParameters")
            cparams.chainLog = compression_params.chain_log
            cparams.hashLog = compression_params.hash_log
            cparams.minMatch = compression_params.min_match
            cparams.searchLog = compression_params.search_log
            cparams.strategy = compression_params.strategy
            cparams.targetLength = compression_params.target_length
            cparams.windowLog = compression_params.window_log

        cdict = lib.ZSTD_createCDict_advanced(
            self._data,
            len(self._data),
            lib.ZSTD_dlm_byRef,
            self._dict_type,
            cparams,
            lib.ZSTD_defaultCMem,
        )
        if cdict == ffi.NULL:
            raise ZstdError("unable to precompute dictionary")

        self._cdict = ffi.gc(
            cdict, lib.ZSTD_freeCDict, size=lib.ZSTD_sizeof_CDict(cdict)
        )

    @property
    def _ddict(self):
        ddict = lib.ZSTD_createDDict_advanced(
            self._data,
            len(self._data),
            lib.ZSTD_dlm_byRef,
            self._dict_type,
            lib.ZSTD_defaultCMem,
        )

        if ddict == ffi.NULL:
            raise ZstdError("could not create decompression dict")

        ddict = ffi.gc(
            ddict, lib.ZSTD_freeDDict, size=lib.ZSTD_sizeof_DDict(ddict)
        )
        self.__dict__["_ddict"] = ddict

        return ddict


def train_dictionary(
    dict_size,
    samples,
    k=0,
    d=0,
    f=0,
    split_point=0.0,
    accel=0,
    notifications=0,
    dict_id=0,
    level=0,
    steps=0,
    threads=0,
):
    """Train a dictionary from sample data using the COVER algorithm.

    A compression dictionary of size ``dict_size`` will be created from the
    iterable of ``samples``. The raw dictionary bytes will be returned.

    The dictionary training mechanism is known as *cover*. More details about it
    are available in the paper *Effective Construction of Relative Lempel-Ziv
    Dictionaries* (authors: Liao, Petri, Moffat, Wirth).

    The cover algorithm takes parameters ``k`` and ``d``. These are the
    *segment size* and *dmer size*, respectively. The returned dictionary
    instance created by this function has ``k`` and ``d`` attributes
    containing the values for these parameters. If a ``ZstdCompressionDict``
    is constructed from raw bytes data (a content-only dictionary), the
    ``k`` and ``d`` attributes will be ``0``.

    The segment and dmer size parameters to the cover algorithm can either be
    specified manually or ``train_dictionary()`` can try multiple values
    and pick the best one, where *best* means the smallest compressed data size.
    This later mode is called *optimization* mode.

    Under the hood, this function always calls
    ``ZDICT_optimizeTrainFromBuffer_fastCover()``. See the corresponding C library
    documentation for more.

    If neither ``steps`` nor ``threads`` is defined, defaults for ``d``, ``steps``,
    and ``level`` will be used that are equivalent with what
    ``ZDICT_trainFromBuffer()`` would use.


    :param dict_size:
       Target size in bytes of the dictionary to generate.
    :param samples:
       A list of bytes holding samples the dictionary will be trained from.
    :param k:
       Segment size : constraint: 0 < k : Reasonable range [16, 2048+]
    :param d:
       dmer size : constraint: 0 < d <= k : Reasonable range [6, 16]
    :param f:
       log of size of frequency array : constraint: 0 < f <= 31 : 1 means
       default(20)
    :param split_point:
       Percentage of samples used for training: Only used for optimization.
       The first # samples * ``split_point`` samples will be used to training.
       The last # samples * (1 - split_point) samples will be used for testing.
       0 means default (0.75), 1.0 when all samples are used for both training
       and testing.
    :param accel:
       Acceleration level: constraint: 0 < accel <= 10. Higher means faster
       and less accurate, 0 means default(1).
    :param dict_id:
       Integer dictionary ID for the produced dictionary. Default is 0, which uses
       a random value.
    :param steps:
       Number of steps through ``k`` values to perform when trying parameter
       variations.
    :param threads:
       Number of threads to use when trying parameter variations. Default is 0,
       which means to use a single thread. A negative value can be specified to
       use as many threads as there are detected logical CPUs.
    :param level:
       Integer target compression level when trying parameter variations.
    :param notifications:
       Controls writing of informational messages to ``stderr``. ``0`` (the
       default) means to write nothing. ``1`` writes errors. ``2`` writes
       progression info. ``3`` writes more details. And ``4`` writes all info.
    """

    if not isinstance(samples, list):
        raise TypeError("samples must be a list")

    if threads < 0:
        threads = _cpu_count()

    if not steps and not threads:
        d = d or 8
        steps = steps or 4
        level = level or 3

    total_size = sum(map(len, samples))

    samples_buffer = new_nonzero("char[]", total_size)
    sample_sizes = new_nonzero("size_t[]", len(samples))

    offset = 0
    for i, sample in enumerate(samples):
        if not isinstance(sample, bytes):
            raise ValueError("samples must be bytes")

        l = len(sample)
        ffi.memmove(samples_buffer + offset, sample, l)
        offset += l
        sample_sizes[i] = l

    dict_data = new_nonzero("char[]", dict_size)

    dparams = ffi.new("ZDICT_fastCover_params_t *")[0]
    dparams.k = k
    dparams.d = d
    dparams.f = f
    dparams.steps = steps
    dparams.nbThreads = threads
    dparams.splitPoint = split_point
    dparams.accel = accel
    dparams.zParams.notificationLevel = notifications
    dparams.zParams.dictID = dict_id
    dparams.zParams.compressionLevel = level

    zresult = lib.ZDICT_optimizeTrainFromBuffer_fastCover(
        ffi.addressof(dict_data),
        dict_size,
        ffi.addressof(samples_buffer),
        ffi.addressof(sample_sizes, 0),
        len(samples),
        ffi.addressof(dparams),
    )

    if lib.ZDICT_isError(zresult):
        msg = ffi.string(lib.ZDICT_getErrorName(zresult)).decode("utf-8")
        raise ZstdError("cannot train dict: %s" % msg)

    return ZstdCompressionDict(
        ffi.buffer(dict_data, zresult)[:],
        dict_type=DICT_TYPE_FULLDICT,
        k=dparams.k,
        d=dparams.d,
    )


class ZstdDecompressionObj(object):
    """A standard library API compatible decompressor.

    This type implements a compressor that conforms to the API by other
    decompressors in Python's standard library. e.g. ``zlib.decompressobj``
    or ``bz2.BZ2Decompressor``. This allows callers to use zstd compression
    while conforming to a similar API.

    Compressed data chunks are fed into ``decompress(data)`` and
    uncompressed output (or an empty bytes) is returned. Output from
    subsequent calls needs to be concatenated to reassemble the full
    decompressed byte sequence.

    If ``read_across_frames=False``, each instance is single use: once an
    input frame is decoded, ``decompress()`` will raise an exception. If
    ``read_across_frames=True``, instances can decode multiple frames.

    >>> dctx = zstandard.ZstdDecompressor()
    >>> dobj = dctx.decompressobj()
    >>> data = dobj.decompress(compressed_chunk_0)
    >>> data = dobj.decompress(compressed_chunk_1)

    By default, calls to ``decompress()`` write output data in chunks of size
    ``DECOMPRESSION_RECOMMENDED_OUTPUT_SIZE``. These chunks are concatenated
    before being returned to the caller. It is possible to define the size of
    these temporary chunks by passing ``write_size`` to ``decompressobj()``:

    >>> dctx = zstandard.ZstdDecompressor()
    >>> dobj = dctx.decompressobj(write_size=1048576)

    .. note::

       Because calls to ``decompress()`` may need to perform multiple
       memory (re)allocations, this streaming decompression API isn't as
       efficient as other APIs.
    """

    def __init__(self, decompressor, write_size, read_across_frames):
        self._decompressor = decompressor
        self._write_size = write_size
        self._finished = False
        self._read_across_frames = read_across_frames
        self._unused_input = b""

    def decompress(self, data):
        """Send compressed data to the decompressor and obtain decompressed data.

        :param data:
           Data to feed into the decompressor.
        :return:
           Decompressed bytes.
        """
        if self._finished:
            raise ZstdError("cannot use a decompressobj multiple times")

        in_buffer = ffi.new("ZSTD_inBuffer *")
        out_buffer = ffi.new("ZSTD_outBuffer *")

        data_buffer = ffi.from_buffer(data)

        if len(data_buffer) == 0:
            return b""

        in_buffer.src = data_buffer
        in_buffer.size = len(data_buffer)
        in_buffer.pos = 0

        dst_buffer = ffi.new("char[]", self._write_size)
        out_buffer.dst = dst_buffer
        out_buffer.size = len(dst_buffer)
        out_buffer.pos = 0

        chunks = []

        while True:
            zresult = lib.ZSTD_decompressStream(
                self._decompressor._dctx, out_buffer, in_buffer
            )
            if lib.ZSTD_isError(zresult):
                raise ZstdError(
                    "zstd decompressor error: %s" % _zstd_error(zresult)
                )

            # Always record any output from decompressor.
            if out_buffer.pos:
                chunks.append(ffi.buffer(out_buffer.dst, out_buffer.pos)[:])

            # 0 is only seen when a frame is fully decoded *and* fully flushed.
            # Behavior depends on whether we're in single or multiple frame
            # mode.
            if zresult == 0 and not self._read_across_frames:
                # Mark the instance as done and make any unconsumed input available
                # for retrieval.
                self._finished = True
                self._decompressor = None
                self._unused_input = data[in_buffer.pos : in_buffer.size]
                break
            elif zresult == 0 and self._read_across_frames:
                # We're at the end of a fully flushed frame and we can read more.
                # Try to read more if there's any more input.
                if in_buffer.pos == in_buffer.size:
                    break
                else:
                    out_buffer.pos = 0

            # We're not at the end of the frame *or* we're not fully flushed.

            # The decompressor will write out all the bytes it can to the output
            # buffer. So if the output buffer is partially filled and the input
            # is exhausted, there's nothing more to write. So we've done all we
            # can.
            elif (
                in_buffer.pos == in_buffer.size
                and out_buffer.pos < out_buffer.size
            ):
                break
            else:
                out_buffer.pos = 0

        return b"".join(chunks)

    def flush(self, length=0):
        """Effectively a no-op.

        Implemented for compatibility with the standard library APIs.

        Safe to call at any time.

        :return:
           Empty bytes.
        """
        return b""

    @property
    def unused_data(self):
        """Bytes past the end of compressed data.

        If ``decompress()`` is fed additional data beyond the end of a zstd
        frame, this value will be non-empty once ``decompress()`` fully decodes
        the input frame.
        """
        return self._unused_input

    @property
    def unconsumed_tail(self):
        """Data that has not yet been fed into the decompressor."""
        return b""

    @property
    def eof(self):
        """Whether the end of the compressed data stream has been reached."""
        return self._finished


class ZstdDecompressionReader(object):
    """Read only decompressor that pull uncompressed data from another stream.

    This type provides a read-only stream interface for performing transparent
    decompression from another stream or data source. It conforms to the
    ``io.RawIOBase`` interface. Only methods relevant to reading are
    implemented.

    >>> with open(path, 'rb') as fh:
    >>> dctx = zstandard.ZstdDecompressor()
    >>> reader = dctx.stream_reader(fh)
    >>> while True:
    ...     chunk = reader.read(16384)
    ...     if not chunk:
    ...         break
    ...     # Do something with decompressed chunk.

    The stream can also be used as a context manager:

    >>> with open(path, 'rb') as fh:
    ...     dctx = zstandard.ZstdDecompressor()
    ...     with dctx.stream_reader(fh) as reader:
    ...         ...

    When used as a context manager, the stream is closed and the underlying
    resources are released when the context manager exits. Future operations
    against the stream will fail.

    The ``source`` argument to ``stream_reader()`` can be any object with a
    ``read(size)`` method or any object implementing the *buffer protocol*.

    If the ``source`` is a stream, you can specify how large ``read()`` requests
    to that stream should be via the ``read_size`` argument. It defaults to
    ``zstandard.DECOMPRESSION_RECOMMENDED_INPUT_SIZE``.:

    >>> with open(path, 'rb') as fh:
    ...     dctx = zstandard.ZstdDecompressor()
    ...     # Will perform fh.read(8192) when obtaining data for the decompressor.
    ...     with dctx.stream_reader(fh, read_size=8192) as reader:
    ...         ...

    Instances are *partially* seekable. Absolute and relative positions
    (``SEEK_SET`` and ``SEEK_CUR``) forward of the current position are
    allowed. Offsets behind the current read position and offsets relative
    to the end of stream are not allowed and will raise ``ValueError``
    if attempted.

    ``tell()`` returns the number of decompressed bytes read so far.

    Not all I/O methods are implemented. Notably missing is support for
    ``readline()``, ``readlines()``, and linewise iteration support. This is
    because streams operate on binary data - not text data. If you want to
    convert decompressed output to text, you can chain an ``io.TextIOWrapper``
    to the stream:

    >>> with open(path, 'rb') as fh:
    ...     dctx = zstandard.ZstdDecompressor()
    ...     stream_reader = dctx.stream_reader(fh)
    ...     text_stream = io.TextIOWrapper(stream_reader, encoding='utf-8')
    ...     for line in text_stream:
    ...         ...
    """

    def __init__(
        self,
        decompressor,
        source,
        read_size,
        read_across_frames,
        closefd=True,
    ):
        self._decompressor = decompressor
        self._source = source
        self._read_size = read_size
        self._read_across_frames = bool(read_across_frames)
        self._closefd = bool(closefd)
        self._entered = False
        self._closed = False
        self._bytes_decompressed = 0
        self._finished_input = False
        self._finished_output = False
        self._in_buffer = ffi.new("ZSTD_inBuffer *")
        # Holds a ref to self._in_buffer.src.
        self._source_buffer = None

    def __enter__(self):
        if self._entered:
            raise ValueError("cannot __enter__ multiple times")

        if self._closed:
            raise ValueError("stream is closed")

        self._entered = True
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self._entered = False
        self._decompressor = None
        self.close()
        self._source = None

        return False

    def readable(self):
        return True

    def writable(self):
        return False

    def seekable(self):
        return False

    def readline(self, size=-1):
        raise io.UnsupportedOperation()

    def readlines(self, hint=-1):
        raise io.UnsupportedOperation()

    def write(self, data):
        raise io.UnsupportedOperation()

    def writelines(self, lines):
        raise io.UnsupportedOperation()

    def isatty(self):
        return False

    def flush(self):
        return None

    def close(self):
        if self._closed:
            return None

        self._closed = True

        f = getattr(self._source, "close", None)
        if self._closefd and f:
            f()

    @property
    def closed(self):
        return self._closed

    def tell(self):
        return self._bytes_decompressed

    def readall(self):
        chunks = []

        while True:
            chunk = self.read(1048576)
            if not chunk:
                break

            chunks.append(chunk)

        return b"".join(chunks)

    def __iter__(self):
        raise io.UnsupportedOperation()

    def __next__(self):
        raise io.UnsupportedOperation()

    next = __next__

    def _read_input(self):
        # We have data left over in the input buffer. Use it.
        if self._in_buffer.pos < self._in_buffer.size:
            return

        # All input data exhausted. Nothing to do.
        if self._finished_input:
            return

        # Else populate the input buffer from our source.
        if hasattr(self._source, "read"):
            data = self._source.read(self._read_size)

            if not data:
                self._finished_input = True
                return

            self._source_buffer = ffi.from_buffer(data)
            self._in_buffer.src = self._source_buffer
            self._in_buffer.size = len(self._source_buffer)
            self._in_buffer.pos = 0
        else:
            self._source_buffer = ffi.from_buffer(self._source)
            self._in_buffer.src = self._source_buffer
            self._in_buffer.size = len(self._source_buffer)
            self._in_buffer.pos = 0

    def _decompress_into_buffer(self, out_buffer):
        """Decompress available input into an output buffer.

        Returns True if data in output buffer should be emitted.
        """
        zresult = lib.ZSTD_decompressStream(
            self._decompressor._dctx, out_buffer, self._in_buffer
        )

        if self._in_buffer.pos == self._in_buffer.size:
            self._in_buffer.src = ffi.NULL
            self._in_buffer.pos = 0
            self._in_buffer.size = 0
            self._source_buffer = None

            if not hasattr(self._source, "read"):
                self._finished_input = True

        if lib.ZSTD_isError(zresult):
            raise ZstdError("zstd decompress error: %s" % _zstd_error(zresult))

        # Emit data if there is data AND either:
        # a) output buffer is full (read amount is satisfied)
        # b) we're at end of a frame and not in frame spanning mode
        return out_buffer.pos and (
            out_buffer.pos == out_buffer.size
            or zresult == 0
            and not self._read_across_frames
        )

    def read(self, size=-1):
        if self._closed:
            raise ValueError("stream is closed")

        if size < -1:
            raise ValueError("cannot read negative amounts less than -1")

        if size == -1:
            # This is recursive. But it gets the job done.
            return self.readall()

        if self._finished_output or size == 0:
            return b""

        # We /could/ call into readinto() here. But that introduces more
        # overhead.
        dst_buffer = ffi.new("char[]", size)
        out_buffer = ffi.new("ZSTD_outBuffer *")
        out_buffer.dst = dst_buffer
        out_buffer.size = size
        out_buffer.pos = 0

        self._read_input()
        if self._decompress_into_buffer(out_buffer):
            self._bytes_decompressed += out_buffer.pos
            return ffi.buffer(out_buffer.dst, out_buffer.pos)[:]

        while not self._finished_input:
            self._read_input()
            if self._decompress_into_buffer(out_buffer):
                self._bytes_decompressed += out_buffer.pos
                return ffi.buffer(out_buffer.dst, out_buffer.pos)[:]

        self._bytes_decompressed += out_buffer.pos
        return ffi.buffer(out_buffer.dst, out_buffer.pos)[:]

    def readinto(self, b):
        if self._closed:
            raise ValueError("stream is closed")

        if self._finished_output:
            return 0

        # TODO use writable=True once we require CFFI >= 1.12.
        dest_buffer = ffi.from_buffer(b)
        ffi.memmove(b, b"", 0)
        out_buffer = ffi.new("ZSTD_outBuffer *")
        out_buffer.dst = dest_buffer
        out_buffer.size = len(dest_buffer)
        out_buffer.pos = 0

        self._read_input()
        if self._decompress_into_buffer(out_buffer):
            self._bytes_decompressed += out_buffer.pos
            return out_buffer.pos

        while not self._finished_input:
            self._read_input()
            if self._decompress_into_buffer(out_buffer):
                self._bytes_decompressed += out_buffer.pos
                return out_buffer.pos

        self._bytes_decompressed += out_buffer.pos
        return out_buffer.pos

    def read1(self, size=-1):
        if self._closed:
            raise ValueError("stream is closed")

        if size < -1:
            raise ValueError("cannot read negative amounts less than -1")

        if self._finished_output or size == 0:
            return b""

        # -1 returns arbitrary number of bytes.
        if size == -1:
            size = DECOMPRESSION_RECOMMENDED_OUTPUT_SIZE

        dst_buffer = ffi.new("char[]", size)
        out_buffer = ffi.new("ZSTD_outBuffer *")
        out_buffer.dst = dst_buffer
        out_buffer.size = size
        out_buffer.pos = 0

        # read1() dictates that we can perform at most 1 call to underlying
        # stream to get input. However, we can't satisfy this restriction with
        # decompression because not all input generates output. So we allow
        # multiple read(). But unlike read(), we stop once we have any output.
        while not self._finished_input:
            self._read_input()
            self._decompress_into_buffer(out_buffer)

            if out_buffer.pos:
                break

        self._bytes_decompressed += out_buffer.pos
        return ffi.buffer(out_buffer.dst, out_buffer.pos)[:]

    def readinto1(self, b):
        if self._closed:
            raise ValueError("stream is closed")

        if self._finished_output:
            return 0

        # TODO use writable=True once we require CFFI >= 1.12.
        dest_buffer = ffi.from_buffer(b)
        ffi.memmove(b, b"", 0)

        out_buffer = ffi.new("ZSTD_outBuffer *")
        out_buffer.dst = dest_buffer
        out_buffer.size = len(dest_buffer)
        out_buffer.pos = 0

        while not self._finished_input and not self._finished_output:
            self._read_input()
            self._decompress_into_buffer(out_buffer)

            if out_buffer.pos:
                break

        self._bytes_decompressed += out_buffer.pos
        return out_buffer.pos

    def seek(self, pos, whence=os.SEEK_SET):
        if self._closed:
            raise ValueError("stream is closed")

        read_amount = 0

        if whence == os.SEEK_SET:
            if pos < 0:
                raise OSError("cannot seek to negative position with SEEK_SET")

            if pos < self._bytes_decompressed:
                raise OSError(
                    "cannot seek zstd decompression stream " "backwards"
                )

            read_amount = pos - self._bytes_decompressed

        elif whence == os.SEEK_CUR:
            if pos < 0:
                raise OSError(
                    "cannot seek zstd decompression stream " "backwards"
                )

            read_amount = pos
        elif whence == os.SEEK_END:
            raise OSError(
                "zstd decompression streams cannot be seeked " "with SEEK_END"
            )

        while read_amount:
            result = self.read(
                min(read_amount, DECOMPRESSION_RECOMMENDED_OUTPUT_SIZE)
            )

            if not result:
                break

            read_amount -= len(result)

        return self._bytes_decompressed


class ZstdDecompressionWriter(object):
    """
    Write-only stream wrapper that performs decompression.

    This type provides a writable stream that performs decompression and writes
    decompressed data to another stream.

    This type implements the ``io.RawIOBase`` interface. Only methods that
    involve writing will do useful things.

    Behavior is similar to :py:meth:`ZstdCompressor.stream_writer`: compressed
    data is sent to the decompressor by calling ``write(data)`` and decompressed
    output is written to the inner stream by calling its ``write(data)``
    method:

    >>> dctx = zstandard.ZstdDecompressor()
    >>> decompressor = dctx.stream_writer(fh)
    >>> # Will call fh.write() with uncompressed data.
    >>> decompressor.write(compressed_data)

    Instances can be used as context managers. However, context managers add no
    extra special behavior other than automatically calling ``close()`` when
    they exit.

    Calling ``close()`` will mark the stream as closed and subsequent I/O
    operations will raise ``ValueError`` (per the documented behavior of
    ``io.RawIOBase``). ``close()`` will also call ``close()`` on the
    underlying stream if such a method exists and the instance was created with
    ``closefd=True``.

    The size of chunks to ``write()`` to the destination can be specified:

    >>> dctx = zstandard.ZstdDecompressor()
    >>> with dctx.stream_writer(fh, write_size=16384) as decompressor:
    >>>    pass

    You can see how much memory is being used by the decompressor:

    >>> dctx = zstandard.ZstdDecompressor()
    >>> with dctx.stream_writer(fh) as decompressor:
    >>>    byte_size = decompressor.memory_size()

    ``stream_writer()`` accepts a ``write_return_read`` boolean argument to control
    the return value of ``write()``. When ``True`` (the default)``, ``write()``
    returns the number of bytes that were read from the input. When ``False``,
    ``write()`` returns the number of bytes that were ``write()`` to the inner
    stream.
    """

    def __init__(
        self,
        decompressor,
        writer,
        write_size,
        write_return_read,
        closefd=True,
    ):
        decompressor._ensure_dctx()

        self._decompressor = decompressor
        self._writer = writer
        self._write_size = write_size
        self._write_return_read = bool(write_return_read)
        self._closefd = bool(closefd)
        self._entered = False
        self._closing = False
        self._closed = False

    def __enter__(self):
        if self._closed:
            raise ValueError("stream is closed")

        if self._entered:
            raise ZstdError("cannot __enter__ multiple times")

        self._entered = True

        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self._entered = False
        self.close()

        return False

    def __iter__(self):
        raise io.UnsupportedOperation()

    def __next__(self):
        raise io.UnsupportedOperation()

    def memory_size(self):
        return lib.ZSTD_sizeof_DCtx(self._decompressor._dctx)

    def close(self):
        if self._closed:
            return

        try:
            self._closing = True
            self.flush()
        finally:
            self._closing = False
            self._closed = True

        f = getattr(self._writer, "close", None)
        if self._closefd and f:
            f()

    @property
    def closed(self):
        return self._closed

    def fileno(self):
        f = getattr(self._writer, "fileno", None)
        if f:
            return f()
        else:
            raise OSError("fileno not available on underlying writer")

    def flush(self):
        if self._closed:
            raise ValueError("stream is closed")

        f = getattr(self._writer, "flush", None)
        if f and not self._closing:
            return f()

    def isatty(self):
        return False

    def readable(self):
        return False

    def readline(self, size=-1):
        raise io.UnsupportedOperation()

    def readlines(self, hint=-1):
        raise io.UnsupportedOperation()

    def seek(self, offset, whence=None):
        raise io.UnsupportedOperation()

    def seekable(self):
        return False

    def tell(self):
        raise io.UnsupportedOperation()

    def truncate(self, size=None):
        raise io.UnsupportedOperation()

    def writable(self):
        return True

    def writelines(self, lines):
        raise io.UnsupportedOperation()

    def read(self, size=-1):
        raise io.UnsupportedOperation()

    def readall(self):
        raise io.UnsupportedOperation()

    def readinto(self, b):
        raise io.UnsupportedOperation()

    def write(self, data):
        if self._closed:
            raise ValueError("stream is closed")

        total_write = 0

        in_buffer = ffi.new("ZSTD_inBuffer *")
        out_buffer = ffi.new("ZSTD_outBuffer *")

        data_buffer = ffi.from_buffer(data)
        in_buffer.src = data_buffer
        in_buffer.size = len(data_buffer)
        in_buffer.pos = 0

        dst_buffer = ffi.new("char[]", self._write_size)
        out_buffer.dst = dst_buffer
        out_buffer.size = len(dst_buffer)
        out_buffer.pos = 0

        dctx = self._decompressor._dctx

        while in_buffer.pos < in_buffer.size:
            zresult = lib.ZSTD_decompressStream(dctx, out_buffer, in_buffer)
            if lib.ZSTD_isError(zresult):
                raise ZstdError(
                    "zstd decompress error: %s" % _zstd_error(zresult)
                )

            if out_buffer.pos:
                self._writer.write(
                    ffi.buffer(out_buffer.dst, out_buffer.pos)[:]
                )
                total_write += out_buffer.pos
                out_buffer.pos = 0

        if self._write_return_read:
            return in_buffer.pos
        else:
            return total_write


class ZstdDecompressor(object):
    """
    Context for performing zstandard decompression.

    Each instance is essentially a wrapper around a ``ZSTD_DCtx`` from zstd's
    C API.

    An instance can compress data various ways. Instances can be used multiple
    times.

    The interface of this class is very similar to
    :py:class:`zstandard.ZstdCompressor` (by design).

    Assume that each ``ZstdDecompressor`` instance can only handle a single
    logical compression operation at the same time. i.e. if you call a method
    like ``decompressobj()`` to obtain multiple objects derived from the same
    ``ZstdDecompressor`` instance and attempt to use them simultaneously, errors
    will likely occur.

    If you need to perform multiple logical decompression operations and you
    can't guarantee those operations are temporally non-overlapping, you need
    to obtain multiple ``ZstdDecompressor`` instances.

    Unless specified otherwise, assume that no two methods of
    ``ZstdDecompressor`` instances can be called from multiple Python
    threads simultaneously. In other words, assume instances are not thread safe
    unless stated otherwise.

    :param dict_data:
       Compression dictionary to use.
    :param max_window_size:
       Sets an upper limit on the window size for decompression operations in
       kibibytes. This setting can be used to prevent large memory allocations
       for inputs using large compression windows.
    :param format:
       Set the format of data for the decoder.

       By default this is ``zstandard.FORMAT_ZSTD1``. It can be set to
       ``zstandard.FORMAT_ZSTD1_MAGICLESS`` to allow decoding frames without
       the 4 byte magic header. Not all decompression APIs support this mode.
    """

    def __init__(self, dict_data=None, max_window_size=0, format=FORMAT_ZSTD1):
        self._dict_data = dict_data
        self._max_window_size = max_window_size
        self._format = format

        dctx = lib.ZSTD_createDCtx()
        if dctx == ffi.NULL:
            raise MemoryError()

        self._dctx = dctx

        # Defer setting up garbage collection until full state is loaded so
        # the memory size is more accurate.
        try:
            self._ensure_dctx()
        finally:
            self._dctx = ffi.gc(
                dctx, lib.ZSTD_freeDCtx, size=lib.ZSTD_sizeof_DCtx(dctx)
            )

    def memory_size(self):
        """Size of decompression context, in bytes.

        >>> dctx = zstandard.ZstdDecompressor()
        >>> size = dctx.memory_size()
        """
        return lib.ZSTD_sizeof_DCtx(self._dctx)

    def decompress(
        self,
        data,
        max_output_size=0,
        read_across_frames=False,
        allow_extra_data=True,
    ):
        """
        Decompress data in a single operation.

        This method will decompress the input data in a single operation and
        return the decompressed data.

        The input bytes are expected to contain at least 1 full Zstandard frame
        (something compressed with :py:meth:`ZstdCompressor.compress` or
        similar). If the input does not contain a full frame, an exception will
        be raised.

        ``read_across_frames`` controls whether to read multiple zstandard
        frames in the input. When False, decompression stops after reading the
        first frame. This feature is not yet implemented but the argument is
        provided for forward API compatibility when the default is changed to
        True in a future release. For now, if you need to decompress multiple
        frames, use an API like :py:meth:`ZstdCompressor.stream_reader` with
        ``read_across_frames=True``.

        ``allow_extra_data`` controls how to handle extra input data after a
        fully decoded frame. If False, any extra data (which could be a valid
        zstd frame) will result in ``ZstdError`` being raised. If True, extra
        data is silently ignored. The default will likely change to False in a
        future release when ``read_across_frames`` defaults to True.

        If the input contains extra data after a full frame, that extra input
        data is silently ignored. This behavior is undesirable in many scenarios
        and will likely be changed or controllable in a future release (see
        #181).

        If the frame header of the compressed data does not contain the content
        size, ``max_output_size`` must be specified or ``ZstdError`` will be
        raised. An allocation of size ``max_output_size`` will be performed and an
        attempt will be made to perform decompression into that buffer. If the
        buffer is too small or cannot be allocated, ``ZstdError`` will be
        raised. The buffer will be resized if it is too large.

        Uncompressed data could be much larger than compressed data. As a result,
        calling this function could result in a very large memory allocation
        being performed to hold the uncompressed data. This could potentially
        result in ``MemoryError`` or system memory swapping. If you don't need
        the full output data in a single contiguous array in memory, consider
        using streaming decompression for more resilient memory behavior.

        Usage:

        >>> dctx = zstandard.ZstdDecompressor()
        >>> decompressed = dctx.decompress(data)

        If the compressed data doesn't have its content size embedded within it,
        decompression can be attempted by specifying the ``max_output_size``
        argument:

        >>> dctx = zstandard.ZstdDecompressor()
        >>> uncompressed = dctx.decompress(data, max_output_size=1048576)

        Ideally, ``max_output_size`` will be identical to the decompressed
        output size.

        .. important::

           If the exact size of decompressed data is unknown (not passed in
           explicitly and not stored in the zstd frame), for performance
           reasons it is encouraged to use a streaming API.

        :param data:
           Compressed data to decompress.
        :param max_output_size:
           Integer max size of response.

           If ``0``, there is no limit and we can attempt to allocate an output
           buffer of infinite size.
        :return:
           ``bytes`` representing decompressed output.
        """

        if read_across_frames:
            raise ZstdError(
                "ZstdDecompressor.read_across_frames=True is not yet implemented"
            )

        self._ensure_dctx()

        data_buffer = ffi.from_buffer(data)

        output_size = lib.ZSTD_getFrameContentSize(
            data_buffer, len(data_buffer)
        )

        if output_size == lib.ZSTD_CONTENTSIZE_ERROR:
            raise ZstdError("error determining content size from frame header")
        elif output_size == 0:
            return b""
        elif output_size == lib.ZSTD_CONTENTSIZE_UNKNOWN:
            if not max_output_size:
                raise ZstdError(
                    "could not determine content size in frame header"
                )

            result_buffer = ffi.new("char[]", max_output_size)
            result_size = max_output_size
            output_size = 0
        else:
            result_buffer = ffi.new("char[]", output_size)
            result_size = output_size

        out_buffer = ffi.new("ZSTD_outBuffer *")
        out_buffer.dst = result_buffer
        out_buffer.size = result_size
        out_buffer.pos = 0

        in_buffer = ffi.new("ZSTD_inBuffer *")
        in_buffer.src = data_buffer
        in_buffer.size = len(data_buffer)
        in_buffer.pos = 0

        zresult = lib.ZSTD_decompressStream(self._dctx, out_buffer, in_buffer)
        if lib.ZSTD_isError(zresult):
            raise ZstdError("decompression error: %s" % _zstd_error(zresult))
        elif zresult:
            raise ZstdError(
                "decompression error: did not decompress full frame"
            )
        elif output_size and out_buffer.pos != output_size:
            raise ZstdError(
                "decompression error: decompressed %d bytes; expected %d"
                % (zresult, output_size)
            )
        elif not allow_extra_data and in_buffer.pos < in_buffer.size:
            count = in_buffer.size - in_buffer.pos

            raise ZstdError(
                "compressed input contains %d bytes of unused data, which is disallowed"
                % count
            )

        return ffi.buffer(result_buffer, out_buffer.pos)[:]

    def stream_reader(
        self,
        source,
        read_size=DECOMPRESSION_RECOMMENDED_INPUT_SIZE,
        read_across_frames=False,
        closefd=True,
    ):
        """
        Read-only stream wrapper that performs decompression.

        This method obtains an object that conforms to the ``io.RawIOBase``
        interface and performs transparent decompression via ``read()``
        operations. Source data is obtained by calling ``read()`` on a
        source stream or object implementing the buffer protocol.

        See :py:class:`zstandard.ZstdDecompressionReader` for more documentation
        and usage examples.

        :param source:
           Source of compressed data to decompress. Can be any object
           with a ``read(size)`` method or that conforms to the buffer protocol.
        :param read_size:
           Integer number of bytes to read from the source and feed into the
           compressor at a time.
        :param read_across_frames:
           Whether to read data across multiple zstd frames. If False,
           decompression is stopped at frame boundaries.
        :param closefd:
           Whether to close the source stream when this instance is closed.
        :return:
           :py:class:`zstandard.ZstdDecompressionReader`.
        """
        self._ensure_dctx()
        return ZstdDecompressionReader(
            self, source, read_size, read_across_frames, closefd=closefd
        )

    def decompressobj(
        self,
        write_size=DECOMPRESSION_RECOMMENDED_OUTPUT_SIZE,
        read_across_frames=False,
    ):
        """Obtain a standard library compatible incremental decompressor.

        See :py:class:`ZstdDecompressionObj` for more documentation
        and usage examples.

        :param write_size: size of internal output buffer to collect decompressed
          chunks in.
        :param read_across_frames: whether to read across multiple zstd frames.
          If False, reading stops after 1 frame and subsequent decompress
          attempts will raise an exception.
        :return:
           :py:class:`zstandard.ZstdDecompressionObj`
        """
        if write_size < 1:
            raise ValueError("write_size must be positive")

        self._ensure_dctx()
        return ZstdDecompressionObj(
            self, write_size=write_size, read_across_frames=read_across_frames
        )

    def read_to_iter(
        self,
        reader,
        read_size=DECOMPRESSION_RECOMMENDED_INPUT_SIZE,
        write_size=DECOMPRESSION_RECOMMENDED_OUTPUT_SIZE,
        skip_bytes=0,
    ):
        """Read compressed data to an iterator of uncompressed chunks.

        This method will read data from ``reader``, feed it to a decompressor,
        and emit ``bytes`` chunks representing the decompressed result.

        >>> dctx = zstandard.ZstdDecompressor()
        >>> for chunk in dctx.read_to_iter(fh):
        ...     # Do something with original data.

        ``read_to_iter()`` accepts an object with a ``read(size)`` method that
        will return compressed bytes or an object conforming to the buffer
        protocol.

        ``read_to_iter()`` returns an iterator whose elements are chunks of the
        decompressed data.

        The size of requested ``read()`` from the source can be specified:

        >>> dctx = zstandard.ZstdDecompressor()
        >>> for chunk in dctx.read_to_iter(fh, read_size=16384):
        ...    pass

        It is also possible to skip leading bytes in the input data:

        >>> dctx = zstandard.ZstdDecompressor()
        >>> for chunk in dctx.read_to_iter(fh, skip_bytes=1):
        ...    pass

        .. tip::

           Skipping leading bytes is useful if the source data contains extra
           *header* data. Traditionally, you would need to create a slice or
           ``memoryview`` of the data you want to decompress. This would create
           overhead. It is more efficient to pass the offset into this API.

        Similarly to :py:meth:`ZstdCompressor.read_to_iter`, the consumer of the
        iterator controls when data is decompressed. If the iterator isn't consumed,
        decompression is put on hold.

        When ``read_to_iter()`` is passed an object conforming to the buffer protocol,
        the behavior may seem similar to what occurs when the simple decompression
        API is used. However, this API works when the decompressed size is unknown.
        Furthermore, if feeding large inputs, the decompressor will work in chunks
        instead of performing a single operation.

        :param reader:
           Source of compressed data. Can be any object with a
           ``read(size)`` method or any object conforming to the buffer
           protocol.
        :param read_size:
           Integer size of data chunks to read from ``reader`` and feed into
           the decompressor.
        :param write_size:
           Integer size of data chunks to emit from iterator.
        :param skip_bytes:
           Integer number of bytes to skip over before sending data into
           the decompressor.
        :return:
           Iterator of ``bytes`` representing uncompressed data.
        """

        if skip_bytes >= read_size:
            raise ValueError("skip_bytes must be smaller than read_size")

        if hasattr(reader, "read"):
            have_read = True
        elif hasattr(reader, "__getitem__"):
            have_read = False
            buffer_offset = 0
            size = len(reader)
        else:
            raise ValueError(
                "must pass an object with a read() method or "
                "conforms to buffer protocol"
            )

        if skip_bytes:
            if have_read:
                reader.read(skip_bytes)
            else:
                if skip_bytes > size:
                    raise ValueError("skip_bytes larger than first input chunk")

                buffer_offset = skip_bytes

        self._ensure_dctx()

        in_buffer = ffi.new("ZSTD_inBuffer *")
        out_buffer = ffi.new("ZSTD_outBuffer *")

        dst_buffer = ffi.new("char[]", write_size)
        out_buffer.dst = dst_buffer
        out_buffer.size = len(dst_buffer)
        out_buffer.pos = 0

        while True:
            assert out_buffer.pos == 0

            if have_read:
                read_result = reader.read(read_size)
            else:
                remaining = size - buffer_offset
                slice_size = min(remaining, read_size)
                read_result = reader[buffer_offset : buffer_offset + slice_size]
                buffer_offset += slice_size

            # No new input. Break out of read loop.
            if not read_result:
                break

            # Feed all read data into decompressor and emit output until
            # exhausted.
            read_buffer = ffi.from_buffer(read_result)
            in_buffer.src = read_buffer
            in_buffer.size = len(read_buffer)
            in_buffer.pos = 0

            while in_buffer.pos < in_buffer.size:
                assert out_buffer.pos == 0

                zresult = lib.ZSTD_decompressStream(
                    self._dctx, out_buffer, in_buffer
                )
                if lib.ZSTD_isError(zresult):
                    raise ZstdError(
                        "zstd decompress error: %s" % _zstd_error(zresult)
                    )

                if out_buffer.pos:
                    data = ffi.buffer(out_buffer.dst, out_buffer.pos)[:]
                    out_buffer.pos = 0
                    yield data

                if zresult == 0:
                    return

            # Repeat loop to collect more input data.
            continue

        # If we get here, input is exhausted.

    def stream_writer(
        self,
        writer,
        write_size=DECOMPRESSION_RECOMMENDED_OUTPUT_SIZE,
        write_return_read=True,
        closefd=True,
    ):
        """
        Push-based stream wrapper that performs decompression.

        This method constructs a stream wrapper that conforms to the
        ``io.RawIOBase`` interface and performs transparent decompression
        when writing to a wrapper stream.

        See :py:class:`zstandard.ZstdDecompressionWriter` for more documentation
        and usage examples.

        :param writer:
           Destination for decompressed output. Can be any object with a
           ``write(data)``.
        :param write_size:
           Integer size of chunks to ``write()`` to ``writer``.
        :param write_return_read:
           Whether ``write()`` should return the number of bytes of input
           consumed. If False, ``write()`` returns the number of bytes sent
           to the inner stream.
        :param closefd:
           Whether to ``close()`` the inner stream when this stream is closed.
        :return:
           :py:class:`zstandard.ZstdDecompressionWriter`
        """
        if not hasattr(writer, "write"):
            raise ValueError("must pass an object with a write() method")

        return ZstdDecompressionWriter(
            self,
            writer,
            write_size,
            write_return_read,
            closefd=closefd,
        )

    def copy_stream(
        self,
        ifh,
        ofh,
        read_size=DECOMPRESSION_RECOMMENDED_INPUT_SIZE,
        write_size=DECOMPRESSION_RECOMMENDED_OUTPUT_SIZE,
    ):
        """
        Copy data between streams, decompressing in the process.

        Compressed data will be read from ``ifh``, decompressed, and written
        to ``ofh``.

        >>> dctx = zstandard.ZstdDecompressor()
        >>> dctx.copy_stream(ifh, ofh)

        e.g. to decompress a file to another file:

        >>> dctx = zstandard.ZstdDecompressor()
        >>> with open(input_path, 'rb') as ifh, open(output_path, 'wb') as ofh:
        ...     dctx.copy_stream(ifh, ofh)

        The size of chunks being ``read()`` and ``write()`` from and to the
        streams can be specified:

        >>> dctx = zstandard.ZstdDecompressor()
        >>> dctx.copy_stream(ifh, ofh, read_size=8192, write_size=16384)

        :param ifh:
           Source stream to read compressed data from.

           Must have a ``read()`` method.
        :param ofh:
           Destination stream to write uncompressed data to.

           Must have a ``write()`` method.
        :param read_size:
           The number of bytes to ``read()`` from the source in a single
           operation.
        :param write_size:
           The number of bytes to ``write()`` to the destination in a single
           operation.
        :return:
           2-tuple of integers representing the number of bytes read and
           written, respectively.
        """

        if not hasattr(ifh, "read"):
            raise ValueError("first argument must have a read() method")
        if not hasattr(ofh, "write"):
            raise ValueError("second argument must have a write() method")

        self._ensure_dctx()

        in_buffer = ffi.new("ZSTD_inBuffer *")
        out_buffer = ffi.new("ZSTD_outBuffer *")

        dst_buffer = ffi.new("char[]", write_size)
        out_buffer.dst = dst_buffer
        out_buffer.size = write_size
        out_buffer.pos = 0

        total_read, total_write = 0, 0

        # Read all available input.
        while True:
            data = ifh.read(read_size)
            if not data:
                break

            data_buffer = ffi.from_buffer(data)
            total_read += len(data_buffer)
            in_buffer.src = data_buffer
            in_buffer.size = len(data_buffer)
            in_buffer.pos = 0

            # Flush all read data to output.
            while in_buffer.pos < in_buffer.size:
                zresult = lib.ZSTD_decompressStream(
                    self._dctx, out_buffer, in_buffer
                )
                if lib.ZSTD_isError(zresult):
                    raise ZstdError(
                        "zstd decompressor error: %s" % _zstd_error(zresult)
                    )

                if out_buffer.pos:
                    ofh.write(ffi.buffer(out_buffer.dst, out_buffer.pos))
                    total_write += out_buffer.pos
                    out_buffer.pos = 0

            # Continue loop to keep reading.

        return total_read, total_write

    def decompress_content_dict_chain(self, frames):
        """
        Decompress a series of frames using the content dictionary chaining technique.

        Such a list of frames is produced by compressing discrete inputs where
        each non-initial input is compressed with a *prefix* dictionary consisting
        of the content of the previous input.

        For example, say you have the following inputs:

        >>> inputs = [b"input 1", b"input 2", b"input 3"]

        The zstd frame chain consists of:

        1. ``b"input 1"`` compressed in standalone/discrete mode
        2. ``b"input 2"`` compressed using ``b"input 1"`` as a *prefix* dictionary
        3. ``b"input 3"`` compressed using ``b"input 2"`` as a *prefix* dictionary

        Each zstd frame **must** have the content size written.

        The following Python code can be used to produce a *prefix dictionary chain*:

        >>> def make_chain(inputs):
        ...    frames = []
        ...
        ...    # First frame is compressed in standalone/discrete mode.
        ...    zctx = zstandard.ZstdCompressor()
        ...    frames.append(zctx.compress(inputs[0]))
        ...
        ...    # Subsequent frames use the previous fulltext as a prefix dictionary
        ...    for i, raw in enumerate(inputs[1:]):
        ...        dict_data = zstandard.ZstdCompressionDict(
        ...            inputs[i], dict_type=zstandard.DICT_TYPE_RAWCONTENT)
        ...        zctx = zstandard.ZstdCompressor(dict_data=dict_data)
        ...        frames.append(zctx.compress(raw))
        ...
        ...    return frames

        ``decompress_content_dict_chain()`` returns the uncompressed data of the last
        element in the input chain.

        .. note::

           It is possible to implement *prefix dictionary chain* decompression
           on top of other APIs. However, this function will likely be faster -
           especially for long input chains - as it avoids the overhead of
           instantiating and passing around intermediate objects between
           multiple functions.

        :param frames:
           List of ``bytes`` holding compressed zstd frames.
        :return:
        """
        if not isinstance(frames, list):
            raise TypeError("argument must be a list")

        if not frames:
            raise ValueError("empty input chain")

        # First chunk should not be using a dictionary. We handle it specially.
        chunk = frames[0]
        if not isinstance(chunk, bytes):
            raise ValueError("chunk 0 must be bytes")

        # All chunks should be zstd frames and should have content size set.
        chunk_buffer = ffi.from_buffer(chunk)
        params = ffi.new("ZSTD_frameHeader *")
        zresult = lib.ZSTD_getFrameHeader(
            params, chunk_buffer, len(chunk_buffer)
        )
        if lib.ZSTD_isError(zresult):
            raise ValueError("chunk 0 is not a valid zstd frame")
        elif zresult:
            raise ValueError("chunk 0 is too small to contain a zstd frame")

        if params.frameContentSize == lib.ZSTD_CONTENTSIZE_UNKNOWN:
            raise ValueError("chunk 0 missing content size in frame")

        self._ensure_dctx(load_dict=False)

        last_buffer = ffi.new("char[]", params.frameContentSize)

        out_buffer = ffi.new("ZSTD_outBuffer *")
        out_buffer.dst = last_buffer
        out_buffer.size = len(last_buffer)
        out_buffer.pos = 0

        in_buffer = ffi.new("ZSTD_inBuffer *")
        in_buffer.src = chunk_buffer
        in_buffer.size = len(chunk_buffer)
        in_buffer.pos = 0

        zresult = lib.ZSTD_decompressStream(self._dctx, out_buffer, in_buffer)
        if lib.ZSTD_isError(zresult):
            raise ZstdError(
                "could not decompress chunk 0: %s" % _zstd_error(zresult)
            )
        elif zresult:
            raise ZstdError("chunk 0 did not decompress full frame")

        # Special case of chain length of 1
        if len(frames) == 1:
            return ffi.buffer(last_buffer, len(last_buffer))[:]

        i = 1
        while i < len(frames):
            chunk = frames[i]
            if not isinstance(chunk, bytes):
                raise ValueError("chunk %d must be bytes" % i)

            chunk_buffer = ffi.from_buffer(chunk)
            zresult = lib.ZSTD_getFrameHeader(
                params, chunk_buffer, len(chunk_buffer)
            )
            if lib.ZSTD_isError(zresult):
                raise ValueError("chunk %d is not a valid zstd frame" % i)
            elif zresult:
                raise ValueError(
                    "chunk %d is too small to contain a zstd frame" % i
                )

            if params.frameContentSize == lib.ZSTD_CONTENTSIZE_UNKNOWN:
                raise ValueError("chunk %d missing content size in frame" % i)

            dest_buffer = ffi.new("char[]", params.frameContentSize)

            out_buffer.dst = dest_buffer
            out_buffer.size = len(dest_buffer)
            out_buffer.pos = 0

            in_buffer.src = chunk_buffer
            in_buffer.size = len(chunk_buffer)
            in_buffer.pos = 0

            zresult = lib.ZSTD_decompressStream(
                self._dctx, out_buffer, in_buffer
            )
            if lib.ZSTD_isError(zresult):
                raise ZstdError(
                    "could not decompress chunk %d: %s" % _zstd_error(zresult)
                )
            elif zresult:
                raise ZstdError("chunk %d did not decompress full frame" % i)

            last_buffer = dest_buffer
            i += 1

        return ffi.buffer(last_buffer, len(last_buffer))[:]

    def multi_decompress_to_buffer(
        self, frames, decompressed_sizes=None, threads=0
    ):
        """
        Decompress multiple zstd frames to output buffers as a single operation.

        (Experimental. Not available in CFFI backend.)

        Compressed frames can be passed to the function as a
        ``BufferWithSegments``, a ``BufferWithSegmentsCollection``, or as a
        list containing objects that conform to the buffer protocol. For best
        performance, pass a ``BufferWithSegmentsCollection`` or a
        ``BufferWithSegments``, as minimal input validation will be done for
        that type. If calling from Python (as opposed to C), constructing one
        of these instances may add overhead cancelling out the performance
        overhead of validation for list inputs.

        Returns a ``BufferWithSegmentsCollection`` containing the decompressed
        data. All decompressed data is allocated in a single memory buffer. The
        ``BufferWithSegments`` instance tracks which objects are at which offsets
        and their respective lengths.

        >>> dctx = zstandard.ZstdDecompressor()
        >>> results = dctx.multi_decompress_to_buffer([b'...', b'...'])

        The decompressed size of each frame MUST be discoverable. It can either be
        embedded within the zstd frame or passed in via the ``decompressed_sizes``
        argument.

        The ``decompressed_sizes`` argument is an object conforming to the buffer
        protocol which holds an array of 64-bit unsigned integers in the machine's
        native format defining the decompressed sizes of each frame. If this argument
        is passed, it avoids having to scan each frame for its decompressed size.
        This frame scanning can add noticeable overhead in some scenarios.

        >>> frames = [...]
        >>> sizes = struct.pack('=QQQQ', len0, len1, len2, len3)
        >>>
        >>> dctx = zstandard.ZstdDecompressor()
        >>> results = dctx.multi_decompress_to_buffer(frames, decompressed_sizes=sizes)

        .. note::

           It is possible to pass a ``mmap.mmap()`` instance into this function by
           wrapping it with a ``BufferWithSegments`` instance (which will define the
           offsets of frames within the memory mapped region).

        This function is logically equivalent to performing
        :py:meth:`ZstdCompressor.decompress` on each input frame and returning the
        result.

        This function exists to perform decompression on multiple frames as fast
        as possible by having as little overhead as possible. Since decompression is
        performed as a single operation and since the decompressed output is stored in
        a single buffer, extra memory allocations, Python objects, and Python function
        calls are avoided. This is ideal for scenarios where callers know up front that
        they need to access data for multiple frames, such as when  *delta chains* are
        being used.

        Currently, the implementation always spawns multiple threads when requested,
        even if the amount of work to do is small. In the future, it will be smarter
        about avoiding threads and their associated overhead when the amount of
        work to do is small.

        :param frames:
           Source defining zstd frames to decompress.
        :param decompressed_sizes:
           Array of integers representing sizes of decompressed zstd frames.
        :param threads:
           How many threads to use for decompression operations.

           Negative values will use the same number of threads as logical CPUs
           on the machine. Values ``0`` or ``1`` use a single thread.
        :return:
           ``BufferWithSegmentsCollection``
        """
        raise NotImplementedError()

    def _ensure_dctx(self, load_dict=True):
        lib.ZSTD_DCtx_reset(self._dctx, lib.ZSTD_reset_session_only)

        if self._max_window_size:
            zresult = lib.ZSTD_DCtx_setMaxWindowSize(
                self._dctx, self._max_window_size
            )
            if lib.ZSTD_isError(zresult):
                raise ZstdError(
                    "unable to set max window size: %s" % _zstd_error(zresult)
                )

        zresult = lib.ZSTD_DCtx_setParameter(
            self._dctx, lib.ZSTD_d_format, self._format
        )
        if lib.ZSTD_isError(zresult):
            raise ZstdError(
                "unable to set decoding format: %s" % _zstd_error(zresult)
            )

        if self._dict_data and load_dict:
            zresult = lib.ZSTD_DCtx_refDDict(self._dctx, self._dict_data._ddict)
            if lib.ZSTD_isError(zresult):
                raise ZstdError(
                    "unable to reference prepared dictionary: %s"
                    % _zstd_error(zresult)
                )
