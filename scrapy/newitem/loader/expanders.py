"""
This module provides some commonly used Expanders
"""

from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import get_func_args
from scrapy.utils.datatypes import MergeDict

class TreeExpander(object):
    """An expander which applies the given list of functions consecutively to
    each value returned by the previous function.

    The algorithm consists in an ordered list of functions, each of which
    receives one value and can return zero, one or more values (as a list or
    iterable). If a function returns more than one value, the next function in
    the list will be called with each of those values, potentially returning
    more values and thus expanding the execution into different branches, which
    is why this expander is called Tree Expander.
    
    The expander functions can optionally receive a ``loader_args`` argument,
    which will contain the current active loader arguments.
    """

    def __init__(self, *functions, **default_loader_args):
        self.default_loader_args = default_loader_args
        self.wrapped_funcs = []
        for func in functions:
            if 'loader_args' in get_func_args(func):
                wfunc = self.wrap_with_args(func)
            else:
                wfunc = self.wrap_no_args(func)
            self.wrapped_funcs.append(wfunc)
        
    def wrap_no_args(self, f):
        return lambda x, y: f(x)

    def wrap_with_args(self, f):
        return lambda x, y: f(x, loader_args=y)

    def __call__(self, value, loader_args):
        values = arg_to_iter(value)
        largs = self.default_loader_args
        if loader_args:
            largs = MergeDict(loader_args, self.default_loader_args)
        for func in self.wrapped_funcs:
            next_values = []
            for v in values:
                next_values += arg_to_iter(func(v, largs))
            values = next_values
        return list(values)


class IdentityExpander(object):
    """An expander which returns the original values unchanged. It doesn't
    support any constructor arguments.
    """

    def __call__(self, values, loader_args):
        return arg_to_iter(values)
