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

Read :ref:`topics-settings-ref` for all supported entries.

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

    scrapy-ctl.py crawl domain.com --set LOG_FILE=scrapy.log

2. Environment variables
------------------------

You can populate settings using environment variables prefixed with
``SCRAPY_``. For example, to change the log file location un Unix systems::

    $ export SCRAPY_LOG_FILE=scrapy.log
    $ scrapy-ctl.py crawl example.com

In Windows systems, you can change the environment variables from the Control
Panel following `these guidelines`_.

.. _these guidelines: http://www.microsoft.com/resources/documentation/windows/xp/all/proddocs/en-us/sysdm_advancd_environmnt_addchange_variable.mspx

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
in the :ref:`topics-settings-ref` section.

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

Rationale for setting names
===========================

Setting names are usually prefixed with the component that they configure. For
example, proper setting names for a fictional robots.txt extension would be
``ROBOTSTXT_ENABLED``, ``ROBOTSTXT_OBEY``, ``ROBOTSTXT_CACHEDIR``, etc.


.. _topics-settings-ref:

Built-in settings reference
===========================

Here's a list of all available Scrapy settings, in alphabetical order, along
with their default values and the scope where they apply. 

The scope, where available, shows where the setting is being used, if it's tied
to any particular component. In that case the module of that component will be
shown, typically an extension, middleware or pipeline. It also means that the
component must be enabled in order for the setting to have any effect.

.. setting:: BOT_NAME

BOT_NAME
--------

Default: ``scrapybot``

The name of the bot implemented by this Scrapy project. This will be used to
construct the User-Agent by default, and also for logging.

.. setting:: BOT_VERSION

BOT_VERSION
-----------

Default: ``1.0``

The version of the bot implemented by this Scrapy project. This will be used to
construct the User-Agent by default.

.. setting:: HTTPCACHE_DIR

HTTPCACHE_DIR
-------------

Default: ``''`` (empty string)

The directory to use for storing the (low-level) HTTP cache. If empty the HTTP
cache will be disabled.

.. setting:: HTTPCACHE_EXPIRATION_SECS

HTTPCACHE_EXPIRATION_SECS
-------------------------

Default: ``0``

Number of seconds to use for HTTP cache expiration. Requests that were cached
before this time will be re-downloaded. If zero, cached requests will always
expire. Negative numbers means requests will never expire.

.. setting:: HTTPCACHE_IGNORE_MISSING

HTTPCACHE_IGNORE_MISSING
------------------------

Default: ``False``

If enabled, requests not found in the cache will be ignored instead of downloaded. 

.. setting:: HTTPCACHE_SECTORIZE

HTTPCACHE_SECTORIZE
-------------------

Default: ``True``

Whether to split HTTP cache storage in several dirs for performance.

.. setting:: COMMANDS_MODULE

COMMANDS_MODULE
---------------

Default: ``''`` (empty string)

A module to use for looking for custom Scrapy commands. This is used to add
custom command for your Scrapy project.

Example::

    COMMANDS_MODULE = 'mybot.commands'

.. setting:: COMMANDS_SETTINGS_MODULE

COMMANDS_SETTINGS_MODULE
------------------------

Default: ``''`` (empty string)

A module to use for looking for custom Scrapy command settings.

Example::

    COMMANDS_SETTINGS_MODULE = 'mybot.conf.commands'

.. setting:: CONCURRENT_DOMAINS

CONCURRENT_DOMAINS
------------------

Default: ``8``

Maximum number of domains to scrape in parallel.

.. setting:: CONCURRENT_ITEMS

CONCURRENT_ITEMS
----------------

Default: ``100``

Maximum number of concurrent items (per response) to process in parallel in the
Item Processor (also known as the Item Pipeline).

.. setting:: COOKIES_DEBUG

COOKIES_DEBUG
-------------

Default: ``False``

Enable debugging message of Cookies Downloader Middleware.

.. setting:: DEFAULT_ITEM_CLASS

DEFAULT_ITEM_CLASS
------------------

Default: ``'scrapy.item.Item'``

The default class that will be used for instantiating items in the :ref:`the
Scrapy shell <topics-shell>`.

.. setting:: DEFAULT_REQUEST_HEADERS

DEFAULT_REQUEST_HEADERS
-----------------------

Default::

    {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en',
    }

The default headers used for Scrapy HTTP Requests. They're populated in the
:class:`~scrapy.contrib.downloadermiddleware.defaultheaders.DefaultHeadersMiddleware`.

