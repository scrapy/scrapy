"""
This module contains the ExtensionManager  which takes care of loading and
keeping track of all enabled extensions. It also contains an instantiated
ExtensionManager (extensions) to be used as singleton.
"""
from scrapy.core.exceptions import NotConfigured
from scrapy.utils.misc import load_object
from scrapy import log
from scrapy.conf import settings

class ExtensionManager(object):

    def __init__(self):
        self.loaded = False
        self.enabled = {}
        self.disabled = {}

    def load(self):
        """
        Load enabled extensions in settings module
        """

        self.loaded = False
        self.enabled.clear()
        self.disabled.clear()
        for extension_path in settings.getlist('EXTENSIONS'):
            try:
                cls = load_object(extension_path)
                self.enabled[cls.__name__] = cls()
            except NotConfigured, e:
                self.disabled[cls.__name__] = extension_path
                if e.args:
                    log.msg(e)
        self.loaded = True

    def reload(self):
        self.load()

extensions = ExtensionManager()
