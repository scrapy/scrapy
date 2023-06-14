from zope.interface import implementer

from scrapy.interfaces import IAddon


@implementer(IAddon)
class GoodAddon(object):
    name = "GoodAddon"
    version = "1.0"

    def __init__(self, name=None, version=None):
        if name is not None:
            self.name = name
        if version is not None:
            self.version = version

    def update_addons(self, config, addons):
        pass

    def update_settings(self, config, settings):
        pass

    def check_configuration(self, config, crawler):
        pass


@implementer(IAddon)
class BrokenAddon(object):
    name = "BrokenAddon"
    # No version


_addon = GoodAddon()
