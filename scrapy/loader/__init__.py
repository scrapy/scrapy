"""
Item Loader

See documentation in docs/topics/loaders.rst
"""
import itemloaders

from scrapy.item import Item
from scrapy.selector import Selector

class ItemLoader(itemloaders.ItemLoader):

    default_item_class = Item
    default_selector_class = Selector

    def __init__(self, response=None, item=None, selector=None, parent=None, **context):
        if selector is None and response is not None:
            selector = self.default_selector_class(response)
        context.update(response=response)
        super().__init__(item=item, selector=selector, parent=parent, **context)

    # def get_input_processor(self, field_name):
    #     proc = getattr(self, '%s_in' % field_name, None)
    #     if not proc:
    #         proc = self._get_item_field_attr(field_name, 'input_processor',
    #                                          self.default_input_processor)
    #     return unbound_method(proc)

    # def get_output_processor(self, field_name):
    #     proc = getattr(self, '%s_out' % field_name, None)
    #     if not proc:
    #         proc = self._get_item_field_attr(field_name, 'output_processor',
    #                                          self.default_output_processor)
    #     return unbound_method(proc)

    def _get_item_field_attr(self, field_name, key, default=None):
        if isinstance(self.item, Item):
            value = self.item.fields[field_name].get(key, default)
        else:
            value = default
        return value
