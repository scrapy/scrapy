# Copyright 2016 The Brotli Authors. All rights reserved.
#
# Distributed under MIT license.
# See file LICENSE for detail or copy at https://opensource.org/licenses/MIT

"""Functions to compress and decompress data using the Brotli library."""

import _brotli

# The library version.
version = __version__ = _brotli.__version__

# The compression mode.
MODE_GENERIC = _brotli.MODE_GENERIC
MODE_TEXT = _brotli.MODE_TEXT
MODE_FONT = _brotli.MODE_FONT

# The Compressor object.
Compressor = _brotli.Compressor

# The Decompressor object.
Decompressor = _brotli.Decompressor

# Compress a byte string.
def compress(string, mode=MODE_GENERIC, quality=11, lgwin=22, lgblock=0):
    """Compress a byte string.

    Args:
      string (bytes): The input data.
      mode (int, optional): The compression mode can be MODE_GENERIC (default),
        MODE_TEXT (for UTF-8 format text input) or MODE_FONT (for WOFF 2.0).
      quality (int, optional): Controls the compression-speed vs compression-
        density tradeoff. The higher the quality, the slower the compression.
        Range is 0 to 11. Defaults to 11.
      lgwin (int, optional): Base 2 logarithm of the sliding window size. Range
        is 10 to 24. Defaults to 22.
      lgblock (int, optional): Base 2 logarithm of the maximum input block size.
        Range is 16 to 24. If set to 0, the value will be set based on the
        quality. Defaults to 0.

    Returns:
      The compressed byte string.

    Raises:
      brotli.error: If arguments are invalid, or compressor fails.
    """
    compressor = Compressor(mode=mode, quality=quality, lgwin=lgwin,
                            lgblock=lgblock)
    return compressor.process(string) + compressor.finish()

# Decompress a compressed byte string.
decompress = _brotli.decompress

# Raised if compression or decompression fails.
error = _brotli.error
