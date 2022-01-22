"""
This module provides some commonly used processors for Item Loaders.

See documentation in docs/topics/loaders.rst
"""
from itemloaders import processors

from scrapy.utils.deprecate import create_deprecated_class


MapCompose = create_deprecated_class('MapCompose', processors.MapCompose)

Compose = create_deprecated_class('Compose', processors.Compose)

TakeFirst = create_deprecated_class('TakeFirst', processors.TakeFirst)

Identity = create_deprecated_class('Identity', processors.Identity)

SelectJmes = create_deprecated_class('SelectJmes', processors.SelectJmes)

Join = create_deprecated_class('Join', processors.Join)
