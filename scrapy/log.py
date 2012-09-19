""" 
Scrapy logging facility

See documentation in docs/topics/logging.rst
"""
import sys
import logging
import warnings

from twisted.python import log

import scrapy
from scrapy.utils.python import unicode_to_str
from scrapy.utils.misc import load_object
 
# Logging levels
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL
SILENT = CRITICAL + 1

level_names = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
    SILENT: "SILENT",
}

started = False
formatter = None

class ScrapyFileLogObserver(log.FileLogObserver):

    def __init__(self, f, level=INFO, encoding='utf-8'):
        self.level = level
        self.encoding = encoding
        log.FileLogObserver.__init__(self, f)

    def emit(self, eventDict):
        ev = _adapt_eventdict(eventDict, self.level, self.encoding)
        if ev is not None:
            log.FileLogObserver.emit(self, ev)

def _adapt_eventdict(eventDict, log_level=INFO, encoding='utf-8', prepend_level=True):
    """Adapt Twisted log eventDict making it suitable for logging with a Scrapy
    log observer. It may return None to indicate that the event should be
    ignored by a Scrapy log observer.

    `log_level` is the minimum level being logged, and `encoding` is the log
    encoding.
    """
    ev = eventDict.copy()
    if ev['isError']:
        ev.setdefault('logLevel', ERROR)

    # ignore non-error messages from outside scrapy
    if ev.get('system') != 'scrapy' and not ev['isError']:
        return

    level = ev.get('logLevel')
    if level < log_level:
        return

    spider = ev.get('spider')
    if spider:
        ev['system'] = spider.name

    lvlname = level_names.get(level, 'NOLEVEL')
    message = ev.get('message')
    if message:
        message = [unicode_to_str(x, encoding) for x in message]
        if prepend_level:
            message[0] = "%s: %s" % (lvlname, message[0])
        ev['message'] = message

    why = ev.get('why')
    if why:
        why = unicode_to_str(why, encoding)
        if prepend_level:
            why = "%s: %s" % (lvlname, why)
        ev['why'] = why

    fmt = ev.get('format')
    if fmt:
        fmt = unicode_to_str(fmt, encoding)
        if prepend_level:
            fmt = "%s: %s" % (lvlname, fmt)
        ev['format'] = fmt

    return ev

def _get_log_level(level_name_or_id=None):
    if isinstance(level_name_or_id, int):
        return level_name_or_id
    elif isinstance(level_name_or_id, basestring):
        return globals()[level_name_or_id]
    else:
        raise ValueError("Unknown log level: %r" % level_name_or_id)

def start(logfile=None, loglevel='INFO', logstdout=True, logencoding='utf-8'):
    if log.defaultObserver: # check twisted log not already started
        loglevel = _get_log_level(loglevel)
        file = open(logfile, 'a') if logfile else sys.stderr
        sflo = ScrapyFileLogObserver(file, loglevel, logencoding)
        _oldshowwarning = warnings.showwarning
        log.startLoggingWithObserver(sflo.emit, setStdout=logstdout)
        # restore warnings, wrongly silenced by Twisted
        warnings.showwarning = _oldshowwarning

def msg(message=None, _level=INFO, **kw):
    kw['logLevel'] = kw.pop('level', _level)
    kw.setdefault('system', 'scrapy')
    if message is None:
        log.msg(**kw)
    else:
        log.msg(message, **kw)

def err(_stuff=None, _why=None, **kw):
    kw['logLevel'] = kw.pop('level', ERROR)
    kw.setdefault('system', 'scrapy')
    log.err(_stuff, _why, **kw)

def start_from_settings(settings):
    global started, formatter
    if started or not settings.getbool('LOG_ENABLED'):
        return
    started = True
    formatter = load_object(settings['LOG_FORMATTER'])()

    if not settings.getbool('LOG_ENABLED'):
        return
    start(settings['LOG_FILE'], settings['LOG_LEVEL'], settings['LOG_STDOUT'],
        settings['LOG_ENCODING'])
    msg("Scrapy %s started (bot: %s)" % (scrapy.__version__, \
        settings['BOT_NAME']))
