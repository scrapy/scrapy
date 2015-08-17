import scrapy
from scrapy.addons import Addon

__all__ = ['make_builtin_addon',

           'depth', 'httperror', 'offsite', 'referer', 'urllength',

           'ajaxcrawl', 'chunked', 'cookies', 'defaultheaders',
           'downloadtimeout', 'httpauth', 'httpcache', 'httpcompression',
           'httpproxy', 'metarefresh', 'redirect', 'retry', 'robotstxt',
           'stats', 'useragent',

           'autothrottle', 'corestats', 'closespider', 'debugger', 'feedexport',
           'logstats', 'memdebug', 'memusage', 'spiderstate', 'stacktracedump',
           'statsmailer', 'telnetconsole',
          ]


def make_builtin_addon(addon_name, comp_type, comp, order=0,
                       addon_default_config=None, addon_version=None):
    class ThisAddon(Addon):
        name = addon_name
        version = addon_version or scrapy.__version__
        component_type = comp_type
        component = comp
        component_order = order
        default_config = addon_default_config or {}

    return ThisAddon


# XXX: Below are CLASSES that have lowercase names. This is in line with the
#      original SEP-021 but violates PEP8.
# We might consider prepending all built-in addon names with scrapy_ or similar
# to reduce the chance of name clashes.

# SPIDER MIDDLEWARES

depth = make_builtin_addon(
    'depth',
    'SPIDER_MIDDLEWARES',
    'scrapy.spidermiddlewares.depth.DepthMiddleware',
    900,
)

httperror = make_builtin_addon(
    'httperror',
    'SPIDER_MIDDLEWARES',
    'scrapy.spidermiddlewares.httperror.HttpErrorMiddleware',
    50,
)

offsite = make_builtin_addon(
    'offsite',
    'SPIDER_MIDDLEWARES',
    'scrapy.spidermiddlewares.offsite.OffsiteMiddleware',
    500,
)

referer = make_builtin_addon(
    'referer',
    'SPIDER_MIDDLEWARES',
    'scrapy.spidermiddlewares.referer.RefererMiddleware',
    700,
    {'enabled': True},
)

urllength = make_builtin_addon(
    'urllength',
    'SPIDER_MIDDLEWARES',
    'scrapy.spidermiddlewares.urllength.UrlLengthMiddleware',
    800,
)


# DOWNLOADER MIDDLEWARES

ajaxcrawl = make_builtin_addon(
    'ajaxcrawl',
    'DOWNLOADER_MIDDLEWARES',
    'scrapy.downloadermiddlewares.ajaxcrawl.AjaxCrawlMiddleware',
    560,
)

chunked = make_builtin_addon(
    'chunked',
    'DOWNLOADER_MIDDLEWARES',
    'scrapy.downloadermiddlewares.chunked.ChunkedTransferMiddleware',
    830,
)

cookies = make_builtin_addon(
    'cookies',
    'DOWNLOADER_MIDDLEWARES',
    'scrapy.downloadermiddlewares.cookies.CookiesMiddleware',
    700,
    {'enabled': True},
)

defaultheaders = make_builtin_addon(
    'defaultheaders',
    'DOWNLOADER_MIDDLEWARES',
    'scrapy.downloadermiddlewares.defaultheaders.DefaultHeadersMiddleware',
    550,
)
# Assume every config entry is a header
def defaultheaders_export_config(self, config, settings):
    conf = self.default_config or {}
    conf.update(config)
    settings.set('DEFAULT_REQUEST_HEADERS', conf, 'addon')
defaultheaders.export_config = defaultheaders_export_config

downloadtimeout = make_builtin_addon(
    'downloadtimeout',
    'DOWNLOADER_MIDDLEWARES',
    'scrapy.downloadermiddlewares.downloadtimeout.DownloadTimeoutMiddleware',
    350,
)
downloadtimeout.config_mapping = {'timeout': 'DOWNLOAD_TIMEOUT',
                                  'download_timeout': 'DOWNLOAD_TIMEOUT'}

httpauth = make_builtin_addon(
    'httpauth',
    'DOWNLOADER_MIDDLEWARES',
    'scrapy.downloadermiddlewares.httpauth.HttpAuthMiddleware',
    300,
)

