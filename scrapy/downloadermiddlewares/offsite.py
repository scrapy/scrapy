from __future__ import annotations

import logging
import re
import warnings
from typing import TYPE_CHECKING

from scrapy import Request, Spider, signals
from scrapy.exceptions import IgnoreRequest
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.httpobj import urlparse_cached

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.statscollectors import StatsCollector


logger = logging.getLogger(__name__)


class OffsiteMiddleware:
    crawler: Crawler

    def __init__(self, stats: StatsCollector):
        self.stats = stats
        self.domains_seen: set[str] = set()

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        assert crawler.stats
        o = cls(crawler.stats)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.request_scheduled, signal=signals.request_scheduled)
        o.crawler = crawler
        return o

    def spider_opened(self, spider: Spider) -> None:
        self.host_regex: re.Pattern[str] = self.get_host_regex(spider)
        self.disallowed_host_regex: re.Pattern[str] | None = (
            self._get_disallowed_host_regex(spider)
        )

    def request_scheduled(self, request: Request, spider: Spider) -> None:
        self.process_request(request)

    @_warn_spider_arg
    def process_request(self, request: Request, spider: Spider | None = None) -> None:
        assert self.crawler.spider
        if (
            request.dont_filter
            or request.meta.get("allow_offsite")
            or self.should_follow(request, self.crawler.spider)
        ):
            return
        domain = urlparse_cached(request).hostname
        if domain and domain not in self.domains_seen:
            self.domains_seen.add(domain)
            logger.debug(
                "Filtered offsite request to %(domain)r: %(request)s",
                {"domain": domain, "request": request},
                extra={"spider": self.crawler.spider},
            )
            self.stats.inc_value("offsite/domains")
        self.stats.inc_value("offsite/filtered")
        raise IgnoreRequest

    def should_follow(self, request: Request, spider: Spider) -> bool:
        # hostname can be None for wrong urls (like javascript links)
        host = urlparse_cached(request).hostname or ""
        # If the host matches a disallowed domain, we can reject it
        if self.disallowed_host_regex and self.disallowed_host_regex.search(host):
            return False
        # Otherwise, check allowed domains
        return bool(self.host_regex.search(host))

    @staticmethod
    def _process_domains(
        domains_list: list[str | None], domains_type: str
    ) -> list[str]:
        """Process a domains list and return a list of valid, regex-escaped domains.

        Entries that are URLs or contain ports are warned about and skipped.
        """
        url_pattern = re.compile(r"^https?://.*$")
        port_pattern = re.compile(r":\d+$")
        valid_domains: list[str] = []

        for domain in domains_list:
            if domain is None:
                continue
            if url_pattern.match(domain):
                message = (
                    f"{domains_type} accepts only domains, not URLs. "
                    f"Ignoring URL entry {domain} in {domains_type}."
                )
                warnings.warn(message)
            elif port_pattern.search(domain):
                message = (
                    f"{domains_type} accepts only domains without ports. "
                    f"Ignoring entry {domain} in {domains_type}."
                )
                warnings.warn(message)
            else:
                valid_domains.append(re.escape(domain))
        return valid_domains

    def get_host_regex(self, spider: Spider) -> re.Pattern[str]:
        """Override this method to implement a different offsite policy.

        Returns a compiled regular expression object that matches the hosts
        that are allowed to be crawled.
        """
        allowed_domains = getattr(spider, "allowed_domains", None)
        if not allowed_domains:
            return re.compile("")  # allow all by default

        domains = self._process_domains(allowed_domains, "allowed_domains")
        if domains:
            return re.compile(rf"^(.*\.)?({'|'.join(domains)})$")
        return re.compile("")  # allow all if no valid domains remain

    def _get_disallowed_host_regex(self, spider: Spider) -> re.Pattern[str] | None:
        """Build a regex that positively matches disallowed hosts.

        Returns ``None`` when there are no disallowed domains, meaning
        nothing should be blocked via this mechanism.
        """
        disallowed_domains = getattr(spider, "disallowed_domains", None)
        if not disallowed_domains:
            return None

        domains = self._process_domains(disallowed_domains, "disallowed_domains")
        if domains:
            return re.compile(rf"^(.*\.)?({'|'.join(domains)})$")
        return None
