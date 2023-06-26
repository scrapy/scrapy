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
``ADDONS`` setting and their optional configuration from the respective
settings.

The ``ADDONS`` setting is a dict in which every key is an addon class or its
import path and the value is its priority.

The configuration of an add-on, if necessary at all, is stored as a dictionary
setting whose name is the uppercase add-on name.

This is an example where two add-ons (in this case with one requiring no
configuration) are enabled/configured in a project's ``settings.py``::

    ADDONS = {
        'path.to.someaddon': 0,
        path.to.someaddon2: 1,
    }

    SOMEADDON = {
        'some_config': True,
    }


Writing your own add-ons
========================

Add-ons are (any) Python *objects* that provide Scrapy's *add-on interface*:

.. attribute:: name

    string with add-on name

    :type: ``str``

.. method:: update_settings(config, settings)

    This method is called during the initialization of the
    :class:`~scrapy.crawler.Crawler`. Here, you should perform dependency checks
    (e.g. for external Python libraries) and update the
    :class:`~scrapy.settings.Settings` object as wished, e.g. enable components
    for this add-on or set required configuration of other extensions.

    :param config: Configuration of this add-on
    :type config: ``dict``

    :param settings: The settings object storing Scrapy/component configuration
    :type settings: :class:`~scrapy.settings.Settings`

.. method:: check_configuration(config, crawler)

    This method is called when the :class:`~scrapy.crawler.Crawler` has been
    fully initialized, immediately before it starts crawling. You can perform
    additional dependency and configuration checks here.

    :param config: Configuration of this add-on
    :type config: ``dict``

    :param crawler: Fully initialized Scrapy crawler
    :type crawler: :class:`~scrapy.crawler.Crawler`


Add-on base class
=================

Scrapy comes with a built-in base class for add-ons which provides some
convenience functionality: the add-on configuration can be exposed into
Scrapy's settings via :meth:`~scrapy.addons.Addon.export_config`, configurable
via :attr:`~scrapy.addons.Addon.default_config` and
:attr:`~scrapy.addons.Addon.config_mapping`.

By default, the base add-on class will expose the add-on configuration into
Scrapy's settings namespace, in upper case. It is
easy to write your own functionality while still being able to use the
convenience functions by overwriting
:meth:`~scrapy.addons.Addon.update_settings`.

.. module:: scrapy.addons
   :noindex:

.. autoclass:: Addon
   :members:


Add-on examples
===============

Set some basic configuration using the :class:`Addon` base class::

    from scrapy.addons import Addon

    class MyAddon(Addon):
        name = 'myaddon'

        def update_settings(self, config, settings):
            super().update_settings(settings)
            settings["ITEM_PIPELINES"]["path.to.mypipeline"] = 200
            settings["DNSCACHE_ENABLED"] = True

Check dependencies::

    from scrapy.addons import Addon

    class MyAddon(Addon):
        name = 'myaddon'

        def update_settings(self, config, settings):
            try:
                import boto
            except ImportError:
                raise RuntimeError("myaddon requires the boto library")
            super().update_settings(settings)

Check configuration of fully initialized crawler (see
:ref:`topics-api-crawler`)::

    class MyAddon(object):
        name = 'myaddon'

        def update_settings(self, config, settings):
            super().update_settings(settings)
            settings.set('DNSCACHE_ENABLED', False, priority='addon')

        def check_configuration(self, config, crawler):
            if crawler.settings.getbool('DNSCACHE_ENABLED'):
                # The spider, some other add-on, or the user messed with the
                # DNS cache setting
                raise ValueError("myaddon is incompatible with DNS cache")
