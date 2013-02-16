.. _topics-settings:

========
Settings
========

The Scrapy settings allows you to customize the behaviour of all Scrapy
components, including the core, extensions, pipelines and spiders themselves.

The infrastructure of the settings provides a global namespace of key-value mappings
that the code can use to pull configuration values from. The settings can be
populated through different mechanisms, which are described below.

The settings are also the mechanism for selecting the currently active Scrapy
project (in case you have many).

For a list of available built-in settings see: :ref:`topics-settings-ref`.

Designating the settings
========================

When you use Scrapy, you have to tell it which settings you're using. You can
do this by using an environment variable, ``SCRAPY_SETTINGS_MODULE``.

The value of ``SCRAPY_SETTINGS_MODULE`` should be in Python path syntax, e.g.
``myproject.settings``. Note that the settings module should be on the
Python `import search path`_.

.. _import search path: http://docs.python.org/2/tutorial/modules.html#the-module-search-path

Populating the settings
=======================

Settings can be populated using different mechanisms, each of which having a
different precedence. Here is the list of them in decreasing order of
precedence:

 1. Global overrides (most precedence)
 2. Project settings module
 3. Default settings per-command
 4. Default global settings (less precedence)

These mechanisms are described in more detail below.

1. Global overrides
-------------------

Global overrides are the ones that take most precedence, and are usually
populated by command-line options. You can also override one (or more) settings
from command line using the ``-s`` (or ``--set``) command line option. 

For more information see the :attr:`~scrapy.settings.Settings.overrides`
Settings attribute.

.. highlight:: sh

Example::

    scrapy crawl domain.com -s LOG_FILE=scrapy.log

2. Project settings module
--------------------------

The project settings module is the standard configuration file for your Scrapy
project.  It's where most of your custom settings will be populated. For
example:: ``myproject.settings``.

3. Default settings per-command
-------------------------------

Each :doc:`Scrapy tool </topics/commands>` command can have its own default
settings, which override the global default settings. Those custom command
settings are specified in the ``default_settings`` attribute of the command
class.

4. Default global settings
--------------------------

The global defaults are located in the ``scrapy.settings.default_settings``
module and documented in the :ref:`topics-settings-ref` section.

How to access settings
======================

.. highlight:: python

Settings can be accessed through the :attr:`scrapy.crawler.Crawler.settings`
attribute of the Crawler that is passed to ``from_crawler`` method in
extensions and middlewares::

    class MyExtension(object):

        @classmethod
        def from_crawler(cls, crawler):
            settings = crawler.settings
            if settings['LOG_ENABLED']:
                print "log is enabled!"

In other words, settings can be accessed like a dict, but it's usually preferred
to extract the setting in the format you need it to avoid type errors. In order
to do that you'll have to use one of the methods provided the
:class:`~scrapy.settings.Settings` API.

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

.. setting:: AWS_ACCESS_KEY_ID

AWS_ACCESS_KEY_ID
-----------------

Default: ``None``

The AWS access key used by code that requires access to `Amazon Web services`_,
such as the :ref:`S3 feed storage backend <topics-feed-storage-s3>`.

.. setting:: AWS_SECRET_ACCESS_KEY

AWS_SECRET_ACCESS_KEY
---------------------

Default: ``None``

The AWS secret key used by code that requires access to `Amazon Web services`_,
such as the :ref:`S3 feed storage backend <topics-feed-storage-s3>`.

.. setting:: BOT_NAME

BOT_NAME
--------

Default: ``'scrapybot'``

The name of the bot implemented by this Scrapy project (also known as the
project name). This will be used to construct the User-Agent by default, and
also for logging.

It's automatically populated with your project name when you create your
project with the :command:`startproject` command.

.. setting:: CONCURRENT_ITEMS

CONCURRENT_ITEMS
----------------

Default: ``100``

Maximum number of concurrent items (per response) to process in parallel in the
Item Processor (also known as the :ref:`Item Pipeline <topics-item-pipeline>`).

.. setting:: CONCURRENT_REQUESTS

CONCURRENT_REQUESTS
-------------------

Default: ``16``

The maximum number of concurrent (ie. simultaneous) requests that will be
performed by the Scrapy downloader.


.. setting:: CONCURRENT_REQUESTS_PER_DOMAIN

CONCURRENT_REQUESTS_PER_DOMAIN
------------------------------

Default: ``8``

The maximum number of concurrent (ie. simultaneous) requests that will be
performed to any single domain.

.. setting:: CONCURRENT_REQUESTS_PER_IP

CONCURRENT_REQUESTS_PER_IP
--------------------------

Default: ``0``

The maximum number of concurrent (ie. simultaneous) requests that will be
performed to any single IP. If non-zero, the
:setting:`CONCURRENT_REQUESTS_PER_DOMAIN` setting is ignored, and this one is
used instead. In other words, concurrency limits will be applied per IP, not
per domain.

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

.. setting:: DEPTH_LIMIT

DEPTH_LIMIT
-----------

Default: ``0``

The maximum depth that will be allowed to crawl for any site. If zero, no limit
will be imposed.

