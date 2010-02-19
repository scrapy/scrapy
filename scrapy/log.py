""" 
Scrapy logging facility

See documentation in docs/topics/logging.rst
"""
import sys
from traceback import format_exc

from twisted.python import log
from scrapy.xlib.pydispatch import dispatcher

from scrapy.conf import settings
from scrapy.utils.python import unicode_to_str
 
# Logging levels
SILENT, CRITICAL, ERROR, WARNING, INFO, DEBUG = range(6)
level_names = {
    0: "SILENT",
    1: "CRITICAL",
    2: "ERROR",
    3: "WARNING",
    4: "INFO",
    5: "DEBUG",
}

BOT_NAME = settings['BOT_NAME']

# signal sent when log message is received
# args: message, level, spider
logmessage_received = object()

# default logging level
log_level = DEBUG

started = False

def _get_log_level(level_name_or_id=None):
    if level_name_or_id is None:
        lvlname = settings['LOG_LEVEL'] or settings['LOGLEVEL']
        return globals()[lvlname]
    elif isinstance(level_name_or_id, int) and 0 <= level_name_or_id <= 5:
        return level_name_or_id
    elif isinstance(level_name_or_id, basestring):
        return globals()[level_name_or_id]
    else:
        raise ValueError("Unknown log level: %r" % level_name_or_id)

def start(logfile=None, loglevel=None, logstdout=None):
    """Initialize and start logging facility"""
    global log_level, started

    if started or not settings.getbool('LOG_ENABLED'):
        return
    log_level = _get_log_level(loglevel)
    started = True

    # set log observer
    if log.defaultObserver: # check twisted log not already started
        logfile = logfile or settings['LOG_FILE'] or settings['LOGFILE']
        if logstdout is None:
            logstdout = settings.getbool('LOG_STDOUT')

        file = open(logfile, 'a') if logfile else sys.stderr
        log.startLogging(file, setStdout=logstdout)

def msg(message, level=INFO, component=BOT_NAME, domain=None, spider=None):
    """Log message according to the level"""
    if level > log_level:
        return
    if domain is not None:
        import warnings
        warnings.warn("'domain' argument of scrapy.log.msg() is deprecated, " \
            "use 'spider' argument instead", DeprecationWarning, stacklevel=2)
    dispatcher.send(signal=logmessage_received, message=message, level=level, \
        spider=spider)
    system = domain or (spider.domain_name if spider else component)
    msg_txt = unicode_to_str("%s: %s" % (level_names[level], message))
    log.msg(msg_txt, system=system)

def exc(message, level=ERROR, component=BOT_NAME, domain=None, spider=None):
    message = message + '\n' + format_exc()
    msg(message, level, component, domain, spider)

def err(_stuff=None, _why=None, **kwargs):
    if ERROR > log_level:
        return
    domain = kwargs.pop('domain', None)
    spider = kwargs.pop('spider', None)
    component = kwargs.pop('component', BOT_NAME)
    if domain is not None:
        import warnings
        warnings.warn("'domain' argument of scrapy.log.err() is deprecated, " \
            "use 'spider' argument instead", DeprecationWarning, stacklevel=2)
    kwargs['system'] = domain or (spider.domain_name if spider else component)
    if _why:
        _why = unicode_to_str("ERROR: %s" % _why)
    log.err(_stuff, _why, **kwargs)
