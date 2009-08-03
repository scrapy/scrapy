.. _ref-newitem-fields:

===========
Item Fields
===========

.. module:: scrapy.newitem.fields


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


``BooleanField``
----------------

.. class:: BooleanField

    A boolean (true/false) field.


``DateField``
-------------

.. class:: DateField

    A date, represented in Python by a `datetime.date`_ instance.

.. _datetime.date: http://docs.python.org/library/datetime.html#datetime.date


``DateTimeField``
-----------------

.. class:: DateTimeField

    A date with time, represented in Python by a `datetime.datetime`_ instance.

.. _datetime.datetime: http://docs.python.org/library/datetime.html#datetime.datetime


``DecimalField``
----------------

.. class:: DecimalField

    A fixed-precision decimal number, represented in Python by a `Decimal`_
    instance.

.. _Decimal: http://docs.python.org/library/decimal.html#decimal.Decimal


``FloatField``
--------------

.. class:: FloatField

    A floating-point number represented in Python by a ``float`` instance.


``IntegerField``
----------------

.. class:: IntegerField

    An integer.


``ListField``
-------------

.. class:: ListField(field)

   A special field that works like a list of fields of another provided field kind.

   :param field: The field which the elements of this list must conform to. 
   :type field: a :class:`~scrapy.newitem.fields.BaseField` object

   Usage example::

      class ExampleItem(Item)
         names = fields.ListField(fields.TextField())

      item = ExampleItem()
      item['names'] = [u'John', u'Jeena']


``TextField``
-------------

.. class:: TextField

    A unicode text.

    This class overrides the following methods from :class:`BaseField`:

    .. method:: from_unicode_list(unicode_list)

       Return a unicode string composed by joining the elements of
       ``unicode_list`` with spaces.

       For more info about this method see :class:`BaseField.from_unicode_list`.


``TimeField``
-------------

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
       
    .. method:: from_unicode_list(unicode_list)

       Take the input list of unicode strings and convert it to a proper value
       with the type expected by this field. If no proper value if found,
       ``None`` is returned instead.

       The default behaviour is to return the value of the first item of the
       list, passed through the :meth:`to_python` method, or ``None`` if the
       list is empty::

          return self.to_python(unicode_list[0]) if unicode_list else None

       This default behaviour is provided because it's the more common one, but
       it's typical for :class:`BaseField` subclasses to override this method,
       such as the :meth:`TextField.from_unicode_list` method.

    .. method:: get_default()

       Return the default value for this field, or ``None`` if the field
       doesn't specify any.

