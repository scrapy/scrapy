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

    def __init__(self, item=None, selector=None, response=None, parent=None, **context):
        if selector is None and response is not None:
            selector = self.default_selector_class(response)
        context.update(response=response)
        super().__init__(item=item, selector=selector, parent=parent, **context)

    def get_default_input_processor_for_field(self, field_name):
        proc = self._get_item_field_attr(field_name, 'input_processor')
        if not proc:
            proc = super().get_default_input_processor_for_field(field_name)
        return proc

    def get_default_output_processor_for_field(self, field_name):
        proc = self._get_item_field_attr(field_name, 'output_processor')
        if not proc:
            proc = super().get_default_output_processor_for_field(field_name)
        return proc

    def _get_item_field_attr(self, field_name, key):
        if isinstance(self.item, Item):
            return self.item.fields[field_name].get(key)
        return None
