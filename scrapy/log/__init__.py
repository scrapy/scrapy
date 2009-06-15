""" 
Scrapy logging facility

See documentation in docs/ref/logging.rst
"""
import sys
from traceback import format_exc

from twisted.python import log

from scrapy.conf import settings
from scrapy.utils.python import unicode_to_str
 
# Logging levels
SILENT, CRITICAL, ERROR, WARNING, INFO, DEBUG, TRACE = range(7)
level_names = {
    0: "SILENT",
    1: "CRITICAL",
    2: "ERROR",
    3: "WARNING",
    4: "INFO",
    5: "DEBUG",
    6: "TRACE",
}

BOT_NAME = settings['BOT_NAME']

# default logging level
log_level = DEBUG

started = False

def start(logfile=None, loglevel=None, log_stdout=None):
    """Initialize and start logging facility"""
    global log_level, started

    # set loglevel
    loglevel = loglevel or settings['LOGLEVEL']
    log_level = globals()[loglevel] if loglevel else DEBUG
    if started or not settings.getbool('LOG_ENABLED'):
        return
    started = True

    # set log observer
    if log.defaultObserver: # check twisted log not already started
        logfile = logfile or settings['LOGFILE']
        log_stdout = log_stdout or settings.getbool('LOG_STDOUT')

        file = open(logfile, 'a') if logfile else sys.stderr
        log.startLogging(file, setStdout=log_stdout)

def msg(message, level=INFO, component=BOT_NAME, domain=None):
    """Log message according to the level"""
    component = "%s/%s" % (component, domain) if domain else component
    if level <= log_level:
        msg_txt = unicode_to_str("%s: %s" % (level_names[level], message))
        log.msg(msg_txt, system=component)

def exc(message, level=ERROR, component=BOT_NAME, domain=None):
    message = message + '\n' + format_exc()
    msg(message, level, component, domain)

def err(*args, **kwargs):
    domain = kwargs.pop('domain', None)
    component = kwargs.pop('component', BOT_NAME)
    kwargs['system'] = "%s/%s" % (component, domain) if domain else component
    log.err(*args, **kwargs)
