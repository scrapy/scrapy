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


CloseSpider
-----------

.. exception:: CloseSpider(reason='cancelled')

    This exception can be raised from a spider callback to request the spider to be
    closed/stopped. Supported arguments:

    :param reason: the reason for closing
    :type reason: str

For example:

.. code-block:: python

    def parse_page(self, response):
        if "Bandwidth exceeded" in response.body:
            raise CloseSpider("bandwidth_exceeded")

DontCloseSpider
---------------

.. exception:: DontCloseSpider

This exception can be raised in a :signal:`spider_idle` signal handler to
prevent the spider from being closed.

DropItem
--------

.. exception:: DropItem

The exception that must be raised by item pipeline stages to stop processing an
Item. For more information see :ref:`topics-item-pipeline`.

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

-   Extensions
-   Item pipelines
-   Downloader middlewares
-   Spider middlewares

The exception must be raised in the component's ``__init__`` method.

NotSupported
------------

.. exception:: NotSupported

This exception is raised to indicate an unsupported feature.

StopDownload
-------------

.. versionadded:: 2.2

.. exception:: StopDownload(fail=True)

Raised from a :class:`~scrapy.signals.bytes_received` or :class:`~scrapy.signals.headers_received`
signal handler to indicate that no further bytes should be downloaded for a response.

The ``fail`` boolean parameter controls which method will handle the resulting
response:

* If ``fail=True`` (default), the request errback is called. The response object is
  available as the ``response`` attribute of the ``StopDownload`` exception,
  which is in turn stored as the ``value`` attribute of the received
  :class:`~twisted.python.failure.Failure` object. This means that in an errback
  defined as ``def errback(self, failure)``, the response can be accessed though
  ``failure.value.response``.

* If ``fail=False``, the request callback is called instead.

In both cases, the response could have its body truncated: the body contains
all bytes received up until the exception is raised, including the bytes
received in the signal handler that raises the exception. Also, the response
object is marked with ``"download_stopped"`` in its :attr:`Response.flags`
attribute.

.. note:: ``fail`` is a keyword-only parameter, i.e. raising
    ``StopDownload(False)`` or ``StopDownload(True)`` will raise
    a :class:`TypeError`.

See the documentation for the :class:`~scrapy.signals.bytes_received` and
:class:`~scrapy.signals.headers_received` signals
and the :ref:`topics-stop-response-download` topic for additional information and examples.
