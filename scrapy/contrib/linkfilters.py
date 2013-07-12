import re
from urlparse import urlparse

from scrapy.linkextractor import IGNORED_EXTENSIONS
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.url import canonicalize_url, url_is_from_any_domain, \
        url_has_any_extension


class Canonicalize(object):

    def __call__(self, values):
        for value in arg_to_iter(values):
            yield canonicalize_url(value)


_re_type = type(re.compile('', 0))
_matches = lambda url, regexs: any((r.search(url) for r in regexs))


class Allow(object):

    def __init__(self, allow):
        self.allow = [x if isinstance(x, _re_type) else re.compile(x)
                for x in arg_to_iter(allow)]

    def __call__(self, values):
        for value in arg_to_iter(values):
            if _matches(value, self.allow):
                yield value


class Disallow(object):

    def __init__(self, disallow):
        self.disallow = [x if isinstance(x, _re_type) else re.compile(x)
                for x in arg_to_iter(disallow)]

    def __call__(self, values):
        for value in arg_to_iter(values):
            if not _matches(value, self.disallow):
                yield value


class AllowDomains(object):

    def __init__(self, allow_domains):
        self.allow_domains = set(arg_to_iter(allow_domains))

    def __call__(self, values):
        for value in arg_to_iter(values):
            parsed_url = urlparse(value)
            if url_is_from_any_domain(parsed_url, self.allow_domains):
                yield value


class DisallowDomains(object):

    def __init__(self, disallow_domains):
        self.disallow_domains = set(arg_to_iter(disallow_domains))

    def __call__(self, values):
        for value in arg_to_iter(values):
            parsed_url = urlparse(value)
            if not url_is_from_any_domain(parsed_url, self.disallow_domains):
                yield value


class Unique(object):

    def __init__(self):
        self.value_seen = set()

    def __call__(self, values):
        for value in arg_to_iter(values):
            if value not in self.value_seen:
                self.value_seen.add(value)
                yield value


class DenyExtensions(object):

    def __init__(self, extensions=IGNORED_EXTENSIONS):
        self.extensions = extensions

    def __call__(self, values):
        for value in arg_to_iter(values):
            parsed_url = urlparse(value)
            if not url_has_any_extension(parsed_url, self.extensions):
                yield value
