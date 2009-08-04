from collections import defaultdict

from scrapy.newitem import Item
from scrapy.newitem.loader.reducers import take_first

class ItemLoader(object):

    item_class = Item

    def __init__(self, **loader_args):
        self._response = loader_args.get('response')
        self._item = loader_args.get('item') or self.item_class()
        self._loader_args = loader_args
        self._values = defaultdict(list)

    def add_value(self, field_name, value, **new_loader_args):
        self._values[field_name] += self._expand_value(field_name, value, \
            new_loader_args)

    def replace_value(self, field_name, value, **new_loader_args):
        self._values[field_name] = self._expand_value(field_name, value, \
            new_loader_args)

    def get_item(self):
        item = self._item
        for field_name in self._values:
            item[field_name] = self.get_reduced_value(field_name)
        return item

    def get_expanded_value(self, field_name):
        return self._values[field_name]

    def get_reduced_value(self, field_name):
        reducer = self.get_reducer(field_name)
        return reducer(self._values[field_name])

    def get_expander(self, field_name):
        return getattr(self, 'expand_%s' % field_name, self.expand)

    def get_reducer(self, field_name):
        try:
            return getattr(self, 'reduce_%s' % field_name)
        except AttributeError:
            return self._item.fields[field_name].get('reducer', self.reduce)

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

    def reduce(self, values): # default reducer
        return take_first(values)
