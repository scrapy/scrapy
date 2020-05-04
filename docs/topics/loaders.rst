.. _topics-loaders:

============
Item Loaders
============

.. module:: scrapy.loader
   :synopsis: Item Loader class

Item Loaders provide a convenient mechanism for populating scraped :ref:`Items
<topics-items>`. Even though Items can be populated using their own
dictionary-like API, Item Loaders provide a much more convenient API for
populating them from a scraping process, by automating some common tasks like
parsing the raw extracted data before assigning it.

In other words, :ref:`Items <topics-items>` provide the *container* of
scraped data, while Item Loaders provide the mechanism for *populating* that
container.

Item Loaders are designed to provide a flexible, efficient and easy mechanism
for extending and overriding different field parsing rules, either by spider,
or by source format (HTML, XML, etc) without becoming a nightmare to maintain.

.. note:: Item Loaders used to be a part of ``scrapy``, but moved to a self-contained library.
    This implementation is an extension of ``itemloaders`` library,
    keeping support to :ref:`Items <topics-items>` and :ref:`Response <topics-request-response>`.

Using Item Loaders to populate items
====================================

Here is a typical Item Loader usage in a :ref:`Spider <topics-spiders>`, using
the :ref:`Product item <topics-items-declaring>` declared in the :ref:`Items
chapter <topics-items>`::

    from scrapy.loader import ItemLoader
    from myproject.items import Product

    def parse(self, response):
        l = ItemLoader(item=Product(), response=response)
        l.add_xpath('name', '//div[@class="product_name"]')
        l.add_xpath('name', '//div[@class="product_title"]')
        l.add_xpath('price', '//p[@id="price"]')
        l.add_css('stock', 'p#stock]')
        l.add_value('last_updated', 'today') # you can also use literal values
        return l.load_item()

By quickly looking at that code, we can see the ``name`` field is being
extracted from two different XPath locations in the page:

1. ``//div[@class="product_name"]``
2. ``//div[@class="product_title"]``

In other words, data is being collected by extracting it from two XPath
locations, using the :meth:`~ItemLoader.add_xpath` method. This is the
data that will be assigned to the ``name`` field later.

Afterwards, similar calls are used for ``price`` and ``stock`` fields
(the latter using a CSS selector with the :meth:`~ItemLoader.add_css` method),
and finally the ``last_update`` field is populated directly with a literal value
(``today``) using a different method: :meth:`~ItemLoader.add_value`.

Finally, when all data is collected, the :meth:`ItemLoader.load_item` method is
called which actually returns the item populated with the data
previously extracted and collected with the :meth:`~ItemLoader.add_xpath`,
:meth:`~ItemLoader.add_css`, and :meth:`~ItemLoader.add_value` calls.


Declaring Item Loaders
======================

Item Loaders are declared like Items, by using a class definition syntax. Here
is an example::

    from scrapy.loader import ItemLoader
    from itemloaders.processors import TakeFirst, MapCompose, Join

    class ProductLoader(ItemLoader):

        default_output_processor = TakeFirst()

        name_in = MapCompose(unicode.title)
        name_out = Join()

        price_in = MapCompose(unicode.strip)

        # ...

As you can see, input processors are declared using the ``_in`` suffix while
output processors are declared using the ``_out`` suffix. And you can also
declare a default input/output processors using the
:attr:`ItemLoader.default_input_processor` and
:attr:`ItemLoader.default_output_processor` attributes.
For more information about processors, please refer to ``itemloaders`` documentation.


ItemLoader objects
==================

.. class:: ItemLoader([item, selector, response], \**kwargs)

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

