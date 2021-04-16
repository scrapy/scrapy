.. _using-asyncio:

=======
asyncio
=======

.. versionadded:: 2.0

Scrapy has partial support for :mod:`asyncio`. After you :ref:`install the
asyncio reactor <install-asyncio>`, you may use :mod:`asyncio` and
:mod:`asyncio`-powered libraries in any :doc:`coroutine <coroutines>`.

.. warning:: :mod:`asyncio` support in Scrapy is experimental, and not yet
             recommended for production environments. Future Scrapy versions
             may introduce related changes without a deprecation period or
             warning.

.. _install-asyncio:

Installing the asyncio reactor
==============================

To enable :mod:`asyncio` support, set the :setting:`TWISTED_REACTOR` setting to
``'twisted.internet.asyncioreactor.AsyncioSelectorReactor'``.

If you are using :class:`~scrapy.crawler.CrawlerRunner`, you also need to
install the :class:`~twisted.internet.asyncioreactor.AsyncioSelectorReactor`
reactor manually. You can do that using
:func:`~scrapy.utils.reactor.install_reactor`::

    install_reactor('twisted.internet.asyncioreactor.AsyncioSelectorReactor')

.. _using-custom-loops:

Using custom asyncio loops
==========================    

You can also use custom asyncio event loops with the asyncio reactor. Set the
:setting:`ASYNCIO_EVENT_LOOP` setting to the import path of the desired event loop class to
use it instead of the default asyncio event loop.



