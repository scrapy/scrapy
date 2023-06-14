from zope.interface import moduleProvides

from scrapy.interfaces import IAddon

moduleProvides(IAddon)

name = "AddonModule"
version = "1.0"


def update_settings(config, settings):
    pass


def check_configuration(config, crawler):
    pass
