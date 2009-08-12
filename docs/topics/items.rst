.. _topics-items:

=====
Items
=====

Quick overview
==============

In Scrapy, items are the placeholder to use for the scraped data.  They are
represented by a :class:`ScrapedItem` object, or any descendant class instance,
and store the information in instance attributes.

ScrapedItems
============

.. module:: scrapy.item
   :synopsis: Objects for storing scraped data

.. class:: ScrapedItem

Methods
-------

.. method:: ScrapedItem.__init__(data=None)

    :param data: A dictionary containing attributes and values to be set
        after instancing the item.

    Instanciates a ``ScrapedItem`` object and sets an attribute and its value
    for each key in the given ``data`` dict (if any).  These items are the most
    basic items available, and the common interface from which any items should
    inherit.

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

