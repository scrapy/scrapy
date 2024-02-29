import pytest

from scrapy.downloadermiddlewares.httpcompression import ACCEPTED_ENCODINGS


def test_brotlipy():
    """Test that brotli support is not enabled unless brotli is installed, even
    if brotlipy is installed."""
    try:
        import brotli
    except ImportError:
        pytest.skip("No brotli-providing package installed.")
    if hasattr(brotli.Decompressor, "process"):
        pytest.skip("brotlipy is not installed, brotli is.")
    assert b"br" not in ACCEPTED_ENCODINGS
