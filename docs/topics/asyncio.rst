.. _using-asyncio:

=======
asyncio
=======

Scrapy has partial support for :mod:`asyncio`. After you :ref:`install the
asyncio reactor <install-asyncio>`, you may use :mod:`asyncio` and
:mod:`asyncio`-powered libraries in any :doc:`coroutine <coroutines>`.


.. _install-asyncio:

Installing the asyncio reactor
==============================

To enable :mod:`asyncio` support, your :setting:`TWISTED_REACTOR` setting needs
to be set to ``'twisted.internet.asyncioreactor.AsyncioSelectorReactor'``,
which is the default value.

If you are using :class:`~scrapy.crawler.AsyncCrawlerRunner` or
:class:`~scrapy.crawler.CrawlerRunner`, you also need to
install the :class:`~twisted.internet.asyncioreactor.AsyncioSelectorReactor`
reactor manually. You can do that using
:func:`~scrapy.utils.reactor.install_reactor`:

.. skip: next
.. code-block:: python

    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")


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

.. skip: next
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

Integrating Deferred code and asyncio code
==========================================

Coroutine functions can await on Deferreds by wrapping them into
:class:`asyncio.Future` objects. Scrapy provides two helpers for this:

.. autofunction:: scrapy.utils.defer.deferred_to_future
.. autofunction:: scrapy.utils.defer.maybe_deferred_to_future

.. tip:: If you don't need to support reactors other than the default
         :class:`~twisted.internet.asyncioreactor.AsyncioSelectorReactor`, you
         can use :func:`~scrapy.utils.defer.deferred_to_future`, otherwise you
         should use :func:`~scrapy.utils.defer.maybe_deferred_to_future`.

.. tip:: If you need to use these functions in code that aims to be compatible
         with lower versions of Scrapy that do not provide these functions,
         down to Scrapy 2.0 (earlier versions do not support
         :mod:`asyncio`), you can copy the implementation of these functions
         into your own code.

Coroutines and futures can be wrapped into Deferreds (for example, when a
Scrapy API requires passing a Deferred to it) using the following helpers:

.. autofunction:: scrapy.utils.defer.deferred_from_coro
.. autofunction:: scrapy.utils.defer.deferred_f_from_coro_f
.. autofunction:: scrapy.utils.defer.ensure_awaitable


.. _enforce-asyncio-requirement:

Enforcing asyncio as a requirement
==================================

If you are writing a :ref:`component <topics-components>` that requires asyncio
to work, use :func:`scrapy.utils.asyncio.is_asyncio_available` to
:ref:`enforce it as a requirement <enforce-component-requirements>`. For
example:

.. code-block:: python

    from scrapy.utils.asyncio import is_asyncio_available


    class MyComponent:
        def __init__(self):
            if not is_asyncio_available():
                raise ValueError(
                    f"{MyComponent.__qualname__} requires the asyncio support. "
                    f"Make sure you have configured the asyncio reactor in the "
                    f"TWISTED_REACTOR setting. See the asyncio documentation "
                    f"of Scrapy for more information."
                )

.. autofunction:: scrapy.utils.asyncio.is_asyncio_available
.. autofunction:: scrapy.utils.reactor.is_asyncio_reactor_installed


.. _asyncio-without-reactor:

Using Scrapy without a Twisted reactor
======================================

.. versionadded:: 2.15.0

.. warning::
    This is currently experimental and may not be suitable for production use.

It's possible to use Scrapy without installing a Twisted reactor at all, by
setting the :setting:`TWISTED_REACTOR_ENABLED` setting to ``False``. In this
mode Scrapy will use the asyncio event loop directly, and most of the Scrapy
functionality will work in the same way.

Doing this provides several benefits in certain use cases:

* A Twisted reactor, once stopped, cannot be started again. This prevents, for
  example, using several instances of
  :class:`~scrapy.crawler.AsyncCrawlerProcess` in the same process when they
  use a reactor, but with ``TWISTED_REACTOR_ENABLED=False`` it becomes
  possible.
* There may be limitations imposed by
  :class:`~twisted.internet.asyncioreactor.AsyncioSelectorReactor` and related
  Twisted code, such as the requirement of using
  :class:`~asyncio.SelectorEventLoop` on Windows (see :ref:`asyncio-windows`),
  that do not apply if the reactor is not used.
