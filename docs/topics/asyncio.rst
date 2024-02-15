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


.. _asyncio-preinstalled-reactor:

Handling a pre-installed reactor
================================

``twisted.internet.reactor`` and some other Twisted imports install the default
Twisted reactor as a side effect. Once a Twisted reactor is installed, it is
not possible to switch to a different reactor at run time.

If you :ref:`configure the asyncio Twisted reactor <install-asyncio>` and, at
run time, Scrapy complains that a different reactor is already installed,
chances are you have some such imports in your code.

You can usually fix the issue by moving those offending module-level Twisted
imports to the method or function definitions where they are used. For example,
if you have something like:

.. code-block:: python

    from twisted.internet import reactor


    def my_function():
        reactor.callLater(...)

Switch to something like:

.. code-block:: python

    def my_function():
        from twisted.internet import reactor

        reactor.callLater(...)

Alternatively, you can try to :ref:`manually install the asyncio reactor
<install-asyncio>`, with :func:`~scrapy.utils.reactor.install_reactor`, before
those imports happen.


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
example:

.. code-block:: python

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


.. _asyncio-windows:

Windows-specific notes
======================

The Windows implementation of :mod:`asyncio` can use two event loop
implementations, :class:`~asyncio.ProactorEventLoop` (default) and
:class:`~asyncio.SelectorEventLoop`. However, only
:class:`~asyncio.SelectorEventLoop` works with Twisted.

Scrapy changes the event loop class to :class:`~asyncio.SelectorEventLoop`
automatically when you change the :setting:`TWISTED_REACTOR` setting or call
:func:`~scrapy.utils.reactor.install_reactor`.

.. note:: Other libraries you use may require
          :class:`~asyncio.ProactorEventLoop`, e.g. because it supports
          subprocesses (this is the case with `playwright`_), so you cannot use
          them together with Scrapy on Windows (but you should be able to use
          them on WSL or native Linux).

.. _playwright: https://github.com/microsoft/playwright-python


.. _using-custom-loops:

Using custom asyncio loops
==========================

You can also use custom asyncio event loops with the asyncio reactor. Set the
:setting:`ASYNCIO_EVENT_LOOP` setting to the import path of the desired event
loop class to use it instead of the default asyncio event loop.
