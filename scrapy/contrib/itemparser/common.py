"""Common functions used in Item Parsers code"""

from functools import partial
from scrapy.utils.python import get_func_args

def wrap_parser_context(function, context):
    """Wrap functions that receive parser_context to contain those parser
    arguments pre-loaded and expose a interface that receives only one argument
    """
    if 'parser_context' in get_func_args(function):
        return partial(function, parser_context=context)
    else:
        return function
