"""Request Processors"""
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.url import canonicalize_url, url_is_from_any_domain

from itertools import ifilter

import re

class Canonicalize(object):
    """Canonicalize Request Processor"""

    def __call__(self, requests):
        """Canonicalize all requests' urls"""
        return (x.replace(url=canonicalize_url(x.url)) for x in requests)
        

class FilterDupes(object):
    """Filter duplicate Requests"""

    def __init__(self, *attributes):
        """Initialize comparison attributes"""
        self._attributes = tuple(attributes) if attributes \
                                             else tuple(['url'])

    def _equal_attr(self, obj1, obj2, attr):
        return getattr(obj1, attr) == getattr(obj2, attr)

    def _requests_equal(self, req1, req2):
        """Attribute comparison helper"""
        # look for not equal attribute
        _not_equal = lambda attr: not self._equal_attr(req1, req2, attr)
        for attr in ifilter(_not_equal, self._attributes):
            return False
        # all attributes equal
        return True

    def _request_in(self, request, requests_seen):
        """Check if request is in given requests seen list"""
        _req_seen = lambda r: self._requests_equal(r, request)
        for seen in ifilter(_req_seen, requests_seen):
            return True
        # request not seen
        return False

    def __call__(self, requests):
        """Filter seen requests"""
        # per-call duplicates filter
        self.requests_seen = set()
        _not_seen = lambda r: not self._request_in(r, self.requests_seen)
        for req in ifilter(_not_seen, requests):
            yield req
            # registry seen request
            self.requests_seen.add(req)


class FilterDomain(object):
    """Filter request's domain"""

    def __init__(self, allow=(), deny=()):
         """Initialize allow/deny attributes"""
         self.allow = tuple(arg_to_iter(allow))
         self.deny = tuple(arg_to_iter(deny))

    def __call__(self, requests):
        """Filter domains"""
        processed = (req for req in requests)

        if self.allow:
            processed = (req for req in requests
                            if url_is_from_any_domain(req.url, self.allow))
        if self.deny:
            processed = (req for req in requests
                            if not url_is_from_any_domain(req.url, self.deny))

        return processed


class FilterUrl(object):
    """Filter request's url"""

    def __init__(self, allow=(), deny=()):
        """Initialize allow/deny attributes"""
        _re_type = type(re.compile('', 0))

        self.allow_res = [x if isinstance(x, _re_type) else re.compile(x) 
                          for x in arg_to_iter(allow)]
        self.deny_res = [x if isinstance(x, _re_type) else re.compile(x) 
                         for x in arg_to_iter(deny)]

    def __call__(self, requests):
        """Filter request's url based on allow/deny rules"""
        #TODO: filter valid urls here?
        processed = (req for req in requests)

        if self.allow_res:
            processed = (req for req in requests
                            if self._matches(req.url, self.allow_res))
        if self.deny_res:
            processed = (req for req in requests
                            if not self._matches(req.url, self.deny_res))

        return processed

    def _matches(self, url, regexs):
        """Returns True if url matches any regex in given list"""
        return any(r.search(url) for r in regexs)

