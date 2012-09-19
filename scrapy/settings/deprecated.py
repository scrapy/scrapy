import warnings
from scrapy.exceptions import ScrapyDeprecationWarning

DEPRECATED_SETTINGS = [
    ('TRACK_REFS', 'no longer needed (trackref is always enabled)'),
    ('RESPONSE_CLASSES', 'no longer supported'),
    ('DEFAULT_RESPONSE_ENCODING', 'no longer supported'),
    ('BOT_VERSION', 'no longer used (user agent defaults to Scrapy now)'),
    ('ENCODING_ALIASES', 'no longer needed (encoding discovery uses w3lib now)'),
    ('STATS_ENABLED', 'no longer supported (change STATS_CLASS instead)'),
    ('SQLITE_DB', 'no longer supported'),
]

def check_deprecated_settings(settings):
    deprecated = [x for x in DEPRECATED_SETTINGS if settings[x[0]] is not None]
    if deprecated:
        msg = "You are using the following settings which are deprecated or obsolete"
        msg += " (ask scrapy-users@googlegroups.com for alternatives):"
        msg = msg + "\n    " + "\n    ".join("%s: %s" % x for x in deprecated)
        warnings.warn(msg, ScrapyDeprecationWarning)
