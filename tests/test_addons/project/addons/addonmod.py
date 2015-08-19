import zope.interface

from scrapy.interfaces import IAddon

zope.interface.moduleProvides(IAddon)

FROM = 'test_addons.project.addons.addonmod'
