"""
ItemLoader expanders
"""

from types import UnboundMethodType

from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import get_func_args
from scrapy.utils.datatypes import MergeDict

def tree_expander(*functions, **default_loader_args):
    """Create an ItemLoader expander from a list of functions using the tree
    expansion algorithm described below.

    The functions can optionally accept a ``loader_args`` argument which (if
    present) will be used to pass loader arguments when the function is called.

    The tree expansion algorithm consists in an ordered list of functions, each
    of which receives one value and can return zero, one or more values (as a
    list or iterable). If a function returns more than one value, the next
    function in the pipeline will be called with each of those values,
    potentially returning more values. Hence the name "tree expansion
    algorithm".
    """
    def wrap_y(f):
        return lambda x, y, z: f(y)

    def wrap_xy(f):
        return lambda x, y, z: f(x, y)

    def wrap_yz(f):
        return lambda x, y, z: f(y, z)

    wrapped_funcs = []
    for func in functions:
        if isinstance(func, UnboundMethodType):
            func = func.im_func
            if 'loader_args' in get_func_args(func):
                wfunc = func
            else:
                wfunc = wrap_xy(func)
        else:
            if 'loader_args' in get_func_args(func):
                wfunc = wrap_yz(func)
            else:
                wfunc = wrap_y(func)
        wrapped_funcs.append(wfunc)

    def _expander(loader, value, loader_args):
        values = arg_to_iter(value)
        largs = default_loader_args
        if loader_args:
            largs = MergeDict(loader_args, default_loader_args)
        for func in wrapped_funcs:
            next_values = []
            for v in values:
                next_values += arg_to_iter(func(loader, v, largs))
            values = next_values
        return list(values)

    return _expander