.. setting:: DEFAULT_SPIDER

DEFAULT_SPIDER
--------------

Default: ``None``

The default spider class that will be instantiated for URLs for which no
specific spider is found. This class must have a constructor which receives as
only parameter the domain name of the given URL.

.. setting:: DEPTH_LIMIT

DEPTH_LIMIT
-----------

Default: ``0``

The maximum depth that will be allowed to crawl for any site. If zero, no limit
will be imposed.

.. setting:: DEPTH_STATS

DEPTH_STATS
-----------

Default: ``True``

Whether to collect depth stats.

.. setting:: DOMAIN_SCHEDULER

DOMAIN_SCHEDULER
----------------

Default: ``'scrapy.contrib.domainsch.FifoDomainScheduler'``

The Domain Scheduler to use. The domain scheduler returns the next domain
(spider) to scrape.

.. setting:: DOWNLOADER_DEBUG

DOWNLOADER_DEBUG
----------------

Default: ``False``

Whether to enable the Downloader debugging mode.

.. setting:: DOWNLOADER_MIDDLEWARES

DOWNLOADER_MIDDLEWARES
----------------------

Default:: ``{}``

A dict containing the downloader middlewares enabled in your project, and their
orders. For more info see :ref:`topics-downloader-middleware-setting`.

.. setting:: DOWNLOADER_MIDDLEWARES_BASE

DOWNLOADER_MIDDLEWARES_BASE
---------------------------

Default:: 

    {
        'scrapy.contrib.downloadermiddleware.robotstxt.RobotsTxtMiddleware': 100,
        'scrapy.contrib.downloadermiddleware.httpauth.HttpAuthMiddleware': 300,
        'scrapy.contrib.downloadermiddleware.useragent.UserAgentMiddleware': 400,
        'scrapy.contrib.downloadermiddleware.retry.RetryMiddleware': 500,
        'scrapy.contrib.downloadermiddleware.defaultheaders.DefaultHeadersMiddleware': 550,
        'scrapy.contrib.downloadermiddleware.redirect.RedirectMiddleware': 600,
        'scrapy.contrib.downloadermiddleware.cookies.CookiesMiddleware': 700,
        'scrapy.contrib.downloadermiddleware.httpcompression.HttpCompressionMiddleware': 800,
        'scrapy.contrib.downloadermiddleware.stats.DownloaderStats': 850,
        'scrapy.contrib.downloadermiddleware.httpcache.HttpCacheMiddleware': 900,
    }

A dict containing the downloader middlewares enabled by default in Scrapy. You
should never modify this setting in your project, modify
:setting:`DOWNLOADER_MIDDLEWARES` instead.  For more info see
:ref:`topics-downloader-middleware-setting`.

.. setting:: DOWNLOADER_STATS

DOWNLOADER_STATS
----------------

Default: ``True``

Whether to enable downloader stats collection.

.. setting:: DOWNLOAD_DELAY

DOWNLOAD_DELAY
--------------

Default: ``0``

The amount of time (in secs) that the downloader should wait before downloading
consecutive pages from the same spider. This can be used to throttle the
crawling speed to avoid hitting servers too hard. Decimal numbers are
supported.  Example::

    DOWNLOAD_DELAY = 0.25    # 250 ms of delay 

.. setting:: DOWNLOAD_TIMEOUT

DOWNLOAD_TIMEOUT
----------------

Default: ``180``

The amount of time (in secs) that the downloader will wait before timing out.

.. setting:: DUPEFILTER_CLASS

DUPEFILTER_CLASS
----------------

Default: ``'scrapy.contrib.dupefilter.RequestFingerprintDupeFilter'``

The class used to detect and filter duplicate requests.

The default (``RequestFingerprintDupeFilter``) filters based on request fingerprint
(using ``scrapy.utils.request.request_fingerprint``) and grouping per domain.

.. setting:: EXTENSIONS

EXTENSIONS
----------

Default:: ``{}``

A dict containing the extensions enabled in your project, and their orders. 

.. setting:: EXTENSIONS_BASE

EXTENSIONS_BASE
---------------

