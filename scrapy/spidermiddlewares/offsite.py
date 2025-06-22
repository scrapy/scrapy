"""
Offsite Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

from __future__ import annotations

import logging
import re
import warnings
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from scrapy import Spider, signals
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.downloadermiddlewares.offsite import OffsiteMiddleware
from scrapy.utils.httpobj import urlparse_cached
from scrapy.spidermiddlewares.base import BaseSpiderMiddleware

warnings.warn(
    "The scrapy.spidermiddlewares.offsite module is deprecated, use "
    "scrapy.downloadermiddlewares.offsite instead.",
    ScrapyDeprecationWarning,
)

if TYPE_CHECKING:
    from typing_extensions import Self
    from scrapy.crawler import Crawler
    from scrapy.http import Request, Response
    from scrapy.statscollectors import StatsCollector

logger = logging.getLogger(__name__)

def parse_allowed_domains(domains):
    """Parse allowed_domains into a list of (scheme, host, port) or just host."""
    parsed = []
    for domain in domains:
        if not domain:
            continue
        if "://" in domain:
            u = urlparse(domain)
            if u.hostname:
                parsed.append((u.scheme, u.hostname, u.port or (443 if u.scheme == "https" else 80)))
        else:
            parsed.append((None, domain, None))
    return parsed

def is_url_allowed(url, allowed_domains):
    """Check if a URL is allowed based on allowed_domains (RFC 6454)."""
    u = urlparse(url)
    scheme = u.scheme
    host = u.hostname
    port = u.port or (443 if scheme == "https" else 80)
    for entry in allowed_domains:
        if entry[0] is not None:
            # Full origin: scheme, host, port must match
            if (scheme, host, port) == entry:
                return True
        else:
            # Plain domain: host must match exactly (no subdomains)
            if host == entry[1]:
                return True
    return False

def get_host_regex(domains):
    """Legacy: Return a regex that matches allowed domains and their subdomains."""
    regexes = []
    for domain in domains:
        if not domain:
            continue
        if "://" in domain:
            u = urlparse(domain)
            if u.hostname:
                # Only match the exact host for full origins
                regexes.append(rf"^{re.escape(u.hostname)}$")
        else:
            # Match domain and subdomains
            regexes.append(rf"(^|\.){re.escape(domain)}$")
    if not regexes:
        return re.compile(r".*")
    return re.compile("|".join(regexes), re.IGNORECASE)

class OffsiteMiddleware(BaseSpiderMiddleware):
    """Filter out requests to URLs outside the domains specified by 
    the allowed_domains attribute of the spider.

    allowed_domains can include:
    - Full origins (e.g., "https://example.com", "http://example.com:8080")
    - Plain domains (e.g., "example.com") for backward compatibility (matches only the exact domain)
    Subdomains are not matched unless explicitly listed.
    """
    crawler: Crawler

    def __init__(self, stats: StatsCollector):  # pylint: disable=super-init-not-called
        self.stats: StatsCollector = stats

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        assert crawler.stats
        o = cls(crawler.stats)
        o.crawler = crawler
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def get_processed_request(
        self, request: Request, response: Response | None
    ) -> Request | None:
        if response is None:
            return request
        assert self.crawler.spider
        if (
            request.dont_filter
            or request.meta.get("allow_offsite")
            or self.should_follow(request, self.crawler.spider)
        ):
            return request
        domain = urlparse_cached(request).hostname
        if domain and domain not in self.domains_seen:
            self.domains_seen.add(domain)
            logger.debug(
                "Filtered offsite request to %(domain)r: %(request)s",
                {"domain": domain, "request": request},
                extra={"spider": self.crawler.spider},
            )
            self.stats.inc_value("offsite/domains", spider=self.crawler.spider)
        self.stats.inc_value("offsite/filtered", spider=self.crawler.spider)
        return None

    def should_follow(self, request: Request, spider: Spider) -> bool:
        allowed_domains = getattr(spider, "_allowed_domains", None)
        if allowed_domains is None:
            allowed_domains = parse_allowed_domains(getattr(spider, "allowed_domains", []) or [])
            setattr(spider, "_allowed_domains", allowed_domains)
        return is_url_allowed(request.url, allowed_domains)

    def get_host_regex(self, spider):
        """Legacy: Used by some tests and extensions."""
        return get_host_regex(getattr(spider, "allowed_domains", []) or [])

    def spider_opened(self, spider: Spider) -> None:
        self.domains_seen: set[str] = set()

class URLWarning(Warning):
    pass

class PortWarning(Warning):
    pass