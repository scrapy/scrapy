"""
This module provides some commonly used processors for Item Loaders.

See documentation in docs/topics/loaders.rst
"""
import locale
import re
import string

from scrapy.utils.misc import arg_to_iter
from scrapy.utils.datatypes import MergeDict
from .common import wrap_loader_context, purge_chars  #todo relative it


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

    def __init__(self, pos, fallback_func=None):
        self.pos = pos
        self.fallback_func = fallback_func or (lambda values: None)

    def __call__(self, values):
        filtered = [v for v in values if v != '' and v is not None]
        if self.pos >= len(filtered):
            return self.fallback_func(values)
        else:
            return filtered[self.pos]


class OnlyAsciiItems(object):
    def __init__(self, except_chars=''):
        self.except_chars = except_chars

    def __call__(self, values):
        if isinstance(values, list):
            filtered = []
            for value in values:
                filtered_value = value
                if self.except_chars:  # Filter only if have what to filter
                    filtered_value = purge_chars(value, self.except_chars)
                try:
                    filtered_value.decode('ascii')
                except (UnicodeDecodeError, UnicodeEncodeError):
                    pass
                else:
                    filtered.append(value)
            return filtered
        else:
            filtered_value = values
            if self.except_chars:
                filtered_value = purge_chars(values, self.except_chars)
            try:
                filtered_value.decode('ascii')
            except (UnicodeDecodeError, UnicodeEncodeError):
                pass
            else:
                return values


class OnlyAscii(object):
    def __init__(self, except_chars=''):
        self.except_chars = except_chars

    def __call__(self, values):
        filtered = []
        valid = string.printable + self.except_chars
        if isinstance(values, list):
            for value in values:
                filtered_value = ''
                for char in value:
                    if char in valid:
                        filtered_value += char
                filtered.append(filtered_value)
            return filtered
        else:
            filtered_value = ''
            for char in values:
                if char in valid:
                    filtered_value += char
            return filtered_value or None


class OnlyChars(object):
    def __init__(self, except_chars=''):
        self.except_chars = except_chars

    def __call__(self, values):
        if isinstance(values, list):
            filtered = []
            for value in values:
                if self.except_chars:
                    value = filter(lambda v: v.isalpha() or (v in self.except_chars), value)
                else:
                    value = filter(type(value).isalpha, value)
                if value != '' and value is not None:
                    filtered.append(value)
            return filtered
        if self.except_chars:
            return filter(lambda v: v.isalpha() or (v in self.except_chars), values)
        else:
            return filter(type(values).isalpha, values)


class OnlyCharsItems(object):

    def __init__(self, except_chars=''):
        self.except_chars = except_chars

    def __call__(self, values):
        if isinstance(values, list):
            filtered = []
            for value in values:
                condition = value.isalpha()
                if not condition and self.except_chars:
                    condition = purge_chars(value, self.except_chars).isalpha()
                if value != '' and value is not None and condition:
                    filtered.append(value)
            return filtered
        else:
            condition = values.isalpha()
            if not condition:
                condition = purge_chars(values, self.except_chars).isalpha()
            if values != '' and values is not None and condition:
                return values


class OnlyDigits(object):

    def __init__(self, except_chars=''):
        self.except_chars = except_chars

    def __call__(self, values):
        if isinstance(values, list):
            filtered = []
            for value in values:
                if self.except_chars:
                    value = filter(lambda v: v.isdigit() or (v in self.except_chars), value)
                else:
                    value = filter(type(value).isdigit, value)
                if value != '' and value is not None:
                    filtered.append(value)
            return filtered
        if self.except_chars:
            return filter(lambda v: v.isdigit() or (v in self.except_chars), values)
        else:
            return filter(type(values).isdigit, values)


class OnlyDigitsItems(object):

    def __init__(self, except_chars=''):
        self.except_chars = except_chars

    def __call__(self, values):
        if isinstance(values, list):
            filtered = []
            for value in values:
                condition = value.isdigit()
                if not condition and self.except_chars:
                    condition = purge_chars(value, self.except_chars).isdigit()
                if value != '' and value is not None and condition:
                    filtered.append(value)
            return filtered
        else:
            condition = values.isdigit()
            if not condition:
                condition = purge_chars(values, self.except_chars).isdigit()
            if values != '' and values is not None and condition:
                return values


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


class ParseNum(object):

    def __init__(self, return_type, string_locale='en_US.UTF-8'):
        if return_type == float:
            self.parse_func = locale.atof
        elif return_type == int:
            self.parse_func = locale.atoi
        else:
            raise NotImplementedError('return_type supplied to ParseNum processor has to be '
                                      'either int or float, is {}'.format(return_type))
        self.string_locale = string_locale

    def __call__(self, values):
        # in case we have more than one processor we need to override locale on every call.
        locale.setlocale(locale.LC_ALL, locale=self.string_locale)
        if isinstance(values, list):
            filtered = []
            for value in values:
                if value is not None and value != '':
                    filtered.append(str(self.parse_func(value)))
            return filtered
        else:
            if values is not None and values != '':
                return str(self.parse_func(values)) or None
