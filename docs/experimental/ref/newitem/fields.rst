.. _ref-newitem-fields:

===========
Item Fields
===========

.. module:: scrapy.contrib_exp.newitem.fields

Field options
=============

Every ``Field`` class constructor accepts these arguments.

``default``
-----------

The default value for the field. See :ref:`topics-newitem-index-defaults`.

Field types
===========

These are the available built-in ``Field`` types. See
:ref:`ref-newitem-fields-custom-fields` for info on creating your own field types.

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

.. _ref-newitem-fields-custom-fields:

Creating custom fields
======================

All field classes are subclasses of the :class:`BaseField` class (see below)
which you can also subclass to create your own custom fields. 

You can also subclass a more specific field class, say :class:`DecimalField`,
to implement a ``PriceField``, for example.

BaseField class
---------------

.. class:: BaseField(default=None)

    The base class for all fields. It only provides code for handling default
    values, not any particular type. It cannot be used directly either, as its
    :meth:`BaseField.to_python` method is not implemented.

    The ``default`` argument (if given) must be of the type expected by this
    field, or any type that is accepted by the :meth:`BaseField.to_python`
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

