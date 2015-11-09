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


def make_builtin_addon(addon_name, addon_default_config=None,
                       addon_version=None):
    class ThisAddon(Addon):
        name = addon_name
        version = addon_version or scrapy.__version__
        default_config = addon_default_config or {}

    return ThisAddon


# XXX: Below are CLASSES that have lowercase names. This is in line with the
#      original SEP-021 but violates PEP8.
# We might consider prepending all built-in addon names with scrapy_ or similar
# to reduce the chance of name clashes.

# SPIDER MIDDLEWARES

depth = make_builtin_addon('depth')

httperror = make_builtin_addon('httperror')

offsite = make_builtin_addon('offsite')

referer = make_builtin_addon('referer')

urllength = make_builtin_addon('urllength')


# DOWNLOADER MIDDLEWARES

ajaxcrawl = make_builtin_addon('ajaxcrawl', {'enabled': True})

chunked = make_builtin_addon('chunked')

cookies = make_builtin_addon('cookies')

defaultheaders = make_builtin_addon('defaultheaders')
# Assume every config entry is a header
def defaultheaders_export_config(self, config, settings):
    conf = self.default_config or {}
    conf.update(config)
    settings.set('DEFAULT_REQUEST_HEADERS', conf, 'addon')
defaultheaders.export_config = defaultheaders_export_config

downloadtimeout = make_builtin_addon('downloadtimeout')
downloadtimeout.config_mapping = {'timeout': 'DOWNLOAD_TIMEOUT',
                                  'download_timeout': 'DOWNLOAD_TIMEOUT'}

httpauth = make_builtin_addon('httpauth')

httpcache = make_builtin_addon('httpcache', {'enabled': True})

httpcompression = make_builtin_addon('httpcompression')
httpcompression.config_mapping = {'enabled': 'COMPRESSION_ENABLED'}

httpproxy = make_builtin_addon('httpproxy')

metarefresh = make_builtin_addon('metarefresh')
metarefresh.config_mapping = {'max_times': 'REDIRECT_MAX_TIMES'}

redirect = make_builtin_addon('redirect')

retry = make_builtin_addon('retry')

robotstxt = make_builtin_addon('robotstxt', {'obey': True})

stats = make_builtin_addon('stats')

useragent = make_builtin_addon('useragent')
useragent.config_mapping = {'user_agent': 'USER_AGENT'}


# ITEM PIPELINES


# EXTENSIONS

autothrottle = make_builtin_addon('autothrottle', {'enabled': True})

corestats = make_builtin_addon('corestats')

closespider = make_builtin_addon('closespider')

debugger = make_builtin_addon('debugger')

feedexport = make_builtin_addon('feedexport')
feedexport.settings_prefix = 'FEED'

logstats = make_builtin_addon('logstats')

memdebug = make_builtin_addon('memdebug', {'enabled': True})

memusage = make_builtin_addon('memusage', {'enabled': True})

spiderstate = make_builtin_addon('spiderstate')

stacktracedump = make_builtin_addon('stacktracedump')

statsmailer = make_builtin_addon('statsmailer')

telnetconsole = make_builtin_addon('telnetconsole')
