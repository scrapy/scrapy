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

.. _asyncio-await-dfd:

Awaiting on Deferreds
=====================

When the asyncio reactor isn't installed, you can await on Deferreds in the
coroutines directly. When it is installed, this is not possible anymore, due to
specifics of the Scrapy coroutine integration (the coroutines are wrapped into
asyncio Futures, not into Deferreds directly), and you need to wrap them into
Futures. Scrapy provides two helpers for this:

.. autofunction:: scrapy.utils.defer.deferred_to_future
.. autofunction:: scrapy.utils.defer.maybe_deferred_to_future
.. versionadded:: VERSION
.. note:: In earlier versions of Scrapy you can implement these functions yourself.

If you want to write universal code that works on any reactor,
you should use ``maybe_deferred_to_future`` on all Deferreds::

    from scrapy.utils.defer import maybe_deferred_to_future

    class MySpider(Spider):
        # ...
        async def parse_with_deferred(self, response):
            additional_response = await maybe_deferred_to_future(treq.get('https://additional.url'))
            additional_data = await maybe_deferred_to_future(treq.content(additional_response))
            # ... use response and additional_data to yield items and requests
