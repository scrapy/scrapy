"""This module contains the default values for all settings used by Scrapy.

For more information about these settings you can read the settings
documentation in docs/topics/settings.rst

Scrapy developers, if you add a setting here remember to:

* add it in alphabetical order, with the exception that enabling flags and
  other high-level settings for a group should come first in their group
  and pairs like host/port and user/password should be in the usual order
* group similar settings without leaving blank lines
* add its documentation to the available settings documentation
  (docs/topics/settings.rst)
"""

import sys
from importlib import import_module
from pathlib import Path

ADDONS = {}

AJAXCRAWL_ENABLED = False
AJAXCRAWL_MAXSIZE = 32768

ASYNCIO_EVENT_LOOP = None

AUTOTHROTTLE_ENABLED = False
AUTOTHROTTLE_DEBUG = False
AUTOTHROTTLE_MAX_DELAY = 60.0
AUTOTHROTTLE_START_DELAY = 5.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

BOT_NAME = "scrapybot"

CLOSESPIDER_ERRORCOUNT = 0
CLOSESPIDER_ITEMCOUNT = 0
CLOSESPIDER_PAGECOUNT = 0
CLOSESPIDER_TIMEOUT = 0

COMMANDS_MODULE = ""

COMPRESSION_ENABLED = True

CONCURRENT_ITEMS = 100

CONCURRENT_REQUESTS = 16
CONCURRENT_REQUESTS_PER_DOMAIN = 8
CONCURRENT_REQUESTS_PER_IP = 0

COOKIES_ENABLED = True
COOKIES_DEBUG = False

CRAWLSPIDER_FOLLOW_LINKS = True

DEFAULT_DROPITEM_LOG_LEVEL = "WARNING"

DEFAULT_ITEM_CLASS = "scrapy.item.Item"

DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en",
}

DEPTH_LIMIT = 0
DEPTH_PRIORITY = 0
DEPTH_STATS_VERBOSE = False

DNSCACHE_ENABLED = True
DNSCACHE_SIZE = 10000
DNS_RESOLVER = "scrapy.resolver.CachingThreadedResolver"
DNS_TIMEOUT = 60

DOWNLOAD_DELAY = 0

DOWNLOAD_FAIL_ON_DATALOSS = True

DOWNLOAD_HANDLERS = {}
DOWNLOAD_HANDLERS_BASE = {
    "data": "scrapy.core.downloader.handlers.datauri.DataURIDownloadHandler",
    "file": "scrapy.core.downloader.handlers.file.FileDownloadHandler",
    "http": "scrapy.core.downloader.handlers.http.HTTPDownloadHandler",
    "https": "scrapy.core.downloader.handlers.http.HTTPDownloadHandler",
    "s3": "scrapy.core.downloader.handlers.s3.S3DownloadHandler",
    "ftp": "scrapy.core.downloader.handlers.ftp.FTPDownloadHandler",
}

DOWNLOAD_MAXSIZE = 1024 * 1024 * 1024  # 1024m
DOWNLOAD_WARNSIZE = 32 * 1024 * 1024  # 32m

DOWNLOAD_TIMEOUT = 180  # 3mins

DOWNLOADER = "scrapy.core.downloader.Downloader"

DOWNLOADER_CLIENTCONTEXTFACTORY = (
    "scrapy.core.downloader.contextfactory.ScrapyClientContextFactory"
)
DOWNLOADER_CLIENT_TLS_CIPHERS = "DEFAULT"
# Use highest TLS/SSL protocol version supported by the platform, also allowing negotiation:
DOWNLOADER_CLIENT_TLS_METHOD = "TLS"
DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING = False

DOWNLOADER_HTTPCLIENTFACTORY = (
    "scrapy.core.downloader.webclient.ScrapyHTTPClientFactory"
)

DOWNLOADER_MIDDLEWARES = {}
DOWNLOADER_MIDDLEWARES_BASE = {
    # Engine side
    "scrapy.downloadermiddlewares.offsite.OffsiteMiddleware": 50,
    "scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware": 100,
    "scrapy.downloadermiddlewares.httpauth.HttpAuthMiddleware": 300,
    "scrapy.downloadermiddlewares.downloadtimeout.DownloadTimeoutMiddleware": 350,
    "scrapy.downloadermiddlewares.defaultheaders.DefaultHeadersMiddleware": 400,
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": 500,
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": 550,
    "scrapy.downloadermiddlewares.ajaxcrawl.AjaxCrawlMiddleware": 560,
    "scrapy.downloadermiddlewares.redirect.MetaRefreshMiddleware": 580,
    "scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware": 590,
    "scrapy.downloadermiddlewares.redirect.RedirectMiddleware": 600,
    "scrapy.downloadermiddlewares.cookies.CookiesMiddleware": 700,
    "scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware": 750,
    "scrapy.downloadermiddlewares.stats.DownloaderStats": 850,
    "scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware": 900,
    # Downloader side
}

DOWNLOADER_STATS = True

DUPEFILTER_CLASS = "scrapy.dupefilters.RFPDupeFilter"

