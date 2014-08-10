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

        Start the crawler. This calls :meth:`configure` if it hasn't been called yet.
        Returns a deferred that is fired when the crawl is finished.

.. _topics-api-settings:

Settings API
============

.. module:: scrapy.settings
   :synopsis: Settings manager

.. attribute:: SETTINGS_PRIORITIES

    Dictionary that sets the key name and priority level of the default
    settings priorities used in Scrapy.

    Each item defines a settings entry point, giving it a code name for
    identification and an integer priority. Greater priorities take more
    precedence over lesser ones when setting and retrieving values in the
    :class:`~scrapy.settings.Settings` class.

    .. highlight:: python

    ::

        SETTINGS_PRIORITIES = {
            'default': 0,
            'command': 10,
            'project': 20,
            'cmdline': 40,
        }

    For a detailed explanation on each settings sources, see:
    :ref:`topics-settings`.

.. class:: Settings(values={}, priority='project')

    This object stores Scrapy settings for the configuration of internal
    components, and can be used for any further customization.

    After instantiation of this class, the new object will have the global
    default settings described on :ref:`topics-settings-ref` already
    populated.

    Additional values can be passed on initialization with the ``values``
    argument, and they would take the ``priority`` level.  If the latter
    argument is a string, the priority name will be looked up in
    :attr:`~scrapy.settings.SETTINGS_PRIORITIES`. Otherwise, a expecific
    integer should be provided.

    Once the object is created, new settings can be loaded or updated with the
    :meth:`~scrapy.settings.Settings.set` method, and can be accessed with the
    square bracket notation of dictionaries, or with the
    :meth:`~scrapy.settings.Settings.get` method of the instance and its value
    conversion variants.  When requesting a stored key, the value with the
    highest priority will be retrieved.

    .. method:: set(name, value, priority='project')

       Store a key/value attribute with a given priority.

       Settings should be populated *before* configuring the Crawler object
       (through the :meth:`~scrapy.crawler.Crawler.configure` method),
       otherwise they won't have any effect.

       :param name: the setting name
       :type name: string

       :param value: the value to associate with the setting
       :type value: any

       :param priority: the priority of the setting. Should be a key of
           :attr:`~scrapy.settings.SETTINGS_PRIORITIES` or an integer
       :type priority: string or int

    .. method:: setdict(values, priority='project')

       Store key/value pairs with a given priority.

       This is a helper function that calls
       :meth:`~scrapy.settings.Settings.set` for every item of ``values``
       with the provided ``priority``.

       :param values: the settings names and values
       :type values: dict

       :param priority: the priority of the settings. Should be a key of
           :attr:`~scrapy.settings.SETTINGS_PRIORITIES` or an integer
       :type priority: string or int

    .. method:: setmodule(module, priority='project')

       Store settings from a module with a given priority.

       This is a helper function that calls
       :meth:`~scrapy.settings.Settings.set` for every globally declared
       uppercase variable of ``module`` with the provided ``priority``.

       :param module: the module or the path of the module
       :type module: module object or string

       :param priority: the priority of the settings. Should be a key of
           :attr:`~scrapy.settings.SETTINGS_PRIORITIES` or an integer
       :type priority: string or int

    .. method:: get(name, default=None, required=False)

       Get a setting value without affecting its original type.

       :param name: the setting name
       :type name: string

       :param default: the value to return if no setting is found
       :type default: any

       :param required: if ``True`` and it returns ``None`` will raise a
            :class:`~scrapy.exceptions.NotConfigured` exception
       :type required: boolean

    .. method:: getbool(name, default=False, required=False)

       Get a setting value as a boolean. For example, both ``1`` and ``'1'``, and
       ``True`` return ``True``, while ``0``, ``'0'``, ``False`` and ``None``
       return ``False````

       For example, settings populated through environment variables set to ``'0'``
       will return ``False`` when using this method.

       :param name: the setting name
       :type name: string

       :param default: the value to return if no setting is found
       :type default: any

       :param required: if ``True`` and it returns ``None`` will raise a
            :class:`~scrapy.exceptions.NotConfigured` exception
       :type required: boolean

    .. method:: getint(name, default=0, required=False)

       Get a setting value as an int

       :param name: the setting name
       :type name: string

       :param default: the value to return if no setting is found
       :type default: any

       :param required: if ``True`` and it returns ``None`` will raise a
            :class:`~scrapy.exceptions.NotConfigured` exception
       :type required: boolean

    .. method:: getfloat(name, default=0.0, required=False)

       Get a setting value as a float

       :param name: the setting name
       :type name: string

       :param default: the value to return if no setting is found
       :type default: any

       :param required: if ``True`` and it returns ``None`` will raise a
            :class:`~scrapy.exceptions.NotConfigured` exception
       :type required: boolean

    .. method:: getlist(name, default=None, required=False)

       Get a setting value as a list. If the setting original type is a list it
       will be returned verbatim. If it's a string it will be split by ",".

       For example, settings populated through environment variables set to
       ``'one,two'`` will return a list ['one', 'two'] when using this method.

       :param name: the setting name
       :type name: string

       :param default: the value to return if no setting is found
       :type default: any

       :param required: if ``True`` and it returns ``None`` will raise a
            :class:`~scrapy.exceptions.NotConfigured` exception
       :type required: boolean

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

    .. method:: get_value(key, default=None)

        Return the value for the given stats key or default if it doesn't exist.

    .. method:: get_stats()

        Get all stats from the currently running spider as a dict.

    .. method:: set_value(key, value)

        Set the given value for the given stats key.

    .. method:: set_stats(stats)

        Override the current stats with the dict passed in ``stats`` argument.

    .. method:: inc_value(key, count=1, start=0)

        Increment the value of the given stats key, by the given count,
        assuming the start value given (when it's not set).

    .. method:: max_value(key, value)

        Set the given value for the given key only if current value for the
        same key is lower than value. If there is no current value for the
        given key, the value is always set. 

    .. method:: min_value(key, value)

        Set the given value for the given key only if current value for the
        same key is greater than value. If there is no current value for the
        given key, the value is always set.

    .. method:: clear_stats()

        Clear all stats.

    The following methods are not part of the stats collection api but instead
    used when implementing custom stats collectors:

    .. method:: open_spider(spider)

        Open the given spider for stats collection.

    .. method:: close_spider(spider)

        Close the given spider. After this is called, no more specific stats
        can be accessed or collected.

.. _deferreds: http://twistedmatrix.com/documents/current/core/howto/defer.html
.. _deferred: http://twistedmatrix.com/documents/current/core/howto/defer.html
