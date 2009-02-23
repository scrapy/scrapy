"""
This module contains the default values for all settings used by Scrapy. 

For more information about these settings you can read the settings
documentation in docs/ref/settings.rst

Scrapy developers, if you add a setting here remember to:

* add it in alphabetical order
* group similar settings without leaving blank lines
* add its documentation to the available settings documentation
  (docs/ref/settings.rst)

"""

from os.path import join, abspath, dirname

ADAPTORS_DEBUG = False

BOT_NAME = 'scrapybot'
BOT_VERSION = '1.0'

CACHE2_DIR = ''
CACHE2_IGNORE_MISSING = False
CACHE2_SECTORIZE = True
CACHE2_EXPIRATION_SECS = 0

CLOSEDOMAIN_TIMEOUT = 0
CLOSEDOMAIN_NOTIFY = []

CLUSTER_LOGDIR = ''

CLUSTER_MASTER_PORT = 8790
CLUSTER_MASTER_ENABLED = 0
CLUSTER_MASTER_POLL_INTERVAL = 60
CLUSTER_MASTER_NODES = {}
CLUSTER_MASTER_CACHEFILE = ""

CLUSTER_WORKER_ENABLED = 0
CLUSTER_WORKER_MAXPROC = 4
CLUSTER_WORKER_PORT = 8789

COMMANDS_MODULE = ''
COMMANDS_SETTINGS_MODULE = ''

CONCURRENT_DOMAINS = 8    # number of domains to scrape in parallel

DEFAULT_ITEM_CLASS = 'scrapy.item.ScrapedItem'

DEFAULT_SPIDER = None

DEPTH_LIMIT = 0
DEPTH_STATS = True

DOWNLOAD_DELAY = 0
DOWNLOAD_TIMEOUT = 180      # 3mins

DOWNLOADER_DEBUG = False

DOWNLOADER_MIDDLEWARES = [
    # Engine side
    'scrapy.contrib.downloadermiddleware.robotstxt.RobotsTxtMiddleware',
    'scrapy.contrib.downloadermiddleware.errorpages.ErrorPagesMiddleware',
    'scrapy.contrib.downloadermiddleware.cookies.CookiesMiddleware',
    'scrapy.contrib.downloadermiddleware.httpauth.HttpAuthMiddleware',
    'scrapy.contrib.downloadermiddleware.useragent.UserAgentMiddleware',
    'scrapy.contrib.downloadermiddleware.retry.RetryMiddleware',
    'scrapy.contrib.downloadermiddleware.common.CommonMiddleware',
    'scrapy.contrib.downloadermiddleware.redirect.RedirectMiddleware',
    'scrapy.contrib.downloadermiddleware.compression.CompressionMiddleware',
    'scrapy.contrib.downloadermiddleware.debug.CrawlDebug',
    'scrapy.contrib.downloadermiddleware.stats.DownloaderStats',
    'scrapy.contrib.downloadermiddleware.cache.CacheMiddleware',
    # Downloader side
]

DOWNLOADER_STATS = True

DUPEFILTER_FILTERCLASS = 'scrapy.dupefilter.SimplePerDomainFilter'

ENABLED_SPIDERS_FILE = ''

ENGINE_DEBUG = False

EXTENSIONS = [
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

GROUPSETTINGS_ENABLED = False
GROUPSETTINGS_MODULE = ''

# Item pipelines are typically set in specific commands settings
ITEM_PIPELINES = []

LOG_ENABLED = True
LOG_STDOUT = False
LOGLEVEL = 'DEBUG'
LOGFILE = None

MAIL_HOST = 'localhost'
MAIL_FROM = 'scrapy@localhost'

MEMDEBUG_ENABLED = False        # enable memory debugging
MEMDEBUG_NOTIFY = []            # send memory debugging report by mail at engine shutdown

MEMORYSTORE = 'scrapy.core.scheduler.MemoryStore'

MEMUSAGE_ENABLED = 1
MEMUSAGE_LIMIT_MB = 0
MEMUSAGE_NOTIFY_MAIL = []
MEMUSAGE_REPORT = False
MEMUSAGE_WARNING_MB = 0

MYSQL_CONNECTION_SETTINGS = {}

NEWSPIDER_MODULE = ''

PRIORITIZER = 'scrapy.core.prioritizers.RandomPrioritizer'

REQUEST_HEADER_ACCEPT = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
REQUEST_HEADER_ACCEPT_LANGUAGE = 'en'

REQUESTS_QUEUE_SIZE = 0
REQUESTS_PER_DOMAIN = 8     # max simultaneous requests per domain

# contrib.middleware.retry.RetryMiddleware default settings
RETRY_TIMES = 2 # initial response + 2 retries = 3 requests
RETRY_HTTP_CODES = ['500', '503', '504', '400', '408', '200']

ROBOTSTXT_OBEY = False

SCHEDULER = 'scrapy.core.scheduler.Scheduler'

SCHEDULER_MIDDLEWARES = [
        'scrapy.contrib.schedulermiddleware.duplicatesfilter.DuplicatesFilterMiddleware',
        ]

SCHEDULER_ORDER = 'BFO'   # available orders: BFO (default), DFO

SPIDER_MODULES = []

SPIDERPROFILER_ENABLED = False

SPIDER_MIDDLEWARES = [
    # Engine side
    'scrapy.contrib.itemsampler.ItemSamplerMiddleware',
    'scrapy.contrib.spidermiddleware.limit.RequestLimitMiddleware',
    'scrapy.contrib.spidermiddleware.restrict.RestrictMiddleware',
    'scrapy.contrib.spidermiddleware.offsite.OffsiteMiddleware',
    'scrapy.contrib.spidermiddleware.referer.RefererMiddleware',
    'scrapy.contrib.spidermiddleware.urllength.UrlLengthMiddleware',
    'scrapy.contrib.spidermiddleware.depth.DepthMiddleware',
    # Spider side
]

STATS_ENABLED = True
STATS_CLEANUP = False
STATS_DEBUG = False

# deprecated settings - the stats web service should be moved to the web console
STATS_WSPORT = 8089
STATS_WSTIMEOUT = 15

TEMPLATES_DIR = abspath(join(dirname(__file__), '..', 'templates'))

URLLENGTH_LIMIT = 2083

USER_AGENT = '%s/%s' % (BOT_NAME, BOT_VERSION)

TELNETCONSOLE_ENABLED = 1
#TELNETCONSOLE_PORT = 2020  # if not set uses a dynamic port

WEBCONSOLE_ENABLED = True
WEBCONSOLE_PORT = None
WEBCONSOLE_LOGFILE = None

# this setting is used by the cluster master to pass additional settings to
# workers at connection time
GLOBAL_CLUSTER_SETTINGS = [] 