Default:: 

    {
        'scrapy.stats.corestats.CoreStats': 0,
        'scrapy.management.web.WebConsole': 0,
        'scrapy.management.telnet.TelnetConsole': 0,
        'scrapy.contrib.webconsole.scheduler.SchedulerQueue': 0,
        'scrapy.contrib.webconsole.livestats.LiveStats': 0,
        'scrapy.contrib.webconsole.spiderctl.Spiderctl': 0,
        'scrapy.contrib.webconsole.enginestatus.EngineStatus': 0,
        'scrapy.contrib.webconsole.stats.StatsDump': 0,
        'scrapy.contrib.spider.reloader.SpiderReloader': 0,
        'scrapy.contrib.memusage.MemoryUsage': 0,
        'scrapy.contrib.memdebug.MemoryDebugger': 0,
        'scrapy.contrib.closedomain.CloseDomain': 0,
        'scrapy.contrib.debug.StackTraceDump': 0,
    }

The list of available extensions. Keep in mind that some of them need need to
be enabled through a setting. By default, this setting contains all stable
built-in extensions. 

For more information See the :ref:`extensions user guide  <topics-extensions>`
and the :ref:`list of available extensions <topics-extensions-ref>`.

.. setting:: GROUPSETTINGS_ENABLED

GROUPSETTINGS_ENABLED
---------------------

Default: ``False``

Whether to enable group settings where spiders pull their settings from.

.. setting:: GROUPSETTINGS_MODULE

GROUPSETTINGS_MODULE
--------------------

Default: ``''`` (empty string)

The module to use for pulling settings from, if the group settings is enabled. 

.. setting:: ITEM_PIPELINES

ITEM_PIPELINES
--------------

Default: ``[]``

The item pipelines to use (a list of classes).

Example::

   ITEM_PIPELINES = [
       'mybot.pipeline.validate.ValidateMyItem',
       'mybot.pipeline.validate.StoreMyItem'
   ]

.. setting:: LOG_ENABLED

LOG_ENABLED
-----------

Default: ``True``

Enable logging.

.. setting:: LOG_STDOUT

LOG_STDOUT
----------

Default: ``False``

If enabled logging will be sent to standard output, otherwise standard error
will be used.

.. setting:: LOGFILE

LOGFILE
-------

Default: ``None``

File name to use for logging output. If None, standard input (or error) will be
used depending on the value of the LOG_STDOUT setting.

.. setting:: LOGLEVEL

LOGLEVEL
--------

Default: ``'DEBUG'``

Minimum level to log. Available levels are: SILENT, CRITICAL, ERROR, WARNING,
INFO, DEBUG, TRACE

.. setting:: MAIL_FROM

MAIL_FROM
---------

Default: ``'scrapy@localhost'``

Email to use as sender address for sending emails using the :ref:`Scrapy e-mail
sending facility <topics-email>`.

.. setting:: MAIL_HOST

MAIL_HOST
---------

Default: ``'localhost'``

Host to use for sending emails using the :ref:`Scrapy e-mail sending facility
<topics-email>`.

.. setting:: MEMDEBUG_ENABLED

MEMDEBUG_ENABLED
----------------

Default: ``False``

Whether to enable memory debugging.

.. setting:: MEMDEBUG_NOTIFY

MEMDEBUG_NOTIFY
---------------

Default: ``[]``

When memory debugging is enabled a memory report will be sent to the specified
addresses if this setting is not empty, otherwise the report will be written to
the log.

Example::

    MEMDEBUG_NOTIFY = ['user@example.com']

.. setting:: MEMUSAGE_ENABLED

MEMUSAGE_ENABLED
----------------

Default: ``False``

Scope: ``scrapy.contrib.memusage``

Whether to enable the memory usage extension that will shutdown the Scrapy
process when it exceeds a memory limit, and also notify by email when that
happened.

See :ref:`topics-extensions-ref-memusage`.

.. setting:: MEMUSAGE_LIMIT_MB

MEMUSAGE_LIMIT_MB
-----------------

Default: ``0``

Scope: ``scrapy.contrib.memusage``

The maximum amount of memory to allow (in megabytes) before shutting down
Scrapy  (if MEMUSAGE_ENABLED is True). If zero, no check will be performed.

See :ref:`topics-extensions-ref-memusage`.

.. setting:: MEMUSAGE_NOTIFY_MAIL

MEMUSAGE_NOTIFY_MAIL
--------------------

Default: ``False``

Scope: ``scrapy.contrib.memusage``

A list of emails to notify if the memory limit has been reached.

Example::

    MEMUSAGE_NOTIFY_MAIL = ['user@example.com']

See :ref:`topics-extensions-ref-memusage`.

.. setting:: MEMUSAGE_REPORT

MEMUSAGE_REPORT
---------------

Default: ``False``

Scope: ``scrapy.contrib.memusage``

