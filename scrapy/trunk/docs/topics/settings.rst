===============
Scrapy settings
===============

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
 3. Per-command defaults
 4. scrapy_settings
 5. Global defaults (less precedence)

This mechanisms are described with more detail below.

1. Global overrides
-------------------

Global overrides are the ones that takes most precedence, and are usually
populated as a results of command line modifiers.

Example::
   >>> from scrapy.conf import settings
   >>> settings.overrides['LOG_ENABLED'] = True

2. Environment variables
------------------------

You can populate settings using environment variables prefixed with
``SCRAPY_``. For example, to change the log file location::

    $ export SCRAPY_LOG_FILE=/tmp/scrapy.log
    $ scrapy-ctl.py crawl example.com

3. Per-command defaults
-----------------------

Each scrapy-ctl command can have its own default settings, which override the
default Scrapy settings. Those custom command settings are usually located in
inside scrapy.conf.commands, or inside the module specified in the
:setting:`COMMANDS_SETTINGS_MODULE` setting.

4. scrapy_settings
------------------

scrapy_settings is the standard configuration file for your Scrapy project.
It's where most of your custom settings will be populated.

5. Global defaults
------------------

The global defaults are located in scrapy.conf.default_settings and documented
in the :reference:`settings` page.


How to access settings
======================

To access settings from Python code::

   >>> from scrapy.conf import settings
   >>> print settings['LOG_ENABLED']
   True

Available settings
==================

See :reference:`settings`.

Rationale for setting names
===========================

Setting names are usually prefixed with the component that they configure. For
example, proper setting names for a fictitional robots.txt extension would be
``ROBOTSTXT_ENABLED``, ``ROBOTSTXT_OBEY``, ``ROBOTSTXT_CACHEDIR``, etc.
