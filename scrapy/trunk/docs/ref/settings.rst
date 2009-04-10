.. _settings:

Available Settings
==================

Here's a list of all available Scrapy settings, in alphabetical order, along
with their default values and the scope where they apply. 

The scope, where available, shows where the setting is being used, if it's tied
to any particular component. In that case the module of that component will be
shown, typically an extension, middleware or pipeline. It also means that the
component must be enabled in order for the setting to have any effect.

.. setting:: ADAPTORS_DEBUG

ADAPTORS_DEBUG
--------------

Default: ``False``

Enable debug mode for adaptors. 

See :ref:`topics-adaptors`.

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

CACHE2_DIR
----------

Default: ``''`` (empty string)

The directory to use for storing the low-level HTTP cache. If empty the HTTP
cache will be disabled.

.. setting:: CACHE2_EXPIRATION_SECS

CACHE2_EXPIRATION_SECS
----------------------

Default: ``0``

Number of seconds to use for cache expiration. Requests that were cached before
this time will be re-downloaded. If zero, cached requests will always expire.
Negative numbers means requests will never expire.

.. setting:: CACHE2_IGNORE_MISSING

CACHE2_IGNORE_MISSING
---------------------

Default: ``False``

If enabled, requests not found in the cache will be ignored instead of downloaded. 

.. setting:: CACHE2_SECTORIZE

CACHE2_SECTORIZE
----------------

Default: ``True``

Whether to split HTTP cache storage in several dirs for performance improvements.

.. setting:: CLOSEDOMAIN_NOTIFY

CLOSEDOMAIN_NOTIFY
------------------

Default: ``[]``
Scope: ``scrapy.contrib.closedomain``

A list of emails to notify if the domain has been automatically closed by timeout.

.. setting:: CLOSEDOMAIN_TIMEOUT

CLOSEDOMAIN_TIMEOUT
-------------------

Default: ``0``
Scope: ``scrapy.contrib.closedomain``

A timeout (in secs) for automatically closing a spider. Spiders that remain
open for more than this time will be automatically closed. If zero, the
automatically closing is disabled.

.. setting:: CLUSTER_LOGDIR

CLUSTER_LOGDIR
--------------

Default: ``''`` (empty string)

The directory to use for cluster logging.

.. setting:: CLUSTER_MASTER_CACHEFILE

CLUSTER_MASTER_CACHEFILE
------------------------

Default: ``''``

The file to use for storing the state of the cluster master, before shotting
down. And also used for restoring the state on start up. If not set, state
won't be persisted.

.. setting:: CLUSTER_MASTER_ENABLED

CLUSTER_MASTER_ENABLED
------------------------

Default: ``False``

A boolean which specifies whether to enabled the cluster master.

.. setting:: CLUSTER_MASTER_NODES

CLUSTER_MASTER_NODES
--------------------

Default: ``{}``

A dict which defines the nodes of the cluster.  The keys are the node/worker
names and the values are the worker URLs.

Example::

    CLUSTER_MASTER_NODES = {
        'local': 'localhost:8789',
        'remote': 'someworker.example.com:8789',
    }

.. setting:: CLUSTER_MASTER_POLL_INTERVAL

CLUSTER_MASTER_POLL_INTERVAL
----------------------------

Default: ``60``

The amount of time (in secs) that the master should wait before polling the
workers.

.. setting:: CLUSTER_MASTER_PORT

CLUSTER_MASTER_PORT
-------------------

Default: ``8790``

The port where the cluster master will listen.

.. setting:: CLUSTER_WORKER_ENABLED

CLUSTER_WORKER_ENABLED
------------------------

Default: ``False``

A boolean which specifies whether to enabled the cluster master.

.. setting:: CLUSTER_WORKER_MAXPROC

CLUSTER_WORKER_MAXPROC
------------------------

Default: ``4``

The maximum number of process that the cluster worker will be allowed to spawn.

.. setting:: CLUSTER_WORKER_PORT

CLUSTER_WORKER_PORT
-------------------

Default: ``8789``

The port where the cluster worker will listen.

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

