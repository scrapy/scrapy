.. _topics-exceptions:

==========
Exceptions
==========

.. module:: scrapy.core.exceptions
   :synopsis: Core exceptions

.. _topics-exceptions-ref:

Built-in Exceptions reference
=============================

Here's a list of all exceptions included in Scrapy and their usage.

DropItem
--------

.. exception:: DropItem

The exception that must be raised by item pipeline stages to stop processing an
Item. For more information see :ref:`topics-item-pipeline`.

IgnoreRequest
-------------

.. exception:: IgnoreRequest

This exception can be raised by the Scheduler or any downlaoder middleware to
indicate that the request should be ignored.

NotConfigured
-------------

.. exception:: NotConfigured

This exception can be raised by some components to indicate that they will
remain disabled. Those component include:

 * Extensions
 * Item pipelines
 * Downloader middlwares
 * Spider middlewares

The exception must be raised in the component constructor.

NotSupported
------------

.. exception:: NotSupported

This exception is raised to indicate an unsupported feature.

