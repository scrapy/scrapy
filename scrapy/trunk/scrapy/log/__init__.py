""" 
Crawler logging functionality
"""
import sys

from twisted.python import log

from scrapy.conf import settings
 
# Logging levels
levels = {
    0: "SILENT",
    1: "CRITICAL",
    2: "ERROR",
    3: "WARNING",
    4: "INFO",
    5: "DEBUG",
    6: "TRACE",
}

BOT_NAME = settings['BOT_NAME']

# Set logging level module attributes
for v, k in levels.items():
    setattr(sys.modules[__name__], k, v)

# default logging level
log_level = DEBUG

started = False

def start(logfile=None, loglevel=None, log_stdout=None):
    """ Init logging """
    if started or not settings.getbool('LOG_ENABLED'):
        return

    logfile = logfile or settings['LOGFILE']
    loglevel = loglevel or settings['LOGLEVEL']
    log_stdout = log_stdout or settings.getbool('LOG_STDOUT')

    file = open(logfile, 'a') if logfile else sys.stderr
    level = int(getattr(sys.modules[__name__], loglevel)) if loglevel else DEBUG
    log.startLogging(file, setStdout=log_stdout)
    setattr(sys.modules[__name__], 'log_level', level)
    setattr(sys.modules[__name__], 'started', True)

def msg(message, level=INFO, component=BOT_NAME, domain=None):
    """ Log message according to the level """
    component = "%s/%s" % (BOT_NAME, domain) if domain else component
    if level <= log_level:
        log.msg("%s: %s" % (levels[level], message), system=component)

def exc(message, level=ERROR, component=BOT_NAME, domain=None):
    from traceback import format_exc
    message = message + '\n' + format_exc()
    msg(message, level, component, domain)

err = log.err
