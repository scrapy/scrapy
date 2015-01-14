"""
This module provides some commonly used processors for Item Loaders.

See documentation in docs/topics/loaders.rst
"""
import re

from scrapy.utils.misc import arg_to_iter
from scrapy.utils.datatypes import MergeDict
from .common import wrap_loader_context


class MapCompose(object):

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
        return values


class Compose(object):

    def __init__(self, *functions, **default_loader_context):
        self.functions = functions
        self.stop_on_none = default_loader_context.get('stop_on_none', True)
        self.default_loader_context = default_loader_context

    def __call__(self, value, loader_context=None):
        if loader_context:
            context = MergeDict(loader_context, self.default_loader_context)
        else:
            context = self.default_loader_context
        wrapped_funcs = [wrap_loader_context(f, context) for f in self.functions]
        for func in wrapped_funcs:
            if value is None and self.stop_on_none:
                break
            value = func(value)
        return value


class TakeFirst(object):

    def __call__(self, values):
        for value in values:
            if value is not None and value != '':
                return value


class Identity(object):

    def __call__(self, values):
        return values


class Join(object):

    def __init__(self, separator=u' '):
        self.separator = separator

    def __call__(self, values):
        return self.separator.join(values)


class Strip(object):
    def __init__(self, chars=None):
        self.chars = chars

    def __call__(self, values):
        if isinstance(values, list):
            filtered = []
            for value in values:
                value = value.strip(self.chars)
                if value != '' and value is not None:
                    filtered.append(value)
            return filtered
        return values.strip(self.chars)


class TakeNth(object):

    def __init__(self, pos):
        self.pos = pos

    def __call__(self, values):
        values = [v for v in values if v != '' and v is not None]
        return values[self.pos]


class OnlyEnglish(object):
    def __call__(self, values):
        if isinstance(values, list):
            filtered = []
            for value in values:
                try:
                    value.decode('ascii')
                except (UnicodeDecodeError, UnicodeEncodeError):
                    pass
                else:
                    filtered.append(value)
            return filtered
        else:
            try:
                values.decode('ascii')
            except (UnicodeDecodeError, UnicodeEncodeError):
                pass
            else:
                return values


class OnlyChars(object):

    def __call__(self, values):
        if isinstance(values, list):
            filtered = []
            for value in values:
                value = filter(type(value).isalpha, value)
                if value != '' and value is not None:
                    filtered.append(value)
            return filtered
        return filter(type(values).isalpha, values)


class Filter(object):

    def __init__(self, filter_func):
        self.filter_func = filter_func

    def __call__(self, values):
        if isinstance(values, list):
            filtered = []
            for value in values:
                value = filter(self.filter_func, value)
                if value != '' and value is not None:
                    filtered.append(value)
            return filtered
        return filter(self.filter_func, values)


class Replace(object):

    def __init__(self, find, replace, count=-1):
        self.find = find
        self.replace = replace
        self.count = count

    def __call__(self, values):
        if isinstance(values, list):
            filtered = []
            for value in values:
                value = value.replace(self.find, self.replace, self.count)
                if value != '' and value is not None:
                    filtered.append(value)
            return filtered
        return values.replace(self.find, self.replace)


class ReSub(object):

    def __init__(self, find, replace, count=0, flags=0):
        self.find = find
        self.replace = replace
        self.count = count
        self.flags = flags

    def __call__(self, values):
        if isinstance(values, list):
            filtered = []
            for value in values:
                value = re.sub(self.find, self.replace, value, self.count, self.flags)
                if value != '' and value is not None:
                    filtered.append(value)
            return filtered
        return re.sub(self.find, self.replace, values, self.count, self.flags)


class OnlyDigits(object):

    def __call__(self, values):
        if isinstance(values, list):
            filtered = []
            for value in values:
                value = filter(type(value).isdigit, value)
                if value != '' and value is not None:
                    filtered.append(value)
            return filtered
        return filter(type(values).isdigit, values)