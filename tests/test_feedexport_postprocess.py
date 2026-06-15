from __future__ import annotations

import bz2
import gzip
import lzma
import marshal
import pickle
import sys
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from scrapy.utils.test import get_crawler
from tests.test_feedexport import TestFeedExportBase, path_to_url, printf_escape
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from scrapy import Spider


class TestFeedPostProcessedExports(TestFeedExportBase):
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

    def _named_tempfile(self, name) -> str:
        return str(Path(self.temp_dir, name))

    async def run_and_export(
        self, spider_cls: type[Spider], settings: dict[str, Any]
    ) -> dict[str, bytes | None]:
        """Run spider with specified settings; return exported data with filename."""

        FEEDS = settings.get("FEEDS") or {}
        settings["FEEDS"] = {
            printf_escape(path_to_url(file_path)): feed_options
            for file_path, feed_options in FEEDS.items()
        }

        content: dict[str, bytes | None] = {}
        try:
            spider_cls.start_urls = [self.mockserver.url("/")]
            crawler = get_crawler(spider_cls, settings)
            await crawler.crawl_async()

            for file_path in FEEDS:
                content[str(file_path)] = (
                    Path(file_path).read_bytes() if Path(file_path).exists() else None
                )

        finally:
            for file_path in FEEDS:
                if not Path(file_path).exists():
                    continue

                Path(file_path).unlink()

        return content

    def get_gzip_compressed(self, data, compresslevel=9, mtime=0, filename=""):
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

    @coroutine_test
    async def test_gzip_plugin(self):
        filename = self._named_tempfile("gzip_file")

        settings = {
            "FEEDS": {
                filename: {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                },
            },
        }

        data = await self.exported_data(self.items, settings)
        try:
            gzip.decompress(data[filename])
        except OSError:
            pytest.fail("Received invalid gzip data.")

    @coroutine_test
    async def test_gzip_plugin_compresslevel(self):
        filename_to_compressed = {
            self._named_tempfile("compresslevel_0"): self.get_gzip_compressed(
                self.expected, compresslevel=0
            ),
            self._named_tempfile("compresslevel_9"): self.get_gzip_compressed(
                self.expected, compresslevel=9
            ),
        }

        settings = {
            "FEEDS": {
                self._named_tempfile("compresslevel_0"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                    "gzip_compresslevel": 0,
                    "gzip_mtime": 0,
                    "gzip_filename": "",
                },
                self._named_tempfile("compresslevel_9"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                    "gzip_compresslevel": 9,
                    "gzip_mtime": 0,
                    "gzip_filename": "",
                },
            },
        }

        data = await self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = gzip.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @coroutine_test
    async def test_gzip_plugin_mtime(self):
        filename_to_compressed = {
            self._named_tempfile("mtime_123"): self.get_gzip_compressed(
                self.expected, mtime=123
            ),
            self._named_tempfile("mtime_123456789"): self.get_gzip_compressed(
                self.expected, mtime=123456789
            ),
        }

        settings = {
            "FEEDS": {
                self._named_tempfile("mtime_123"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                    "gzip_mtime": 123,
                    "gzip_filename": "",
                },
                self._named_tempfile("mtime_123456789"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                    "gzip_mtime": 123456789,
                    "gzip_filename": "",
                },
            },
        }

        data = await self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = gzip.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @coroutine_test
    async def test_gzip_plugin_filename(self):
        filename_to_compressed = {
            self._named_tempfile("filename_FILE1"): self.get_gzip_compressed(
                self.expected, filename="FILE1"
            ),
            self._named_tempfile("filename_FILE2"): self.get_gzip_compressed(
                self.expected, filename="FILE2"
            ),
        }

        settings = {
            "FEEDS": {
                self._named_tempfile("filename_FILE1"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                    "gzip_mtime": 0,
                    "gzip_filename": "FILE1",
                },
                self._named_tempfile("filename_FILE2"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                    "gzip_mtime": 0,
                    "gzip_filename": "FILE2",
                },
            },
        }

        data = await self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = gzip.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @coroutine_test
    async def test_lzma_plugin(self):
        filename = self._named_tempfile("lzma_file")

        settings = {
            "FEEDS": {
                filename: {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                },
            },
        }

        data = await self.exported_data(self.items, settings)
        try:
            lzma.decompress(data[filename])
        except lzma.LZMAError:
            pytest.fail("Received invalid lzma data.")

    @coroutine_test
    async def test_lzma_plugin_format(self):
        filename_to_compressed = {
            self._named_tempfile("format_FORMAT_XZ"): lzma.compress(
                self.expected, format=lzma.FORMAT_XZ
            ),
            self._named_tempfile("format_FORMAT_ALONE"): lzma.compress(
                self.expected, format=lzma.FORMAT_ALONE
            ),
        }

        settings = {
            "FEEDS": {
                self._named_tempfile("format_FORMAT_XZ"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_format": lzma.FORMAT_XZ,
                },
                self._named_tempfile("format_FORMAT_ALONE"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_format": lzma.FORMAT_ALONE,
                },
            },
        }

        data = await self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = lzma.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @coroutine_test
    async def test_lzma_plugin_check(self):
        filename_to_compressed = {
            self._named_tempfile("check_CHECK_NONE"): lzma.compress(
                self.expected, check=lzma.CHECK_NONE
            ),
            self._named_tempfile("check_CHECK_CRC256"): lzma.compress(
                self.expected, check=lzma.CHECK_SHA256
            ),
        }

        settings = {
            "FEEDS": {
                self._named_tempfile("check_CHECK_NONE"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_check": lzma.CHECK_NONE,
                },
                self._named_tempfile("check_CHECK_CRC256"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_check": lzma.CHECK_SHA256,
                },
            },
        }

        data = await self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = lzma.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @coroutine_test
    async def test_lzma_plugin_preset(self):
        filename_to_compressed = {
            self._named_tempfile("preset_PRESET_0"): lzma.compress(
                self.expected, preset=0
            ),
            self._named_tempfile("preset_PRESET_9"): lzma.compress(
                self.expected, preset=9
            ),
        }

        settings = {
            "FEEDS": {
                self._named_tempfile("preset_PRESET_0"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_preset": 0,
                },
                self._named_tempfile("preset_PRESET_9"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_preset": 9,
                },
            },
        }

        data = await self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = lzma.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @coroutine_test
    async def test_lzma_plugin_filters(self):
        if "PyPy" in sys.version:
            # https://foss.heptapod.net/pypy/pypy/-/issues/3527
            pytest.skip("lzma filters doesn't work in PyPy")

        filters = [{"id": lzma.FILTER_LZMA2}]
        compressed = lzma.compress(self.expected, filters=filters)
        filename = self._named_tempfile("filters")

        settings = {
            "FEEDS": {
                filename: {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_filters": filters,
                },
            },
        }

        data = await self.exported_data(self.items, settings)
        assert compressed == data[filename]
        result = lzma.decompress(data[filename])
        assert result == self.expected

    @coroutine_test
    async def test_bz2_plugin(self):
        filename = self._named_tempfile("bz2_file")

        settings = {
            "FEEDS": {
                filename: {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.Bz2Plugin"],
                },
            },
        }

        data = await self.exported_data(self.items, settings)
        try:
            bz2.decompress(data[filename])
        except OSError:
            pytest.fail("Received invalid bz2 data.")

    @coroutine_test
    async def test_bz2_plugin_compresslevel(self):
        filename_to_compressed = {
            self._named_tempfile("compresslevel_1"): bz2.compress(
                self.expected, compresslevel=1
            ),
            self._named_tempfile("compresslevel_9"): bz2.compress(
                self.expected, compresslevel=9
            ),
        }

        settings = {
            "FEEDS": {
                self._named_tempfile("compresslevel_1"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.Bz2Plugin"],
                    "bz2_compresslevel": 1,
                },
                self._named_tempfile("compresslevel_9"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.Bz2Plugin"],
                    "bz2_compresslevel": 9,
                },
            },
        }

        data = await self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = bz2.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @coroutine_test
    async def test_custom_plugin(self):
        filename = self._named_tempfile("csv_file")

        settings = {
            "FEEDS": {
                filename: {
                    "format": "csv",
                    "postprocessing": [self.MyPlugin1],
                },
            },
        }

        data = await self.exported_data(self.items, settings)
        assert data[filename] == self.expected

    @coroutine_test
    async def test_custom_plugin_with_parameter(self):
        expected = b"foo\r\n\nbar\r\n\n"
        filename = self._named_tempfile("newline")

        settings = {
            "FEEDS": {
                filename: {
                    "format": "csv",
                    "postprocessing": [self.MyPlugin1],
                    "plugin1_char": b"\n",
                },
            },
        }

        data = await self.exported_data(self.items, settings)
        assert data[filename] == expected

    @coroutine_test
    async def test_custom_plugin_with_compression(self):
        expected = b"foo\r\n\nbar\r\n\n"

        filename_to_decompressor = {
            self._named_tempfile("bz2"): bz2.decompress,
            self._named_tempfile("lzma"): lzma.decompress,
            self._named_tempfile("gzip"): gzip.decompress,
        }

        settings = {
            "FEEDS": {
                self._named_tempfile("bz2"): {
                    "format": "csv",
                    "postprocessing": [
                        self.MyPlugin1,
                        "scrapy.extensions.postprocessing.Bz2Plugin",
                    ],
                    "plugin1_char": b"\n",
                },
                self._named_tempfile("lzma"): {
                    "format": "csv",
                    "postprocessing": [
                        self.MyPlugin1,
                        "scrapy.extensions.postprocessing.LZMAPlugin",
                    ],
                    "plugin1_char": b"\n",
                },
                self._named_tempfile("gzip"): {
                    "format": "csv",
                    "postprocessing": [
                        self.MyPlugin1,
                        "scrapy.extensions.postprocessing.GzipPlugin",
                    ],
                    "plugin1_char": b"\n",
                },
            },
        }

        data = await self.exported_data(self.items, settings)

        for filename, decompressor in filename_to_decompressor.items():
            result = decompressor(data[filename])
            assert result == expected

    @coroutine_test
    async def test_exports_compatibility_with_postproc(self):
        filename_to_expected = {
            self._named_tempfile("csv"): b"foo\r\nbar\r\n",
            self._named_tempfile("json"): b'[\n{"foo": "bar"}\n]',
            self._named_tempfile("jsonlines"): b'{"foo": "bar"}\n',
            self._named_tempfile("xml"): b'<?xml version="1.0" encoding="utf-8"?>\n'
            b"<items>\n<item><foo>bar</foo></item>\n</items>",
        }

        settings = {
            "FEEDS": {
                self._named_tempfile("csv"): {
                    "format": "csv",
                    "postprocessing": [self.MyPlugin1],
                    # empty plugin to activate postprocessing.PostProcessingManager
                },
                self._named_tempfile("json"): {
                    "format": "json",
                    "postprocessing": [self.MyPlugin1],
                },
                self._named_tempfile("jsonlines"): {
                    "format": "jsonlines",
                    "postprocessing": [self.MyPlugin1],
                },
                self._named_tempfile("xml"): {
                    "format": "xml",
                    "postprocessing": [self.MyPlugin1],
                },
                self._named_tempfile("marshal"): {
                    "format": "marshal",
                    "postprocessing": [self.MyPlugin1],
                },
                self._named_tempfile("pickle"): {
                    "format": "pickle",
                    "postprocessing": [self.MyPlugin1],
                },
            },
        }

        data = await self.exported_data(self.items, settings)

        for filename, result in data.items():
            if "pickle" in filename:
                expected, result = self.items[0], pickle.loads(result)
            elif "marshal" in filename:
                expected, result = self.items[0], marshal.loads(result)
            else:
                expected = filename_to_expected[filename]
            assert result == expected
