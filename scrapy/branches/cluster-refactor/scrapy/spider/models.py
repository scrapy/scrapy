"""
Base class for scrapy spiders
"""
from zope.interface import Interface, Attribute, invariant, implements
from twisted.plugin import IPlugin

from scrapy.core.exceptions import UsageError

def _valid_start_urls(obj):
    """Check the start urls specified are valid"""
    if not obj.start_urls:
        raise UsageError("A start url is required")

def _valid_domain_name(obj):
    """Check the domain name specified is valid"""
    if not obj.domain_name:
        raise UsageError("A site domain name is required")

def _valid_download_delay(obj):
    """Check the download delay is valid, if specified"""
    delay = getattr(obj, 'download_delay', 0)
    if not type(delay) in (int, long, float):
        raise UsageError("download_delay must be numeric")
    if float(delay) < 0.0:
        raise UsageError("download_delay must be positive")

class ISpider(Interface, IPlugin) :
    """Interface to be implemented by site-specific web spiders"""
    
    start_urls = Attribute(
        """A sequence of URLs to retrieve to initiate the spider for this 
        site. A single URL may also be provided here.""")
    
    domain_name = Attribute(
         """The domain name of the site to be scraped.""")

    download_delay = Attribute(
         """Optional delay in seconds to wait between web page downloads.
         Note that this delay does not apply to image downloads.
         A delay of less than a second can be specified.""")

    user_agent = Attribute(
         """Optional User-Agent to use for this domain""")

    invariant(_valid_start_urls)
    invariant(_valid_domain_name)
    invariant(_valid_download_delay)

    def parse(self, pagedata) :
        """This is first called with the data corresponding to start_url. It
        must return a (possibly empty) sequence where each element is either:
         * A Request object for further processing.
         * An object that extends ScrapedItem (defined in scrapeditem module)
         * or None (this will be ignored)

        When a Request object is returned, the Request is scheduled, then
        downloaded and finally its results is handled to the Request callback.
        That callback must behave the same way as this function.

        When a ScrapedItem is returned, it is passed to the transformation pipeline
        and finally the destination systems are updated.

        The simplest way to use this is to have a method in your class for each
        page type. So each function knows the layout and how to extract data
        for a single page (or set of similar pages). A typical class might work
        like:
        * parse() parses the landing page and returns Requests
          for a category() function to parse category pages.
        * category() parses the category pages and returns links and callbacks
          for a item() function to parse item pages.
        * item() parses the item details page and returns objects that
          extend ScrapedItem
        """
        pass

    def init_domain(self):
        """This is first called to initialize domain specific quirks, like 
        session cookies or login stuff
        """
        pass


class BaseSpider(object):
    """Base class for scrapy spiders. All spiders must inherit from this
    class."""

    implements(ISpider)
    domain_name = None
    extra_domain_names = []
