"""
Crawler class

The Crawler class can be used to crawl pages using the Scrapy crawler from
outside a Scrapy project, for example, from a standalone script. 

To use it, instantiate it and call the "crawl" method with one (or more)
requests. For example:

    >>> from scrapy.crawler import Crawler
    >>> from scrapy.http import Request
    >>> def parse_response(response):
    ...     print "Visited: %s" % response.url
    ...
    >>> request = Request('http://scrapy.org', callback=parse_response)
    >>> crawler = Crawler()
    >>> crawler.crawl(request)
    Visited http://scrapy.org 
    >>>

Request callbacks follow the same API of spiders callback, which means that all
requests returned from the callbacks will be followed.

See examples/scripts/count_and_follow_links.py for a more detailed example.

WARNING: The Crawler class currently has a big limitation - it cannot be used
more than once in the same Python process. This is due to the fact that Twisted
reactors cannot be restarted. Hopefully, this limitation will be removed in the
future.
"""

from scrapy.xlib.pydispatch import dispatcher
from scrapy.core.manager import scrapymanager
from scrapy.core.engine import scrapyengine
from scrapy.conf import settings as scrapy_settings
from scrapy import log

class Crawler(object):

    def __init__(self, enable_log=False, stop_on_error=False, silence_errors=False, \
            settings=None):
        self.stop_on_error = stop_on_error
        self.silence_errors = silence_errors
        # disable offsite middleware (by default) because it prevents free crawling
        if settings is not None:
            settings.overrides.update(settings)
        scrapy_settings.overrides['SPIDER_MIDDLEWARES'] = {
            'scrapy.contrib.spidermiddleware.offsite.OffsiteMiddleware': None}
        scrapy_settings.overrides['LOG_ENABLED'] = enable_log
        scrapymanager.configure()
        dispatcher.connect(self._logmessage_received, signal=log.logmessage_received)

    def crawl(self, *args):
        scrapymanager.runonce(*args)

    def stop(self):
        scrapyengine.stop()
        log.log_level = log.SILENT
        scrapyengine.kill()

    def _logmessage_received(self, message, level):
        if level <= log.ERROR:
            if not self.silence_errors:
                print "Crawler error: %s" % message
            if self.stop_on_error:
                self.stop()
