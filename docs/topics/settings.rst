.. _topics-settings:

========
Settings
========

.. module:: scrapy.conf
   :synopsis: Settings manager

The Scrapy settings allows you to customize the behaviour of all Scrapy
components, including the core, extensions, pipelines and spiders themselves.

The settings infrastructure provides a global namespace of key-value mappings
where the code can pull configuration values from. The settings can be
populated through different mechanisms, which are described below.

Read :ref:`settings` for all supported entries.

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

You can also override one (or more) settings from command line using the
``--set`` command line argument. 

.. highlight:: sh

Example::

    scrapy-ctl.py crawl domain.com --set=LOG_FILE:/tmp/scrapy.log

2. Environment variables
------------------------

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

Here's an example of the simplest way to access settings from Python code::

   >>> from scrapy.conf import settings
   >>> print settings['LOG_ENABLED']
   True

In other words, settings can be accesed like a dict, but it's usually preferred
to extract the setting in the format you need it to avoid type errors. In order
to do that you'll have to use one of the following methods:

.. class:: Settings()

   The Settings object is automatically instantiated when the
   :mod:`scrapy.conf` module is loaded, and it's usually accessed like this::

   >>> from scrapy.conf import settings

.. method:: Settings.get(name, default=None)

   Get a setting value without affecting its original type.

   ``name`` is a string with the setting name

   ``default`` is the value to return if no setting is found

.. method:: Settings.getbool(name, deafult=Flse)

   Get a setting value as a boolean. For example, both ``1`` and ``'1'``, and
   ``True`` return ``True``, while ``0``, ``'0'``, ``False`` and ``None``
   return ``False````

   For example, settings populated through environment variables set to ``'0'``
   will return ``False`` when using this method.

   ``name`` is a string with the setting name

   ``default`` is the value to return if no setting is found

.. method:: Settings.getint(name, default=0)

   Get a setting value as an int

   ``name`` is a string with the setting name

   ``default`` is the value to return if no setting is found

.. method:: Settings.getfloat(name, default=0.0)

   Get a setting value as a float

   ``name`` is a string with the setting name

   ``default`` is the value to return if no setting is found

.. method:: Settings.getlist(name, default=None)

   Get a setting value as a list. If the setting original type is a list it
   will be returned verbatim. If it's a string it will be splitted by ",".

   For example, settings populated through environment variables set to
   ``'one,two'`` will return a list ['one', 'two'] when using this method.

   ``name`` is a string with the setting name

   ``default`` is the value to return if no setting is found

Available built-in settings
===========================

See :ref:`settings`.

Rationale for setting names
===========================

Setting names are usually prefixed with the component that they configure. For
example, proper setting names for a fictional robots.txt extension would be
``ROBOTSTXT_ENABLED``, ``ROBOTSTXT_OBEY``, ``ROBOTSTXT_CACHEDIR``, etc.
