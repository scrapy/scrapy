.. _using-asyncio:

=======
asyncio
=======

.. versionadded:: 2.0

Scrapy has partial support for :mod:`asyncio`. After you :ref:`install the
asyncio reactor <install-asyncio>`, you may use :mod:`asyncio` and
:mod:`asyncio`-powered libraries in any :doc:`coroutine <coroutines>`.


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


.. _asyncio-windows:

Windows-specific notes
======================

The Windows implementation of :mod:`asyncio` can use two event loop
implementations:

-   :class:`~asyncio.SelectorEventLoop`, default before Python 3.8, required
    when using Twisted.

-   :class:`~asyncio.ProactorEventLoop`, default since Python 3.8, cannot work
    with Twisted.

So on Python 3.8+ the event loop class needs to be changed.

.. versionchanged:: 2.6.0
   The event loop class is changed automatically when you change the
   :setting:`TWISTED_REACTOR` setting or call
   :func:`~scrapy.utils.reactor.install_reactor`.

To change the event loop class manually, call the following code before
installing the reactor::

    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

You can put this in the same function that installs the reactor, if you do that
yourself, or in some code that runs before the reactor is installed, e.g.
``settings.py``.

.. note:: Other libraries you use may require
          :class:`~asyncio.ProactorEventLoop`, e.g. because it supports
          subprocesses (this is the case with `playwright`_), so you cannot use
          them together with Scrapy on Windows (but you should be able to use
          them on WSL or native Linux).

.. _playwright: https://github.com/microsoft/playwright-python


.. _asyncio-await-dfd:

Awaiting on Deferreds
=====================

When the asyncio reactor isn't installed, you can await on Deferreds in the
coroutines directly. When it is installed, this is not possible anymore, due to
specifics of the Scrapy coroutine integration (the coroutines are wrapped into
:class:`asyncio.Future` objects, not into
:class:`~twisted.internet.defer.Deferred` directly), and you need to wrap them into
Futures. Scrapy provides two helpers for this:

.. autofunction:: scrapy.utils.defer.deferred_to_future
.. autofunction:: scrapy.utils.defer.maybe_deferred_to_future
.. tip:: If you need to use these functions in code that aims to be compatible
         with lower versions of Scrapy that do not provide these functions,
         down to Scrapy 2.0 (earlier versions do not support
         :mod:`asyncio`), you can copy the implementation of these functions
         into your own code.


.. _enforce-asyncio-requirement:

Enforcing asyncio as a requirement
==================================

If you are writing a :ref:`component <topics-components>` that requires asyncio
to work, use :func:`scrapy.utils.reactor.is_asyncio_reactor_installed` to
:ref:`enforce it as a requirement <enforce-component-requirements>`. For
example::

    from scrapy.utils.reactor import is_asyncio_reactor_installed

    class MyComponent:

        def __init__(self):
            if not is_asyncio_reactor_installed():
                raise ValueError(
                    f"{MyComponent.__qualname__} requires the asyncio Twisted "
                    f"reactor. Make sure you have it configured in the "
                    f"TWISTED_REACTOR setting. See the asyncio documentation "
                    f"of Scrapy for more information."
                )
