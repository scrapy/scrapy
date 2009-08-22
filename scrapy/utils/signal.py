"""Helper functinos for working with signals"""

from scrapy.xlib.pydispatch import dispatcher
from scrapy.xlib.pydispatch.robust import sendRobust
from scrapy import log

def send_catch_log(*args, **kwargs):
    """Same as dispatcher.robust.sendRobust but logs any exceptions raised by
    the signal handlers
    """
    for receiver, result in sendRobust(*args, **kwargs):
        if isinstance(result, Exception):
            log.msg("Exception caught on signal dispatch: receiver=%r, " \
                " exception=%r" % (receiver, result), level=log.ERROR)
