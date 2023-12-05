# Copyright (c) 2017-present, Gregory Szorc
# All rights reserved.
#
# This software may be modified and distributed under the terms
# of the BSD license. See the LICENSE file for details.

"""Python interface to the Zstandard (zstd) compression library."""

from __future__ import absolute_import, unicode_literals

# This module serves 2 roles:
#
# 1) Export the C or CFFI "backend" through a central module.
# 2) Implement additional functionality built on top of C or CFFI backend.

import builtins
import io
import os
import platform

from typing import ByteString

# Some Python implementations don't support C extensions. That's why we have
# a CFFI implementation in the first place. The code here import one of our
# "backends" then re-exports the symbols from this module. For convenience,
# we support falling back to the CFFI backend if the C extension can't be
# imported. But for performance reasons, we only do this on unknown Python
# implementation. Notably, for CPython we require the C extension by default.
# Because someone will inevitably want special behavior, the behavior is
# configurable via an environment variable. A potentially better way to handle
# this is to import a special ``__importpolicy__`` module or something
# defining a variable and `setup.py` could write the file with whatever
# policy was specified at build time. Until someone needs it, we go with
# the hacky but simple environment variable approach.
_module_policy = os.environ.get("PYTHON_ZSTANDARD_IMPORT_POLICY", "default")

if _module_policy == "default":
    if platform.python_implementation() in ("CPython",):
        from .backend_c import *  # type: ignore

        backend = "cext"
    elif platform.python_implementation() in ("PyPy",):
        from .backend_cffi import *  # type: ignore

        backend = "cffi"
    else:
        try:
            from .backend_c import *

            backend = "cext"
        except ImportError:
            from .backend_cffi import *

            backend = "cffi"
elif _module_policy == "cffi_fallback":
    try:
        from .backend_c import *

        backend = "cext"
    except ImportError:
        from .backend_cffi import *

        backend = "cffi"
elif _module_policy == "rust":
    from .backend_rust import *  # type: ignore

    backend = "rust"
elif _module_policy == "cext":
    from .backend_c import *

    backend = "cext"
elif _module_policy == "cffi":
    from .backend_cffi import *

    backend = "cffi"
else:
    raise ImportError(
        "unknown module import policy: %s; use default, cffi_fallback, "
        "cext, or cffi" % _module_policy
    )

# Keep this in sync with python-zstandard.h, rust-ext/src/lib.rs, and debian/changelog.
__version__ = "0.22.0"

_MODE_CLOSED = 0
_MODE_READ = 1
_MODE_WRITE = 2


def open(
    filename,
    mode="rb",
    cctx=None,
    dctx=None,
    encoding=None,
    errors=None,
    newline=None,
    closefd=None,
):
    """Create a file object with zstd (de)compression.

    The object returned from this function will be a
    :py:class:`ZstdDecompressionReader` if opened for reading in binary mode,
    a :py:class:`ZstdCompressionWriter` if opened for writing in binary mode,
    or an ``io.TextIOWrapper`` if opened for reading or writing in text mode.

    :param filename:
       ``bytes``, ``str``, or ``os.PathLike`` defining a file to open or a
       file object (with a ``read()`` or ``write()`` method).
    :param mode:
       ``str`` File open mode. Accepts any of the open modes recognized by
       ``open()``.
    :param cctx:
       ``ZstdCompressor`` to use for compression. If not specified and file
       is opened for writing, the default ``ZstdCompressor`` will be used.
    :param dctx:
       ``ZstdDecompressor`` to use for decompression. If not specified and file
       is opened for reading, the default ``ZstdDecompressor`` will be used.
    :param encoding:
        ``str`` that defines text encoding to use when file is opened in text
        mode.
    :param errors:
       ``str`` defining text encoding error handling mode.
    :param newline:
       ``str`` defining newline to use in text mode.
    :param closefd:
       ``bool`` whether to close the file when the returned object is closed.
        Only used if a file object is passed. If a filename is specified, the
        opened file is always closed when the returned object is closed.
    """
    normalized_mode = mode.replace("t", "")

    if normalized_mode in ("r", "rb"):
        dctx = dctx or ZstdDecompressor()
        open_mode = "r"
        raw_open_mode = "rb"
    elif normalized_mode in ("w", "wb", "a", "ab", "x", "xb"):
        cctx = cctx or ZstdCompressor()
        open_mode = "w"
        raw_open_mode = normalized_mode
        if not raw_open_mode.endswith("b"):
            raw_open_mode = raw_open_mode + "b"
    else:
        raise ValueError("Invalid mode: {!r}".format(mode))

    if hasattr(os, "PathLike"):
        types = (str, bytes, os.PathLike)
    else:
        types = (str, bytes)

    if isinstance(filename, types):  # type: ignore
        inner_fh = builtins.open(filename, raw_open_mode)
        closefd = True
    elif hasattr(filename, "read") or hasattr(filename, "write"):
        inner_fh = filename
        closefd = bool(closefd)
    else:
        raise TypeError(
            "filename must be a str, bytes, file or PathLike object"
        )

    if open_mode == "r":
        fh = dctx.stream_reader(inner_fh, closefd=closefd)
    elif open_mode == "w":
        fh = cctx.stream_writer(inner_fh, closefd=closefd)
    else:
        raise RuntimeError("logic error in zstandard.open() handling open mode")

    if "b" not in normalized_mode:
        return io.TextIOWrapper(
            fh, encoding=encoding, errors=errors, newline=newline
        )
    else:
        return fh


def compress(data: ByteString, level: int = 3) -> bytes:
    """Compress source data using the zstd compression format.

    This performs one-shot compression using basic/default compression
    settings.

    This method is provided for convenience and is equivalent to calling
    ``ZstdCompressor(level=level).compress(data)``.

    If you find yourself calling this function in a tight loop,
    performance will be greater if you construct a single ``ZstdCompressor``
    and repeatedly call ``compress()`` on it.
    """
    cctx = ZstdCompressor(level=level)

    return cctx.compress(data)


def decompress(data: ByteString, max_output_size: int = 0) -> bytes:
    """Decompress a zstd frame into its original data.

    This performs one-shot decompression using basic/default compression
    settings.

    This method is provided for convenience and is equivalent to calling
    ``ZstdDecompressor().decompress(data, max_output_size=max_output_size)``.

    If you find yourself calling this function in a tight loop, performance
    will be greater if you construct a single ``ZstdDecompressor`` and
    repeatedly call ``decompress()`` on it.
    """
    dctx = ZstdDecompressor()

    return dctx.decompress(data, max_output_size=max_output_size)
