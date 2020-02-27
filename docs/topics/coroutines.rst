==========
Coroutines
==========

.. versionadded:: 2.0

Scrapy has partial support for the :ref:`coroutine syntax <async>`.

The following callables may be defined as coroutines using ``async def``, and
hence use coroutine syntax (e.g. ``await``, ``async for``, ``async with``):

-   :class:`~scrapy.http.Request` callbacks.

    .. note:: Because `asynchronous generators were introduced in Python 3.6`_,
              you can only use ``yield`` if you are using Python 3.6 or later.

              If you need to output multiple items or requests and you are
              using Python 3.5, return an iterable (e.g. a list) instead.

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

.. _asynchronous generators were introduced in Python 3.6: https://www.python.org/dev/peps/pep-0525/
