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

To use an Item Loader, you must first instantiate it. You can either
instantiate it with a dict-like object (e.g. Item or dict) or without one, in
which case an Item is automatically instantiated in the Item Loader ``__init__`` method
using the Item class specified in the :attr:`ItemLoader.default_item_class`
attribute.

Then, you start collecting values into the Item Loader, typically using
:ref:`Selectors <topics-selectors>`. You can add more than one value to
the same item field; the Item Loader will know how to "join" those values later
using a proper processing function.

.. note:: Collected data is internally stored as lists,
   allowing to add several values to the same field.
   If an ``item`` argument is passed when creating a loader,
   each of the item's values will be stored as-is if it's already
   an iterable, or wrapped with a list if it's a single value.

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

.. _topics-loaders-processors:


Declaring Item Loaders
======================

Item Loaders are declared like Items, by using a class definition syntax. Here
is an example::

    from scrapy.loader import ItemLoader
    from itemloaders.processors import TakeFirst, MapCompose, Join

    from myproject.items import ProductItem

    class ProductLoader(ItemLoader):

        default_item_class = ProductItem

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