Number of domains to scrape concurrently in one process. This doesn't affect
the number of domains scraped concurrently by the Scrapy cluster which spawns a
new process per domain.

.. setting:: DEFAULT_ITEM_CLASS

DEFAULT_ITEM_CLASS
------------------

Default: ``'scrapy.item.ScrapedItem'``

The default class that will be used for items, for example, in the shell
console. 

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

.. setting:: DOWNLOADER_DEBUG

DOWNLOADER_DEBUG
----------------

Default: ``False``

Whether to enable the Downloader debugging mode.

.. setting:: DOWNLOADER_MIDDLEWARES

DOWNLOADER_MIDDLEWARES
----------------------

Default:: 

    [
        'scrapy.contrib.downloadermiddleware.robotstxt.RobotsTxtMiddleware',
        'scrapy.contrib.downloadermiddleware.errorpages.ErrorPagesMiddleware',
        'scrapy.contrib.downloadermiddleware.cookies.CookiesMiddleware',
        'scrapy.contrib.downloadermiddleware.httpauth.HttpAuthMiddleware',
        'scrapy.contrib.downloadermiddleware.useragent.UserAgentMiddleware',
        'scrapy.contrib.downloadermiddleware.retry.RetryMiddleware',
        'scrapy.contrib.downloadermiddleware.common.CommonMiddleware',
        'scrapy.contrib.downloadermiddleware.redirect.RedirectMiddleware',
        'scrapy.contrib.downloadermiddleware.httpcompression.HttpCompressionMiddleware',
        'scrapy.contrib.downloadermiddleware.debug.CrawlDebug',
        'scrapy.contrib.downloadermiddleware.stats.DownloaderStats',
        'scrapy.contrib.downloadermiddleware.cache.CacheMiddleware',
    ]

The list of enabled downloader middlewares. Keep in mind that some may need to
be enabled through a particular setting. The top (first) middleware is closer
to the engine, while the bottom (last) middleware is closer to the downloader.

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

.. setting:: DUPEFILTER_FILTERCLASS

DUPEFILTER_FILTERCLASS
----------------------------

Default: ``scrapy.contrib.spidermiddleware.SimplePerDomainFilter``

The class used to detect and filter duplicated requests.

Default ``SimplePerDomainFilter`` filter based on request fingerprint and
grouping per domain.

.. setting:: ENGINE_DEBUG

ENGINE_DEBUG
------------

Default: ``False``

Whether to enable the Scrapy Engine debugging mode.

.. setting:: ENABLED_SPIDERS_FILE

ENABLED_SPIDERS_FILE
--------------------

Default: ``''`` (empty string)

A file name with the list of enabled spiders. Scrapy will this file to
configure what spiders are enabled and which ones aren't. The file must contain
one spider name (domain_name) per line.

.. setting:: EXTENSIONS 

EXTENSIONS
----------

Default:: 

    [
        'scrapy.stats.corestats.CoreStats',
        'scrapy.xpath.extension.ResponseLibxml2',
        'scrapy.management.web.WebConsole',
        'scrapy.management.telnet.TelnetConsole',
        'scrapy.contrib.webconsole.scheduler.SchedulerQueue',
        'scrapy.contrib.webconsole.livestats.LiveStats',
        'scrapy.contrib.webconsole.spiderctl.Spiderctl',
        'scrapy.contrib.webconsole.enginestatus.EngineStatus',
        'scrapy.contrib.webconsole.stats.StatsDump',
        'scrapy.contrib.webconsole.spiderstats.SpiderStats',
        'scrapy.contrib.spider.reloader.SpiderReloader',
        'scrapy.contrib.memusage.MemoryUsage',
        'scrapy.contrib.memdebug.MemoryDebugger',
        'scrapy.contrib.pbcluster.ClusterWorker',
        'scrapy.contrib.pbcluster.ClusterMasterWeb',
        'scrapy.contrib.pbcluster.ClusterCrawler',
        'scrapy.contrib.closedomain.CloseDomain',
        'scrapy.contrib.debug.StackTraceDump',
        'scrapy.contrib.response.soup.ResponseSoup',
    ]

