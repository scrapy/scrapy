.. _topics-items:

=====
Items
=====

.. module:: scrapy.item
   :synopsis: Item and Field classes

The main goal in scraping is to extract structured data from unstructured
sources, typically, web pages. :ref:`Spiders <topics-spiders>` may return the
extracted data as `items`, Python objects that define key-value pairs.

Scrapy supports :ref:`multiple types of items <item-types>`. When you create an
item, you may use whichever type of item you want. When you write code that
receives an item, your code should :ref:`work for any item type
<supporting-item-types>`.

.. _item-types:

Item Types
==========

Scrapy supports the following types of items, via the `itemadapter`_ library:
:ref:`dictionaries <dict-items>`, :ref:`Item objects <item-objects>`,
:ref:`dataclass objects <dataclass-items>`, and :ref:`attrs objects <attrs-items>`.

.. _itemadapter: https://github.com/scrapy/itemadapter

.. _dict-items:

Dictionaries
------------

As an item type, :class:`dict` is convenient and familiar.

.. _item-objects:

Item objects
------------

:class:`Item` provides a :class:`dict`-like API plus additional features that
make it the most feature-complete item type:

.. autoclass:: scrapy.Item
   :members: copy, deepcopy, fields
   :undoc-members:

:class:`Item` objects replicate the standard :class:`dict` API, including
its ``__init__`` method.

:class:`Item` allows the defining of field names, so that:

-   :class:`KeyError` is raised when using undefined field names (i.e.
    prevents typos going unnoticed)

-   :ref:`Item exporters <topics-exporters>` can export all fields by
    default even if the first scraped object does not have values for all
    of them

:class:`Item` also allows the defining of field metadata, which can be used to
:ref:`customize serialization <topics-exporters-field-serialization>`.

:mod:`trackref` tracks :class:`Item` objects to help find memory leaks
(see :ref:`topics-leaks-trackrefs`).

Example:

.. code-block:: python

    from scrapy.item import Item, Field


    class CustomItem(Item):
        one_field = Field()
        another_field = Field()

.. _dataclass-items:

Dataclass objects
-----------------

.. versionadded:: 2.2

:func:`~dataclasses.dataclass` allows the defining of item classes with field names,
so that :ref:`item exporters <topics-exporters>` can export all fields by
default even if the first scraped object does not have values for all of them.

Additionally, ``dataclass`` items also allow you to:

* define the type and default value of each defined field.

* define custom field metadata through :func:`dataclasses.field`, which can be used to
  :ref:`customize serialization <topics-exporters-field-serialization>`.

Example:

.. code-block:: python

    from dataclasses import dataclass


    @dataclass
    class CustomItem:
        one_field: str
        another_field: int

.. note:: Field types are not enforced at run time.

.. _attrs-items:

attr.s objects
--------------

.. versionadded:: 2.2

:func:`attr.s` allows the defining of item classes with field names,
so that :ref:`item exporters <topics-exporters>` can export all fields by
default even if the first scraped object does not have values for all of them.

Additionally, ``attr.s`` items also allow to:

* define the type and default value of each defined field.

* define custom field :ref:`metadata <attrs:metadata>`, which can be used to
  :ref:`customize serialization <topics-exporters-field-serialization>`.

In order to use this type, the :doc:`attrs package <attrs:index>` needs to be installed.

Example:

.. code-block:: python

    import attr


    @attr.s
    class CustomItem:
        one_field = attr.ib()
        another_field = attr.ib()


Working with Item objects
=========================

.. _topics-items-declaring:

Declaring Item subclasses
-------------------------

Item subclasses are declared using a simple class definition syntax and
:class:`Field` objects. Here is an example:

.. code-block:: python

    import scrapy


    class Product(scrapy.Item):
        name = scrapy.Field()
        price = scrapy.Field()
        stock = scrapy.Field()
        tags = scrapy.Field()
        last_updated = scrapy.Field(serializer=str)

.. note:: Those familiar with `Django`_ will notice that Scrapy Items are
   declared similar to `Django Models`_, except that Scrapy Items are much
   simpler as there is no concept of different field types.

.. _Django: https://www.djangoproject.com/
.. _Django Models: https://docs.djangoproject.com/en/dev/topics/db/models/


.. _topics-items-fields:

Declaring fields
----------------

:class:`Field` objects are used to specify metadata for each field. For
example, the serializer function for the ``last_updated`` field illustrated in
the example above.

You can specify any kind of metadata for each field. There is no restriction on
the values accepted by :class:`Field` objects. For this same
reason, there is no reference list of all available metadata keys. Each key
defined in :class:`Field` objects could be used by a different component, and
only those components know about it. You can also define and use any other
:class:`Field` key in your project too, for your own needs. The main goal of
:class:`Field` objects is to provide a way to define all field metadata in one
place. Typically, those components whose behaviour depends on each field use
certain field keys to configure that behaviour. You must refer to their
documentation to see which metadata keys are used by each component.

It's important to note that the :class:`Field` objects used to declare the item
do not stay assigned as class attributes. Instead, they can be accessed through
the :attr:`~scrapy.Item.fields` attribute.

