"""
Item Loader

See documentation in docs/topics/loaders.rst
"""
import itemloaders

from scrapy.item import Item
from scrapy.selector import Selector


class ItemLoader(itemloaders.ItemLoader):
    """
    Return a new Item Loader for populating the given Item. If no item is
    given, one is instantiated automatically using the class in
    :attr:`default_item_class`.

    When instantiated with a ``selector`` or a ``response`` parameters
    the :class:`ItemLoader` class provides convenient mechanisms for extracting
    data from web pages using :ref:`selectors <topics-selectors>`.

    :param item: The item instance to populate using subsequent calls to
        :meth:`~ItemLoader.add_xpath`, :meth:`~ItemLoader.add_css`,
        or :meth:`~ItemLoader.add_value`.
    :type item: :class:`~scrapy.item.Item` object

    :param selector: The selector to extract data from, when using the
        :meth:`add_xpath` (resp. :meth:`add_css`) or :meth:`replace_xpath`
        (resp. :meth:`replace_css`) method.
    :type selector: :class:`~scrapy.selector.Selector` object

    :param response: The response used to construct the selector using the
        :attr:`default_selector_class`, unless the selector argument is given,
        in which case this argument is ignored.
    :type response: :class:`~scrapy.http.Response` object

    The item, selector, response and the remaining keyword arguments are
    assigned to the Loader context (accessible through the :attr:`context` attribute).
    """

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