The list of available extensions. Keep in mind that some of them need need to
be enabled through a setting. By default, this setting contains all stable
built-in extensions. 

For more information See the :ref:`extensions user guide  <topics-extensions>`
and the :ref:`list of available extensions <ref-extensions>`.

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
sending facility <ref-email>`.

.. setting:: MAIL_HOST

MAIL_HOST
---------

Default: ``'localhost'``

Host to use for sending emails using the :ref:`Scrapy e-mail sending facility
<ref-email>`.

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

See :ref:`ref-extensions-memusage`.

.. setting:: MEMUSAGE_LIMIT_MB

MEMUSAGE_LIMIT_MB
-----------------

Default: ``0``

Scope: ``scrapy.contrib.memusage``

The maximum amount of memory to allow (in megabytes) before shutting down
Scrapy  (if MEMUSAGE_ENABLED is True). If zero, no check will be performed.

See :ref:`ref-extensions-memusage`.

.. setting:: MEMUSAGE_NOTIFY_MAIL

MEMUSAGE_NOTIFY_MAIL
--------------------

Default: ``False``

Scope: ``scrapy.contrib.memusage``

A list of emails to notify if the memory limit has been reached.

Example::

    MEMUSAGE_NOTIFY_MAIL = ['user@example.com']

See :ref:`ref-extensions-memusage`.

.. setting:: MEMUSAGE_REPORT

MEMUSAGE_REPORT
---------------

Default: ``False``

Scope: ``scrapy.contrib.memusage``

Whether to send a memory usage report after each domain has been closed.

See :ref:`ref-extensions-memusage`.

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

.. setting:: REQUEST_HEADER_ACCEPT

REQUEST_HEADER_ACCEPT
---------------------

Default: ``'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'``

Default value to use for the ``Accept`` request header (if not already set
before). 

See :ref:`ref-downloader-middleware-common`.

.. setting:: REQUEST_HEADER_ACCEPT_LANGUAGE

REQUEST_HEADER_ACCEPT_LANGUAGE
------------------------------

Default: ``'en'``

Default value to use for the ``Accept-Language`` request header, if not already
set before. 

See :ref:`ref-downloader-middleware-common`.

.. setting:: REQUESTS_QUEUE_SIZE

REQUESTS_PER_DOMAIN
-------------------

Default: ``8``

Specifies how many concurrent (ie. simultaneous) requests will be performed per
open spider.

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

Default: ``'BFO'``

Scope: ``scrapy.core.scheduler``

The order to use for the crawling scheduler.

.. setting:: SCHEDULER_MIDDLEWARES

SCHEDULER_MIDDLEWARES
----------------------

Default:: 

    [
        'scrapy.contrib.schedulermiddleware.duplicatesfilter.DuplicatesFilterMiddleware',
    ]

The list of enabled scheduler middlewares. Keep in mind that some may need to
be enabled through a particular setting. The top (first) middleware is closer
to the engine, while the bottom (last) middleware is closer to the scheduler.

.. setting:: SPIDERPROFILER_ENABLED

SPIDERPROFILER_ENABLED
----------------------

Default: ``False``

Enable the spider profiler. Warning: this could have a big impact in
performance.

.. setting:: SPIDER_MIDDLEWARES

SPIDER_MIDDLEWARES
------------------

Default::

    [
        'scrapy.contrib.itemsampler.ItemSamplerMiddleware',
        'scrapy.contrib.spidermiddleware.limit.RequestLimitMiddleware',
        'scrapy.contrib.spidermiddleware.restrict.RestrictMiddleware',
        'scrapy.contrib.spidermiddleware.offsite.OffsiteMiddleware',
        'scrapy.contrib.spidermiddleware.referer.RefererMiddleware',
        'scrapy.contrib.spidermiddleware.urllength.UrlLengthMiddleware',
        'scrapy.contrib.spidermiddleware.depth.DepthMiddleware',
    ]

The list of enabled spider middlewares. Keep in mind that some may need to be
enabled through a particular setting. The top (first) middleware is closer to
the engine, while the bottom (last) middleware is closer to the spider.

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
