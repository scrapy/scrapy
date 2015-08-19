import zope.interface

from scrapy.addons import Addon
from scrapy.interfaces import IAddon


class Addon(object):
    FROM = 'test_addons.addons'


@zope.interface.declarations.implementer(IAddon)
class GoodAddon(object):

    name = 'GoodAddon'
    version = '1.0'

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


@zope.interface.declarations.implementer(IAddon)
class BrokenAddon(object):

    name = 'BrokenAddon'
    # No version


_addon = GoodAddon()
