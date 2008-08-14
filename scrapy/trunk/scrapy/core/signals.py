"""
Scrapy core signals
"""
from pydispatch import dispatcher

from scrapy.core import log

# After the execution engine has started
# args: None
engine_started = object()

# After the execution engine has stopped
# args: None
engine_stopped = object()

# Before opening a new domain for crawling
# args: domain, spider
domain_open = object()

# After a domain has been opened for crawling
# args: domain, spider
domain_opened = object()

# When a domain has no remaining requests to process
# args: domain, spider
domain_idle = object()

# After a domain has been closed
# args: domain, spider, status
# status is a string and its possible values are: "finished" or "cancelled"
domain_closed = object()

# domain has been initialized (successful or not)
# args: domain, spider, status
domain_initialized = object()

# New request received from spiders
# args: request, spider, response
# response is the response (fed to the spider) which generated the request
request_received = object()

# When request is sent in the downloader
# args: request, spider
request_uploaded = object()

# When new response is received (by the engine) from the downloader (middleware)
# args: response, spider
response_received = object()

# When response arrives from the downloader
# args: response, spider
response_downloaded = object()

# After item is returned from spiders
# args: item, spider, response
item_scraped = object()

# After item is processed by pipeline and pass all its stages
# args: item, spider, response, pipe_output
item_passed = object()

# After item is dropped by pipeline
# args: item, spider, response, exception
item_dropped = object()

def send_catch_log(signal, sender=None, **kwargs):
    """
    Send a signal and log any exceptions raised by its listeners
    """
    try:
        dispatcher.send(signal=signal, sender=sender, **kwargs)
    except:
        log.exc("Exception catched on signal dispatch")