.. autoclass:: scrapy.Field

    The :class:`Field` class is just an alias to the built-in :class:`dict` class and
    doesn't provide any extra functionality or attributes. In other words,
    :class:`Field` objects are plain-old Python dicts. A separate class is used
    to support the :ref:`item declaration syntax <topics-items-declaring>`
    based on class attributes.

.. note:: Field metadata can also be declared for ``dataclass`` and ``attrs``
    items. Please refer to the documentation for `dataclasses.field`_ and
    `attr.ib`_ for additional information.

    .. _dataclasses.field: https://docs.python.org/3/library/dataclasses.html#dataclasses.field
    .. _attr.ib: https://www.attrs.org/en/stable/api-attr.html#attr.ib


Working with Item objects
-------------------------

Here are some examples of common tasks performed with items, using the
``Product`` item :ref:`declared above  <topics-items-declaring>`. You will
notice the API is very similar to the :class:`dict` API.

Creating items
''''''''''''''

.. code-block:: pycon

    >>> product = Product(name="Desktop PC", price=1000)
    >>> print(product)
    Product(name='Desktop PC', price=1000)


Getting field values
''''''''''''''''''''

.. code-block:: pycon

    >>> product["name"]
    Desktop PC
    >>> product.get("name")
    Desktop PC

    >>> product["price"]
    1000

    >>> product["last_updated"]
    Traceback (most recent call last):
        ...
    KeyError: 'last_updated'

    >>> product.get("last_updated", "not set")
    not set

    >>> product["lala"]  # getting unknown field
    Traceback (most recent call last):
        ...
    KeyError: 'lala'

    >>> product.get("lala", "unknown field")
    'unknown field'

    >>> "name" in product  # is name field populated?
    True

    >>> "last_updated" in product  # is last_updated populated?
    False

    >>> "last_updated" in product.fields  # is last_updated a declared field?
    True

    >>> "lala" in product.fields  # is lala a declared field?
    False


Setting field values
''''''''''''''''''''

.. code-block:: pycon

    >>> product["last_updated"] = "today"
    >>> product["last_updated"]
    today

    >>> product["lala"] = "test"  # setting unknown field
    Traceback (most recent call last):
        ...
    KeyError: 'Product does not support field: lala'


Accessing all populated values
''''''''''''''''''''''''''''''

To access all populated values, just use the typical :class:`dict` API:

.. code-block:: pycon

    >>> product.keys()
    ['price', 'name']

    >>> product.items()
    [('price', 1000), ('name', 'Desktop PC')]


.. _copying-items:

Copying items
'''''''''''''

To copy an item, you must first decide whether you want a shallow copy or a
deep copy.

If your item contains :term:`mutable` values like lists or dictionaries,
a shallow copy will keep references to the same mutable values across all
different copies.

For example, if you have an item with a list of tags, and you create a shallow
copy of that item, both the original item and the copy have the same list of
tags. Adding a tag to the list of one of the items will add the tag to the
other item as well.

If that is not the desired behavior, use a deep copy instead.

See :mod:`copy` for more information.

To create a shallow copy of an item, you can either call
:meth:`~scrapy.Item.copy` on an existing item
(``product2 = product.copy()``) or instantiate your item class from an existing
item (``product2 = Product(product)``).

To create a deep copy, call :meth:`~scrapy.Item.deepcopy` instead
(``product2 = product.deepcopy()``).


Other common tasks
''''''''''''''''''

Creating dicts from items:

.. code-block:: pycon

    >>> dict(product)  # create a dict from all populated values
    {'price': 1000, 'name': 'Desktop PC'}

    Creating items from dicts:

    >>> Product({"name": "Laptop PC", "price": 1500})
    Product(price=1500, name='Laptop PC')

    >>> Product({"name": "Laptop PC", "lala": 1500})  # warning: unknown field in dict
    Traceback (most recent call last):
        ...
    KeyError: 'Product does not support field: lala'


Extending Item subclasses
-------------------------

You can extend Items (to add more fields or to change some metadata for some
fields) by declaring a subclass of your original Item.

For example:

.. code-block:: python

    class DiscountedProduct(Product):
        discount_percent = scrapy.Field(serializer=str)
        discount_expiration_date = scrapy.Field()

You can also extend field metadata by using the previous field metadata and
appending more values, or changing existing values, like this:

.. code-block:: python

    class SpecificProduct(Product):
        name = scrapy.Field(Product.fields["name"], serializer=my_serializer)

That adds (or replaces) the ``serializer`` metadata key for the ``name`` field,
keeping all the previously existing metadata values.


.. _supporting-item-types:

Supporting All Item Types
=========================

In code that receives an item, such as methods of :ref:`item pipelines
<topics-item-pipeline>` or :ref:`spider middlewares
<topics-spider-middleware>`, it is a good practice to use the
:class:`~itemadapter.ItemAdapter` class and the
:func:`~itemadapter.is_item` function to write code that works for
any supported item type.

Other classes related to items
==============================

.. autoclass:: ItemMeta
