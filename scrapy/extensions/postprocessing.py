"""Extension for processing data before they are exported to feeds."""

from __future__ import annotations

from bz2 import BZ2File
from gzip import GzipFile
from io import IOBase
from lzma import LZMAFile
from typing import IO, Any, BinaryIO, Protocol, cast

from scrapy.utils.misc import load_object


class PostprocessingPluginProtocol(Protocol):
    """:class:`~typing.Protocol` of :ref:`post-processing plugins
    <post-processing>`."""

    def __init__(self, file: BinaryIO, feed_options: dict[str, Any]) -> None:
        """Initialize the plugin.

        *file* is a file-like object that implements at least the
        :meth:`~typing.BinaryIO.write`, :meth:`~typing.BinaryIO.tell` and
        :meth:`~typing.BinaryIO.close` methods.

        *feed_options* are the :ref:`options of the feed <feed-options>` that
        uses the plugin, which may be used to modify the behavior of the
        plugin.
        """

    def write(self, data: bytes | memoryview) -> int:
        """Process and write *data* into the target file of the plugin, and
        return the number of bytes written."""

    def close(self) -> None:
        """Run clean-up code.

        For example, you might want to close a file wrapper that you might have
        used to compress data written into the file received in the
        :meth:`__init__` method.

        .. warning:: Do *not* close the file from the :meth:`__init__` method.
        """


class GzipPlugin:
    """
    Compresses received data using `gzip <https://en.wikipedia.org/wiki/Gzip>`_.

    Accepted ``feed_options`` parameters:

    - `gzip_compresslevel`
    - `gzip_mtime`
    - `gzip_filename`

    See :py:class:`gzip.GzipFile` for more info about parameters.
    """

    def __init__(self, file: BinaryIO, feed_options: dict[str, Any]) -> None:
        self.file = file
        self.feed_options = feed_options
        compress_level = self.feed_options.get("gzip_compresslevel", 9)
        mtime = self.feed_options.get("gzip_mtime")
        filename = self.feed_options.get("gzip_filename")
        self.gzipfile = GzipFile(
            fileobj=self.file,
            mode="wb",
            compresslevel=compress_level,
            mtime=mtime,
            filename=filename,
        )

    def write(self, data: bytes) -> int:
        return self.gzipfile.write(data)

    def close(self) -> None:
        self.gzipfile.close()


class Bz2Plugin:
    """
    Compresses received data using `bz2 <https://en.wikipedia.org/wiki/Bzip2>`_.

    Accepted ``feed_options`` parameters:

    - `bz2_compresslevel`

    See :py:class:`bz2.BZ2File` for more info about parameters.
    """

    def __init__(self, file: BinaryIO, feed_options: dict[str, Any]) -> None:
        self.file = file
        self.feed_options = feed_options
        compress_level = self.feed_options.get("bz2_compresslevel", 9)
        self.bz2file = BZ2File(
            filename=self.file, mode="wb", compresslevel=compress_level
        )

    def write(self, data: bytes) -> int:
        return self.bz2file.write(data)

    def close(self) -> None:
        self.bz2file.close()


class LZMAPlugin:
    """
    Compresses received data using `lzma <https://en.wikipedia.org/wiki/Lempel–Ziv–Markov_chain_algorithm>`_.

    Accepted ``feed_options`` parameters:

    - `lzma_format`
    - `lzma_check`
    - `lzma_preset`
    - `lzma_filters`

    See :py:class:`lzma.LZMAFile` for more info about parameters.
    """

    def __init__(self, file: BinaryIO, feed_options: dict[str, Any]) -> None:
        self.file = file
        self.feed_options = feed_options

        format = self.feed_options.get("lzma_format")
        check = self.feed_options.get("lzma_check", -1)
        preset = self.feed_options.get("lzma_preset")
        filters = self.feed_options.get("lzma_filters")
        self.lzmafile = LZMAFile(
            filename=self.file,
            mode="wb",
            format=format,
            check=check,
            preset=preset,
            filters=filters,
        )

    def write(self, data: bytes) -> int:
        return self.lzmafile.write(data)

    def close(self) -> None:
        self.lzmafile.close()


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

    def __init__(
        self, plugins: list[Any], file: IO[bytes], feed_options: dict[str, Any]
    ) -> None:
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
        return cast(int, self.head_plugin.write(data))

    def tell(self) -> int:
        return self.file.tell()

    def close(self) -> None:
        """
        Close the target file along with all the plugins.
        """
        self.head_plugin.close()

    def writable(self) -> bool:
        return True

    def _load_plugins(self, plugins: list[Any]) -> list[Any]:
        return [load_object(plugin) for plugin in plugins]

    def _get_head_plugin(self) -> Any:
        prev = self.file
        for plugin in self.plugins[::-1]:
            prev = plugin(prev, self.feed_options)
        return prev
