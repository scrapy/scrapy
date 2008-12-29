Available settings
==================

Here's a full list of all available Scrapy settings, in alphabetical order,
along with their default values and the scope where they apply. 

The scope, where available, shows where the setting is being used, if it's tied
to any particular component. In that case the module of that component will be
shown, typically an extension, middleware or pipeline. It also means that the
component must be enabled in order for the setting to have any effect.

.. setting:: ADAPTORS_DEBUG

ADAPTORS_DEBUG
--------------

Default: ``False``

Enable debug mode for adaptors.

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

.. setting:: CACHE2_DIR
.. setting:: CACHE2_IGNORE_MISSING
.. setting:: CACHE2_SECTORIZE
.. setting:: CLOSEDOMAIN_NOTIFY
.. setting:: CLOSEDOMAIN_TIMEOUT
.. setting:: CLUSTER_LOGDIR
.. setting:: CLUSTER_MASTER_CACHEFILE
.. setting:: CLUSTER_MASTER_ENABLED
.. setting:: CLUSTER_MASTER_NODES
.. setting:: CLUSTER_MASTER_POLL_INTERVAL
.. setting:: CLUSTER_MASTER_PORT
.. setting:: CLUSTER_WORKER_ENABLED
.. setting:: CLUSTER_WORKER_MAXPROC
.. setting:: CLUSTER_WORKER_PORT
.. setting:: CLUSTER_WORKER_SVNWORKDIR
.. setting:: COMMANDS_MODULE

COMMANDS_MODULE
---------------

Default: ``None``

A module to use for looking for custom Scrapy commands. This is used to add
custom command for your Scrapy project.

Example::
    COMMANDS_MODULE = 'mybot.commands'

.. setting:: COMMANDS_SETTINGS_MODULE

COMMANDS_SETTINGS_MODULE
------------------------

Default: ``None``

A module to use for looking for custom Scrapy command settings.

Example::
    COMMANDS_SETTINGS_MODULE = 'mybot.conf.commands'

.. setting:: DEFAULT_ITEM_CLASS

DEFAULT_ITEM_CLASS
------------------

Default: ``'scrapy.item.ScrapedItem'``

The default class that will be used for items, for example, in the shell
console. 

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

Wether to collect depth stats.

.. setting:: DOWNLOADER_MIDDLEWARES
.. setting:: DOWNLOADER_STATS
.. setting:: DOWNLOAD_TIMEOUT
.. setting:: ENABLED_SPIDERS_FILE
.. setting:: EXTENSIONS 
.. setting:: GLOBAL_CLUSTER_SETTINGS
.. setting:: GROUPSETTINGS_ENABLED
.. setting:: GROUPSETTINGS_MODULE
.. setting:: ITEM_PIPELINES

LOG_ENABLED
-----------

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
Scope: ``scrapy.mail``

Host to use for sending emails from Scrapy.

.. setting:: MEMDEBUG_ENABLED

MEMDEBUG_ENABLED
----------------

Default: ``False``

Wether to enable memory debugging.

.. setting:: MEMDEBUG_NOTIFY

Default: ``[]``

If memory debugging is enabled a memory report will be sent to the specified
addresses.

Example::
    MEMDEBUG_NOTIFY = ['user@example.com']

.. setting:: MEMUSAGE_ENABLED

MEMUSAGE_ENABLED
----------------

Default: ``False``
Scope: ``scrapy.contrib.memusage``

Wether to enable the memory usage extension that will shutdown the Scrapy
process when it exceeds a memory limit, and also notify by email when that
happened.

.. setting:: MEMUSAGE_LIMIT_MB

MEMUSAGE_LIMIT_MB
-----------------

Default: ``0``
Scope: ``scrapy.contrib.memusage``

The maximum amount of memory to allow (in megabytes) before shutting down
Scrapy  (if MEMUSAGE_ENABLED is True). If zero, no check will be performed.

.. setting:: MEMUSAGE_NOTIFY_MAIL

MEMUSAGE_NOTIFY_MAIL
--------------------

Default: ``False``
Scope: ``scrapy.contrib.memusage``

A list of emails to notify if the memory limit has been reached.

Example::
    MEMUSAGE_NOTIFY_MAIL = ['user@example.com']

.. setting:: MEMUSAGE_REPORT

MEMUSAGE_REPORT
---------------

Default: ``False``
Scope: ``scrapy.contrib.memusage``

Wether to send a memory usage report after each domain has been closed.

.. setting:: MEMUSAGE_WARNING_MB

MEMUSAGE_LIMIT_MB
-----------------

Default: ``0``
Scope: ``scrapy.contrib.memusage``

The maximum amount of memory to allow (in megabytes) before sending a warning
email notifying about it. If zero, no warning will be produced.

.. setting:: MYSQL_CONNECTION_SETTINGS
.. setting:: NEWSPIDER_MODULE

NEWSPIDER_MODULE
----------------

Default: ``''``

Module where to create new spiders using the genspider command.

Example::
    NEWSPIDER_MODULE = 'mybot.spiders_dev'

.. setting:: REQUESTS_QUEUE_SIZE

REQUESTS_QUEUE_SIZE
-------------------

Default: ``0``
Scope: ``scrapy.contrib.spidermiddleware.limit``

If non zero, it will be used as an upper limit for the amount of requests that
can be scheduled per domain.

.. setting:: SCHEDULER

SCHEDULER
---------

Default: ``'scrapy.core.scheduler.Scheduler'``

The scheduler to use for crawling.

.. setting:: SCHEDULER_ORDER 

Default: ``'BFO'``
Scope: ``scrapy.core.scheduler``

The order to use for the crawling scheduler.

.. setting:: SHOVEITEM_CACHE_OPT
.. setting:: SHOVEITEM_CACHE_URI
.. setting:: SHOVEITEM_STORE_OPT
.. setting:: SHOVEITEM_STORE_URI
.. setting:: SPIDERPROFILER_ENABLED
.. setting:: SPIDER_MIDDLEWARES
.. setting:: SPIDER_MODULES

SPIDER_MODULES
--------------

Default: ``[]``

A list of modules where Scrapy will look for spiders.

Example::
    SPIDER_MODULES = ['mybot.spiders_prod', 'mybot.spiders_dev']

.. setting:: STATS_CLEANUP

STATS_CLEANUP
-------------

Default: ``False``

Whether to cleanup (to save memory) the stats for a given domain,
when the domain is closed.

.. setting:: STATS_DEBUG

STATS_DEBUG
-----------

Default: ``False``

Enable debugging mode for Scrapy stats. This logs the stats when a domain is
closed.

.. setting:: STATS_ENABLED

STATS_ENABLED
-------------

Default: ``True``

Enable stats collection.

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

Default: ``None``
Scope: ``scrapy.management.telnet``

The port to use for the telnet console. If unset, a dynamically assigned port
is used.


.. setting:: TEMPLATES_DIR

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

Default: ``"%s/%s" % (BOT_NAME, BOT_VERSION)``

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

Default: ``None``

The port to use for the web console. If unset, a dynamically assigned port is
used.

.. setting:: WS_CACHESIZE
.. setting:: WS_ENABLED
.. setting:: WS_PORT
.. setting:: WS_REDIRECTURL
