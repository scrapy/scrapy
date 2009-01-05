.. _topics-items:

=====
Items
=====

.. module:: scrapy.item
   :synopsis: Objects for storing scraped data

Quick overview
==============

| In Scrapy, items are the placeholder to use for the scraped data.
  They are represented by a :class:`ScrapedItem` object, or any descendant class instance, and store the information in class attributes.

ScrapedItems
============

.. class:: ScrapedItem

Methods
-------

.. method:: ScrapedItem.__init__(data={})

    Instanciates a ``ScrapedItem`` object and sets an attribute and its value for each key in the given ``data`` dict.

.. method:: ScrapedItem.attribute(self, attrname, value, override=False, add=False, **kwargs)

    Sets the item's ``attrname`` attribute with the given ``value`` filtering it through the attribute's adaptor pipeline (if any).

    ``attrname`` is a string containing the name of the attribute you're setting.

    ``value`` is the value you want to assign, which will be adapted by the corresponding adaptors for the given attribute (if any).

    ``override``, if True, makes this method avoid checking if there was a previous value and sets ``value`` no matter what.

    ``add``, if True, tries to concatenate the given ``value`` with the one already set in the item. This will work as long as
    the old value is a list (in which case the new value will be appended, or the list will be extended if both are lists),
    or as long as both values are strings (in which case ``add`` will be used as the delimiter, or default to '' if ``add=True``).

    ``kwargs`` - any extra parameters will be passed to any adaptor that receives an 'adaptor_args' parameter as a dictionary.
    Check the Adaptors reference for more information.

.. method:: ScrapedItem.set_adaptors(self, adaptors_dict)

    Receives a dict containing a list of adaptors for each desired attribute (key) and sets each of them as their adaptor pipeline.

.. method:: ScrapedItem.set_attrib_adaptors(self, attrib, pipe)

    Sets the provided iterable (``pipe``) as the adaptor pipeline for the given attribute (``attrib``)

.. method:: ScrapedItem.add_adaptor(self, attrib, adaptor, position=None)

    Adds an adaptor to an already existing (or not) pipeline.

    ``attr`` is the name of the attribute you're adding adaptors to.

    ``adaptor`` is a callable to be added to the pipeline.

    ``position`` is an integer representing the place where to add the adaptor.
    If it's ``None``, the adaptor will be appended at the end of the pipeline.

Examples
--------

Setting some basic attributes to a newly created item::

    >>> from scrapy.item import ScrapedItem
    >>> person = ScrapedItem()
    >>> person.attribute('name', 'John')
    >>> person.attribute('age', 35)
    >>> person
    ScrapedItem({'age': 35, 'name': 'John'})

We can also create an item and set its attributes by passing them inline using a dictionary, like::

    >>> person = ScrapedItem({'name': 'John', 'age': 35})
    >>> person
    ScrapedItem({'age': 35, 'name': 'John'})

Also, notice that making consecutive calls to the attribute method does *not* change its value, unless you use the `override` parameter::

    >>> person = ScrapedItem()
    >>> person.attribute('name', 'John')
    >>> person
    ScrapedItem({'name': 'John'})

    >>> person.attribute('name', 'Charlie')
    >>> person
    ScrapedItem({'name': 'John'})

    >>> person.attribute('name', 'Charlie', override=True)
    >>> person
    ScrapedItem({'name': 'Charlie'})

There's also an `add` parameter useful for concatenating lists or strings given a delimiter (or not)::

    >>> person = ScrapedItem()
    >>> person.attribute('name', 'John')
    >>> person
    ScrapedItem({'name': 'John'})

    # If add is True, '' is used as the default delimiter for joining strings
    >>> person.attribute('name', 'Doe', add=True)
    >>> person
    ScrapedItem({'name': 'JohnDoe'})

    # Otherwise, you can specify your own delimiter
    >>> person.attribute('name', 'Smith', add=' ')
    >>> person
    ScrapedItem({'name': 'JohnDoe Smith'})

    >>> person.attribute('children', ['Ken', 'Tom'])
    >>> person
    ScrapedItem({'name': 'JohnDoe Smith', 'children': ['Ken', 'Tom']})

    # You can also append to lists...
    >>> person.attribute('children', 'Billy', add=True)
    >>> person
    ScrapedItem({'name': 'JohnDoe Smith', 'children': ['Ken', 'Tom', 'Billy']})

    # And even extend them
    >>> person.attribute('children', ['Dan', 'George'], add=True)
    >>> person
    ScrapedItem({'name': 'JohnDoe Smith', 'children': ['Ken', 'Tom', 'Billy', 'Dan', 'George']})

Now, normally when we're scraping an HTML file, or almost any kind of file, information doesn't come to us exactly as we need it. We usually
have to make some adaptations here and there; and that's when the adaptors enter the game.
