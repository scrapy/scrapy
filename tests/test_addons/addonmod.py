import zope.interface

from scrapy.interfaces import IAddon

zope.interface.moduleProvides(IAddon)

FROM = "test_addons.addonmod"

name = "AddonModule"
version = "1.0"

def update_settings(config, settings):
    pass

def check_configuration(config, crawler):
    pass
