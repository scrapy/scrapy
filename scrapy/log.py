""" 
Scrapy logging facility

See documentation in docs/topics/logging.rst
"""
import sys
import logging

from twisted.python import log

from scrapy.conf import settings
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
    message = ev.get('message')
    lvlname = level_names.get(level, 'NOLEVEL')
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
    return ev

def _get_log_level(level_name_or_id=None):
    if level_name_or_id is None:
        lvlname = settings['LOG_LEVEL']
        return globals()[lvlname]
    elif isinstance(level_name_or_id, int):
        return level_name_or_id
    elif isinstance(level_name_or_id, basestring):
        return globals()[level_name_or_id]
    else:
        raise ValueError("Unknown log level: %r" % level_name_or_id)

def start(logfile=None, loglevel=None, logstdout=None):
    global started
    if started or not settings.getbool('LOG_ENABLED'):
        return
    started = True

    if log.defaultObserver: # check twisted log not already started
        loglevel = _get_log_level(loglevel)
        logfile = logfile or settings['LOG_FILE']
        file = open(logfile, 'a') if logfile else sys.stderr
        if logstdout is None:
            logstdout = settings.getbool('LOG_STDOUT')
        sflo = ScrapyFileLogObserver(file, loglevel, settings['LOG_ENCODING'])
        log.startLoggingWithObserver(sflo.emit, setStdout=logstdout)
        msg("Started project: %s" % settings['BOT_NAME'])

def msg(message, level=INFO, **kw):
    if 'component' in kw:
        import warnings
        warnings.warn("Argument `component` of scrapy.log.msg() is deprecated", \
            DeprecationWarning, stacklevel=2)
    kw.setdefault('system', 'scrapy')
    kw['logLevel'] = level
    log.msg(message, **kw)

def err(_stuff=None, _why=None, **kw):
    kw.setdefault('system', 'scrapy')
    kw['logLevel'] = kw.pop('level', ERROR)
    log.err(_stuff, _why, **kw)

formatter = load_object(settings['LOG_FORMATTER'])()
