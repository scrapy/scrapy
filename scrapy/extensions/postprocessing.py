"""
Extension for processing data before they are exported to feeds.
"""
from bz2 import BZ2File
from gzip import GzipFile
from io import IOBase
from lzma import LZMAFile
from typing import Any, BinaryIO, Dict, List

from scrapy.utils.misc import load_object


class GzipPlugin:
    """
    Compresses received data with with :py:mod:`gzip` module.

    Accepted ``feed_options`` parameters:

    - `gzip_compresslevel`
    - `gzip_mtime`
    - `gzip_filename`
    See :py:class:`gzip.GzipFile` for more info about parameters.
    """

    def __init__(self, file: BinaryIO, feed_options: Dict[str, Any]) -> None:
        self.file = file
        self.feed_options = feed_options
        compress_level = self.feed_options.get("gzip_compresslevel", 9)
        mtime = self.feed_options.get("gzip_mtime")
        filename = self.feed_options.get("gzip_filename")
        self.gzipfile = GzipFile(fileobj=self.file, mode="wb", compresslevel=compress_level,
                                 mtime=mtime, filename=filename)

    def write(self, data: bytes) -> int:
        """Compress and write the `data` into the target file."""
        return self.gzipfile.write(data)

    def close(self) -> None:
        """Close target file."""
        self.gzipfile.close()
        self.file.close()


class Bz2Plugin:
    """
    Compresses received data with :py:mod:`bz2` module.

    Accepted ``feed_options`` parameters:

    - `bz2_compresslevel`
    See :py:class:`bz2.BZ2File` for more info about parameters.
    """

    def __init__(self, file: BinaryIO, feed_options: Dict[str, Any]) -> None:
        self.file = file
        self.feed_options = feed_options
        compress_level = self.feed_options.get("bz2_compresslevel", 9)
        self.bz2file = BZ2File(filename=self.file, mode="wb", compresslevel=compress_level)

    def write(self, data: bytes) -> int:
        """Compress and write the `data` into the target file."""
        return self.bz2file.write(data)

    def close(self) -> None:
        """Close target file."""
        self.bz2file.close()
        self.file.close()


class LZMAPlugin:
    """
    Compresses received data with :py:mod:`lzma` module.

    Accepted ``feed_options`` parameters:

    - `lzma_format`
    - `lzma_check`
    - `lzma_preset`
    - `lzma_filter`
    See :py:class:`lzma.LZMAFile` for more info about parameters.
    """

    def __init__(self, file: BinaryIO, feed_options: Dict[str, Any]) -> None:
        self.file = file
        self.feed_options = feed_options

        format = self.feed_options.get("lzma_format")
        check = self.feed_options.get("lzma_check", -1)
        preset = self.feed_options.get("lzma_preset")
        filters = self.feed_options.get("lzma_filter")
        self.lzmafile = LZMAFile(filename=self.file, mode="wb", format=format,
                                 check=check, preset=preset, filters=filters)

    def write(self, data: bytes) -> int:
        """Compress and write the `data` into the target file."""
        return self.lzmafile.write(data)

    def close(self) -> None:
        """Close target file."""
        self.lzmafile.close()
        self.file.close()


# io.IOBase is subclassed here, so that exporters can use the PostProcessingManager
# instance as a file like writable object. This could be needed by some exporters
# such as CsvItemExporter which wraps the feed storage with io.TextIOWrapper.
class PostProcessingManager(IOBase):
    """
    This will manage and use declared plugins to process data in a
    pipeline-ish way.
    :param plugins: all the declared plugins for the feed
    :type plugins: list
    :param file: final target file where the processed data will be written
    :type file: file like object
    """

    def __init__(self, plugins: List[Any], file: BinaryIO, feed_options: Dict[str, Any]) -> None:
        self.plugins = self._load_plugins(plugins)
        self.file = file
        self.feed_options = feed_options
        self.head_plugin = self._get_head_plugin()

    def write(self, data: bytes) -> int:
        """
        Uses all the declared plugins to process data first, then writes
        the processed data to target file.
        :param data: data passed to be written to target file
        :type data: bytes
        :return: returns number of bytes written
        :rtype: int
        """
        return self.head_plugin.write(data)

    def close(self) -> None:
        """
        Close the target file along with all the plugins.
        """
        self.head_plugin.close()

    def writable(self) -> bool:
        return True

    def _load_plugins(self, plugins: List[Any]) -> List[Any]:
        plugins = [load_object(plugin) for plugin in plugins]
        return plugins

    def _get_head_plugin(self) -> Any:
        prev = self.file
        for plugin in self.plugins[::-1]:
            prev = plugin(prev, self.feed_options)
        return prev
