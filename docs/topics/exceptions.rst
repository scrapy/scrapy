.. _topics-exceptions:

==========
Exceptions
==========

.. module:: scrapy.exceptions
   :synopsis: Scrapy exceptions

.. _topics-exceptions-ref:

Built-in Exceptions reference
=============================

Here's a list of all exceptions included in Scrapy and their usage.

DropItem
--------

.. exception:: DropItem

The exception that must be raised by item pipeline stages to stop processing an
Item. For more information see :ref:`topics-item-pipeline`.

CloseSpider
-----------

.. exception:: CloseSpider(reason='cancelled')

    This exception can be raised from a spider callback to request the spider to be
    closed/stopped. Supported arguments:

    :param reason: the reason for closing
    :type reason: str

For example::

    def parse_page(self, response):
        if 'Bandwidth exceeded' in response.body:
            raise CloseSpider('bandwidth_exceeded')

IgnoreRequest
-------------

.. exception:: IgnoreRequest

This exception can be raised by the Scheduler or any downloader middleware to
indicate that the request should be ignored.

NotConfigured
-------------

.. exception:: NotConfigured

This exception can be raised by some components to indicate that they will
remain disabled. Those components include:

 * Extensions
 * Item pipelines
 * Downloader middlwares
 * Spider middlewares

The exception must be raised in the component constructor.

NotSupported
------------

.. exception:: NotSupported

This exception is raised to indicate an unsupported feature.

