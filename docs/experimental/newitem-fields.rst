.. _ref-newitem-fields:

=====================
Item Fields Reference
=====================

Item Fields can be used to specify the type of each Item attribute and its
default value. For example::

    from scrapy.contrib_exp.newitem import Item, fields

    class NewsItem(Item):
        content = fields.TextField()
        author = fields.TextField(default=u'Myself')
        published = fields.DateField()
        views = fields.IntegerField(default=0)

Fields which contain a default value will always return that value when not
set, while fields which don't contain a default value will always return
``None`` when not set::

    >>> it = NewsItem()
    >>> it.content is None
    True
    >>> it.author
    u'Myself'
    >>> it.published is None
    True
    >>> it.views
    0

All field classes are subclasses of the :class:`BaseField` class which you can
also subclass to create your own custom fields. But you can also subclass a
more specific field class, say :class:`DecimalField`, to implement a
``PriceField``, for example.

.. module:: scrapy.contrib_exp.newitem.fields

BaseField class
===============

.. class:: BaseField(default=None)

    The base class for all fields. It only provides code for handling default
    values, not any particular type. It cannot be used directly either, as its
    :meth:`BaseField.to_python` method is not implemented.

    The ``default`` argument (if given) must be of the type expected by this
    field, or any type that is accepted by the :meth:``BaseField.to_python``
    method of this field.

    For example::

        class NewsItem(Item):
            content = fields.TextField() # correct, no default value
            author = fields.TextField(default=u'Myself") # correct, with default value
            published = fields.DateField(default=23) # wrong default type (will raise TypeError) 

    .. method:: to_python(value)

       Convert the input value to the type expected by this field and return
       it.
       
       For example, :class:`IntegerField` would convert ``'1'`` to ``1``, while
       :class:`DecimalField` would convert ``'1'`` to ``Decimal('1')`` and so
       on.
       
       This method is not implemented in the :class:`BaseField` class, so it
       must always be implemented in all its subclasses, in order to be usable.

       This method should raise ``TypeError`` if the input type is not
       supported, and ``ValueError`` if the input type is support but its value
       is not appropriate (for example, an integer outside a given range).

       This method must always return object of the expected field type.
       
    .. method:: get_default()

       Return the default value for this field, or ``None`` if the field
       doesn't specify any.


Available built-in Fields
=========================

TextField
---------

.. class:: TextField

    A unicode text.

IntegerField
------------

.. class:: IntegerField

    An integer.

DecimalField
------------

.. class:: DecimalField

    A fixed-precision decimal number, represented in Python by a `Decimal`_
    instance.

.. _Decimal: http://docs.python.org/library/decimal.html#decimal.Decimal

FloatField
----------

.. class:: FloatField

    A floating-point number represented in Python by a ``float`` instance.

BooleanField
------------

.. class:: BooleanField

    A boolean (true/false) field.

DateTimeField
-------------

.. class:: DateTimeField

    A date with time, represented in Python by a `datetime.datetime`_ instance.

.. _datetime.datetime: http://docs.python.org/library/datetime.html#datetime.datetime

DateField
---------

.. class:: DateField

    A date, represented in Python by a `datetime.date`_ instance.

.. _datetime.date: http://docs.python.org/library/datetime.html#datetime.date

TimeField
---------

.. class:: TimeField

    A time, represented in Python by a `datetime.time`_ instance.

.. _datetime.time: http://docs.python.org/library/datetime.html#datetime.time

