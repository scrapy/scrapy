"""
Offsite Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""
import re
import logging
import warnings

from scrapy import signals
from scrapy.http import Request
from scrapy.utils.httpobj import urlparse_cached

logger = logging.getLogger(__name__)


class OffsiteMiddleware(object):
    """Filters out Requests for URLs outside the domains covered by the spider.

   This middleware filters out every request whose host names aren't in the
   spider's :attr:`~scrapy.spiders.Spider.allowed_domains` attribute.
   All subdomains of any domain in the list are also allowed.
   E.g. the rule ``www.example.org`` will also allow ``bob.www.example.org``
   but not ``www2.example.com`` nor ``example.com``.

   When your spider returns a request for a domain not belonging to those
   covered by the spider, this middleware will log a debug message similar to
   this one::

      DEBUG: Filtered offsite request to 'www.othersite.com': <GET http://www.othersite.com/some/page.html>

   To avoid filling the log with too much noise, it will only print one of
   these messages for each new domain filtered. So, for example, if another
   request for ``www.othersite.com`` is filtered, no log message will be
   printed. But if a request for ``someothersite.com`` is filtered, a message
   will be printed (but only for the first request filtered).

   If the spider doesn't define an
   :attr:`~scrapy.spiders.Spider.allowed_domains` attribute, or the
   attribute is empty, the offsite middleware will allow all requests.

   If the request has the :attr:`~scrapy.http.Request.dont_filter` attribute
   set, the offsite middleware will allow the request even if its domain is not
   listed in allowed domains.
   """

    def __init__(self, stats):
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler):
        o = cls(crawler.stats)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def process_spider_output(self, response, result, spider):
        for x in result:
            if isinstance(x, Request):
                if x.dont_filter or self.should_follow(x, spider):
                    yield x
                else:
                    domain = urlparse_cached(x).hostname
                    if domain and domain not in self.domains_seen:
                        self.domains_seen.add(domain)
                        logger.debug(
                            "Filtered offsite request to %(domain)r: %(request)s",
                            {'domain': domain, 'request': x}, extra={'spider': spider})
                        self.stats.inc_value('offsite/domains', spider=spider)
                    self.stats.inc_value('offsite/filtered', spider=spider)
            else:
                yield x

    def should_follow(self, request, spider):
        regex = self.host_regex
        # hostname can be None for wrong urls (like javascript links)
        host = urlparse_cached(request).hostname or ''
        return bool(regex.search(host))

    def get_host_regex(self, spider):
        """Override this method to implement a different offsite policy"""
        allowed_domains = getattr(spider, 'allowed_domains', None)
        if not allowed_domains:
            return re.compile('')  # allow all by default
        url_pattern = re.compile("^https?://.*$")
        for domain in allowed_domains:
            if url_pattern.match(domain):
                message = ("allowed_domains accepts only domains, not URLs. "
                           "Ignoring URL entry %s in allowed_domains." % domain)
                warnings.warn(message, URLWarning)
        domains = [re.escape(d) for d in allowed_domains if d is not None]
        regex = r'^(.*\.)?(%s)$' % '|'.join(domains)
        return re.compile(regex)

    def spider_opened(self, spider):
        self.host_regex = self.get_host_regex(spider)
        self.domains_seen = set()


class URLWarning(Warning):
    pass