* :class:`~twisted.internet.asyncioreactor.AsyncioSelectorReactor` manages the
  underlying event loop, and while :class:`~scrapy.crawler.AsyncCrawlerRunner`
  can use a pre-existing reactor which, in turn, can use a pre-existing event
  loop, it's easier to use :class:`~scrapy.crawler.AsyncCrawlerRunner` with a
  pre-existing loop directly.
* Omitting the reactor machinery may improve performance and reliability.

Limitations
-----------

As some Scrapy features and components require a reactor, they don't work and
are disabled without it. Replacements that don't require a reactor may be added
in future Scrapy versions. The following features are not available:

* The default HTTP(S) download handler,
  :class:`~scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler` (this
  is likely the biggest difference; Scrapy provides an HTTP(S) download handler
  that doesn't require a reactor and will be used instead of it:
  :class:`~scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler`)
* :class:`~scrapy.core.downloader.handlers.ftp.FTPDownloadHandler`
* :class:`~scrapy.core.downloader.handlers.http2.H2DownloadHandler`
* :ref:`topics-shell`
* :ref:`topics-telnetconsole`
* :class:`~scrapy.crawler.CrawlerRunner` and
  :class:`~scrapy.crawler.CrawlerProcess`
  (:class:`~scrapy.crawler.AsyncCrawlerProcess` and
  :class:`~scrapy.crawler.AsyncCrawlerRunner` are available)
* Twisted-specific DNS resolvers (the :setting:`DNS_RESOLVER` setting)
* User and 3rd-party code that requires a reactor (see :ref:`below
  <asyncio-without-reactor-migrate>` for examples)

Note that importing Twisted modules and, among other things, creating and using
:class:`~twisted.internet.defer.Deferred` objects doesn't require a reactor, so
code that uses :class:`~twisted.internet.defer.Deferred`,
:class:`~twisted.python.failure.Failure` and some other Twisted APIs will not
necessarily stop working.

Other differences
-----------------

When :setting:`TWISTED_REACTOR_ENABLED` is set to ``False``, Scrapy will change
the defaults of some other settings:

* :setting:`TELNETCONSOLE_ENABLED` is set to ``False``.
* The ``"http"`` and ``"https"`` keys in :setting:`DOWNLOAD_HANDLERS_BASE` are
  set to ``"scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler"``.
* The ``"ftp"`` key in :setting:`DOWNLOAD_HANDLERS_BASE` is set to ``None``.

Thus, :class:`~scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler` is
used by default for making HTTP(S) requests. Please refer to its documentation
for its differences and limitations compared to
:class:`~scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler`.

Additionally, :class:`~scrapy.crawler.AsyncCrawlerProcess` will install a
:term:`meta path finder` that prevents :mod:`twisted.internet.reactor` from
being imported.

.. _asyncio-without-reactor-migrate:

Adding support to existing code
-------------------------------

Code that doesn't directly use Twisted APIs or APIs that depend on Twisted ones
doesn't need special support for running without a reactor.

Here are some examples of APIs and patterns that need a replacement:

* Using :meth:`reactor.callLater()
  <twisted.internet.base.ReactorBase.callLater>` for sleeping or delayed calls.
  You can use :meth:`asyncio.loop.call_later` instead.
* Using :func:`twisted.internet.threads.deferToThread`,
  :meth:`reactor.callFromThread()
  <twisted.internet.base.ReactorBase.callFromThread>` and related APIs to
  execute code in other threads. You can use :func:`asyncio.to_thread`,
  :meth:`asyncio.loop.call_soon_threadsafe` and related APIs instead.
* Using :class:`twisted.internet.task.LoopingCall` for scheduling repeated
  tasks. As there is no direct replacement in the standard library, you may
  need to write your own one using :func:`asyncio.sleep` in a task.
* Using Twisted network client and server APIs (:meth:`reactor.connectTCP()
  <twisted.internet.interfaces.IReactorTCP.connectTCP>`,
  :meth:`reactor.listenTCP()
  <twisted.internet.interfaces.IReactorTCP.listenTCP>`,
  :mod:`twisted.web.client`, :mod:`twisted.mail.smtp` etc.). You can use other
  built-in or 3rd-party libraries for this.
