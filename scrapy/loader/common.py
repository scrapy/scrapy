"""Common functions used in Item Loaders code"""

import warnings
from functools import partial

from itemloaders import common

from scrapy.utils.deprecate import ScrapyDeprecationWarning
from scrapy.utils.python import get_func_args


def wrap_loader_context(function, context):
    """Wrap functions that receive loader_context to contain the context
    "pre-loaded" and expose a interface that receives only one argument
    """
    warnings.warn(
        "scrapy.loader.common.wrap_loader_context has moved to a new library."
        "Please update your reference to itemloaders.common.wrap_loader_context",
        ScrapyDeprecationWarning
    )

    return common.wrap_loader_context(function, context)
