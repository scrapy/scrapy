.. _using-asyncio:

=======
asyncio
=======

Scrapy supports :mod:`asyncio` natively. You can use :mod:`asyncio` and
:mod:`asyncio`-powered libraries in any :doc:`coroutine <coroutines>`.

The rest of this page covers advanced topics. If you are starting a new project,
no additional setup is needed.


.. _install-asyncio:

Installing the asyncio reactor
==============================

When Scrapy installs a reactor, it will install the correct one automatically.
If you are managing the reactor yourself, when using
:class:`~scrapy.crawler.AsyncCrawlerRunner` or
:class:`~scrapy.crawler.CrawlerRunner`, you need to install the
:class:`~twisted.internet.asyncioreactor.AsyncioSelectorReactor` reactor
manually. You can do that using :func:`~scrapy.utils.reactor.install_reactor`:

.. skip: next
.. code-block:: python

    install_reactor()

.. autofunction:: scrapy.utils.reactor.install_reactor


.. _asyncio-preinstalled-reactor:

Handling a pre-installed reactor
================================

``twisted.internet.reactor`` and some other Twisted imports install the default
Twisted reactor as a side effect. Once a Twisted reactor is installed, it is
not possible to switch to a different reactor at run time.

If at run time Scrapy complains that a different reactor is already installed,
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
:class:`asyncio.Future` objects. Scrapy provides a helper for this:

.. autofunction:: scrapy.utils.defer.deferred_to_future

Coroutines and futures can be wrapped into Deferreds (for example, when a
Scrapy API requires passing a Deferred to it) using the following helpers:

.. autofunction:: scrapy.utils.defer.deferred_from_coro
.. autofunction:: scrapy.utils.defer.deferred_f_from_coro_f

The following function helps with a reverse wrapping:

.. autofunction:: scrapy.utils.defer.ensure_awaitable

.. seealso:: :ref:`asyncio-old-versions`


.. _asyncio-without-reactor:

Using Scrapy without a Twisted reactor
======================================

.. versionadded:: 2.15.0

.. warning::
    This is currently experimental and may not be suitable for production use.

.. note:: As the Twisted download handlers cannot be used without a reactor,
    the default download handler in this mode is
    :class:`~scrapy.core.downloader.handlers._aiohttp.AiohttpDownloadHandler`.

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
  :class:`~scrapy.core.downloader.handlers._aiohttp.AiohttpDownloadHandler`)
* :class:`~scrapy.core.downloader.handlers.ftp.FTPDownloadHandler` (replaced
  by :class:`~scrapy.core.downloader.handlers._aioftp.AioftpDownloadHandler`)
* :class:`~scrapy.core.downloader.handlers.http2.H2DownloadHandler`
* :ref:`topics-telnetconsole`
* :class:`~scrapy.crawler.CrawlerRunner` and
  :class:`~scrapy.crawler.CrawlerProcess`
  (:class:`~scrapy.crawler.AsyncCrawlerProcess` and
  :class:`~scrapy.crawler.AsyncCrawlerRunner` are available)
* Twisted-specific DNS resolvers (the :setting:`TWISTED_DNS_RESOLVER` setting)
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
  set to ``"scrapy.core.downloader.handlers._aiohttp.AiohttpDownloadHandler"``.
* The ``"ftp"`` and ``"ftps"`` keys in :setting:`DOWNLOAD_HANDLERS_BASE` are
  set to ``"scrapy.core.downloader.handlers._aioftp.AioftpDownloadHandler"``.

Thus, :class:`~scrapy.core.downloader.handlers._aiohttp.AiohttpDownloadHandler`
is used by default for making HTTP(S) requests. Please refer to its
documentation for its differences and limitations compared to
:class:`~scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler`.

Additionally, :class:`~scrapy.crawler.AsyncCrawlerProcess` will install a
:term:`meta path finder` that prevents :mod:`twisted.internet.reactor` from
being imported. It will be uninstalled when :meth:`AsyncCrawlerProcess.start()
<scrapy.crawler.AsyncCrawlerProcess.start>` exits.

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
  tasks. As there is no direct replacement in the standard library, you can use
  :class:`scrapy.utils.asyncio.AsyncioLoopingCall` or write your own simple
  implementation using :func:`asyncio.sleep` in a task.
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

Scrapy provides this replacement for
:class:`~twisted.internet.task.LoopingCall`:

.. autoclass:: scrapy.utils.asyncio.AsyncioLoopingCall

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
automatically when installing the asyncio reactor.

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

You can use custom asyncio event loops. Set the :setting:`ASYNCIO_EVENT_LOOP`
setting to the import path of the desired event loop class to use it instead of
the default asyncio event loop.


.. _asyncio-old-versions:

Supporting older Scrapy versions
================================

Scrapy before 2.13.0 doesn't use the asyncio reactor by default, and users of
newer versions can opt out of it, so if you have code that uses asyncio APIs
you should decide which configurations to support.

.. _enforce-asyncio-requirement:

Enforcing asyncio as a requirement
----------------------------------

If your code requires asyncio to work, or you want to make it simpler, use
:func:`scrapy.utils.asyncio.is_asyncio_available` to :ref:`enforce asyncio as a
requirement <enforce-component-requirements>`. For example:

.. code-block:: python

    try:
        from scrapy.utils.asyncio import is_asyncio_available
    except ImportError:  # Scrapy < 2.14
        from scrapy.utils.reactor import (
            is_asyncio_reactor_installed as is_asyncio_available,
        )


    class MyComponent:
        def __init__(self):
            if not is_asyncio_available():
                raise ValueError(f"{MyComponent.__qualname__} requires asyncio support.")

With this in place you can safely write code that assumes asyncio support, e.g.
code that calls asyncio APIs, awaits on futures and uses
:func:`~scrapy.utils.defer.deferred_to_future` to await on Deferreds.

.. autofunction:: scrapy.utils.asyncio.is_asyncio_available

Making asyncio optional
-----------------------

If, instead, you also want to support configurations where asyncio isn't
available, you cannot use asyncio-specific APIs directly. This includes
:func:`~scrapy.utils.defer.deferred_to_future`; you should use the following
function instead:

.. autofunction:: scrapy.utils.defer.maybe_deferred_to_future

You can also write two branches of the same code for asyncio and non-asyncio
environments, switching between them using
:func:`~scrapy.utils.asyncio.is_asyncio_available`.

Additionally, Scrapy provides unified helpers for some useful APIs that
automatically choose a Twisted-based implementation when asyncio is not
available:

.. autofunction:: scrapy.utils.asyncio.sleep
.. autofunction:: scrapy.utils.asyncio.call_later
.. autofunction:: scrapy.utils.asyncio.create_looping_call
.. autofunction:: scrapy.utils.asyncio.run_in_thread

Using newer helpers
-------------------

Many of the asyncio-related Scrapy helpers are only available in some Scrapy
versions; in that case their documentation shows the first version where that
specific helper is available. If you want to use a helper with a Scrapy version
where it's not available, you can simply copy the relevant code into your
project.

When you want to check whether the Scrapy version used provides a given helper,
prefer a ``try ... except ImportError`` approach to comparing the versions
directly, as future Scrapy versions will drop some of these helpers.

You can also :ref:`require a specific minimum Scrapy version
<enforce-component-requirements>`.
