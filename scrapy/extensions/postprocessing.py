"""
Extension for processing data before they are exported to feeds.
"""

from scrapy.utils.misc import load_object
from zope.interface import Interface


class PostProcessorPlugin(Interface):
    """
    Interface for plugin which will be used by PostProcessingManager
    for pre-export data processing.
    """

    def __init__(self, file):
        """
        Initialize plugin with target file to which post-processed
        data will be written
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


class PostProcessingManager:
    """
    This will manage and use declared plugins to process data in a
    pipeline-ish way.
    :param plugins: all the declared plugins for the feed
    :type plugins: list
    :param file: final target file where the processed data will be written
    :type file: file like object
    """

    def __init__(self, plugins, file):
        self.plugins = self._load_plugins(plugins)
        self.file = file
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
            prev = plugin(prev)
        return prev