.. setting:: DEPTH_PRIORITY

DEPTH_PRIORITY
--------------

Default: ``0``

An integer that is used to adjust the request priority based on its depth.

If zero, no priority adjustment is made from depth.

.. setting:: DEPTH_STATS

DEPTH_STATS
-----------

Default: ``True``

Whether to collect maximum depth stats.

.. setting:: DEPTH_STATS_VERBOSE

DEPTH_STATS_VERBOSE
-------------------

Default: ``False``

Whether to collect verbose depth stats. If this is enabled, the number of
requests for each depth is collected in the stats.

.. setting:: DNSCACHE_ENABLED

DNSCACHE_ENABLED
----------------

Default: ``True``

Whether to enable DNS in-memory cache.

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
        'scrapy.contrib.downloadermiddleware.downloadtimeout.DownloadTimeoutMiddleware': 350,
        'scrapy.contrib.downloadermiddleware.useragent.UserAgentMiddleware': 400,
        'scrapy.contrib.downloadermiddleware.retry.RetryMiddleware': 500,
        'scrapy.contrib.downloadermiddleware.defaultheaders.DefaultHeadersMiddleware': 550,
        'scrapy.contrib.downloadermiddleware.redirect.MetaRefreshMiddleware': 580,
        'scrapy.contrib.downloadermiddleware.httpcompression.HttpCompressionMiddleware': 590,
        'scrapy.contrib.downloadermiddleware.redirect.RedirectMiddleware': 600,
        'scrapy.contrib.downloadermiddleware.cookies.CookiesMiddleware': 700,
        'scrapy.contrib.downloadermiddleware.httpproxy.HttpProxyMiddleware': 750,
        'scrapy.contrib.downloadermiddleware.chunked.ChunkedTransferMiddleware': 830,
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

This setting is also affected by the :setting:`RANDOMIZE_DOWNLOAD_DELAY`
setting (which is enabled by default). By default, Scrapy doesn't wait a fixed
amount of time between requests, but uses a random interval between 0.5 and 1.5
* :setting:`DOWNLOAD_DELAY`.

You can also change this setting per spider.

.. setting:: DOWNLOAD_HANDLERS

DOWNLOAD_HANDLERS
-----------------

Default: ``{}``

A dict containing the request downloader handlers enabled in your project.
See `DOWNLOAD_HANDLERS_BASE` for example format.

.. setting:: DOWNLOAD_HANDLERS_BASE

DOWNLOAD_HANDLERS_BASE
----------------------

Default:: 

    {
        'file': 'scrapy.core.downloader.handlers.file.FileDownloadHandler',
        'http': 'scrapy.core.downloader.handlers.http.HttpDownloadHandler',
        'https': 'scrapy.core.downloader.handlers.http.HttpDownloadHandler',
        's3': 'scrapy.core.downloader.handlers.s3.S3DownloadHandler',
    }

A dict containing the request download handlers enabled by default in Scrapy.
You should never modify this setting in your project, modify
:setting:`DOWNLOAD_HANDLERS` instead. 

.. setting:: DOWNLOAD_TIMEOUT

DOWNLOAD_TIMEOUT
----------------

Default: ``180``

The amount of time (in secs) that the downloader will wait before timing out.

.. setting:: DUPEFILTER_CLASS

DUPEFILTER_CLASS
----------------

Default: ``'scrapy.dupefilter.RFPDupeFilter'``

The class used to detect and filter duplicate requests.

The default (``RFPDupeFilter``) filters based on request fingerprint using
the ``scrapy.utils.request.request_fingerprint`` function.

.. setting:: jDITOR

EDITOR
------

Default: `depends on the environment`

The editor to use for editing spiders with the :command:`edit` command. It
defaults to the ``EDITOR`` environment variable, if set. Otherwise, it defaults
to ``vi`` (on Unix systems) or the IDLE editor (on Windows).

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
        'scrapy.contrib.corestats.CoreStats': 0,
        'scrapy.webservice.WebService': 0,
        'scrapy.telnet.TelnetConsole': 0,
        'scrapy.contrib.memusage.MemoryUsage': 0,
        'scrapy.contrib.memdebug.MemoryDebugger': 0,
        'scrapy.contrib.closespider.CloseSpider': 0,
        'scrapy.contrib.feedexport.FeedExporter': 0,
        'scrapy.contrib.logstats.LogStats': 0,
        'scrapy.contrib.spiderstate.SpiderState': 0,
        'scrapy.contrib.throttle.AutoThrottle': 0,
    }

The list of available extensions. Keep in mind that some of them need to
be enabled through a setting. By default, this setting contains all stable
built-in extensions. 

For more information See the :ref:`extensions user guide  <topics-extensions>`
and the :ref:`list of available extensions <topics-extensions-ref>`.

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

Whether to enable logging.

.. setting:: LOG_ENCODING

LOG_ENCODING
------------

Default: ``'utf-8'``

The encoding to use for logging.

.. setting:: LOG_FILE

LOG_FILE
--------

Default: ``None``

File name to use for logging output. If None, standard error will be used.

.. setting:: LOG_LEVEL

