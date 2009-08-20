"""Helper functinos for working with signals"""

from scrapy.xlib.pydispatch import dispatcher
from scrapy import log

def send_catch_log(*args, **kwargs):
    """Same as dispatcher.send but logs any exceptions raised by the signal
    handlers
    """
    try:
        dispatcher.send(*args, **kwargs)
    except:
        log.exc("Exception catched on signal dispatch")
