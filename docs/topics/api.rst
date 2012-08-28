.. _topics-api:

========
Core API
========

.. versionadded:: 0.15

This section documents the Scrapy core API, and it's intended for developers of
extensions and middlewares.

.. _topics-api-crawler:

Crawler API
===========

The main entry point to Scrapy API is the :class:`~scrapy.crawler.Crawler`
object, passed to extensions through the ``from_crawler`` class method. This
object provides access to all Scrapy core components, and it's the only way for
extensions to access them and hook their functionality into Scrapy.

.. module:: scrapy.crawler
   :synopsis: The Scrapy crawler

The Extension Manager is responsible for loading and keeping track of installed
extensions and it's configured through the :setting:`EXTENSIONS` setting which
contains a dictionary of all available extensions and their order similar to
how you :ref:`configure the downloader middlewares
<topics-downloader-middleware-setting>`.

.. class:: Crawler(settings)

    The Crawler object must be instantiated with a
    :class:`scrapy.settings.Settings` object.

    .. attribute:: settings

        The settings manager of this crawler.

        This is used by extensions & middlewares to access the Scrapy settings
        of this crawler.

        For an introduction on Scrapy settings see :ref:`topics-settings`.

        For the API see :class:`~scrapy.settings.Settings` class.

    .. attribute:: signals

        The signals manager of this crawler.

        This is used by extensions & middlewares to hook themselves into Scrapy
        functionality.

        For an introduction on signals see :ref:`topics-signals`.

        For the API see :class:`~scrapy.signalmanager.SignalManager` class.

    .. attribute:: stats

        The stats collector of this crawler.

        This is used from extensions & middlewares to record stats of their
        behaviour, or access stats collected by other extensions.

        For an introduction on stats collection see :ref:`topics-stats`.

        For the API see :class:`~scrapy.statscol.StatsCollector` class.

    .. attribute:: extensions

        The extension manager that keeps track of enabled extensions.

        Most extensions won't need to access this attribute.

        For an introduction on extensions and a list of available extensions on
        Scrapy see :ref:`topics-extensions`.

    .. attribute:: spiders

        The spider manager which takes care of loading and instantiating
        spiders.

        Most extensions won't need to access this attribute.

    .. attribute:: engine

        The execution engine, which coordinates the core crawling logic
        between the scheduler, downloader and spiders.

        Some extension may want to access the Scrapy engine, to modify inspect
        or modify the downloader and scheduler behaviour, although this is an
        advanced use and this API is not yet stable.

    .. method:: configure()

        Configure the crawler.

        This loads extensions, middlewares and spiders, leaving the crawler
        ready to be started. It also configures the execution engine.

    .. method:: start()

        Start the crawler. This calss :meth:`configure` if it hasn't been called yet.

Settings API
============

.. module:: scrapy.settings
   :synopsis: Settings manager

.. class:: Settings()

    This object that provides access to Scrapy settings.

    .. attribute:: overrides

       Global overrides are the ones that take most precedence, and are usually
       populated by command-line options.

       Overrides should be populated *before* configuring the Crawler object
       (through the :meth:`~scrapy.crawler.Crawler.configure` method),
       otherwise they won't have any effect. You don't typically need to worry
       about overrides unless you are implementing your own Scrapy command.

    .. method:: get(name, default=None)

       Get a setting value without affecting its original type.

       :param name: the setting name
       :type name: string

       :param default: the value to return if no setting is found
       :type default: any

    .. method:: getbool(name, default=False)

       Get a setting value as a boolean. For example, both ``1`` and ``'1'``, and
       ``True`` return ``True``, while ``0``, ``'0'``, ``False`` and ``None``
       return ``False````

       For example, settings populated through environment variables set to ``'0'``
       will return ``False`` when using this method.

       :param name: the setting name
       :type name: string

       :param default: the value to return if no setting is found
       :type default: any

    .. method:: getint(name, default=0)

       Get a setting value as an int

       :param name: the setting name
       :type name: string

       :param default: the value to return if no setting is found
       :type default: any

    .. method:: getfloat(name, default=0.0)

       Get a setting value as a float

       :param name: the setting name
       :type name: string

       :param default: the value to return if no setting is found
       :type default: any

    .. method:: getlist(name, default=None)

       Get a setting value as a list. If the setting original type is a list it
       will be returned verbatim. If it's a string it will be split by ",".

       For example, settings populated through environment variables set to
       ``'one,two'`` will return a list ['one', 'two'] when using this method.

       :param name: the setting name
       :type name: string

       :param default: the value to return if no setting is found
       :type default: any

