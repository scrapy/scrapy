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

RobustScrapedItems
==================

.. warning::

   RobustScapedItems are deprecated and will be replaced by the :ref:`New item
   API <topics-newitem-index-item>` (still in development).

.. module:: scrapy.contrib.item
   :synopsis: Objects for storing scraped data

.. class:: RobustScrapedItem

    RobustScrapedItems are more complex items (compared to
    :class:`ScrapedItem`) and have a few more features available, which
    include:

    * Attributes dictionary: items that inherit from RobustScrapedItem are
      defined with a dictionary of attributes in the class.  This allows the
      item to have more logic at the moment of handling and setting attributes
      than the :class:`ScrapedItem`.

    * Adaptors: perhaps the most important of the features these items provide.
      The adaptors are a system designed for filtering/modifying data before
      setting it to the item, that makes cleansing tasks a lot easier.

    * Type checking: RobustScrapedItems come with a built-in type checking
      which assures you that no data of the wrong type will get into the items
      without raising a warning.

    * Versioning: These items also provide versioning by making a unique hash
      for each item based on its attributes values.

    * ItemDeltas: You can subtract two RobustScrapedItems, which allows you to
      know the difference between a pair of items.  This difference is
      represented by a RobustItemDelta object.

Attributes
----------

.. attribute:: RobustScrapedItem.ATTRIBUTES

    This attribute **must** be specified when writing your items, and it's a
    dictionary in which the keys are the names of the attributes your item will
    have, and their values are the type of those attributes.  For multivalued
    attributes, you should write the type of the values inside a list, e.g:
    ``'numbers': [int]``

Methods
-------

.. method:: RobustScrapedItem.__init__(data=None, adaptor_args=None)

    :param data: Idem as for ScrapedItems
    :param adaptor_args: A dictionary of the kind
        ``'attribute': [list_of_adaptors]``" for defining adaptors automatically
        after instancing the item.

    Constructor of RobustScrapedItem objects.

.. method:: RobustScrapedItem.attribute(attrname, value, override=False, add=False, ***kwargs)

    Sets the item's ``attrname`` attribute with the given ``value`` filtering
    it through the given attribute's adaptor pipeline (if any).

    :param attrname: a string containing the name of the attribute you want
        to set.

    :param value: the value you want to assign, which will be adapted by
        the corresponding adaptors for the given attribute (if any).

    :param override: if True, makes this method avoid checking if there
        was a previous value and sets ``value`` no matter what.

    :param add: if True, tries to concatenate the given ``value`` with the one
        already set in the item. For multivalued attributes, this will extend
        the list of already-set values, with the new ones.
        For single valued attributes, the method _add_single_attributes (which
        is explained below) will be called.

    :param kwargs: any extra parameters will be passed in a dictionary to any
        adaptor that receives a parameter called ``adaptor_args``.
        Check the :ref:`topics-adaptors` topic for more information.

.. method:: RobustScrapedItem.set_adaptors(adaptors_dict)

    Receives a dict containing a list of adaptors for each desired attribute
    (key) and sets each of them as their adaptor pipeline.

.. method:: RobustScrapedItem.set_attrib_adaptors(attrib, pipe)

    Sets the provided iterable (``pipe``) as the adaptor pipeline for the
    given attribute (``attrib``)

.. method:: RobustScrapedItem.add_adaptor(attrib, adaptor, position=None)

    Adds an adaptor to an already existing (or not) pipeline.

    :param attr: the name of the attribute you're adding adaptors to.

    :param adaptor: a callable to be added to the pipeline.

    :param position: an integer representing the place where to add the adaptor.
        If it's ``None``, the adaptor will be appended at the end of the pipeline.

.. method:: RobustScrapedItem._add_single_attributes(attrname, attrtype, attributes)

    This method is the one to be called whenever a single attribute has to be
    joined before storing into an item. That is,
    every time you have multiple results at the end of your adaptors pipeline,
    and you called the ``attribute`` method with the parameter `add=True`.

    This method is intended to be overriden by you, since by default it
    raises an exception.

    :param attrname: the name of the attribute you're setting
    :param attrtype: the type of the attribute you're setting
    :param attributes: the list of resulting values after the adaptors pipeline
        (the one you have to join somehow)

Examples
--------

Creating a pretty basic item with a few attributes::

    from scrapy.contrib.item import RobustScrapedItem

    class MyItem(RobustScrapedItem):
        ATTRIBUTES = {
            'name': basestring,
            'size': basestring,
            'colours': [basestring],
        }

Setting some adaptors::

    
.. note::

    More RobustScrapedItem examples are about to come. In the meantime, check the :ref:`topics-adaptors` topic to see a few of them.

