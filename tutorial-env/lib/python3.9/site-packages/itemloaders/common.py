"""Common functions used in Item Loaders code"""

from functools import partial

from itemloaders.utils import get_func_args


def wrap_loader_context(function, context):
    """Wrap functions that receive loader_context to contain the context
    "pre-loaded" and expose a interface that receives only one argument
    """
    if "loader_context" in get_func_args(function):
        return partial(function, loader_context=context)
    else:
        return function
