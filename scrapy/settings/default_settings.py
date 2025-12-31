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

__all__ = [
    "ADDONS",
    "AJAXCRAWL_ENABLED",
    "AJAXCRAWL_MAXSIZE",
    "ASYNCIO_EVENT_LOOP",
    "AUTOTHROTTLE_DEBUG",
    "AUTOTHROTTLE_ENABLED",
    "AUTOTHROTTLE_MAX_DELAY",
    "AUTOTHROTTLE_START_DELAY",
    "AUTOTHROTTLE_TARGET_CONCURRENCY",
    "BOT_NAME",
    "CLOSESPIDER_ERRORCOUNT",
    "CLOSESPIDER_ITEMCOUNT",
    "CLOSESPIDER_PAGECOUNT",
    "CLOSESPIDER_TIMEOUT",
    "COMMANDS_MODULE",
    "COMPRESSION_ENABLED",
    "CONCURRENT_ITEMS",
    "CONCURRENT_REQUESTS",
    "CONCURRENT_REQUESTS_PER_DOMAIN",
    "COOKIES_DEBUG",
    "COOKIES_ENABLED",
    "CRAWLSPIDER_FOLLOW_LINKS",
    "DEFAULT_DROPITEM_LOG_LEVEL",
    "DEFAULT_ITEM_CLASS",
    "DEFAULT_REQUEST_HEADERS",
    "DEPTH_LIMIT",
    "DEPTH_PRIORITY",
    "DEPTH_STATS_VERBOSE",
    "DNSCACHE_ENABLED",
    "DNSCACHE_SIZE",
    "DNS_RESOLVER",
    "DNS_TIMEOUT",
    "DOWNLOADER",
    "DOWNLOADER_CLIENTCONTEXTFACTORY",
    "DOWNLOADER_CLIENT_TLS_CIPHERS",
    "DOWNLOADER_CLIENT_TLS_METHOD",
    "DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING",
    "DOWNLOADER_HTTPCLIENTFACTORY",
    "DOWNLOADER_MIDDLEWARES",
    "DOWNLOADER_MIDDLEWARES_BASE",
    "DOWNLOADER_STATS",
    "DOWNLOAD_DELAY",
    "DOWNLOAD_FAIL_ON_DATALOSS",
    "DOWNLOAD_HANDLERS",
    "DOWNLOAD_HANDLERS_BASE",
    "DOWNLOAD_MAXSIZE",
    "DOWNLOAD_TIMEOUT",
    "DOWNLOAD_WARNSIZE",
    "DUPEFILTER_CLASS",
    "EDITOR",
    "EXTENSIONS",
    "EXTENSIONS_BASE",
    "FEEDS",
    "FEED_EXPORTERS",
    "FEED_EXPORTERS_BASE",
    "FEED_EXPORT_BATCH_ITEM_COUNT",
    "FEED_EXPORT_ENCODING",
    "FEED_EXPORT_FIELDS",
    "FEED_EXPORT_INDENT",
    "FEED_FORMAT",
    "FEED_STORAGES",
    "FEED_STORAGES_BASE",
    "FEED_STORAGE_FTP_ACTIVE",
    "FEED_STORAGE_GCS_ACL",
    "FEED_STORAGE_S3_ACL",
    "FEED_STORE_EMPTY",
    "FEED_TEMPDIR",
    "FEED_URI_PARAMS",
    "FILES_STORE_GCS_ACL",
    "FILES_STORE_S3_ACL",
    "FORCE_CRAWLER_PROCESS",
    "FTP_PASSIVE_MODE",
    "FTP_PASSWORD",
    "FTP_USER",
    "GCS_PROJECT_ID",
    "HTTPCACHE_ALWAYS_STORE",
    "HTTPCACHE_DBM_MODULE",
    "HTTPCACHE_DIR",
    "HTTPCACHE_ENABLED",
    "HTTPCACHE_EXPIRATION_SECS",
    "HTTPCACHE_GZIP",
    "HTTPCACHE_IGNORE_HTTP_CODES",
    "HTTPCACHE_IGNORE_MISSING",
    "HTTPCACHE_IGNORE_RESPONSE_CACHE_CONTROLS",
    "HTTPCACHE_IGNORE_SCHEMES",
    "HTTPCACHE_POLICY",
    "HTTPCACHE_STORAGE",
    "HTTPPROXY_AUTH_ENCODING",
    "HTTPPROXY_ENABLED",
    "IMAGES_STORE_GCS_ACL",
    "IMAGES_STORE_S3_ACL",
    "ITEM_PIPELINES",
    "ITEM_PIPELINES_BASE",
    "ITEM_PROCESSOR",
    "JOBDIR",
    "LOGSTATS_INTERVAL",
    "LOG_DATEFORMAT",
    "LOG_ENABLED",
    "LOG_ENCODING",
    "LOG_FILE",
    "LOG_FILE_APPEND",
    "LOG_FORMAT",
    "LOG_FORMATTER",
    "LOG_LEVEL",
    "LOG_SHORT_NAMES",
    "LOG_STDOUT",
    "LOG_VERSIONS",
    "MAIL_FROM",
    "MAIL_HOST",
    "MAIL_PASS",
    "MAIL_PORT",
    "MAIL_USER",
    "MEMDEBUG_ENABLED",
    "MEMDEBUG_NOTIFY",
    "MEMUSAGE_CHECK_INTERVAL_SECONDS",
    "MEMUSAGE_ENABLED",
    "MEMUSAGE_LIMIT_MB",
    "MEMUSAGE_NOTIFY_MAIL",
    "MEMUSAGE_WARNING_MB",
    "METAREFRESH_ENABLED",
    "METAREFRESH_IGNORE_TAGS",
    "METAREFRESH_MAXDELAY",
    "NEWSPIDER_MODULE",
    "PERIODIC_LOG_DELTA",
    "PERIODIC_LOG_STATS",
    "PERIODIC_LOG_TIMING_ENABLED",
    "RANDOMIZE_DOWNLOAD_DELAY",
    "REACTOR_THREADPOOL_MAXSIZE",
    "REDIRECT_ENABLED",
    "REDIRECT_MAX_TIMES",
    "REDIRECT_PRIORITY_ADJUST",
    "REFERER_ENABLED",
    "REFERRER_POLICY",
    "REQUEST_FINGERPRINTER_CLASS",
    "RETRY_ENABLED",
    "RETRY_EXCEPTIONS",
    "RETRY_HTTP_CODES",
    "RETRY_PRIORITY_ADJUST",
    "RETRY_TIMES",
    "ROBOTSTXT_OBEY",
    "ROBOTSTXT_PARSER",
    "ROBOTSTXT_USER_AGENT",
    "SCHEDULER",
    "SCHEDULER_DEBUG",
    "SCHEDULER_DISK_QUEUE",
    "SCHEDULER_MEMORY_QUEUE",
    "SCHEDULER_PRIORITY_QUEUE",
    "SCHEDULER_START_DISK_QUEUE",
    "SCHEDULER_START_MEMORY_QUEUE",
    "SCRAPER_SLOT_MAX_ACTIVE_SIZE",
    "SPIDER_CONTRACTS",
    "SPIDER_CONTRACTS_BASE",
    "SPIDER_LOADER_CLASS",
    "SPIDER_LOADER_WARN_ONLY",
    "SPIDER_MIDDLEWARES",
    "SPIDER_MIDDLEWARES_BASE",
    "SPIDER_MODULES",
    "STATSMAILER_RCPTS",
    "STATS_CLASS",
    "STATS_DUMP",
    "TELNETCONSOLE_ENABLED",
    "TELNETCONSOLE_HOST",
    "TELNETCONSOLE_PASSWORD",
    "TELNETCONSOLE_PORT",
    "TELNETCONSOLE_USERNAME",
    "TEMPLATES_DIR",
    "TWISTED_REACTOR",
    "URLLENGTH_LIMIT",
    "USER_AGENT",
    "WARN_ON_GENERATOR_RETURN_VALUE",
]

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
    "http": "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler",
    "https": "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler",
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
    "scrapy.extensions.logcount.LogCount": 0,
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
SCHEDULER_PRIORITY_QUEUE = "scrapy.pqueues.DownloaderAwarePriorityQueue"
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


def __getattr__(name: str):
    if name == "CONCURRENT_REQUESTS_PER_IP":
        import warnings  # noqa: PLC0415

        from scrapy.exceptions import ScrapyDeprecationWarning  # noqa: PLC0415

        warnings.warn(
            "The scrapy.settings.default_settings.CONCURRENT_REQUESTS_PER_IP attribute is deprecated, use scrapy.settings.default_settings.CONCURRENT_REQUESTS_PER_DOMAIN instead.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return 0

    raise AttributeError
