"""
Base class for Scrapy spiders

See documentation in docs/ref/spiders.rst
"""
from zope.interface import Interface, Attribute, invariant, implements
from twisted.plugin import IPlugin

from scrapy import log
from scrapy.http import Request

def _valid_domain_name(obj):
    """Check the domain name specified is valid"""
    if not obj.domain_name:
        raise ValueError("A site domain name is required")

def _valid_download_delay(obj):
    """Check the download delay is valid, if specified"""
    delay = getattr(obj, 'download_delay', 0)
    if not type(delay) in (int, long, float):
        raise ValueError("download_delay must be numeric")
    if float(delay) < 0.0:
        raise ValueError("download_delay must be positive")

class ISpider(Interface, IPlugin) :
    """Interface to be implemented by site-specific web spiders"""

    domain_name = Attribute(
         """The domain name of the site to be scraped.""")

    download_delay = Attribute(
         """Optional delay in seconds to wait between web page downloads.
         Note that this delay does not apply to image downloads.
         A delay of less than a second can be specified.""")

    user_agent = Attribute(
         """Optional User-Agent to use for this domain""")

    invariant(_valid_domain_name)
    invariant(_valid_download_delay)

    def init_domain(self):
        """This is first called to initialize domain specific quirks, like 
        session cookies or login stuff
        """
        pass


class BaseSpider(object):
    """Base class for scrapy spiders. All spiders must inherit from this
    class.
    """

    implements(ISpider)

    start_urls = []
    domain_name = None
    extra_domain_names = []

    def log(self, message, level=log.DEBUG):
        """Log the given messages at the given log level. Always use this
        method to send log messages from your spider
        """
        log.msg(message, domain=self.domain_name, level=level)

    def start_requests(self):
        return [self.make_request_from_url(url) for url in self.start_urls]

    def make_request_from_url(self, url):
        return Request(url, callback=self.parse, dont_filter=True)

    def parse(self, response):
        """This is the default callback function used to parse the start
        requests, although it can be overrided in descendant spiders.
        """
        pass
