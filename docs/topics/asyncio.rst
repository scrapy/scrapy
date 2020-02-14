===============
asyncio support
===============

.. versionadded:: 2.0.0

Scrapy has limited support for :mod:`asyncio`, including support for
:ref:`coroutine syntax <async>`.

.. warning:: :mod:`asyncio` support in Scrapy is experimental. Future Scrapy
             versions may introduce related API and behavior changes without a
             deprecation period or warning.

Installing the asyncio reactor
==============================

Set the :setting:`TWISTED_REACTOR` setting to
``twisted.internet.asyncioreactor.AsyncioSelectorReactor`` to enable
:mod:`asyncio` support.

If you are using :class:`~scrapy.crawler.CrawlerRunner`, you also need to
install the :class:`~twisted.internet.asyncioreactor.AsyncioSelectorReactor`
reactor manually. You can do that using
:func:`~scrapy.utils.reactor.install_reactor`::

    install_reactor('twisted.internet.asyncioreactor.AsyncioSelectorReactor')