EDITOR = "vi"
if sys.platform == "win32":
    EDITOR = "%s -m idlelib.idle"

EXTENSIONS = {}
EXTENSIONS_BASE = {
    "scrapy.extensions.corestats.CoreStats": 0,
    "scrapy.extensions.telnet.TelnetConsole": 0,
    "scrapy.extensions.memusage.MemoryUsage": 0,
    "scrapy.extensions.memdebug.MemoryDebugger": 0,
    "scrapy.extensions.closespider.CloseSpider": 0,
    "scrapy.extensions.feedexport.FeedExporter": 0,
    "scrapy.extensions.logstats.LogStats": 0,
    "scrapy.extensions.spiderstate.SpiderState": 0,
    "scrapy.extensions.throttle.AutoThrottle": 0,
}

FEEDS = {}
FEED_EXPORT_BATCH_ITEM_COUNT = 0
FEED_EXPORT_ENCODING = None
FEED_EXPORT_FIELDS = None
FEED_EXPORT_INDENT = 0
FEED_EXPORTERS = {}
FEED_EXPORTERS_BASE = {
    "json": "scrapy.exporters.JsonItemExporter",
    "jsonlines": "scrapy.exporters.JsonLinesItemExporter",
    "jsonl": "scrapy.exporters.JsonLinesItemExporter",
    "jl": "scrapy.exporters.JsonLinesItemExporter",
    "csv": "scrapy.exporters.CsvItemExporter",
    "xml": "scrapy.exporters.XmlItemExporter",
    "marshal": "scrapy.exporters.MarshalItemExporter",
    "pickle": "scrapy.exporters.PickleItemExporter",
}
FEED_FORMAT = "jsonlines"
FEED_STORE_EMPTY = True
FEED_STORAGES = {}
FEED_STORAGES_BASE = {
    "": "scrapy.extensions.feedexport.FileFeedStorage",
    "file": "scrapy.extensions.feedexport.FileFeedStorage",
    "ftp": "scrapy.extensions.feedexport.FTPFeedStorage",
    "gs": "scrapy.extensions.feedexport.GCSFeedStorage",
    "s3": "scrapy.extensions.feedexport.S3FeedStorage",
    "stdout": "scrapy.extensions.feedexport.StdoutFeedStorage",
}
FEED_STORAGE_FTP_ACTIVE = False
FEED_STORAGE_GCS_ACL = ""
FEED_STORAGE_S3_ACL = ""
FEED_TEMPDIR = None
FEED_URI_PARAMS = None  # a function to extend uri arguments

FILES_STORE_GCS_ACL = ""
FILES_STORE_S3_ACL = "private"

FORCE_CRAWLER_PROCESS = False

FTP_PASSIVE_MODE = True
FTP_USER = "anonymous"
FTP_PASSWORD = "guest"  # noqa: S105

GCS_PROJECT_ID = None

HTTPCACHE_ENABLED = False
HTTPCACHE_ALWAYS_STORE = False
HTTPCACHE_DBM_MODULE = "dbm"
HTTPCACHE_DIR = "httpcache"
HTTPCACHE_EXPIRATION_SECS = 0
HTTPCACHE_GZIP = False
HTTPCACHE_IGNORE_HTTP_CODES = []
HTTPCACHE_IGNORE_MISSING = False
HTTPCACHE_IGNORE_RESPONSE_CACHE_CONTROLS = []
HTTPCACHE_IGNORE_SCHEMES = ["file"]
HTTPCACHE_POLICY = "scrapy.extensions.httpcache.DummyPolicy"
HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

HTTPPROXY_ENABLED = True
HTTPPROXY_AUTH_ENCODING = "latin-1"

IMAGES_STORE_GCS_ACL = ""
IMAGES_STORE_S3_ACL = "private"

ITEM_PIPELINES = {}
ITEM_PIPELINES_BASE = {}

ITEM_PROCESSOR = "scrapy.pipelines.ItemPipelineManager"

JOBDIR = None

LOG_ENABLED = True
LOG_DATEFORMAT = "%Y-%m-%d %H:%M:%S"
LOG_ENCODING = "utf-8"
LOG_FILE = None
LOG_FILE_APPEND = True
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
LOG_FORMATTER = "scrapy.logformatter.LogFormatter"
LOG_LEVEL = "DEBUG"
LOG_SHORT_NAMES = False
LOG_STDOUT = False
LOG_VERSIONS = [
    "lxml",
    "libxml2",
    "cssselect",
    "parsel",
    "w3lib",
    "Twisted",
    "Python",
    "pyOpenSSL",
    "cryptography",
    "Platform",
]

LOGSTATS_INTERVAL = 60.0

MAIL_FROM = "scrapy@localhost"
MAIL_HOST = "localhost"
MAIL_PORT = 25
MAIL_USER = None
MAIL_PASS = None

MEMDEBUG_ENABLED = False  # enable memory debugging
MEMDEBUG_NOTIFY = []  # send memory debugging report by mail at engine shutdown

