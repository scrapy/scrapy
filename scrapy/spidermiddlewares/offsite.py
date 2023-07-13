import logging
import re
import warnings

from scrapy import signals
from scrapy.http import Request
from scrapy.spidermiddlewares.handler.basespidermiddleware import BaseSpiderMiddleware
from scrapy.utils.httpobj import urlparse_cached

logger = logging.getLogger(__name__)


class OffsiteMiddleware(BaseSpiderMiddleware):
    _sm_component_name = "OffsiteMiddleware"

    def __init__(self, stats):
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler):
        o = cls(crawler.stats)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def handle(self, packet, spider, result):
        if isinstance(packet, Request):
            result = self.process_spider_output(packet, result, spider)

        self.get_next().handle(packet, spider, result)

    def process_spider_output(self, response, result, spider):
        return (r for r in result or () if self._filter(r, spider))

    def process_spider_input(self, request, spider, result):
        return result

    def _filter(self, request, spider):
        if not isinstance(request, Request):
            return True
        if request.dont_filter or self.should_follow(request, spider):
            return True
        domain = urlparse_cached(request).hostname
        if domain and domain not in self.domains_seen:
            self.domains_seen.add(domain)
            logger.debug(
                "Filtered offsite request to %(domain)r: %(request)s",
                {"domain": domain, "request": request},
                extra={"spider": spider},
            )
            self.stats.inc_value("offsite/domains", spider=spider)
        self.stats.inc_value("offsite/filtered", spider=spider)
        return False

    def should_follow(self, request, spider):
        regex = self.host_regex
        host = urlparse_cached(request).hostname or ""
        return bool(regex.search(host))

    def get_host_regex(self, spider):
        allowed_domains = getattr(spider, "allowed_domains", None)
        if not allowed_domains:
            return re.compile("")  # allow all by default
        url_pattern = re.compile(r"^https?://.*$")
        port_pattern = re.compile(r":\d+$")
        domains = []
        for domain in allowed_domains:
            if domain is None:
                continue
            if url_pattern.match(domain):
                message = (
                    "allowed_domains accepts only domains, not URLs. "
                    f"Ignoring URL entry {domain} in allowed_domains."
                )
                warnings.warn(message, URLWarning)
            elif port_pattern.search(domain):
                message = (
                    "allowed_domains accepts only domains without ports. "
                    f"Ignoring entry {domain} in allowed_domains."
                )
                warnings.warn(message, PortWarning)
            else:
                domains.append(re.escape(domain))
        regex = rf'^(.*\.)?({"|".join(domains)})$'
        return re.compile(regex)

    def spider_opened(self, spider):
        self.host_regex = self.get_host_regex(spider)
        self.domains_seen = set()


class URLWarning(Warning):
    pass


class PortWarning(Warning):
    pass
