from collections import defaultdict

from scrapy.utils.datatypes import MergeDict
from scrapy.newitem import Item
from scrapy.newitem.loader.reducers import TakeFirst
from scrapy.newitem.loader.expanders import IdentityExpander
from scrapy.xpath import HtmlXPathSelector

class Loader(object):

    default_item_class = Item
    default_expander = IdentityExpander()
    default_reducer = TakeFirst()

    def __init__(self, item=None, **loader_args):
        if item is None:
            item = self.default_item_class()
        self._item = loader_args['item'] = item
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


class XPathLoader(Loader):

    default_selector_class = HtmlXPathSelector

    def __init__(self, item=None, selector=None, response=None, **loader_args):
        if selector is None and response is None:
            raise RuntimeError("%s must be instantiated with a selector" \
                "or response" % self.__class__.__name__)
        if selector is None:
            selector = self.default_selector_class(response)
        self.selector = selector
        loader_args.update(selector=selector, response=response)
        super(XPathLoader, self).__init__(item, **loader_args)

    def add_xpath(self, field_name, xpath, re=None, **new_loader_args):
        self.add_value(field_name, self._get_values(field_name, xpath, re),
            **new_loader_args)

    def replace_xpath(self, field_name, xpath, re=None, **new_loader_args):
        self.replace_value(field_name, self._get_values(field_name, xpath, re), \
            **new_loader_args)

    def _get_values(self, field_name, xpath, re):
        x = self.selector.x(xpath)
        return x.re(re) if re else x.extract()