httpcache = make_builtin_addon(
    'httpcache',
    'DOWNLOADER_MIDDLEWARES',
    'scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware',
    900,
    {'enabled': True},
)

httpcompression = make_builtin_addon(
    'httpcompression',
    'DOWNLOADER_MIDDLEWARES',
    'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware',
    590,
    {'enabled': True},
)
httpcompression.config_mapping = {'enabled': 'COMPRESSION_ENABLED'}

httpproxy = make_builtin_addon(
    'httpproxy',
    'DOWNLOADER_MIDDLEWARES',
    'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware',
    750,
)

metarefresh = make_builtin_addon(
    'metarefresh',
    'DOWNLOADER_MIDDLEWARES',
    'scrapy.downloadermiddlewares.redirect.MetaRefreshMiddleware',
    580,
    {'enabled': True},
)
metarefresh.config_mapping = {'max_times': 'REDIRECT_MAX_TIMES'}

redirect = make_builtin_addon(
    'redirect',
    'DOWNLOADER_MIDDLEWARES',
    'scrapy.downloadermiddlewares.redirect.RedirectMiddleware',
    600,
    {'enabled': True},
)

retry = make_builtin_addon(
    'retry',
    'DOWNLOADER_MIDDLEWARES',
    'scrapy.downloadermiddlewares.retry.RetryMiddleware',
    500,
    {'enabled': True},
)

robotstxt = make_builtin_addon(
    'robotstxt',
    'DOWNLOADER_MIDDLEWARES',
    'scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware',
    100,
    {'obey': True},
)

stats = make_builtin_addon(
    'stats',
    'DOWNLOADER_MIDDLEWARES',
    'scrapy.downloadermiddlewares.stats.DownloaderStats',
    850,
)

useragent = make_builtin_addon(
    'useragent',
    'DOWNLOADER_MIDDLEWARES',
    'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware',
    400,
)
useragent.config_mapping = {'user_agent': 'USER_AGENT'}


# ITEM PIPELINES


# EXTENSIONS

autothrottle = make_builtin_addon(
    'throttle',
    'EXTENSIONS',
    'scrapy.extensions.throttle.AutoThrottle',
    0,
    {'enabled': True},
)

corestats = make_builtin_addon(
    'corestats',
    'EXTENSIONS'
    'scrapy.extensions.corestats.CoreStats',
    0,
)

closespider = make_builtin_addon(
    'closespider',
    'EXTENSIONS'
    'scrapy.extensions.closespider.CloseSpider',
    0,
)

debugger = make_builtin_addon(
    'debugger',
    'EXTENSIONS'
    'scrapy.extensions.debug.Debugger',
    0,
)

feedexport = make_builtin_addon(
    'feedexport',
    'EXTENSIONS'
    'scrapy.extensions.feedexport.FeedExporter',
    0,
)
feedexport.settings_prefix = 'FEED'

logstats = make_builtin_addon(
    'logstats',
    'EXTENSIONS'
    'scrapy.extensions.logstats.LogStats',
    0,
)

memdebug = make_builtin_addon(
    'memdebug',
    'EXTENSIONS'
    'scrapy.extensions.memdebug.MemoryDebugger',
    0,
    {'enabled': True},
)

memusage = make_builtin_addon(
    'memusage',
    'EXTENSIONS'
    'scrapy.extensions.memusage.MemoryUsage',
    0,
    {'enabled': True},
)

spiderstate = make_builtin_addon(
    'spiderstate',
    'EXTENSIONS'
    'scrapy.extensions.spiderstate.SpiderState',
    0,
)

stacktracedump = make_builtin_addon(
    'stacktracedump',
    'EXTENSIONS'
    'scrapy.extensions.debug.StackTraceDump',
    0,
)

statsmailer = make_builtin_addon(
    'statsmailer',
    'EXTENSIONS'
    'scrapy.extensions.statsmailer.StatsMailer',
    0,
)

telnetconsole = make_builtin_addon(
    'telnetconsole',
    'EXTENSIONS'
    'scrapy.telnet.TelnetConsole',
    0,
)