MEMUSAGE_ENABLED = True
MEMUSAGE_CHECK_INTERVAL_SECONDS = 60.0
MEMUSAGE_LIMIT_MB = 0
MEMUSAGE_NOTIFY_MAIL = []
MEMUSAGE_WARNING_MB = 0

METAREFRESH_ENABLED = True
METAREFRESH_IGNORE_TAGS = ["noscript"]
METAREFRESH_MAXDELAY = 100

NEWSPIDER_MODULE = ""

PERIODIC_LOG_DELTA = None
PERIODIC_LOG_STATS = None
PERIODIC_LOG_TIMING_ENABLED = False

RANDOMIZE_DOWNLOAD_DELAY = True

REACTOR_THREADPOOL_MAXSIZE = 10

REDIRECT_ENABLED = True
REDIRECT_MAX_TIMES = 20  # uses Firefox default setting
REDIRECT_PRIORITY_ADJUST = +2

REFERER_ENABLED = True
REFERRER_POLICY = "scrapy.spidermiddlewares.referer.DefaultReferrerPolicy"

REQUEST_FINGERPRINTER_CLASS = "scrapy.utils.request.RequestFingerprinter"
REQUEST_FINGERPRINTER_IMPLEMENTATION = "SENTINEL"

RETRY_ENABLED = True
RETRY_EXCEPTIONS = [
    "twisted.internet.defer.TimeoutError",
    "twisted.internet.error.TimeoutError",
    "twisted.internet.error.DNSLookupError",
    "twisted.internet.error.ConnectionRefusedError",
    "twisted.internet.error.ConnectionDone",
    "twisted.internet.error.ConnectError",
    "twisted.internet.error.ConnectionLost",
    "twisted.internet.error.TCPTimedOutError",
    "twisted.web.client.ResponseFailed",
    # OSError is raised by the HttpCompression middleware when trying to
    # decompress an empty response
    OSError,
    "scrapy.core.downloader.handlers.http11.TunnelError",
]
RETRY_HTTP_CODES = [500, 502, 503, 504, 522, 524, 408, 429]
RETRY_PRIORITY_ADJUST = -1
RETRY_TIMES = 2  # initial response + 2 retries = 3 requests

ROBOTSTXT_OBEY = False
ROBOTSTXT_PARSER = "scrapy.robotstxt.ProtegoRobotParser"
ROBOTSTXT_USER_AGENT = None

SCHEDULER = "scrapy.core.scheduler.Scheduler"
SCHEDULER_DEBUG = False
SCHEDULER_DISK_QUEUE = "scrapy.squeues.PickleLifoDiskQueue"
SCHEDULER_MEMORY_QUEUE = "scrapy.squeues.LifoMemoryQueue"
SCHEDULER_PRIORITY_QUEUE = "scrapy.pqueues.ScrapyPriorityQueue"
SCHEDULER_START_DISK_QUEUE = "scrapy.squeues.PickleFifoDiskQueue"
SCHEDULER_START_MEMORY_QUEUE = "scrapy.squeues.FifoMemoryQueue"

SCRAPER_SLOT_MAX_ACTIVE_SIZE = 5000000

SPIDER_CONTRACTS = {}
SPIDER_CONTRACTS_BASE = {
    "scrapy.contracts.default.UrlContract": 1,
    "scrapy.contracts.default.CallbackKeywordArgumentsContract": 1,
    "scrapy.contracts.default.MetadataContract": 1,
    "scrapy.contracts.default.ReturnsContract": 2,
    "scrapy.contracts.default.ScrapesContract": 3,
}

SPIDER_LOADER_CLASS = "scrapy.spiderloader.SpiderLoader"
SPIDER_LOADER_WARN_ONLY = False

SPIDER_MIDDLEWARES = {}
SPIDER_MIDDLEWARES_BASE = {
    # Engine side
    "scrapy.spidermiddlewares.start.StartSpiderMiddleware": 25,
    "scrapy.spidermiddlewares.httperror.HttpErrorMiddleware": 50,
    "scrapy.spidermiddlewares.referer.RefererMiddleware": 700,
    "scrapy.spidermiddlewares.urllength.UrlLengthMiddleware": 800,
    "scrapy.spidermiddlewares.depth.DepthMiddleware": 900,
    # Spider side
}

SPIDER_MODULES = []

STATS_CLASS = "scrapy.statscollectors.MemoryStatsCollector"
STATS_DUMP = True

STATSMAILER_RCPTS = []

TELNETCONSOLE_ENABLED = 1
TELNETCONSOLE_HOST = "127.0.0.1"
TELNETCONSOLE_PORT = [6023, 6073]
TELNETCONSOLE_USERNAME = "scrapy"
TELNETCONSOLE_PASSWORD = None

TEMPLATES_DIR = str((Path(__file__).parent / ".." / "templates").resolve())

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

URLLENGTH_LIMIT = 2083

USER_AGENT = f"Scrapy/{import_module('scrapy').__version__} (+https://scrapy.org)"

WARN_ON_GENERATOR_RETURN_VALUE = True
