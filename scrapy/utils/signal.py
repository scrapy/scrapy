"""Helper functinos for working with signals"""

from scrapy.xlib.pydispatch import dispatcher
from scrapy.xlib.pydispatch.robust import sendRobust
from scrapy import log

def send_catch_log(*args, **kwargs):
    """Same as dispatcher.robust.sendRobust but logs any exceptions raised by
    the signal handlers
    """
    results = sendRobust(*args, **kwargs)
    for receiver, response in results:
        if isinstance(response, Exception):
            log.msg("Exception caught on signal dispatch: receiver=%r, " \
                " exception=%r" % (receiver, response), level=log.ERROR)
    return results
