.. _items:

=====
Items
=====

In Scrapy, Items are the placeholder to use for the scraped data. They are
represented by a :class:`~scrapy.item.ScrapedItem` object, or any subclass
instance, and store the information in instance attributes.

.. module:: scrapy.item

ScrapedItem
-----------

.. autoclass:: ScrapedItem(object)
   :members:

   .. automethod:: __init__

      :param data: A dictionary containing attributes and values to be set
         after instancing the item.

Examples
--------

Creating an item and setting some attributes::

   >>> from scrapy.item import ScrapedItem
   >>> item = ScrapedItem()
   >>> item.name = 'John'
   >>> item.last_name = 'Smith'
   >>> item.age = 23
   >>> item
   ScrapedItem({'age': 23, 'last_name': 'Smith', 'name': 'John'})

Creating an item and setting its attributes inline::

   >>> person = ScrapedItem({'name': 'John', 'age': 23, 'last_name': 'Smith'})
   >>> person
   ScrapedItem({'age': 23, 'last_name': 'Smith', 'name': 'John'})

