"""
This module provides some commonly used processors for Item Loaders.

See documentation in docs/topics/loaders.rst
"""

from scrapy.utils.misc import arg_to_iter
from scrapy.utils.datatypes import MergeDict
from .common import wrap_loader_context

class ApplyConcat(object):

    def __init__(self, *functions, **default_loader_context):
        self.functions = functions
        self.default_loader_context = default_loader_context
        
    def __call__(self, value, loader_context=None):
        values = arg_to_iter(value)
        if loader_context:
            context = MergeDict(loader_context, self.default_loader_context)
        else:
            context = self.default_loader_context
        wrapped_funcs = [wrap_loader_context(f, context) for f in self.functions]
        for func in wrapped_funcs:
            next_values = []
            for v in values:
                next_values += arg_to_iter(func(v))
            values = next_values
        return list(values)


class TakeFirst(object):

    def __call__(self, values):
        for value in values:
            if value:
                return value


class Identity(object):

    def __call__(self, values):
        return values


class Join(object):

    def __init__(self, separator=u' '):
        self.separator = separator

    def __call__(self, values):
        return self.separator.join(values)
