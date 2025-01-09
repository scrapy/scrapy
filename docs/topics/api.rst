.. _topics-api:

========
Core API
========

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

.. autoclass:: Crawler
    :members: get_addon, get_downloader_middleware, get_extension,
        get_item_pipeline, get_spider_middleware

    The Crawler object must be instantiated with a
    :class:`scrapy.Spider` subclass and a
    :class:`scrapy.settings.Settings` object.

    .. attribute:: request_fingerprinter

        The request fingerprint builder of this crawler.

        This is used from extensions and middlewares to build short, unique
        identifiers for requests. See :ref:`request-fingerprints`.

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

        For the API see :class:`~scrapy.statscollectors.StatsCollector` class.

    .. attribute:: extensions

        The extension manager that keeps track of enabled extensions.

        Most extensions won't need to access this attribute.

        For an introduction on extensions and a list of available extensions on
        Scrapy see :ref:`topics-extensions`.

    .. attribute:: engine

        The execution engine, which coordinates the core crawling logic
        between the scheduler, downloader and spiders.

        Some extension may want to access the Scrapy engine, to inspect  or 
        modify the downloader and scheduler behaviour, although this is an
        advanced use and this API is not yet stable.

    .. attribute:: spider

        Spider currently being crawled. This is an instance of the spider class
        provided while constructing the crawler, and it is created after the
        arguments given in the :meth:`crawl` method.

    .. method:: crawl(*args, **kwargs)

        Starts the crawler by instantiating its spider class with the given
        ``args`` and ``kwargs`` arguments, while setting the execution engine in
        motion. Should be called only once.

        Returns a deferred that is fired when the crawl is finished.

    .. automethod:: stop

.. autoclass:: CrawlerRunner
   :members:

.. autoclass:: CrawlerProcess
   :show-inheritance:
   :members:
   :inherited-members:

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

    .. code-block:: python

        SETTINGS_PRIORITIES = {
            "default": 0,
            "command": 10,
            "addon": 15,
            "project": 20,
            "spider": 30,
            "cmdline": 40,
        }

    For a detailed explanation on each settings sources, see:
    :ref:`topics-settings`.

.. autofunction:: get_settings_priority

.. autoclass:: Settings
   :show-inheritance:
   :members:

.. autoclass:: BaseSettings
   :members:

.. _topics-api-spiderloader:

SpiderLoader API
================

.. module:: scrapy.spiderloader
   :synopsis: The spider loader

.. class:: SpiderLoader

    This class is in charge of retrieving and handling the spider classes
    defined across the project.

    Custom spider loaders can be employed by specifying their path in the
    :setting:`SPIDER_LOADER_CLASS` project setting. They must fully implement
    the :class:`scrapy.interfaces.ISpiderLoader` interface to guarantee an
    errorless execution.

    .. method:: from_settings(settings)

       This class method is used by Scrapy to create an instance of the class.
       It's called with the current project settings, and it loads the spiders
       found recursively in the modules of the :setting:`SPIDER_MODULES`
       setting.

       :param settings: project settings
       :type settings: :class:`~scrapy.settings.Settings` instance

    .. method:: load(spider_name)

       Get the Spider class with the given name. It'll look into the previously
       loaded spiders for a spider class with name ``spider_name`` and will raise
       a KeyError if not found.

       :param spider_name: spider class name
       :type spider_name: str

    .. method:: list()

       Get the names of the available spiders in the project.

    .. method:: find_by_request(request)

       List the spiders' names that can handle the given request. Will try to
       match the request's url against the domains of the spiders.

       :param request: queried request
       :type request: :class:`~scrapy.Request` instance

.. _topics-api-signals:

Signals API
===========

.. automodule:: scrapy.signalmanager
    :synopsis: The signal manager
    :members:
    :undoc-members:

.. _topics-api-stats:

Stats Collector API
===================

There are several Stats Collectors available under the
:mod:`scrapy.statscollectors` module and they all implement the Stats
Collector API defined by the :class:`~scrapy.statscollectors.StatsCollector`
class (which they all inherit from).

.. module:: scrapy.statscollectors
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
