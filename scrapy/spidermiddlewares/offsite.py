"""
Offsite Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

from __future__ import annotations

import logging
import re
import warnings
from typing import TYPE_CHECKING

from scrapy import Spider, signals
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.spidermiddlewares.base import BaseSpiderMiddleware
from scrapy.utils.httpobj import urlparse_cached

warnings.warn(
    "The scrapy.spidermiddlewares.offsite module is deprecated, use "
    "scrapy.downloadermiddlewares.offsite instead.",
    ScrapyDeprecationWarning,
)

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http import Request, Response
    from scrapy.statscollectors import StatsCollector


logger = logging.getLogger(__name__)


class OffsiteMiddleware(BaseSpiderMiddleware):
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
            # skip start requests for backward compatibility
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
        regex = self.host_regex
        # hostname can be None for wrong urls (like javascript links)
        host = urlparse_cached(request).hostname or ""
        return bool(regex.search(host))

    def get_host_regex(self, spider: Spider) -> re.Pattern[str]:
        """Override this method to implement a different offsite policy"""
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
        regex = rf"^(.*\.)?({'|'.join(domains)})$"
        return re.compile(regex)

    def spider_opened(self, spider: Spider) -> None:
        self.host_regex: re.Pattern[str] = self.get_host_regex(spider)
        self.domains_seen: set[str] = set()


class URLWarning(Warning):
    pass


class PortWarning(Warning):
    pass
