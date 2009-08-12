"""
Item Parser

See documentation in docs/topics/itemparser.rst
"""

from collections import defaultdict

from scrapy.newitem import Item
from scrapy.xpath import HtmlXPathSelector
from scrapy.utils.misc import arg_to_iter
from .common import wrap_parser_context
from .parsers import Identity

class ItemParser(object):

    default_item_class = Item
    default_input_parser = Identity()
    default_output_parser = Identity()

    def __init__(self, item=None, **context):
        if item is None:
            item = self.default_item_class()
        self.item = context['item'] = item
        self.context = context
        self._values = defaultdict(list)

    def add_value(self, field_name, value):
        parsed_value = self._parse_input_value(field_name, value)
        self._values[field_name] += arg_to_iter(parsed_value)

    def replace_value(self, field_name, value):
        parsed_value = self._parse_input_value(field_name, value)
        self._values[field_name] = arg_to_iter(parsed_value)

    def populate_item(self):
        item = self.item
        for field_name in self._values:
            item[field_name] = self.get_output_value(field_name)
        return item

    def get_output_value(self, field_name):
        parser = self.get_output_parser(field_name)
        parser = wrap_parser_context(parser, self.context)
        return parser(self._values[field_name])

    def get_collected_values(self, field_name):
        return self._values[field_name]

    def get_input_parser(self, field_name):
        parser = getattr(self, '%s_in' % field_name, None)
        if not parser:
            parser = self.item.fields[field_name].get('input_parser', \
                self.default_input_parser)
        return parser

    def get_output_parser(self, field_name):
        parser = getattr(self, '%s_out' % field_name, None)
        if not parser:
            parser = self.item.fields[field_name].get('output_parser', \
                self.default_output_parser)
        return parser

    def _parse_input_value(self, field_name, value):
        parser = self.get_input_parser(field_name)
        parser = wrap_parser_context(parser, self.context)
        return parser(value)


class XPathItemParser(ItemParser):

    default_selector_class = HtmlXPathSelector

    def __init__(self, item=None, selector=None, response=None, **context):
        if selector is None and response is None:
            raise RuntimeError("%s must be instantiated with a selector" \
                "or response" % self.__class__.__name__)
        if selector is None:
            selector = self.default_selector_class(response)
        self.selector = selector
        context.update(selector=selector, response=response)
        super(XPathItemParser, self).__init__(item, **context)

    def add_xpath(self, field_name, xpath, re=None):
        self.add_value(field_name, self._get_values(field_name, xpath, re))

    def replace_xpath(self, field_name, xpath, re=None):
        self.replace_value(field_name, self._get_values(field_name, xpath, re))

    def _get_values(self, field_name, xpath, re):
        x = self.selector.x(xpath)
        return x.re(re) if re else x.extract()

