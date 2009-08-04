from collections import defaultdict
from types import UnboundMethodType

from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import get_func_args
from scrapy.utils.datatypes import MergeDict

from scrapy.newitem.models import Item

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


class ItemLoader(object):

    item_class = Item

    def __init__(self, **loader_args):
        self._response = loader_args.get('response')
        self._item = loader_args.get('item') or self.item_class()
        self._loader_args = loader_args
        self._values = defaultdict(list)

    def add_value(self, field_name, value, **new_loader_args):
        evalue = self._expand_value(field_name, value, new_loader_args)
        self._values[field_name].extend(evalue)

    def replace_value(self, field_name, value, **new_loader_args):
        evalue = self._expand_value(field_name, value, new_loader_args)
        self._values[field_name] = evalue

    def get_item(self):
        item = self._item
        for field_name in self._values:
            item[field_name] = self.get_value(field_name)
        return item

    def get_value(self, field_name):
        values = self._values[field_name]
        field = self._item.fields[field_name]
        reducer = self.get_reducer(field_name)
        # XXX: calling different methods based on reducer is ugly
        if reducer:
            return field.to_python(reducer(values))
        else:
            return field.from_unicode_list(values)

    def get_reducer(self, field_name):
        return getattr(self, 'reduce_%s' % field_name, None)

    def get_expander(self, field_name):
        return getattr(self, 'expand_%s' % field_name, self.expand)

    def _expand_value(self, field_name, value, new_loader_args):
        if new_loader_args:
            loader_args = self._loader_args.copy()
            loader_args.update(new_loader_args)
        else: # shortcut for most common case
            loader_args = self._loader_args
        expander = self.get_expander(field_name)
        return expander(value, loader_args=loader_args)

    def expand(self, value, loader_args): # default expander
        return value