Whether to send a memory usage report after each domain has been closed.

See :ref:`topics-extensions-ref-memusage`.

.. setting:: MEMUSAGE_WARNING_MB

MEMUSAGE_WARNING_MB
-------------------

Default: ``0``

Scope: ``scrapy.contrib.memusage``

The maximum amount of memory to allow (in megabytes) before sending a warning
email notifying about it. If zero, no warning will be produced.

.. setting:: MYSQL_CONNECTION_SETTINGS

MYSQL_CONNECTION_SETTINGS
-------------------------

Default: ``{}``

Scope: ``scrapy.utils.db.mysql_connect``

Settings to use for MySQL connections performed through
``scrapy.utils.db.mysql_connect``

.. setting:: NEWSPIDER_MODULE

NEWSPIDER_MODULE
----------------

Default: ``''``

Module where to create new spiders using the ``genspider`` command.

Example::

    NEWSPIDER_MODULE = 'mybot.spiders_dev'

.. setting:: PROJECT_NAME

PROJECT_NAME
------------

Default: ``Not Defined``

The name of the current project. It matches the project module name as created
by ``startproject`` command, and is only defined by project settings file.

.. setting:: REDIRECT_MAX_TIMES

REDIRECT_MAX_TIMES
------------------

Default: ``20``

Defines the maximun times a request can be redirected. After this maximun the
request's response is returned as is. We used Firefox default value for the
same task.

.. setting:: REDIRECT_MAX_METAREFRESH_DELAY

REDIRECT_MAX_METAREFRESH_DELAY
------------------------------

Default: ``100``

Some sites use meta-refresh for redirecting to a session expired page, so we
restrict automatic redirection to a maximum delay (in seconds)

.. setting:: REDIRECT_PRIORITY_ADJUST

REDIRECT_PRIORITY_ADJUST
------------------------------

Default: ``+2``

Adjust redirect request priority relative to original request.
A negative priority adjust means more priority.

.. setting:: REQUESTS_PER_DOMAIN

REQUESTS_PER_DOMAIN
-------------------

Default: ``8``

Specifies how many concurrent (ie. simultaneous) requests will be performed per
open spider.

.. setting:: REQUESTS_QUEUE_SIZE

REQUESTS_QUEUE_SIZE
-------------------

Default: ``0``

Scope: ``scrapy.contrib.spidermiddleware.limit``

If non zero, it will be used as an upper limit for the amount of requests that
can be scheduled per domain.

.. setting:: ROBOTSTXT_OBEY

ROBOTSTXT_OBEY
--------------

Default: ``False``

Scope: ``scrapy.contrib.downloadermiddleware.robotstxt``

If enabled, Scrapy will respect robots.txt policies. For more information see
:topic:`robotstxt`

.. setting:: SCHEDULER

SCHEDULER
---------

Default: ``'scrapy.core.scheduler.Scheduler'``

The scheduler to use for crawling.

.. setting:: SCHEDULER_ORDER 

SCHEDULER_ORDER
---------------

Default: ``'BFO'``

Scope: ``scrapy.core.scheduler``

The order to use for the crawling scheduler. Available orders are: 

* ``'BFO'``:  `Breadth-first order`_ - typically consumes more memory but
  reaches most relevant pages earlier.

* ``'DFO'``:  `Depth-first order`_ - typically consumes less memory than
  but takes longer to reach most relevant pages.

.. _Breadth-first order: http://en.wikipedia.org/wiki/Breadth-first_search
.. _Depth-first order: http://en.wikipedia.org/wiki/Depth-first_search

.. setting:: SCHEDULER_MIDDLEWARES

SCHEDULER_MIDDLEWARES
---------------------

Default:: ``{}``

A dict containing the scheduler middlewares enabled in your project, and their
orders. 

.. setting:: SCHEDULER_MIDDLEWARES_BASE

SCHEDULER_MIDDLEWARES_BASE
--------------------------

Default:: 

    SCHEDULER_MIDDLEWARES_BASE = {
        'scrapy.contrib.schedulermiddleware.duplicatesfilter.DuplicatesFilterMiddleware': 500,
    }

A dict containing the scheduler middlewares enabled by default in Scrapy. You
should never modify this setting in your project, modify
:setting:`SCHEDULER_MIDDLEWARES` instead. 

.. setting:: SPIDERPROFILER_ENABLED

SPIDERPROFILER_ENABLED
----------------------

Default: ``False``

Enable the spider profiler. Warning: this could have a big impact in
performance.

