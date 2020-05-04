"""
This module provides some commonly used processors for Item Loaders.

See documentation in docs/topics/loaders.rst
"""
from collections import ChainMap

from itemloaders import processors

from scrapy.loader.common import wrap_loader_context
from scrapy.utils.deprecate import create_deprecated_class
from scrapy.utils.misc import arg_to_iter


MapCompose = create_deprecated_class('MapCompose', processors.MapCompose)

Compose = create_deprecated_class('Compose', processors.Compose)

TakeFirst = create_deprecated_class('TakeFirst', processors.TakeFirst)

Identity = create_deprecated_class('Identity', processors.Identity)

SelectJmes = create_deprecated_class('SelectJmes', processors.SelectJmes)

Join = create_deprecated_class('Join', processors.Join)
