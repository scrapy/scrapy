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

import sys, os
from os.path import join, abspath, dirname

BOT_NAME = 'scrapybot'
BOT_VERSION = '1.0'

CLOSESPIDER_TIMEOUT = 0
CLOSESPIDER_PAGECOUNT = 0
CLOSESPIDER_ITEMCOUNT = 0

COMMANDS_MODULE = ''

CONCURRENT_ITEMS = 100

CONCURRENT_REQUESTS = 16
CONCURRENT_REQUESTS_PER_DOMAIN = 8
CONCURRENT_REQUESTS_PER_IP = 0

CONCURRENT_SPIDERS = 8

COOKIES_ENABLED = True
COOKIES_DEBUG = False

DEFAULT_ITEM_CLASS = 'scrapy.item.Item'

DEFAULT_REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en',
}

DEFAULT_RESPONSE_ENCODING = 'ascii'

DEPTH_LIMIT = 0
DEPTH_STATS = True
DEPTH_PRIORITY = 1

DNSCACHE_ENABLED = True

DOWNLOAD_DELAY = 0

DOWNLOAD_HANDLERS = {}
DOWNLOAD_HANDLERS_BASE = {
    'file': 'scrapy.core.downloader.handlers.file.FileDownloadHandler',
    'http': 'scrapy.core.downloader.handlers.http.HttpDownloadHandler',
    'https': 'scrapy.core.downloader.handlers.http.HttpDownloadHandler',
    's3': 'scrapy.core.downloader.handlers.s3.S3DownloadHandler',
}

DOWNLOAD_TIMEOUT = 180      # 3mins

DOWNLOADER_DEBUG = False

DOWNLOADER_HTTPCLIENTFACTORY = 'scrapy.core.downloader.webclient.ScrapyHTTPClientFactory'

DOWNLOADER_MIDDLEWARES = {}

DOWNLOADER_MIDDLEWARES_BASE = {
    # Engine side
    'scrapy.contrib.downloadermiddleware.robotstxt.RobotsTxtMiddleware': 100,
    'scrapy.contrib.downloadermiddleware.httpauth.HttpAuthMiddleware': 300,
    'scrapy.contrib.downloadermiddleware.downloadtimeout.DownloadTimeoutMiddleware': 350,
    'scrapy.contrib.downloadermiddleware.useragent.UserAgentMiddleware': 400,
    'scrapy.contrib.downloadermiddleware.retry.RetryMiddleware': 500,
    'scrapy.contrib.downloadermiddleware.defaultheaders.DefaultHeadersMiddleware': 550,
    'scrapy.contrib.downloadermiddleware.redirect.RedirectMiddleware': 600,
    'scrapy.contrib.downloadermiddleware.cookies.CookiesMiddleware': 700,
    'scrapy.contrib.downloadermiddleware.httpproxy.HttpProxyMiddleware': 750,
    'scrapy.contrib.downloadermiddleware.httpcompression.HttpCompressionMiddleware': 800,
    'scrapy.contrib.downloadermiddleware.chunked.ChunkedTransferMiddleware': 830,
    'scrapy.contrib.downloadermiddleware.stats.DownloaderStats': 850,
    'scrapy.contrib.downloadermiddleware.httpcache.HttpCacheMiddleware': 900,
    # Downloader side
}

DOWNLOADER_STATS = True

DUPEFILTER_CLASS = 'scrapy.dupefilter.RFPDupeFilter'

try:
    EDITOR = os.environ['EDITOR']
except KeyError:
    if sys.platform == 'win32':
        EDITOR = '%s -m idlelib.idle'
    else:
        EDITOR = 'vi'

ENCODING_ALIASES = {}

ENCODING_ALIASES_BASE = {
    # gb2312 is superseded by gb18030
    'gb2312': 'gb18030',
    'chinese': 'gb18030',
    'csiso58gb231280': 'gb18030',
    'euc- cn': 'gb18030',
    'euccn': 'gb18030',
    'eucgb2312-cn': 'gb18030',
    'gb2312-1980': 'gb18030',
    'gb2312-80': 'gb18030',
    'iso- ir-58': 'gb18030',
    # gbk is superseded by gb18030
    'gbk': 'gb18030',
    '936': 'gb18030',
    'cp936': 'gb18030',
    'ms936': 'gb18030',
    # latin_1 is a subset of cp1252
    'latin_1': 'cp1252',
    'iso-8859-1': 'cp1252',
    'iso8859-1': 'cp1252',
    '8859': 'cp1252',
    'cp819': 'cp1252',
    'latin': 'cp1252',
    'latin1': 'cp1252',
    'l1': 'cp1252',
    # others
    'zh-cn': 'gb18030',
    'win-1251': 'cp1251',
    'macintosh' : 'mac_roman',
    'x-sjis': 'shift_jis',
}

EXTENSIONS = {}

EXTENSIONS_BASE = {
    'scrapy.contrib.corestats.CoreStats': 0,
    'scrapy.webservice.WebService': 0,
    'scrapy.telnet.TelnetConsole': 0,
    'scrapy.contrib.memusage.MemoryUsage': 0,
    'scrapy.contrib.memdebug.MemoryDebugger': 0,
    'scrapy.contrib.closespider.CloseSpider': 0,
    'scrapy.contrib.feedexport.FeedExporter': 0,
    'scrapy.contrib.logstats.LogStats': 0,
}