LOG_LEVEL
---------

Default: ``'DEBUG'``

Minimum level to log. Available levels are: CRITICAL, ERROR, WARNING,
INFO, DEBUG. For more info see :ref:`topics-logging`.

.. setting:: LOG_STDOUT

LOG_STDOUT
----------

Default: ``False``

If ``True``, all standard output (and error) of your process will be redirected
to the log. For example if you ``print 'hello'`` it will appear in the Scrapy
log.

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

Whether to send a memory usage report after each spider has been closed.

See :ref:`topics-extensions-ref-memusage`.

.. setting:: MEMUSAGE_WARNING_MB

MEMUSAGE_WARNING_MB
-------------------

Default: ``0``

Scope: ``scrapy.contrib.memusage``

The maximum amount of memory to allow (in megabytes) before sending a warning
email notifying about it. If zero, no warning will be produced.

.. setting:: NEWSPIDER_MODULE

NEWSPIDER_MODULE
----------------

Default: ``''``

Module where to create new spiders using the :command:`genspider` command.

Example::

    NEWSPIDER_MODULE = 'mybot.spiders_dev'

.. setting:: RANDOMIZE_DOWNLOAD_DELAY

RANDOMIZE_DOWNLOAD_DELAY
------------------------

Default: ``True``

If enabled, Scrapy will wait a random amount of time (between 0.5 and 1.5
* :setting:`DOWNLOAD_DELAY`) while fetching requests from the same
spider.

This randomization decreases the chance of the crawler being detected (and
subsequently blocked) by sites which analyze requests looking for statistically
significant similarities in the time between their requests.

The randomization policy is the same used by `wget`_ ``--random-wait`` option.

If :setting:`DOWNLOAD_DELAY` is zero (default) this option has no effect.

.. _wget: http://www.gnu.org/software/wget/manual/wget.html

.. setting:: REDIRECT_MAX_TIMES

REDIRECT_MAX_TIMES
------------------

Default: ``20``

Defines the maximum times a request can be redirected. After this maximum the
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
------------------------

Default: ``+2``

Adjust redirect request priority relative to original request.
A negative priority adjust means more priority.

.. setting:: ROBOTSTXT_OBEY

ROBOTSTXT_OBEY
--------------

Default: ``False``

Scope: ``scrapy.contrib.downloadermiddleware.robotstxt``

If enabled, Scrapy will respect robots.txt policies. For more information see
:ref:`topics-dlmw-robots`

.. setting:: SCHEDULER

SCHEDULER
---------

Default: ``'scrapy.core.scheduler.Scheduler'``

The scheduler to use for crawling.

.. setting:: SPIDER_MIDDLEWARES


SPIDER_CONTRACTS
----------------

Default:: ``{}``

A dict containing the scrapy contracts enabled in your project, used for
testing spiders. For more info see :ref:`topics-contracts`.

SPIDER_CONTRACTS_BASE
---------------------

Default::

    {
        'scrapy.contracts.default.UrlContract' : 1,
        'scrapy.contracts.default.ReturnsContract': 2,
        'scrapy.contracts.default.ScrapesContract': 3,
    }

A dict containing the scrapy contracts enabled by default in Scrapy. You should
never modify this setting in your project, modify :setting:`SPIDER_CONTRACTS`
instead. For more info see :ref:`topics-contracts`.

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

Default: ``'scrapy.statscol.MemoryStatsCollector'``

The class to use for collecting stats, who must implement the
:ref:`topics-api-stats`.

.. setting:: STATS_DUMP

STATS_DUMP
----------

Default: ``True``

Dump the :ref:`Scrapy stats <topics-stats>` (to the Scrapy log) once the spider
finishes.

For more info see: :ref:`topics-stats`.

.. setting:: STATSMAILER_RCPTS

STATSMAILER_RCPTS
-----------------

Default: ``[]`` (empty list)

Send Scrapy stats after spiders finish scraping. See
:class:`~scrapy.contrib.statsmailer.StatsMailer` for more info.

.. setting:: TELNETCONSOLE_ENABLED

TELNETCONSOLE_ENABLED
---------------------

Default: ``True``

A boolean which specifies if the :ref:`telnet console <topics-telnetconsole>`
will be enabled (provided its extension is also enabled).

.. setting:: TELNETCONSOLE_PORT

TELNETCONSOLE_PORT
------------------

Default: ``[6023, 6073]``

The port range to use for the telnet console. If set to ``None`` or ``0``, a
dynamically assigned port is used. For more info see
:ref:`topics-telnetconsole`.

.. setting:: TEMPLATES_DIR

TEMPLATES_DIR
-------------

Default: ``templates`` dir inside scrapy module

The directory where to look for templates when creating new projects with
:command:`startproject` command.

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

Default: ``"Scrapy/VERSION (+http://scrapy.org)"``

The default User-Agent to use when crawling, unless overridden. 

.. _Amazon web services: http://aws.amazon.com/
.. _breadth-first order: http://en.wikipedia.org/wiki/Breadth-first_search
.. _depth-first order: http://en.wikipedia.org/wiki/Depth-first_search
