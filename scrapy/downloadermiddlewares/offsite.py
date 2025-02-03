from __future__ import annotations

import logging
import re
import warnings
from typing import TYPE_CHECKING

from scrapy import Request, Spider, signals
from scrapy.exceptions import IgnoreRequest
from scrapy.utils.httpobj import urlparse_cached

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.statscollectors import StatsCollector


logger = logging.getLogger(__name__)


class OffsiteMiddleware:
    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        assert crawler.stats
        o = cls(crawler.stats)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.request_scheduled, signal=signals.request_scheduled)
        return o

    def __init__(self, stats: StatsCollector):
        self.stats = stats
        self.domains_seen: set[str] = set()

    def spider_opened(self, spider: Spider) -> None:
        self.host_regex: re.Pattern[str] = self.get_host_regex(spider)

    def request_scheduled(self, request: Request, spider: Spider) -> None:
        self.process_request(request, spider)

    def process_request(self, request: Request, spider: Spider) -> None:
        if (
            request.dont_filter
            or request.meta.get("allow_offsite")
            or self.should_follow(request, spider)
        ):
            return
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
        raise IgnoreRequest

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
                warnings.warn(message)
            elif port_pattern.search(domain):
                message = (
                    "allowed_domains accepts only domains without ports. "
                    f"Ignoring entry {domain} in allowed_domains."
                )
                warnings.warn(message)
            else:
                domains.append(re.escape(domain))
        regex = rf"^(.*\.)?({'|'.join(domains)})$"
        return re.compile(regex)