.. setting:: SPIDER_MIDDLEWARES

SPIDER_MIDDLEWARES
------------------

Default:: ``{}``

A dict containing the spider middlewares enabled in your project, and their
orders. For more info see :ref:`topics-spider-middleware-setting`.

.. setting:: SPIDER_MIDDLEWARES_BASE

SPIDER_MIDDLEWARES_BASE
-----------------------

Default::

    {
        'scrapy.contrib.spidermiddleware.httperror.HttpErrorMiddleware': 50,
        'scrapy.contrib.itemsampler.ItemSamplerMiddleware': 100,
        'scrapy.contrib.spidermiddleware.requestlimit.RequestLimitMiddleware': 200,
        'scrapy.contrib.spidermiddleware.restrict.RestrictMiddleware': 300,
        'scrapy.contrib.spidermiddleware.offsite.OffsiteMiddleware': 500,
        'scrapy.contrib.spidermiddleware.referer.RefererMiddleware': 700,
        'scrapy.contrib.spidermiddleware.urllength.UrlLengthMiddleware': 800,
        'scrapy.contrib.spidermiddleware.depth.DepthMiddleware': 900,
    }

A dict containing the spider middlewares enabled by default in Scrapy. You
should never modify this setting in your project, modify
:setting:`SPIDER_MIDDLEWARES` instead. For more info see
:ref:`topics-spider-middleware-setting`.

.. setting:: SPIDER_MODULES

SPIDER_MODULES
--------------

Default: ``[]``

A list of modules where Scrapy will look for spiders.

Example::

    SPIDER_MODULES = ['mybot.spiders_prod', 'mybot.spiders_dev']

.. setting:: STATS_CLASS

STATS_CLASS
-----------

Default: ``'scrapy.stats.collector.MemoryStatsCollector'``

The class to use for collecting stats (must implement the Stats Collector API,
or subclass the StatsCollector class).

.. setting:: STATS_DUMP

STATS_DUMP
----------

Default: ``False``

Dump (to log) domain-specific stats collected when a domain is closed, and all
global stats when the Scrapy process finishes (ie. when the engine is
shutdown).

.. setting:: STATS_ENABLED

STATS_ENABLED
-------------

Default: ``True``

Enable stats collection.

.. setting:: STATSMAILER_RCPTS

STATSMAILER_RCPTS
-----------------

Default: ``[]`` (empty list)

Send Scrapy stats after domains finish scrapy. See
:class:`~scrapy.contrib.statsmailer.StatsMailer` for more info.

.. setting:: TELNETCONSOLE_ENABLED

TELNETCONSOLE_ENABLED
---------------------

Default: ``True``

Scope: ``scrapy.management.telnet``

A boolean which specifies if the telnet management console will be enabled
(provided its extension is also enabled).

.. setting:: TELNETCONSOLE_PORT

TELNETCONSOLE_PORT
------------------

Default: ``6023``

The port to use for the telnet console. If set to ``None`` or ``0``, a
dynamically assigned port is used. For more info see
:ref:`topics-telnetconsole`.

.. setting:: TEMPLATES_DIR

TEMPLATES_DIR
-------------

Default: ``templates`` dir inside scrapy module

The directory where to look for template when creating new projects with
scrapy-admin.py newproject.

.. setting:: URLLENGTH_LIMIT

URLLENGTH_LIMIT
---------------

Default: ``2083``

Scope: ``contrib.spidermiddleware.urllength``

The maximum URL length to allow for crawled URLs. For more information about
the default value for this setting see: http://www.boutell.com/newfaq/misc/urllength.html

.. setting:: USER_AGENT

USER_AGENT
----------

Default: ``"%s/%s" % (BOT_NAME, BOT_VERSION)``

The default User-Agent to use when crawling, unless overrided. 

.. setting:: WEBCONSOLE_ENABLED

WEBCONSOLE_ENABLED
------------------

Default: True

A boolean which specifies if the web management console will be enabled
(provided its extension is also enabled).

.. setting:: WEBCONSOLE_LOGFILE

WEBCONSOLE_LOGFILE
------------------

Default: ``None``

A file to use for logging HTTP requests made to the web console. If unset web
the log is sent to standard scrapy log.

.. setting:: WEBCONSOLE_PORT

WEBCONSOLE_PORT
---------------

Default: ``6080``

The port to use for the web console. If set to ``None`` or ``0``, a dynamically
assigned port is used. For more info see :ref:`topics-webconsole`.

