"""Common functions used in Item Loaders code"""

from functools import partial
import string
from scrapy.utils.python import get_func_args


def wrap_loader_context(function, context):
    """Wrap functions that receive loader_context to contain the context
    "pre-loaded" and expose a interface that receives only one argument
    """
    if 'loader_context' in get_func_args(function):
        return partial(function, loader_context=context)
    else:
        return function


def clean_punctuation(text):
    """Strips text of punctuation and whitespaces"""
    chars = string.punctuation + string.whitespace
    for c in chars:
        if c in text:
            text = text.replace(c, '')
    return text