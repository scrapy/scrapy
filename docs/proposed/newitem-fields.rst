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

``BooleanField``
----------------

.. class:: BooleanField

A true/false field.

``DateField``
-------------

.. class:: DateField

A date, represented in Python by a ``datetime.date`` instance.

``DateTimeField``
-----------------

.. class:: DateTimeField

A date with time, represented in Python by a ``datetime.datetime`` instance.

``DecimalField``
----------------

.. class:: DecimalField

A fixed-precision decimal number, represented in Python by a :class:`~decimal.Decimal` instance.

``FloatField``
--------------

.. class:: FloatField

A floating-point number represented in Python by a ``float`` instance.

``IntegerField``
----------------

.. class:: IntegerField

An integer.

``StringField``
---------------

A text field.

.. class:: StringField