FEED_URI = None
FEED_URI_PARAMS = None # a function to extend uri arguments
FEED_FORMAT = 'jsonlines'
FEED_STORE_EMPTY = False
FEED_STORAGES = {}
FEED_STORAGES_BASE = {
    '': 'scrapy.contrib.feedexport.FileFeedStorage',
    'file': 'scrapy.contrib.feedexport.FileFeedStorage',
    'stdout': 'scrapy.contrib.feedexport.StdoutFeedStorage',
    's3': 'scrapy.contrib.feedexport.S3FeedStorage',
    'ftp': 'scrapy.contrib.feedexport.FTPFeedStorage',
}
FEED_EXPORTERS = {}
FEED_EXPORTERS_BASE = {
    'json': 'scrapy.contrib.exporter.JsonItemExporter',
    'jsonlines': 'scrapy.contrib.exporter.JsonLinesItemExporter',
    'csv': 'scrapy.contrib.exporter.CsvItemExporter',
    'xml': 'scrapy.contrib.exporter.XmlItemExporter',
    'marshal': 'scrapy.contrib.exporter.MarshalItemExporter',
}

HTTPCACHE_ENABLED = False
HTTPCACHE_DIR = 'httpcache'
HTTPCACHE_IGNORE_MISSING = False
HTTPCACHE_STORAGE = 'scrapy.contrib.downloadermiddleware.httpcache.FilesystemCacheStorage'
HTTPCACHE_EXPIRATION_SECS = 0
HTTPCACHE_IGNORE_HTTP_CODES = []
HTTPCACHE_IGNORE_SCHEMES = ['file']
HTTPCACHE_DBM_MODULE = 'anydbm'

ITEM_PROCESSOR = 'scrapy.contrib.pipeline.ItemPipelineManager'

# Item pipelines are typically set in specific commands settings
ITEM_PIPELINES = []

LOG_ENABLED = True
LOG_ENCODING = 'utf-8'
LOG_FORMATTER = 'scrapy.logformatter.LogFormatter'
LOG_STDOUT = False
LOG_LEVEL = 'DEBUG'
LOG_FILE = None

LOGSTATS_INTERVAL = 60.0

MAIL_DEBUG = False
MAIL_HOST = 'localhost'
MAIL_PORT = 25
MAIL_FROM = 'scrapy@localhost'
MAIL_PASS = None
MAIL_USER = None

MEMDEBUG_ENABLED = False        # enable memory debugging
MEMDEBUG_NOTIFY = []            # send memory debugging report by mail at engine shutdown

MEMUSAGE_ENABLED = 1
MEMUSAGE_LIMIT_MB = 0
MEMUSAGE_NOTIFY_MAIL = []
MEMUSAGE_REPORT = False
MEMUSAGE_WARNING_MB = 0

NEWSPIDER_MODULE = ''

RANDOMIZE_DOWNLOAD_DELAY = True

REDIRECT_ENABLED = True
REDIRECT_MAX_METAREFRESH_DELAY = 100
REDIRECT_MAX_TIMES = 20 # uses Firefox default setting
REDIRECT_PRIORITY_ADJUST = +2

RETRY_ENABLED = True
RETRY_TIMES = 2 # initial response + 2 retries = 3 requests
RETRY_HTTP_CODES = [500, 503, 504, 400, 408]
RETRY_PRIORITY_ADJUST = -1

ROBOTSTXT_OBEY = False

SCHEDULER = 'scrapy.core.scheduler.Scheduler'
SCHEDULER_DISK_QUEUE = 'scrapy.squeue.MarshalDiskQueue'

SELECTORS_BACKEND = None # possible values: libxml2, lxml

SPIDER_MANAGER_CLASS = 'scrapy.spidermanager.SpiderManager'

SPIDER_MIDDLEWARES = {}

SPIDER_MIDDLEWARES_BASE = {
    # Engine side
    'scrapy.contrib.spidermiddleware.httperror.HttpErrorMiddleware': 50,
    'scrapy.contrib.spidermiddleware.offsite.OffsiteMiddleware': 500,
    'scrapy.contrib.spidermiddleware.referer.RefererMiddleware': 700,
    'scrapy.contrib.spidermiddleware.urllength.UrlLengthMiddleware': 800,
    'scrapy.contrib.spidermiddleware.depth.DepthMiddleware': 900,
    # Spider side
}

SPIDER_MODULES = []

SQLITE_DB = 'scrapy.db'

STATS_CLASS = 'scrapy.statscol.MemoryStatsCollector'
STATS_ENABLED = True
STATS_DUMP = True

STATSMAILER_RCPTS = []

TEMPLATES_DIR = abspath(join(dirname(__file__), '..', 'templates'))

URLLENGTH_LIMIT = 2083

USER_AGENT = '%s/%s' % (BOT_NAME, BOT_VERSION)

TELNETCONSOLE_ENABLED = 1
TELNETCONSOLE_PORT = [6023, 6073]
TELNETCONSOLE_HOST = '0.0.0.0'

WEBSERVICE_ENABLED = True
WEBSERVICE_LOGFILE = None
WEBSERVICE_PORT = [6080, 7030]
WEBSERVICE_HOST = '0.0.0.0'
WEBSERVICE_RESOURCES = {}
WEBSERVICE_RESOURCES_BASE = {
    'scrapy.contrib.webservice.crawler.CrawlerResource': 1,
    'scrapy.contrib.webservice.enginestatus.EngineStatusResource': 1,
    'scrapy.contrib.webservice.stats.StatsResource': 1,
}
