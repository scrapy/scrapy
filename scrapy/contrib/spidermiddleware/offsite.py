"""
Offsite Spider Middleware

See documentation in docs/ref/spider-middleware.rst
"""

import re

from scrapy.xlib.pydispatch import dispatcher
from scrapy.core import signals
from scrapy.http import Request
from scrapy.utils.httpobj import urlparse_cached

class OffsiteMiddleware(object):

    def __init__(self):
        self.host_regexes = {}
        dispatcher.connect(self.domain_opened, signal=signals.domain_opened)
        dispatcher.connect(self.domain_closed, signal=signals.domain_closed)

    def process_spider_output(self, response, result, spider):
        return (x for x in result if not isinstance(x, Request) or \
            self.should_follow(x, spider))

    def should_follow(self, request, spider):
        regex = self.host_regexes[spider]
        # hostanme can be None for wrong urls (like javascript links)
        host = urlparse_cached(request).hostname or ''
        return bool(regex.search(host))

    def get_host_regex(self, domains):
        """Override this method to implement a different offsite policy"""
        domains = [d.replace('.', r'\.') for d in domains]
        regex = r'^(|.*\.)(%s)$' % '|'.join(domains)
        return re.compile(regex)

    def domain_opened(self, spider):
        domains = [spider.domain_name] + spider.extra_domain_names
        self.host_regexes[spider] = self.get_host_regex(domains)

    def domain_closed(self, spider):
        del self.host_regexes[spider]
