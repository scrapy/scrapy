"""
This module provides some commonly used processors for Item Loaders.

See documentation in docs/topics/loaders.rst
"""
try:
    from collections import ChainMap
except ImportError:
    from scrapy.utils.datatypes import MergeDict as ChainMap

from scrapy.utils.misc import arg_to_iter
from scrapy.loader.common import wrap_loader_context


class MapCompose(object):

    def __init__(self, *functions, **default_loader_context):
        self.functions = functions
        self.default_loader_context = default_loader_context

    def __call__(self, value, loader_context=None):
        values = arg_to_iter(value)
        if loader_context:
            context = ChainMap(loader_context, self.default_loader_context)
        else:
            context = self.default_loader_context
        wrapped_funcs = [wrap_loader_context(f, context) for f in self.functions]
        for func in wrapped_funcs:
            next_values = []
            for v in values:
                try:
                    next_values += arg_to_iter(func(v))
                except Exception as e:
                    raise ValueError("Error in MapCompose with "
                                     "%s value=%r error='%s: %s'" %
                                     (str(func), value, type(e).__name__,
                                      str(e)))
            values = next_values
        return values


class Compose(object):

    def __init__(self, *functions, **default_loader_context):
        self.functions = functions
        self.stop_on_none = default_loader_context.get('stop_on_none', True)
        self.default_loader_context = default_loader_context

    def __call__(self, value, loader_context=None):
        if loader_context:
            context = ChainMap(loader_context, self.default_loader_context)
        else:
            context = self.default_loader_context
        wrapped_funcs = [wrap_loader_context(f, context) for f in self.functions]
        for func in wrapped_funcs:
            if value is None and self.stop_on_none:
                break
            try:
                value = func(value)
            except Exception as e:
                raise ValueError("Error in Compose with "
                                 "%s value=%r error='%s: %s'" %
                                 (str(func), value, type(e).__name__, str(e)))
        return value


class TakeFirst(object):

    def __call__(self, values):
        for value in values:
            if value is not None and value != '':
                return value


class Identity(object):

    def __call__(self, values):
        return values


class SelectJmes(object):
    """
        Query the input string for the jmespath (given at instantiation),
        and return the answer
        Requires : jmespath(https://github.com/jmespath/jmespath)
        Note: SelectJmes accepts only one input element at a time.
    """
    def __init__(self, json_path):
        self.json_path = json_path
        import jmespath
        self.compiled_path = jmespath.compile(self.json_path)

    def __call__(self, value):
        """Query value for the jmespath query and return answer
        :param value: a data structure (dict, list) to extract from
        :return: Element extracted according to jmespath query
        """
        return self.compiled_path.search(value)


class Join(object):

    def __init__(self, separator=u' '):
        self.separator = separator

    def __call__(self, values):
        return self.separator.join(values)
