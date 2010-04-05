"""
Base class for Scrapy spiders

See documentation in docs/topics/spiders.rst
"""

import warnings

from zope.interface import Interface, Attribute, invariant, implements
from twisted.plugin import IPlugin

from scrapy import log
from scrapy.http import Request
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.trackref import object_ref

class ISpider(Interface, IPlugin) :
    """Interface used by TwistedPluginSpiderManager to discover spiders"""
    pass

class BaseSpider(object_ref):
    """Base class for scrapy spiders. All spiders must inherit from this
    class.
    """

    implements(ISpider)

    # XXX: class attributes kept for backwards compatibility
    name = None
    start_urls = []
    allowed_domains = []

    def __init__(self, name=None, **kwargs):
        self.__dict__.update(kwargs)
        # XXX: SEP-12 backward compatibility (remove for 0.10)
        if hasattr(self, 'domain_name'):
            warnings.warn("Spider.domain_name attribute is deprecated, use Spider.name instead and Spider.allowed_domains", \
                DeprecationWarning, stacklevel=4)
            self.name = self.domain_name
            self.allowed_domains = [self.name]
            if hasattr(self, 'extra_domain_names'):
                warnings.warn("Spider.extra_domain_names attribute is deprecated - user Spider.allowed_domains instead", \
                    DeprecationWarning, stacklevel=4)
                self.allowed_domains += list(self.extra_domain_names)

        if name is not None:
            self.name = name
        # XXX: create instance attributes (class attributes were kept for
        # backwards compatibility)
        if not self.start_urls:
            self.start_urls = []
        if not self.allowed_domains:
            self.allowed_domains = []
        if not self.name:
            raise ValueError("%s must have a name" % type(self).__name__)

        # XXX: SEP-12 forward compatibility (remove for 0.10)
        self.domain_name = self.name
        self.extra_domain_names = self.allowed_domains

    def log(self, message, level=log.DEBUG):
        """Log the given messages at the given log level. Always use this
        method to send log messages from your spider
        """
        log.msg(message, spider=self, level=level)

    def start_requests(self):
        reqs = []
        for url in self.start_urls:
            reqs.extend(arg_to_iter(self.make_requests_from_url(url)))
        return reqs

    def make_requests_from_url(self, url):
        return Request(url, callback=self.parse, dont_filter=True)

    def parse(self, response):
        """This is the default callback function used to parse the start
        requests, although it can be overrided in descendant spiders.
        """
        pass

    def __str__(self):
        return "<%s %r>" % (type(self).__name__, self.name)

    __repr__ = __str__
