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

import os
import sys
from importlib import import_module
from os.path import join, abspath, dirname

import six

AJAXCRAWL_ENABLED = False

AUTOTHROTTLE_ENABLED = False
AUTOTHROTTLE_DEBUG = False
AUTOTHROTTLE_MAX_DELAY = 60.0
AUTOTHROTTLE_START_DELAY = 5.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

BOT_NAME = 'scrapybot'

CLOSESPIDER_TIMEOUT = 0
CLOSESPIDER_PAGECOUNT = 0
CLOSESPIDER_ITEMCOUNT = 0
CLOSESPIDER_ERRORCOUNT = 0

COMMANDS_MODULE = ''

COMPRESSION_ENABLED = True

CONCURRENT_ITEMS = 100

CONCURRENT_REQUESTS = 16
CONCURRENT_REQUESTS_PER_DOMAIN = 8
CONCURRENT_REQUESTS_PER_IP = 0

COOKIES_ENABLED = True
COOKIES_DEBUG = False

DEFAULT_ITEM_CLASS = 'scrapy.item.Item'

DEFAULT_REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en',
}

DEPTH_LIMIT = 0
DEPTH_STATS = True
DEPTH_PRIORITY = 0

DNSCACHE_ENABLED = True
DNSCACHE_SIZE = 10000
DNS_TIMEOUT = 60

DOWNLOAD_DELAY = 0

DOWNLOAD_HANDLERS = {}
DOWNLOAD_HANDLERS_BASE = {
    'file': 'scrapy.core.downloader.handlers.file.FileDownloadHandler',
    'http': 'scrapy.core.downloader.handlers.http.HTTPDownloadHandler',
    'https': 'scrapy.core.downloader.handlers.http.HTTPDownloadHandler',
    's3': 'scrapy.core.downloader.handlers.s3.S3DownloadHandler',
    'ftp': 'scrapy.core.downloader.handlers.ftp.FTPDownloadHandler',
}

DOWNLOAD_TIMEOUT = 180      # 3mins

DOWNLOAD_MAXSIZE = 1024*1024*1024   # 1024m
DOWNLOAD_WARNSIZE = 32*1024*1024    # 32m

DOWNLOADER = 'scrapy.core.downloader.Downloader'

DOWNLOADER_HTTPCLIENTFACTORY = 'scrapy.core.downloader.webclient.ScrapyHTTPClientFactory'
DOWNLOADER_CLIENTCONTEXTFACTORY = 'scrapy.core.downloader.contextfactory.ScrapyClientContextFactory'
DOWNLOADER_CLIENT_TLS_METHOD = 'TLS' # Use highest TLS/SSL protocol version supported by the platform,
                                     # also allowing negotiation

DOWNLOADER_MIDDLEWARES = {}

DOWNLOADER_MIDDLEWARES_BASE = {
    # Engine side
    'scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware': 100,
    'scrapy.downloadermiddlewares.httpauth.HttpAuthMiddleware': 300,
    'scrapy.downloadermiddlewares.downloadtimeout.DownloadTimeoutMiddleware': 350,
    'scrapy.downloadermiddlewares.defaultheaders.DefaultHeadersMiddleware': 400,
    'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': 500,
    'scrapy.downloadermiddlewares.retry.RetryMiddleware': 550,
    'scrapy.downloadermiddlewares.ajaxcrawl.AjaxCrawlMiddleware': 560,
    'scrapy.downloadermiddlewares.redirect.MetaRefreshMiddleware': 580,
    'scrapy.downloadermiddlewares.redirect.RedirectMiddleware': 600,
    'scrapy.downloadermiddlewares.cookies.CookiesMiddleware': 700,
    'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': 750,
    'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 810,
    'scrapy.downloadermiddlewares.chunked.ChunkedTransferMiddleware': 830,
    'scrapy.downloadermiddlewares.stats.DownloaderStats': 850,
    'scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware': 900,
    # Downloader side
}

DOWNLOADER_STATS = True

DUPEFILTER_CLASS = 'scrapy.dupefilters.RFPDupeFilter'

try:
    EDITOR = os.environ['EDITOR']
except KeyError:
    if sys.platform == 'win32':
        EDITOR = '%s -m idlelib.idle'
    else:
        EDITOR = 'vi'

EXTENSIONS = {}

EXTENSIONS_BASE = {
    'scrapy.extensions.corestats.CoreStats': 0,
    'scrapy.extensions.telnet.TelnetConsole': 0,
    'scrapy.extensions.memusage.MemoryUsage': 0,
    'scrapy.extensions.memdebug.MemoryDebugger': 0,
    'scrapy.extensions.closespider.CloseSpider': 0,
    'scrapy.extensions.feedexport.FeedExporter': 0,
    'scrapy.extensions.logstats.LogStats': 0,
    'scrapy.extensions.spiderstate.SpiderState': 0,
    'scrapy.extensions.throttle.AutoThrottle': 0,
}

FEED_TEMPDIR = None
FEED_URI = None
FEED_URI_PARAMS = None  # a function to extend uri arguments
FEED_FORMAT = 'jsonlines'
FEED_STORE_EMPTY = False
FEED_EXPORT_ENCODING = None
FEED_EXPORT_FIELDS = None
FEED_STORAGES = {}
FEED_STORAGES_BASE = {
    '': 'scrapy.extensions.feedexport.FileFeedStorage',
    'file': 'scrapy.extensions.feedexport.FileFeedStorage',
    'stdout': 'scrapy.extensions.feedexport.StdoutFeedStorage',
    's3': 'scrapy.extensions.feedexport.S3FeedStorage',
    'ftp': 'scrapy.extensions.feedexport.FTPFeedStorage',
}
FEED_EXPORTERS = {}
FEED_EXPORTERS_BASE = {
    'json': 'scrapy.exporters.JsonItemExporter',
    'jsonlines': 'scrapy.exporters.JsonLinesItemExporter',
    'jl': 'scrapy.exporters.JsonLinesItemExporter',
    'csv': 'scrapy.exporters.CsvItemExporter',
    'xml': 'scrapy.exporters.XmlItemExporter',
    'marshal': 'scrapy.exporters.MarshalItemExporter',
    'pickle': 'scrapy.exporters.PickleItemExporter',
}

