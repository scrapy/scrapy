from collections import defaultdict

from scrapy.utils.datatypes import MergeDict
from scrapy.newitem import Item
from scrapy.newitem.loader.reducers import TakeFirst
from scrapy.newitem.loader.expanders import IdentityExpander

class ItemLoader(object):

    default_item_class = Item
    default_expander = IdentityExpander()
    default_reducer = TakeFirst()

    def __init__(self, **loader_args):
        self._response = loader_args.get('response')
        self._item = loader_args.setdefault('item', self.default_item_class())
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
        expander = getattr(self, '%s_exp' % field_name, None)
        if not expander:
            expander = self._item.fields[field_name].get('expander', \
                self.default_expander)
        return expander

    def get_reducer(self, field_name):
        reducer = getattr(self, '%s_red' % field_name, None)
        if not reducer:
            reducer = self._item.fields[field_name].get('reducer', \
                self.default_reducer)
        return reducer

    def _expand_value(self, field_name, value, new_loader_args):
        loader_args = self._loader_args
        if new_loader_args:
            loader_args = MergeDict(new_loader_args, self._loader_args)
        expander = self.get_expander(field_name)
        return expander(value, loader_args=loader_args)
