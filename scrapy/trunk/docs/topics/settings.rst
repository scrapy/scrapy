.. _topics-settings:

========
Settings
========

The Scrapy settings allows you to customize the behaviour of all Scrapy
components, including the core, extensions, pipelines and spiders themselves.

The settings infrastructure provides a global namespace of key-value mappings
where the code can pull configuration values from. The settings can be
populated through different mechanisms, which are described below.

How to populate settings
========================

Settings can be populated using different mechanisms, each of which having a
different precedence. Here is the list of them in decreasing order of
precedence:

 1. Global overrides (most precedence)
 2. Environment variables
 3. scrapy_settings
 4. Default settings per-command
 5. Default global settings (less precedence)

This mechanisms are described with more detail below.

1. Global overrides
-------------------

Global overrides are the ones that takes most precedence, and are usually
populated by command line options.

Example::
   >>> from scrapy.conf import settings
   >>> settings.overrides['LOG_ENABLED'] = True

2. Environment variables
------------------------

.. highlight:: sh

You can populate settings using environment variables prefixed with
``SCRAPY_``. For example, to change the log file location::

    $ export SCRAPY_LOG_FILE=/tmp/scrapy.log
    $ scrapy-ctl.py crawl example.com

3. scrapy_settings
------------------

scrapy_settings is the standard configuration file for your Scrapy project.
It's where most of your custom settings will be populated.

4. Default settings per-command
-------------------------------

Each scrapy-ctl command can have its own default settings, which override the
global default settings. Those custom command settings are located inside the
``scrapy.conf.commands`` module, or you can specify custom settings to override
per-comand inside your project, by writing them in the module referenced by the
:setting:`COMMANDS_SETTINGS_MODULE` setting. Those settings will take more

5. Default global settings
--------------------------

The global defaults are located in scrapy.conf.default_settings and documented
in the :ref:`settings` page.


How to access settings
======================

.. highlight:: python

To access settings from Python code::

   >>> from scrapy.conf import settings
   >>> print settings['LOG_ENABLED']
   True

Available settings
==================

See :ref:`settings`.

Rationale for setting names
===========================

Setting names are usually prefixed with the component that they configure. For
example, proper setting names for a fictional robots.txt extension would be
``ROBOTSTXT_ENABLED``, ``ROBOTSTXT_OBEY``, ``ROBOTSTXT_CACHEDIR``, etc.
