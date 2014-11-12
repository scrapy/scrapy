"""Item Loader

See documentation in docs/topics/loaders.rst

"""
from collections import defaultdict
import six

from scrapy.item import Item
from scrapy.selector import Selector
from scrapy.utils.decorator import deprecated
from scrapy.utils.deprecate import create_deprecated_class
from scrapy.utils.misc import arg_to_iter, extract_regex
from scrapy.utils.python import flatten

from .common import wrap_loader_context
from .processor import Identity


class ItemLoader(object):

    default_item_class = Item
    default_input_processor = Identity()
    default_output_processor = Identity()
    default_selector_class = Selector

    def __init__(self, item=None, selector=None, response=None, **context):
        if selector is None and response is not None:
            selector = self.default_selector_class(response)
        self.selector = selector
        context.update(selector=selector, response=response)
        if item is None:
            item = self.default_item_class()
        self.item = context['item'] = item
        self.context = context
        self._values = defaultdict(list)

    def add_value(self, field_name, value, *processors, **kw):
        value = self.get_value(value, *processors, **kw)
        if value is None:
            return
        if not field_name:
            for k, v in six.iteritems(value):
                self._add_value(k, v)
        else:
            self._add_value(field_name, value)

    def replace_value(self, field_name, value, *processors, **kw):
        value = self.get_value(value, *processors, **kw)
        if value is None:
            return
        if not field_name:
            for k, v in six.iteritems(value):
                self._replace_value(k, v)
        else:
            self._replace_value(field_name, value)

    def _add_value(self, field_name, value):
        value = arg_to_iter(value)
        processed_value = self._process_input_value(field_name, value)
        if processed_value:
            self._values[field_name] += arg_to_iter(processed_value)

    def _replace_value(self, field_name, value):
        self._values.pop(field_name, None)
        self._add_value(field_name, value)

    def get_value(self, value, *processors, **kw):
        regex = kw.get('re', None)
        if regex:
            value = arg_to_iter(value)
            value = flatten([extract_regex(regex, x) for x in value])

        for proc in processors:
            if value is None:
                break
            proc = wrap_loader_context(proc, self.context)
            value = proc(value)
        return value

    def load_item(self):
        item = self.item
        for field_name in self._values:
            value = self.get_output_value(field_name)
            if value is not None:
                item[field_name] = value
        return item

    def get_output_value(self, field_name):
        proc = self.get_output_processor(field_name)
        proc = wrap_loader_context(proc, self.context)
        try:
            return proc(self._values[field_name])
        except Exception as e:
            raise ValueError("Error with output processor: field=%r value=%r error='%s: %s'" % \
                (field_name, self._values[field_name], type(e).__name__, str(e)))

    def get_collected_values(self, field_name):
        return self._values[field_name]

    def get_input_processor(self, field_name):
        proc = getattr(self, '%s_in' % field_name, None)
        if not proc:
            proc = self._get_item_field_attr(field_name, 'input_processor', \
                self.default_input_processor)
        return proc

    def get_output_processor(self, field_name):
        proc = getattr(self, '%s_out' % field_name, None)
        if not proc:
            proc = self._get_item_field_attr(field_name, 'output_processor', \
                self.default_output_processor)
        return proc

    def _process_input_value(self, field_name, value):
        proc = self.get_input_processor(field_name)
        proc = wrap_loader_context(proc, self.context)
        return proc(value)

    def _get_item_field_attr(self, field_name, key, default=None):
        if isinstance(self.item, Item):
            value = self.item.fields[field_name].get(key, default)
        else:
            value = default
        return value

    def _check_selector_method(self):
        if self.selector is None:
            raise RuntimeError("To use XPath or CSS selectors, "
                "%s must be instantiated with a selector "
                "or a response" % self.__class__.__name__)

    def add_xpath(self, field_name, xpath, *processors, **kw):
        values = self._get_xpathvalues(xpath, **kw)
        self.add_value(field_name, values, *processors, **kw)

    def replace_xpath(self, field_name, xpath, *processors, **kw):
        values = self._get_xpathvalues(xpath, **kw)
        self.replace_value(field_name, values, *processors, **kw)

    def get_xpath(self, xpath, *processors, **kw):
        values = self._get_xpathvalues(xpath, **kw)
        return self.get_value(values, *processors, **kw)

    @deprecated(use_instead='._get_xpathvalues()')
    def _get_values(self, xpaths, **kw):
        return self._get_xpathvalues(xpaths, **kw)

    def _get_xpathvalues(self, xpaths, **kw):
        self._check_selector_method()
        xpaths = arg_to_iter(xpaths)
        return flatten([self.selector.xpath(xpath).extract() for xpath in xpaths])

    def add_css(self, field_name, css, *processors, **kw):
        values = self._get_cssvalues(css, **kw)
        self.add_value(field_name, values, *processors, **kw)

    def replace_css(self, field_name, css, *processors, **kw):
        values = self._get_cssvalues(css, **kw)
        self.replace_value(field_name, values, *processors, **kw)

    def get_css(self, css, *processors, **kw):
        values = self._get_cssvalues(css, **kw)
        return self.get_value(values, *processors, **kw)

    def _get_cssvalues(self, csss, **kw):
        self._check_selector_method()
        csss = arg_to_iter(csss)
        return flatten([self.selector.css(css).extract() for css in csss])


XPathItemLoader = create_deprecated_class('XPathItemLoader', ItemLoader)
