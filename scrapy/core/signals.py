"""
Scrapy core signals

These signals are documented in docs/ref/signals.rst. Please don't add new
signals here without documenting them there.
"""

from pydispatch import dispatcher

from scrapy import log

engine_started = object()
engine_stopped = object()
domain_open = object()
domain_opened = object()
domain_idle = object()
domain_closed = object()
request_received = object()
request_uploaded = object()
response_received = object()
response_downloaded = object()
item_scraped = object()
item_passed = object()
item_dropped = object()

def send_catch_log(signal, sender=None, **kwargs):
    """
    Send a signal and log any exceptions raised by its listeners
    """
    try:
        dispatcher.send(signal=signal, sender=sender, **kwargs)
    except:
        log.exc("Exception catched on signal dispatch")
