"""
Extension for processing data before they are exported to feeds.
"""

from bz2 import BZ2File
from gzip import GzipFile
from lzma import LZMAFile

from scrapy.utils.misc import load_object
from zope.interface import Interface, implementer


class PostProcessorPlugin(Interface):
    """
    Interface for plugin which will be used by PostProcessingManager
    for pre-export data processing.
    """

    def __init__(self, file, feed_options):
        """
        Initialize plugin with target file to which post-processed
        data will be written and the feed-specific options (see :setting:`FEEDS`).
        """

    def write(self, data):
        """
        Write `data` to plugin's target file.
        :param data: data passed to be written to file
        :type data: bytes
        :return: returns number of bytes written
        :rtype: int
        """

    def close(self):
        """
        Close this plugin.
        """


@implementer(PostProcessorPlugin)
class GzipPlugin:

    def __init__(self, file, feed_options):
        self.file = file
        self.feed_options = feed_options
        compress_level = self.feed_options.get("gzip_compresslevel", 9)
        self.gzipfile = GzipFile(fileobj=self.file, mode="wb", compresslevel=compress_level)

    def write(self, data):
        return self.gzipfile.write(data)

    def close(self):
        self.gzipfile.close()
        self.file.close()


@implementer(PostProcessorPlugin)
class Bz2File:

    def __init__(self, file, feed_options):
        self.file = file
        self.feed_options = feed_options
        compress_level = self.feed_options.get("bz2_compresslevel", 9)
        self.bz2file = BZ2File(filename=self.file, mode="wb", compresslevel=compress_level)

    def write(self, data):
        return self.bz2file.write(data)

    def close(self):
        self.bz2file.close()
        self.file.close()


@implementer(PostProcessorPlugin)
class LZMAPlugin:

    def __init__(self, file, feed_options):
        self.file = file
        self.feed_options = feed_options

        format = self.feed_options.get("lzma_format")
        check = self.feed_options.get("lzma_check", -1)
        preset = self.feed_options.get("lzma_preset")
        filters = self.feed_options.get("lzma_filter")
        self.lzmafile = LZMAFile(filename=self.file, mode="wb", format=format,
                                 check=check, preset=preset, filters=filters)

    def write(self, data):
        return self.lzmafile.write(data)

    def close(self):
        self.lzmafile.close()
        self.file.close()


class PostProcessingManager:
    """
    This will manage and use declared plugins to process data in a
    pipeline-ish way.
    :param plugins: all the declared plugins for the feed
    :type plugins: list
    :param file: final target file where the processed data will be written
    :type file: file like object
    """

    def __init__(self, plugins, file, feed_options):
        self.plugins = self._load_plugins(plugins)
        self.file = file
        self.feed_options = feed_options
        self.head_plugin = self._get_head_plugin()

    def write(self, data):
        """
        Uses all the declared plugins to process data first, then writes
        the processed data to target file.
        :param data: data passed to be written to target file
        :type data: bytes
        :return: returns number of bytes written
        :rtype: int
        """
        return self.head_plugin.write(data)

    def close(self):
        """
        Close the target file along with all the plugins.
        """
        self.head_plugin.close()

    def _load_plugins(self, plugins):
        plugins = [load_object(plugin) for plugin in plugins]
        return plugins

    def _get_head_plugin(self):
        prev = self.file
        for plugin in self.plugins[::-1]:
            prev = plugin(prev, self.feed_options)
        return prev