.. _topics-api-signals:

Signals API
===========

.. module:: scrapy.signalmanager
   :synopsis: The signal manager

.. class:: SignalManager

    .. method:: connect(receiver, signal)

        Connect a receiver function to a signal.

        The signal can be any object, although Scrapy comes with some
        predefined signals that are documented in the :ref:`topics-signals`
        section.

        :param receiver: the function to be connected
        :type receiver: callable

        :param signal: the signal to connect to
        :type signal: object

    .. method:: send_catch_log(signal, \*\*kwargs)

        Send a signal, catch exceptions and log them.

        The keyword arguments are passed to the signal handlers (connected
        through the :meth:`connect` method).

    .. method:: send_catch_log_deferred(signal, \*\*kwargs)

        Like :meth:`send_catch_log` but supports returning `deferreds`_ from
        signal handlers.

        Returns a `deferred`_ that gets fired once all signal handlers
        deferreds were fired. Send a signal, catch exceptions and log them.

        The keyword arguments are passed to the signal handlers (connected
        through the :meth:`connect` method).

    .. method:: disconnect(receiver, signal)

        Disconnect a receiver function from a signal. This has the opposite
        effect of the :meth:`connect` method, and the arguments are the same.

    .. method:: disconnect_all(signal)

        Disconnect all receivers from the given signal.

        :param signal: the signal to disconnect from
        :type signal: object

.. _topics-api-stats:

Stats Collector API
===================

There are several Stats Collectors available under the
:mod:`scrapy.statscol` module and they all implement the Stats
Collector API defined by the :class:`~scrapy.statscol.StatsCollector`
class (which they all inherit from).

.. module:: scrapy.statscol
   :synopsis: Stats Collectors

.. class:: StatsCollector

    .. method:: get_value(key, default=None, spider=None)

        Return the value for the given stats key or default if it doesn't exist.
        If spider is ``None`` the global stats table is consulted, otherwise the
        spider specific one is. If the spider is not yet opened a ``KeyError``
        exception is raised.

    .. method:: get_stats(spider=None)

        Get all stats from the given spider (if spider is given) or all global
        stats otherwise, as a dict. If spider is not opened ``KeyError`` is
        raised.

    .. method:: set_value(key, value, spider=None)

        Set the given value for the given stats key on the global stats (if
        spider is not given) or the spider-specific stats (if spider is given),
        which must be opened or a ``KeyError`` will be raised.

    .. method:: set_stats(stats, spider=None)

        Set the given stats (as a dict) for the given spider. If the spider is
        not opened a ``KeyError`` will be raised.

    .. method:: inc_value(key, count=1, start=0, spider=None)

        Increment the value of the given stats key, by the given count,
        assuming the start value given (when it's not set). If spider is not
        given the global stats table is used, otherwise the spider-specific
        stats table is used, which must be opened or a ``KeyError`` will be
        raised.

    .. method:: max_value(key, value, spider=None)

        Set the given value for the given key only if current value for the
        same key is lower than value. If there is no current value for the
        given key, the value is always set. If spider is not given, the global
        stats table is used, otherwise the spider-specific stats table is used,
        which must be opened or a KeyError will be raised.

    .. method:: min_value(key, value, spider=None)

        Set the given value for the given key only if current value for the
        same key is greater than value. If there is no current value for the
        given key, the value is always set. If spider is not given, the global
        stats table is used, otherwise the spider-specific stats table is used,
        which must be opened or a KeyError will be raised.

    .. method:: clear_stats(spider=None)

        Clear all global stats (if spider is not given) or all spider-specific
        stats if spider is given, in which case it must be opened or a
        ``KeyError`` will be raised.

    .. method:: iter_spider_stats()

        Return a iterator over ``(spider, spider_stats)`` for each open spider
        currently tracked by the stats collector, where ``spider_stats`` is the
        dict containing all spider-specific stats.

        Global stats are not included in the iterator. If you want to get
        those, use :meth:`get_stats` method.

    The following methods are not part of the stats collection api but instead
    used when implementing custom stats collectors:

    .. method:: open_spider(spider)

        Open the given spider for stats collection.

    .. method:: close_spider(spider)

        Close the given spider. After this is called, no more specific stats
        for this spider can be accessed.

    .. method:: engine_stopped()

        Called after the engine is stopped, to dump or persist global stats.

.. _deferreds: http://twistedmatrix.com/documents/current/core/howto/defer.html
.. _deferred: http://twistedmatrix.com/documents/current/core/howto/defer.html
