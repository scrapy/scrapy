"""
This module provides some commonly used processors for Item Loaders.

See documentation in docs/topics/loaders.rst
"""
from collections import ChainMap
import warnings

from itemloaders import processors

from scrapy.loader.common import wrap_loader_context
from scrapy.utils.deprecate import ScrapyDeprecationWarning
from scrapy.utils.misc import arg_to_iter


def deprecation_warning(cls):
    warnings.warn(
        f"{cls.__module__}.{cls.__name__} has moved to a new library."
        f"Please update your reference to itemloaders.processors.{cls.__name__}",
        ScrapyDeprecationWarning
    )


class MapCompose(processors.MapCompose):

    def __init__(self, *functions, **default_loader_context):
        deprecation_warning(type(self))
        super().__init__(*functions, **default_loader_context)


class Compose(processors.Compose):

    def __init__(self, *functions, **default_loader_context):
        deprecation_warning(type(self))
        super().__init__(*functions, **default_loader_context)


class TakeFirst(processors.TakeFirst):

    def __init__(self):
        deprecation_warning(type(self))
        super().__init__()


class Identity(processors.Identity):

    def __init__(self):
        deprecation_warning(type(self))
        super().__init__()


class SelectJmes(processors.SelectJmes):

    def __init__(self, json_path):
        deprecation_warning(type(self))
        super().__init__(json_path)


class Join(processors.Join):

    def __init__(self, separator=u' '):
        deprecation_warning(type(self))
        super().__init__(separator)
