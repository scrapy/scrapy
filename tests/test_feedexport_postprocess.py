from __future__ import annotations

import bz2
import gzip
import lzma
import marshal
import pickle
import sys
import tempfile
from io import BytesIO
from typing import IO, TYPE_CHECKING

import pytest

from scrapy.extensions.postprocessing import PostProcessingManager
from tests.utils.decorators import coroutine_test
from tests.utils.feedexport import export_by_format, export_by_path, unique_path

if TYPE_CHECKING:
    from pathlib import Path

    from tests.mockserver.http import MockServer


class TestFeedPostProcessedExports:
    items = [{"foo": "bar"}]
    expected = b"foo\r\nbar\r\n"

    class MyPlugin1:
        def __init__(self, file, feed_options):
            self.file = file
            self.feed_options = feed_options
            self.char = self.feed_options.get("plugin1_char", b"")

        def write(self, data):
            written_count = self.file.write(data)
            written_count += self.file.write(self.char)
            return written_count

        def close(self):
            self.file.close()

    def get_gzip_compressed(
        self,
        data: bytes,
        compresslevel: int = 9,
        mtime: int = 0,
        filename: str = "",
    ) -> bytes:
        data_stream = BytesIO()
        gzipf = gzip.GzipFile(
            fileobj=data_stream,
            filename=filename,
            mtime=mtime,
            compresslevel=compresslevel,
            mode="wb",
        )
        gzipf.write(data)
        gzipf.close()
        data_stream.seek(0)
        return data_stream.read()

    def test_tell_reports_target_file_position(self):
        """Exporters that wrap the file they get, e.g. through
        :class:`io.TextIOWrapper`, need it to report a position."""
        file = BytesIO()
        manager = PostProcessingManager([self.MyPlugin1], file, {})
        assert manager.tell() == 0
        manager.write(b"foo")
        assert manager.tell() == file.tell() == 3

    @coroutine_test
    async def test_gzip_plugin(self, mockserver: MockServer, tmp_path: Path) -> None:
        filename = tmp_path / "gzip_file"

        settings = {
            "FEEDS": {
                filename: {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                },
            },
        }

        data = await export_by_path(mockserver, self.items, settings)
        try:
            gzip.decompress(data[filename])
        except OSError:
            pytest.fail("Received invalid gzip data.")

    @coroutine_test
    async def test_gzip_plugin_compresslevel(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        filename_to_compressed = {
            tmp_path / "compresslevel_0": self.get_gzip_compressed(
                self.expected, compresslevel=0
            ),
            tmp_path / "compresslevel_9": self.get_gzip_compressed(
                self.expected, compresslevel=9
            ),
        }

        settings = {
            "FEEDS": {
                tmp_path / "compresslevel_0": {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                    "gzip_compresslevel": 0,
                    "gzip_mtime": 0,
                    "gzip_filename": "",
                },
                tmp_path / "compresslevel_9": {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                    "gzip_compresslevel": 9,
                    "gzip_mtime": 0,
                    "gzip_filename": "",
                },
            },
        }

        data = await export_by_path(mockserver, self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = gzip.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @coroutine_test
    async def test_gzip_plugin_mtime(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        filename_to_compressed = {
            tmp_path / "mtime_123": self.get_gzip_compressed(self.expected, mtime=123),
            tmp_path / "mtime_123456789": self.get_gzip_compressed(
                self.expected, mtime=123456789
            ),
        }

        settings = {
            "FEEDS": {
                tmp_path / "mtime_123": {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                    "gzip_mtime": 123,
                    "gzip_filename": "",
                },
                tmp_path / "mtime_123456789": {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                    "gzip_mtime": 123456789,
                    "gzip_filename": "",
                },
            },
        }

        data = await export_by_path(mockserver, self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = gzip.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @coroutine_test
    async def test_gzip_plugin_filename(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        filename_to_compressed = {
            tmp_path / "filename_FILE1": self.get_gzip_compressed(
                self.expected, filename="FILE1"
            ),
            tmp_path / "filename_FILE2": self.get_gzip_compressed(
                self.expected, filename="FILE2"
            ),
        }

        settings = {
            "FEEDS": {
                tmp_path / "filename_FILE1": {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                    "gzip_mtime": 0,
                    "gzip_filename": "FILE1",
                },
                tmp_path / "filename_FILE2": {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                    "gzip_mtime": 0,
                    "gzip_filename": "FILE2",
                },
            },
        }

        data = await export_by_path(mockserver, self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = gzip.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @coroutine_test
    async def test_lzma_plugin(self, mockserver: MockServer, tmp_path: Path) -> None:
        filename = tmp_path / "lzma_file"

        settings = {
            "FEEDS": {
                filename: {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                },
            },
        }

        data = await export_by_path(mockserver, self.items, settings)
        try:
            lzma.decompress(data[filename])
        except lzma.LZMAError:
            pytest.fail("Received invalid lzma data.")

    @coroutine_test
    async def test_lzma_plugin_format(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        filename_to_compressed = {
            tmp_path / "format_FORMAT_XZ": lzma.compress(
                self.expected, format=lzma.FORMAT_XZ
            ),
            tmp_path / "format_FORMAT_ALONE": lzma.compress(
                self.expected, format=lzma.FORMAT_ALONE
            ),
        }

        settings = {
            "FEEDS": {
                tmp_path / "format_FORMAT_XZ": {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_format": lzma.FORMAT_XZ,
                },
                tmp_path / "format_FORMAT_ALONE": {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_format": lzma.FORMAT_ALONE,
                },
            },
        }

        data = await export_by_path(mockserver, self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = lzma.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @coroutine_test
    async def test_lzma_plugin_check(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        filename_to_compressed = {
            tmp_path / "check_CHECK_NONE": lzma.compress(
                self.expected, check=lzma.CHECK_NONE
            ),
            tmp_path / "CHECK_SHA256": lzma.compress(
                self.expected, check=lzma.CHECK_SHA256
            ),
        }

        settings = {
            "FEEDS": {
                tmp_path / "check_CHECK_NONE": {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_check": lzma.CHECK_NONE,
                },
                tmp_path / "CHECK_SHA256": {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_check": lzma.CHECK_SHA256,
                },
            },
        }

        data = await export_by_path(mockserver, self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = lzma.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @coroutine_test
    async def test_lzma_plugin_preset(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        filename_to_compressed = {
            tmp_path / "preset_PRESET_0": lzma.compress(self.expected, preset=0),
            tmp_path / "preset_PRESET_9": lzma.compress(self.expected, preset=9),
        }

        settings = {
            "FEEDS": {
                tmp_path / "preset_PRESET_0": {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_preset": 0,
                },
                tmp_path / "preset_PRESET_9": {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_preset": 9,
                },
            },
        }

        data = await export_by_path(mockserver, self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = lzma.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @coroutine_test
    async def test_lzma_plugin_filters(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        if "PyPy" in sys.version:
            # https://foss.heptapod.net/pypy/pypy/-/issues/3527
            pytest.skip("lzma filters doesn't work in PyPy")

        filters = [{"id": lzma.FILTER_LZMA2}]
        compressed = lzma.compress(self.expected, filters=filters)
        filename = tmp_path / "filters"

        settings = {
            "FEEDS": {
                filename: {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_filters": filters,
                },
            },
        }

        data = await export_by_path(mockserver, self.items, settings)
        assert compressed == data[filename]
        result = lzma.decompress(data[filename])
        assert result == self.expected

    @coroutine_test
    async def test_bz2_plugin(self, mockserver: MockServer, tmp_path: Path) -> None:
        filename = tmp_path / "bz2_file"

        settings = {
            "FEEDS": {
                filename: {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.Bz2Plugin"],
                },
            },
        }

        data = await export_by_path(mockserver, self.items, settings)
        try:
            bz2.decompress(data[filename])
        except OSError:
            pytest.fail("Received invalid bz2 data.")

    @coroutine_test
    async def test_bz2_plugin_compresslevel(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        filename_to_compressed = {
            tmp_path / "compresslevel_1": bz2.compress(self.expected, compresslevel=1),
            tmp_path / "compresslevel_9": bz2.compress(self.expected, compresslevel=9),
        }

        settings = {
            "FEEDS": {
                tmp_path / "compresslevel_1": {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.Bz2Plugin"],
                    "bz2_compresslevel": 1,
                },
                tmp_path / "compresslevel_9": {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.Bz2Plugin"],
                    "bz2_compresslevel": 9,
                },
            },
        }

        data = await export_by_path(mockserver, self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = bz2.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @coroutine_test
    async def test_custom_plugin(self, mockserver: MockServer, tmp_path: Path) -> None:
        filename = tmp_path / "csv_file"

        settings = {
            "FEEDS": {
                filename: {
                    "format": "csv",
                    "postprocessing": [self.MyPlugin1],
                },
            },
        }

        data = await export_by_path(mockserver, self.items, settings)
        assert data[filename] == self.expected

    @coroutine_test
    async def test_custom_plugin_with_parameter(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        expected = b"foo\r\n\nbar\r\n\n"
        filename = tmp_path / "newline"

        settings = {
            "FEEDS": {
                filename: {
                    "format": "csv",
                    "postprocessing": [self.MyPlugin1],
                    "plugin1_char": b"\n",
                },
            },
        }

        data = await export_by_path(mockserver, self.items, settings)
        assert data[filename] == expected

    @coroutine_test
    async def test_custom_plugin_with_compression(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        expected = b"foo\r\n\nbar\r\n\n"

        filename_to_decompressor = {
            tmp_path / "bz2": bz2.decompress,
            tmp_path / "lzma": lzma.decompress,
            tmp_path / "gzip": gzip.decompress,
        }

        settings = {
            "FEEDS": {
                tmp_path / "bz2": {
                    "format": "csv",
                    "postprocessing": [
                        self.MyPlugin1,
                        "scrapy.extensions.postprocessing.Bz2Plugin",
                    ],
                    "plugin1_char": b"\n",
                },
                tmp_path / "lzma": {
                    "format": "csv",
                    "postprocessing": [
                        self.MyPlugin1,
                        "scrapy.extensions.postprocessing.LZMAPlugin",
                    ],
                    "plugin1_char": b"\n",
                },
                tmp_path / "gzip": {
                    "format": "csv",
                    "postprocessing": [
                        self.MyPlugin1,
                        "scrapy.extensions.postprocessing.GzipPlugin",
                    ],
                    "plugin1_char": b"\n",
                },
            },
        }

        data = await export_by_path(mockserver, self.items, settings)

        for filename, decompressor in filename_to_decompressor.items():
            result = decompressor(data[filename])
            assert result == expected

    @coroutine_test
    async def test_exports_compatibility_with_postproc(
        self, mockserver: MockServer, tmp_path: Path
    ) -> None:
        filename_to_expected = {
            tmp_path / "csv": b"foo\r\nbar\r\n",
            tmp_path / "json": b'[\n{"foo": "bar"}\n]',
            tmp_path / "jsonlines": b'{"foo": "bar"}\n',
            tmp_path / "xml": b'<?xml version="1.0" encoding="utf-8"?>\n'
            b"<items>\n<item><foo>bar</foo></item>\n</items>",
        }

        settings = {
            "FEEDS": {
                tmp_path / "csv": {
                    "format": "csv",
                    "postprocessing": [self.MyPlugin1],
                    # empty plugin to activate postprocessing.PostProcessingManager
                },
                tmp_path / "json": {
                    "format": "json",
                    "postprocessing": [self.MyPlugin1],
                },
                tmp_path / "jsonlines": {
                    "format": "jsonlines",
                    "postprocessing": [self.MyPlugin1],
                },
                tmp_path / "xml": {
                    "format": "xml",
                    "postprocessing": [self.MyPlugin1],
                },
                tmp_path / "marshal": {
                    "format": "marshal",
                    "postprocessing": [self.MyPlugin1],
                },
                tmp_path / "pickle": {
                    "format": "pickle",
                    "postprocessing": [self.MyPlugin1],
                },
            },
        }

        data = await export_by_path(mockserver, self.items, settings)

        for path, expected in filename_to_expected.items():
            assert data[path] == expected
        assert pickle.loads(data[tmp_path / "pickle"]) == self.items[0]
        assert marshal.loads(data[tmp_path / "marshal"]) == self.items[0]


@coroutine_test
async def test_storage_file_no_postprocessing(
    mockserver: MockServer, tmp_path: Path
) -> None:
    class Storage:
        open_file: IO[bytes]
        store_file: IO[bytes]

        def __init__(self, uri, *, feed_options=None):
            pass

        def open(self, spider):
            Storage.open_file = tempfile.NamedTemporaryFile(prefix="feed-")
            return Storage.open_file

        def store(self, file):
            Storage.store_file = file
            file.close()

    settings = {
        "FEEDS": {unique_path(tmp_path): {"format": "jsonlines"}},
        "FEED_STORAGES": {"file": Storage},
    }
    await export_by_format(mockserver, [], settings)
    assert Storage.open_file is Storage.store_file


@coroutine_test
async def test_storage_file_postprocessing(
    mockserver: MockServer, tmp_path: Path
) -> None:
    class Storage:
        open_file: IO[bytes]
        store_file: IO[bytes]
        file_was_closed: bool

        def __init__(self, uri, *, feed_options=None):
            pass

        def open(self, spider):
            Storage.open_file = tempfile.NamedTemporaryFile(prefix="feed-")
            return Storage.open_file

        def store(self, file):
            Storage.store_file = file
            Storage.file_was_closed = file.closed
            file.close()

    settings = {
        "FEEDS": {
            unique_path(tmp_path): {
                "format": "jsonlines",
                "postprocessing": [
                    "scrapy.extensions.postprocessing.GzipPlugin",
                ],
            },
        },
        "FEED_STORAGES": {"file": Storage},
    }
    await export_by_format(mockserver, [], settings)
    assert Storage.open_file is Storage.store_file
    assert not Storage.file_was_closed
