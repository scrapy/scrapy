===============
asyncio support
===============

.. versionadded:: 2.0

Scrapy has partial support for :mod:`asyncio` and
:ref:`coroutine syntax <async>`.

.. warning:: :mod:`asyncio` support in Scrapy is experimental. Future Scrapy
             versions may introduce related API and behavior changes without a
             deprecation period or warning.

Installing the asyncio reactor
==============================

To enable :mod:`asyncio` support, set the :setting:`TWISTED_REACTOR` setting to
``twisted.internet.asyncioreactor.AsyncioSelectorReactor``.

If you are using :class:`~scrapy.crawler.CrawlerRunner`, you also need to
install the :class:`~twisted.internet.asyncioreactor.AsyncioSelectorReactor`
reactor manually. You can do that using
:func:`~scrapy.utils.reactor.install_reactor`::

    install_reactor('twisted.internet.asyncioreactor.AsyncioSelectorReactor')


Coroutine support
=================

The following callables may be defined as coroutines and use
:ref:`coroutine syntax <async>`:

-   :class:`~scrapy.http.Request` callbacks.

    However, you cannot use ``yield``. If you need to output multiple items or
    requests, return an iterable (e.g. a list) instead.

-   The :meth:`process_item` method of
    :ref:`item pipelines <topics-item-pipeline>`.

-   The
    :meth:`~scrapy.downloadermiddlewares.DownloaderMiddleware.process_request`,
    :meth:`~scrapy.downloadermiddlewares.DownloaderMiddleware.process_response`,
    and
    :meth:`~scrapy.downloadermiddlewares.DownloaderMiddleware.process_exception`
    methods of
    :ref:`downloader middlewares <topics-downloader-middleware-custom>`.

-   :ref:`Signal handlers that support deferreds <signal-deferred>`.
