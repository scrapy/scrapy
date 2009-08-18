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

.. exception:: DontCloseDomain

DontCloseDomain
---------------

This exception can be raised by any handler of the :signal:`domain_idle` signal
to avoid the domain from being closed at this time, and wait for the next idle
state.

.. exception:: DropItem

DropItem
--------

The exception that must be raised by item pipeline stages to stop processing an
Item. For more information see :ref:`topics-item-pipeline`.

.. exception:: HttpException

HttpException
-------------

This exception is raised by the downloader when a non-200 response has been
downloaded.

.. exception:: IgnoreRequest

IgnoreRequest
-------------

This exception can be raised by the Scheduler or any downlaoder middleware to
indicate that the request should be ignored.

.. exception:: NotConfigured

NotConfigured
-------------

This exception can be raised by some components to indicate that they will
remain disabled. Those component include:

 * Extensions
 * Item pipelines
 * Downloader middlwares
 * Spider middlewares

The exception must be raised in the component constructor.

.. exception:: NotSupported

NotSupported
------------

This exception is raised to indicate an unsupported feature.