* Using :class:`~scrapy.crawler.CrawlerProcess` or
  :class:`~scrapy.crawler.CrawlerRunner`. You should use
  :class:`~scrapy.crawler.AsyncCrawlerProcess` or
  :class:`~scrapy.crawler.AsyncCrawlerRunner` respectively instead.
* Checking whether ``asyncio`` support is available with
  :func:`scrapy.utils.reactor.is_asyncio_reactor_installed`. You should use
  :func:`scrapy.utils.asyncio.is_asyncio_available` instead.

Scrapy provides unified helpers for some of these examples:

.. autofunction:: scrapy.utils.asyncio.call_later
.. autofunction:: scrapy.utils.asyncio.create_looping_call
.. autoclass:: scrapy.utils.asyncio.AsyncioLoopingCall
.. autofunction:: scrapy.utils.asyncio.run_in_thread

If your code needs to know whether the reactor is available, you can either
check for the value of the :setting:`TWISTED_REACTOR_ENABLED` setting (you need
access to the :class:`~scrapy.crawler.Crawler` instance to do this) or use the
following function:

.. autofunction:: scrapy.utils.reactorless.is_reactorless

In general, code that doesn't use the reactor (directly or indirectly) can be
used unmodified both with the asyncio reactor and without a reactor. This
includes code that converts Deferreds to futures and vice versa as described in
:ref:`asyncio-await-dfd`.

Troubleshooting
---------------

**ImportError: Import of twisted.internet.reactor is forbidden when running
without a Twisted reactor [...]:** Scrapy is configured to run without a
reactor, but some code imported :mod:`twisted.internet.reactor`, most likely
because that code needs a reactor to be used. You need to stop using this code
or set :setting:`TWISTED_REACTOR_ENABLED` back to ``True``. It's also possible
that the reactor isn't really needed but was installed due to the problem
described in :ref:`asyncio-preinstalled-reactor`, in which case it should be
enough to fix the problematic imports.

**RuntimeError: TWISTED_REACTOR_ENABLED is False but a Twisted reactor is
installed:** Scrapy is configured to run without a reactor, but a reactor is
already installed before the Scrapy code is executed. If you are trying to set
:setting:`TWISTED_REACTOR_ENABLED` via :ref:`per-spider settings
<spider-settings>`, it's currently unsupported.

**RuntimeError: We expected a Twisted reactor to be installed but it isn't:**
Scrapy is configured to run with a reactor and not to install one, but a
reactor wasn't installed before the Scrapy code is executed. If you are trying
to set :setting:`TWISTED_REACTOR_ENABLED` via :ref:`per-spider settings
<spider-settings>`, it's currently unsupported.

**RuntimeError: <class> doesn't support TWISTED_REACTOR_ENABLED=False:** The
listed class cannot be used with :setting:`TWISTED_REACTOR_ENABLED` set to
``False``. There may be a replacement in the :ref:`documentation above
<asyncio-without-reactor>` or the documentation of the affected class.


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

.. note:: This problem doesn't apply when not using the reactor, see
    :ref:`asyncio-without-reactor`.

.. _playwright: https://github.com/microsoft/playwright-python


.. _using-custom-loops:

Using custom asyncio loops
==========================

You can also use custom asyncio event loops with the asyncio reactor. Set the
:setting:`ASYNCIO_EVENT_LOOP` setting to the import path of the desired event
loop class to use it instead of the default asyncio event loop.


.. _disable-asyncio:

Switching to a non-asyncio reactor
==================================

If for some reason your code doesn't work with the asyncio reactor, you can use
a different reactor by setting the :setting:`TWISTED_REACTOR` setting to its
import path (e.g. ``'twisted.internet.epollreactor.EPollReactor'``) or to
``None``, which will use the default reactor for your platform. If you are
using :class:`~scrapy.crawler.AsyncCrawlerRunner` or
:class:`~scrapy.crawler.AsyncCrawlerProcess` you also need to switch to their
Deferred-based counterparts: :class:`~scrapy.crawler.CrawlerRunner` or
:class:`~scrapy.crawler.CrawlerProcess` respectively.
