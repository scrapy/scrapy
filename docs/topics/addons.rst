.. _topics-addons:

=======
Add-ons
=======

Scrapy's add-on system is a framework which unifies managing and configuring
components that extend Scrapy's core functionality, such as middlewares,
extensions, or pipelines. It provides users with a plug-and-play experience in
Scrapy extension management, and grants extensive configuration control to
developers.


Activating and configuring add-ons
==================================

Add-ons and their configuration live in Scrapy's
:class:`~scrapy.addons.AddonManager`. During a :class:`~scrapy.crawler.Crawler`
initialization the add-on manager will read a list of enabled add-ons from your
``ADDONS`` setting.

The ``ADDONS`` setting is a dict in which every key is an addon class or its
import path and the value is its priority.

This is an example where two add-ons are enabled in a project's
``settings.py``::

    ADDONS = {
        'path.to.someaddon': 0,
        path.to.someaddon2: 1,
    }


Writing your own add-ons
========================

Add-ons are (any) Python *objects* that include the following method:

.. method:: update_settings(settings)

    This method is called during the initialization of the
    :class:`~scrapy.crawler.Crawler`. Here, you should perform dependency checks
    (e.g. for external Python libraries) and update the
    :class:`~scrapy.settings.Settings` object as wished, e.g. enable components
    for this add-on or set required configuration of other extensions.

    :param settings: The settings object storing Scrapy/component configuration
    :type settings: :class:`~scrapy.settings.Settings`


Add-on examples
===============

Set some basic configuration::

    class MyAddon:
        def update_settings(self, settings):
            settings["ITEM_PIPELINES"]["path.to.mypipeline"] = 200
            settings["DNSCACHE_ENABLED"] = True

Check dependencies::

    class MyAddon:
        def update_settings(self, settings):
            try:
                import boto
            except ImportError:
                raise RuntimeError("MyAddon requires the boto library")
            ...
