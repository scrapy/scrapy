.. _ref-newitem-fields:

====================
Item Field Reference
====================

.. module:: scrapy.contrib_exp.newitem.fields

Field options
=============

``default``
-----------

.. attribute:: Field.default

The default value for the field.


Field types
===========

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