FILES_STORE_S3_ACL = 'private'

HTTPCACHE_ENABLED = False
HTTPCACHE_DIR = 'httpcache'
HTTPCACHE_IGNORE_MISSING = False
HTTPCACHE_STORAGE = 'scrapy.extensions.httpcache.FilesystemCacheStorage'
HTTPCACHE_EXPIRATION_SECS = 0
HTTPCACHE_ALWAYS_STORE = False
HTTPCACHE_IGNORE_HTTP_CODES = []
HTTPCACHE_IGNORE_SCHEMES = ['file']
HTTPCACHE_IGNORE_RESPONSE_CACHE_CONTROLS = []
HTTPCACHE_DBM_MODULE = 'anydbm' if six.PY2 else 'dbm'
HTTPCACHE_POLICY = 'scrapy.extensions.httpcache.DummyPolicy'
HTTPCACHE_GZIP = False

HTTPPROXY_AUTH_ENCODING = 'latin-1'

IMAGES_STORE_S3_ACL = 'private'

ITEM_PROCESSOR = 'scrapy.pipelines.ItemPipelineManager'

ITEM_PIPELINES = {}
ITEM_PIPELINES_BASE = {}

LOG_ENABLED = True
LOG_ENCODING = 'utf-8'
LOG_FORMATTER = 'scrapy.logformatter.LogFormatter'
LOG_FORMAT = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
LOG_DATEFORMAT = '%Y-%m-%d %H:%M:%S'
LOG_STDOUT = False
LOG_LEVEL = 'DEBUG'
LOG_FILE = None

SCHEDULER_DEBUG = False

LOGSTATS_INTERVAL = 60.0

MAIL_HOST = 'localhost'
MAIL_PORT = 25
MAIL_FROM = 'scrapy@localhost'
MAIL_PASS = None
MAIL_USER = None

MEMDEBUG_ENABLED = False        # enable memory debugging
MEMDEBUG_NOTIFY = []            # send memory debugging report by mail at engine shutdown

MEMUSAGE_CHECK_INTERVAL_SECONDS = 60.0
MEMUSAGE_ENABLED = False
MEMUSAGE_LIMIT_MB = 0
MEMUSAGE_NOTIFY_MAIL = []
MEMUSAGE_REPORT = False
MEMUSAGE_WARNING_MB = 0

METAREFRESH_ENABLED = True
METAREFRESH_MAXDELAY = 100

NEWSPIDER_MODULE = ''

RANDOMIZE_DOWNLOAD_DELAY = True

REACTOR_THREADPOOL_MAXSIZE = 10

REDIRECT_ENABLED = True
REDIRECT_MAX_TIMES = 20  # uses Firefox default setting
REDIRECT_PRIORITY_ADJUST = +2

REFERER_ENABLED = True

RETRY_ENABLED = True
RETRY_TIMES = 2  # initial response + 2 retries = 3 requests
RETRY_HTTP_CODES = [500, 502, 503, 504, 408]
RETRY_PRIORITY_ADJUST = -1

ROBOTSTXT_OBEY = False

SCHEDULER = 'scrapy.core.scheduler.Scheduler'
SCHEDULER_DISK_QUEUE = 'scrapy.squeues.PickleLifoDiskQueue'
SCHEDULER_MEMORY_QUEUE = 'scrapy.squeues.LifoMemoryQueue'
SCHEDULER_PRIORITY_QUEUE = 'queuelib.PriorityQueue'

SPIDER_LOADER_CLASS = 'scrapy.spiderloader.SpiderLoader'

SPIDER_MIDDLEWARES = {}

SPIDER_MIDDLEWARES_BASE = {
    # Engine side
    'scrapy.spidermiddlewares.httperror.HttpErrorMiddleware': 50,
    'scrapy.spidermiddlewares.offsite.OffsiteMiddleware': 500,
    'scrapy.spidermiddlewares.referer.RefererMiddleware': 700,
    'scrapy.spidermiddlewares.urllength.UrlLengthMiddleware': 800,
    'scrapy.spidermiddlewares.depth.DepthMiddleware': 900,
    # Spider side
}

SPIDER_MODULES = []

STATS_CLASS = 'scrapy.statscollectors.MemoryStatsCollector'
STATS_DUMP = True

STATSMAILER_RCPTS = []

TEMPLATES_DIR = abspath(join(dirname(__file__), '..', 'templates'))

URLLENGTH_LIMIT = 2083

USER_AGENT = 'Scrapy/%s (+http://scrapy.org)' % import_module('scrapy').__version__

TELNETCONSOLE_ENABLED = 1
TELNETCONSOLE_PORT = [6023, 6073]
TELNETCONSOLE_HOST = '127.0.0.1'

SPIDER_CONTRACTS = {}
SPIDER_CONTRACTS_BASE = {
    'scrapy.contracts.default.UrlContract': 1,
    'scrapy.contracts.default.ReturnsContract': 2,
    'scrapy.contracts.default.ScrapesContract': 3,
}
