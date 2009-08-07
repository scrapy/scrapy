"""
This module provides some commonly used Expanders.

See documentation in docs/topics/newitem-loader.rst
"""

from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import get_func_args
from scrapy.utils.datatypes import MergeDict

class TreeExpander(object):

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

    def __call__(self, values, loader_args):
        return arg_to_iter(values)
