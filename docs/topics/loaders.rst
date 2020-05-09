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
    This implementation is an extension of itemloaders_ library,
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

Besides the usage of Item Loaders as instances, like the example above,
it's quite common to define them as classes.
This allows the loaders to be extended and
also to share common parsing rules across loaders for different websites.
Here is an example on how to define an Item Loader as class::

    from scrapy.loader import ItemLoader
    from itemloaders.processors import TakeFirst, MapCompose, Join

    class ProductLoader(ItemLoader):

        default_output_processor = TakeFirst()

        name_in = MapCompose(unicode.title)
        name_out = Join()

        price_in = MapCompose(unicode.strip)

        # ...

In this case, field input and output processors are declared as the item's
field name followed by a ``_in`` or ``_out`` suffix.
If there's some routine that's generic and shareable across the fields,
it can be define as a default processor through
:attr:`ItemLoader.default_input_processor` and
:attr:`ItemLoader.default_output_processor` attributes.

.. note:: For more information about processors,
    please refer to itemloaders_ documentation.


ItemLoader objects
==================

.. autoclass:: scrapy.loader.ItemLoader
    :members:
    :inherited-members:


Processors
==========

.. _topics-loaders-processors:

Processors documentation is available in `itemloaders processors`_.

.. _itemloaders: https://itemloaders.readthedocs.io/en/latest/
.. _itemloaders processors: https://itemloaders.readthedocs.io/en/latest/built-in-processors.html
