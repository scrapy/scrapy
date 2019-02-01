"""Item Loader

See documentation in docs/topics/loaders.rst

"""
from collections import defaultdict
import six

from scrapy.item import Item
from scrapy.selector import Selector
from scrapy.utils.decorators import deprecated
from scrapy.utils.deprecate import create_deprecated_class
from scrapy.utils.misc import arg_to_iter, extract_regex
from scrapy.utils.python import flatten

from .common import wrap_loader_context
from .processors import Identity


class ItemLoader(object):
    """Return a new Item Loader for populating the given Item. If no item is
    given, one is instantiated automatically using the class in
    :attr:`default_item_class`.

    When instantiated with a `selector` or a `response` parameters
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
    :type response: :class:`Response <scrapy.Response>` object

    The item, selector, response and the remaining keyword arguments are
    assigned to the Loader context (accessible through the :attr:`context` attribute).
    """

    #: An Item class (or factory), used to instantiate items when not given in
    #: the constructor.
    default_item_class = Item

    #: The default input processor to use for those fields which don't specify
    #: one.
    default_input_processor = Identity()

    #: The default output processor to use for those fields which don't specify
    #: one.
    default_output_processor = Identity()

    #: The class used to construct the :attr:`selector` of this
    #: :class:`ItemLoader`, if only a response is given in the constructor.
    #: If a selector is given in the constructor this attribute is ignored.
    #: This attribute is sometimes overridden in subclasses.
    default_selector_class = Selector

    def __init__(self, item=None, selector=None, response=None, parent=None, **context):
        if selector is None and response is not None:
            selector = self.default_selector_class(response)

        #: The :class:`~scrapy.selector.Selector` object to extract data from.
        #: It's either the selector given in the constructor or one created from
        #: the response given in the constructor using the
        #: :attr:`default_selector_class`. This attribute is meant to be
        #: read-only.
        self.selector = selector

        context.update(selector=selector, response=response)
        if item is None:
            item = self.default_item_class()

        #: The currently active :ref:`Context <topics-loaders-context>` of this
        #: Item Loader.
        self.context = context

        self.parent = parent
        self._local_item = context['item'] = item
        self._local_values = defaultdict(list)

    @property
    def _values(self):
        if self.parent is not None:
            return self.parent._values
        else:
            return self._local_values

    @property
    def item(self):
        """The :class:`~scrapy.item.Item` object being parsed by this Item Loader."""
        if self.parent is not None:
            return self.parent.item
        else:
            return self._local_item

    def nested_xpath(self, xpath, **context):
        """Create a nested loader with an xpath selector.
        The supplied selector is applied relative to selector associated
        with this :class:`ItemLoader`. The nested loader shares the :class:`Item`
        with the parent :class:`ItemLoader` so calls to :meth:`add_xpath`,
        :meth:`add_value`, :meth:`replace_value`, etc. will behave as expected."""
        selector = self.selector.xpath(xpath)
        context.update(selector=selector)
        subloader = self.__class__(
            item=self.item, parent=self, **context
        )
        return subloader

    def nested_css(self, css, **context):
        """Create a nested loader with a css selector.
        The supplied selector is applied relative to selector associated
        with this :class:`ItemLoader`. The nested loader shares the :class:`Item`
        with the parent :class:`ItemLoader` so calls to :meth:`add_xpath`,
        :meth:`add_value`, :meth:`replace_value`, etc. will behave as expected."""
        selector = self.selector.css(css)
        context.update(selector=selector)
        subloader = self.__class__(
            item=self.item, parent=self, **context
        )
        return subloader

    def add_value(self, field_name, value, *processors, **kw):
        """Process and then add the given ``value`` for the given field.

        The value is first passed through :meth:`get_value` by giving the
        ``processors`` and ``kwargs``, and then passed through the
        :ref:`field input processor <topics-loaders-processors>` and its result
        appended to the data collected for that field. If the field already
        contains collected data, the new data is added.

        The given ``field_name`` can be ``None``, in which case values for
        multiple fields may be added. And the processed value should be a dict
        with field_name mapped to values.

        Examples::

            loader.add_value('name', u'Color TV')
            loader.add_value('colours', [u'white', u'blue'])
            loader.add_value('length', u'100')
            loader.add_value('name', u'name: foo', TakeFirst(), re='name: (.+)')
            loader.add_value(None, {'name': u'foo', 'sex': u'male'})
        """
        value = self.get_value(value, *processors, **kw)
        if value is None:
            return
        if not field_name:
            for k, v in six.iteritems(value):
                self._add_value(k, v)
        else:
            self._add_value(field_name, value)

    def replace_value(self, field_name, value, *processors, **kw):
        """Similar to :meth:`add_value` but replaces the collected data with the
        new value instead of adding it."""
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
        """Process the given ``value`` by the given ``processors`` and keyword
        arguments.

        Available keyword arguments:

        :param re: a regular expression to use for extracting data from the
            given value using :meth:`~scrapy.utils.misc.extract_regex` method,
            applied before processors
        :type re: str or compiled regex

        Examples:

        .. testsetup:: loader

            >>> from scrapy.loader import ItemLoader
            >>> loader = ItemLoader()

        .. doctest:: loader

           >>> from scrapy.loader.processors import TakeFirst
           >>> loader.get_value('name: foo', TakeFirst(), str.upper, re='name: (.+)')
           'FOO'
        """
        regex = kw.get('re', None)
        if regex:
            value = arg_to_iter(value)
            value = flatten(extract_regex(regex, x) for x in value)

        for proc in processors:
            if value is None:
                break
            proc = wrap_loader_context(proc, self.context)
            value = proc(value)
        return value

    def load_item(self):
        """Populate the item with the data collected so far, and return it. The
        data collected is first passed through the :ref:`output processors
        <topics-loaders-processors>` to get the final value to assign to each
        item field."""
        item = self.item
        for field_name in tuple(self._values):
            value = self.get_output_value(field_name)
            if value is not None:
                item[field_name] = value

        return item

    def get_output_value(self, field_name):
        """Return the collected values parsed using the output processor, for the
        given field. This method doesn't populate or modify the item at all."""
        proc = self.get_output_processor(field_name)
        proc = wrap_loader_context(proc, self.context)
        try:
            return proc(self._values[field_name])
        except Exception as e:
            raise ValueError("Error with output processor: field=%r value=%r error='%s: %s'" % \
                (field_name, self._values[field_name], type(e).__name__, str(e)))

    def get_collected_values(self, field_name):
        """Return the collected values for the given field."""
        return self._values[field_name]

    def get_input_processor(self, field_name):
        """Return the input processor for the given field."""
        proc = getattr(self, '%s_in' % field_name, None)
        if not proc:
            proc = self._get_item_field_attr(field_name, 'input_processor', \
                self.default_input_processor)
        return proc

    def get_output_processor(self, field_name):
        """Return the output processor for the given field."""
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
        """Similar to :meth:`ItemLoader.add_value` but receives an XPath instead of a
        value, which is used to extract a list of unicode strings from the
        selector associated with this :class:`ItemLoader`.

        See :meth:`get_xpath` for ``kwargs``.

        :param xpath: the XPath to extract data from
        :type xpath: str

        Examples::

            # HTML snippet: <p class="product-name">Color TV</p>
            loader.add_xpath('name', '//p[@class="product-name"]')
            # HTML snippet: <p id="price">the price is $1200</p>
            loader.add_xpath('price', '//p[@id="price"]', re='the price is (.*)')
        """
        values = self._get_xpathvalues(xpath, **kw)
        self.add_value(field_name, values, *processors, **kw)

    def replace_xpath(self, field_name, xpath, *processors, **kw):
        """Similar to :meth:`add_xpath` but replaces collected data instead of
        adding it."""
        values = self._get_xpathvalues(xpath, **kw)
        self.replace_value(field_name, values, *processors, **kw)

    def get_xpath(self, xpath, *processors, **kw):
        """Similar to :meth:`ItemLoader.get_value` but receives an XPath instead of a
        value, which is used to extract a list of unicode strings from the
        selector associated with this :class:`ItemLoader`.

        :param xpath: the XPath to extract data from
        :type xpath: str

        :param re: a regular expression to use for extracting data from the
            selected XPath region
        :type re: str or compiled regex

        Examples::

            # HTML snippet: <p class="product-name">Color TV</p>
            loader.get_xpath('//p[@class="product-name"]')
            # HTML snippet: <p id="price">the price is $1200</p>
            loader.get_xpath('//p[@id="price"]', TakeFirst(), re='the price is (.*)')
        """
        values = self._get_xpathvalues(xpath, **kw)
        return self.get_value(values, *processors, **kw)

    @deprecated(use_instead='._get_xpathvalues()')
    def _get_values(self, xpaths, **kw):
        return self._get_xpathvalues(xpaths, **kw)

    def _get_xpathvalues(self, xpaths, **kw):
        self._check_selector_method()
        xpaths = arg_to_iter(xpaths)
        return flatten(self.selector.xpath(xpath).getall() for xpath in xpaths)

    def add_css(self, field_name, css, *processors, **kw):
        """Similar to :meth:`ItemLoader.add_value` but receives a CSS selector
        instead of a value, which is used to extract a list of unicode strings
        from the selector associated with this :class:`ItemLoader`.

        See :meth:`get_css` for ``kwargs``.

        :param css: the CSS selector to extract data from
        :type css: str

        Examples::

            # HTML snippet: <p class="product-name">Color TV</p>
            loader.add_css('name', 'p.product-name')
            # HTML snippet: <p id="price">the price is $1200</p>
            loader.add_css('price', 'p#price', re='the price is (.*)')
        """
        values = self._get_cssvalues(css, **kw)
        self.add_value(field_name, values, *processors, **kw)

    def replace_css(self, field_name, css, *processors, **kw):
        """Similar to :meth:`add_css` but replaces collected data instead of
        adding it."""
        values = self._get_cssvalues(css, **kw)
        self.replace_value(field_name, values, *processors, **kw)

    def get_css(self, css, *processors, **kw):
        """Similar to :meth:`ItemLoader.get_value` but receives a CSS selector
        instead of a value, which is used to extract a list of unicode strings
        from the selector associated with this :class:`ItemLoader`.

        :param css: the CSS selector to extract data from
        :type css: str

        :param re: a regular expression to use for extracting data from the
            selected CSS region
        :type re: str or compiled regex

        Examples::

            # HTML snippet: <p class="product-name">Color TV</p>
            loader.get_css('p.product-name')
            # HTML snippet: <p id="price">the price is $1200</p>
            loader.get_css('p#price', TakeFirst(), re='the price is (.*)')
        """
        values = self._get_cssvalues(css, **kw)
        return self.get_value(values, *processors, **kw)

    def _get_cssvalues(self, csss, **kw):
        self._check_selector_method()
        csss = arg_to_iter(csss)
        return flatten(self.selector.css(css).getall() for css in csss)

XPathItemLoader = create_deprecated_class('XPathItemLoader', ItemLoader)
