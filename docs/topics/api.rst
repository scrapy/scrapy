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

.. autoclass:: Crawler
   :members:

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

.. autodata:: SETTINGS_PRIORITIES

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

.. autointerface:: scrapy.interfaces.ISpiderLoader
   :members: from_settings, load, list, find_by_request
..
    Members listed explicitly due to
    https://bitbucket.org/birkenfeld/sphinx-contrib/issues/208

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

.. autoclass:: StatsCollector
  :members:
