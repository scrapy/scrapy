"""
This module contains the default values for all settings used by Scrapy. 

For more information about these settings you can read the settings
documentation in docs/topics/settings.rst

Scrapy developers, if you add a setting here remember to:

* add it in alphabetical order
* group similar settings without leaving blank lines
* add its documentation to the available settings documentation
  (docs/topics/settings.rst)

"""

from os.path import join, abspath, dirname

BOT_NAME = 'scrapybot'
BOT_VERSION = '1.0'

CLOSEDOMAIN_TIMEOUT = 0
CLOSEDOMAIN_ITEMPASSED = 0

COMMANDS_MODULE = ''
COMMANDS_SETTINGS_MODULE = ''

CONCURRENT_DOMAINS = 8

CONCURRENT_ITEMS = 100

COOKIES_DEBUG = False

DEFAULT_ITEM_CLASS = 'scrapy.item.Item'

DEFAULT_REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en',
}

DEFAULT_SPIDER = None

DEPTH_LIMIT = 0
DEPTH_STATS = True

DOMAIN_SCHEDULER = 'scrapy.contrib.domainsch.FifoDomainScheduler'

DOWNLOAD_DELAY = 0
DOWNLOAD_TIMEOUT = 180      # 3mins

DOWNLOADER_DEBUG = False

DOWNLOADER_MIDDLEWARES = {}

DOWNLOADER_MIDDLEWARES_BASE = {
    # Engine side
    'scrapy.contrib.downloadermiddleware.robotstxt.RobotsTxtMiddleware': 100,
    'scrapy.contrib.downloadermiddleware.httpauth.HttpAuthMiddleware': 300,
    'scrapy.contrib.downloadermiddleware.useragent.UserAgentMiddleware': 400,
    'scrapy.contrib.downloadermiddleware.retry.RetryMiddleware': 500,
    'scrapy.contrib.downloadermiddleware.defaultheaders.DefaultHeadersMiddleware': 550,
    'scrapy.contrib.downloadermiddleware.redirect.RedirectMiddleware': 600,
    'scrapy.contrib.downloadermiddleware.cookies.CookiesMiddleware': 700,
    'scrapy.contrib.downloadermiddleware.httpcompression.HttpCompressionMiddleware': 800,
    'scrapy.contrib.downloadermiddleware.stats.DownloaderStats': 850,
    'scrapy.contrib.downloadermiddleware.cache.HttpCacheMiddleware': 900,
    # Downloader side
}

DOWNLOADER_STATS = True

DUPEFILTER_CLASS = 'scrapy.contrib.dupefilter.RequestFingerprintDupeFilter'

EXTENSIONS = {}

EXTENSIONS_BASE = {
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

GROUPSETTINGS_ENABLED = False
GROUPSETTINGS_MODULE = ''

HTTPCACHE_DIR = ''
HTTPCACHE_IGNORE_MISSING = False
HTTPCACHE_SECTORIZE = True
HTTPCACHE_EXPIRATION_SECS = 0

ITEM_PROCESSOR = 'scrapy.contrib.pipeline.ItemPipelineManager'

# Item pipelines are typically set in specific commands settings
ITEM_PIPELINES = []

LOG_ENABLED = True
LOG_STDOUT = False
LOG_LEVEL = 'DEBUG'
LOG_FILE = None

MAIL_HOST = 'localhost'
MAIL_FROM = 'scrapy@localhost'

MEMDEBUG_ENABLED = False        # enable memory debugging
MEMDEBUG_NOTIFY = []            # send memory debugging report by mail at engine shutdown

MEMUSAGE_ENABLED = 1
MEMUSAGE_LIMIT_MB = 0
MEMUSAGE_NOTIFY_MAIL = []
MEMUSAGE_REPORT = False
MEMUSAGE_WARNING_MB = 0

MYSQL_CONNECTION_SETTINGS = {}

NEWSPIDER_MODULE = ''

REDIRECT_MAX_METAREFRESH_DELAY = 100
REDIRECT_MAX_TIMES = 20 # uses Firefox default setting
REDIRECT_PRIORITY_ADJUST = +2

REQUESTS_QUEUE_SIZE = 0
REQUESTS_PER_DOMAIN = 8     # max simultaneous requests per domain

# contrib.middleware.retry.RetryMiddleware default settings
RETRY_TIMES = 2 # initial response + 2 retries = 3 requests
RETRY_HTTP_CODES = ['500', '503', '504', '400', '408']
RETRY_PRIORITY_ADJUST = -1

ROBOTSTXT_OBEY = False

SCHEDULER = 'scrapy.core.scheduler.Scheduler'

SCHEDULER_MIDDLEWARES = {}

SCHEDULER_MIDDLEWARES_BASE = {
    'scrapy.contrib.schedulermiddleware.duplicatesfilter.DuplicatesFilterMiddleware': 500,
}

SCHEDULER_ORDER = 'BFO'   # available orders: BFO (default), DFO

SPIDER_MODULES = []

SPIDERPROFILER_ENABLED = False

SPIDER_MIDDLEWARES = {}

SPIDER_MIDDLEWARES_BASE = {
    # Engine side
    'scrapy.contrib.spidermiddleware.httperror.HttpErrorMiddleware': 50,
    'scrapy.contrib.itemsampler.ItemSamplerMiddleware': 100,
    'scrapy.contrib.spidermiddleware.requestlimit.RequestLimitMiddleware': 200,
    'scrapy.contrib.spidermiddleware.restrict.RestrictMiddleware': 300,
    'scrapy.contrib.spidermiddleware.offsite.OffsiteMiddleware': 500,
    'scrapy.contrib.spidermiddleware.referer.RefererMiddleware': 700,
    'scrapy.contrib.spidermiddleware.urllength.UrlLengthMiddleware': 800,
    'scrapy.contrib.spidermiddleware.depth.DepthMiddleware': 900,
    # Spider side
}

STATS_CLASS = 'scrapy.stats.collector.MemoryStatsCollector'
STATS_ENABLED = True
STATS_DUMP = False

STATS_SDB_DOMAIN = 'scrapy_stats'
STATS_SDB_ASYNC = False

STATSMAILER_RCPTS = []

TEMPLATES_DIR = abspath(join(dirname(__file__), '..', 'templates'))

URLLENGTH_LIMIT = 2083

USER_AGENT = '%s/%s' % (BOT_NAME, BOT_VERSION)

TELNETCONSOLE_ENABLED = 1
TELNETCONSOLE_PORT = 6023  # if None, uses a dynamic port

WEBCONSOLE_ENABLED = True
WEBCONSOLE_PORT = 6080
WEBCONSOLE_LOGFILE = None

