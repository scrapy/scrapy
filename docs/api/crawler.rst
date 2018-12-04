.. _topics-api-crawler:

===========
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

.. class:: Crawler(spidercls, settings)

    The Crawler object must be instantiated with a
    :class:`scrapy.spiders.Spider` subclass and a
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

    .. method:: crawl(\*args, \**kwargs)

        Starts the crawler by instantiating its spider class with the given
        `args` and `kwargs` arguments, while setting the execution engine in
        motion.

        Returns a deferred that is fired when the crawl is finished.

.. autoclass:: CrawlerRunner
   :members:

.. autoclass:: CrawlerProcess
   :show-inheritance:
   :members:
   :inherited-members:
