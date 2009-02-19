from pydispatch import dispatcher

from scrapy.core import signals
from scrapy.http import Request
from scrapy.core.exceptions import NotConfigured, IgnoreRequest
from scrapy.utils.request import request_fingerprint
from scrapy.utils.misc import load_object
from scrapy.conf import settings
from scrapy import log


class BaseFilter(dict):
    """Base class defining the duplicates requests filtering api"""

    def __init__(self, *args, **kwargs):
        super(BaseFilter, self).__init__(*args, **kwargs)
        dispatcher.connect(self.open, signals.domain_open)
        dispatcher.connect(self.close, signals.domain_closed)

    def open(self, domain):
        """Called when a domain starts"""
        raise NotImplementedError()

    def close(self, domain):
        """Called when a domain is closed"""
        raise NotImplementedError()

    def add(self, domain, request):
        """Called to check if a request was already seen, and adds it to seen set.

        returns True if not seen before, or False otherwise.
        """
        raise NotImplementedError()

    def has(self, domain, request):
        """Called to check if a request was seen but doesnt add request to seen set."""
        raise NotImplementedError()


class SimplePerDomainFilter(BaseFilter):
    """Filter out a request if already seen for same domain"""

    def open(self, domain):
        """Initialize the resources needed for filtering for this domain"""
        self[domain] = set()

    def close(self, domain):
        """Remove the resources reserved for filtering for this domain"""
        del self[domain]

    def add(self, domain, request):
        """Add the fingerprint of a request to the domain set if a equivalent fingerprint has not been added.
        This method will return true if the fingerprint was added and false otherwise.
        """
        fp = request_fingerprint(request)
        if fp not in self[domain]:
            self[domain].add(fp)
            return True
        return False

    def has(self, domain, request):
        fp = request_fingerprint(request)
        return fp in self[domain]


class NullFilter(dict):
    def open(self, domain):
        pass

    def close(self, domain):
        pass

    def add(self, domain, request):
        return True

    def has(self, domain, request):
        return None


try:
    duplicatesfilter
except NameError:
    clspath = settings.get('DUPLICATESFILTER_FILTERCLASS')
    cls = load_object(clspath) if clspath else NullFilter
    duplicatesfilter = cls()

