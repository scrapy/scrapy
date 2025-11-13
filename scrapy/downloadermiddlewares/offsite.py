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
        regex = self.host_regex
        # hostname can be None for wrong urls (like javascript links)
        host = urlparse_cached(request).hostname or ""
        return bool(regex.search(host))

    def get_host_regex(self, spider: Spider) -> re.Pattern[str]:
        """Override this method to implement a different offsite policy.
        Returns a compiled regular expression object that matches the hosts that
        are allowed to be crawled. If None is returned (or method is not overridden),
        all hosts are allowed.
        Example:
        allowed_domains = ['example.com']
        disallowed_domains = ['example2.com']
        This will allow crawling all subdomains of example.com (eg. foo.example.com,
        bar.example.com). But it won't allow crawling example2.com or any subdomain
        (eg. www.example2.com).
        """
        allowed_domains_arg = getattr(spider, "allowed_domains", None)
        disallowed_domains_arg = getattr(spider, "disallowed_domains", None)
        allowed_domains = []
        disallowed_domains = []
        if not allowed_domains_arg and not disallowed_domains_arg:
            return re.compile("")  # allow all by default

        url_pattern = re.compile(r"^https?://.*$")
        port_pattern = re.compile(r":\d+$")
        # domains = []

        def process_domains(domains_list=[], domains_type="allowed_domains"):
            """
            Process the domains list and return a list of valid domains.
            The arguments passed to the spider in allowed_domains and disallowed_domains
            cannot be URLs or contain ports.
            """
            valid_domains = []

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

        if allowed_domains_arg:
            allowed_domains = process_domains(allowed_domains_arg, "allowed_domains")

        if disallowed_domains_arg:
            disallowed_domains = process_domains(
                disallowed_domains_arg, "disallowed_domains"
            )

        if allowed_domains:
            allowed_domain_pattern = rf"^(.*\.)?({'|'.join(allowed_domains)})$"
        else:
            allowed_domain_pattern = ""

        if disallowed_domains:
            disallowed_domain_pattern = rf"^(?!.*(?:{'|'.join(disallowed_domains)}))$"
        else:
            disallowed_domain_pattern = ""

        if allowed_domain_pattern and disallowed_domain_pattern:
            combined_pattern = rf"{allowed_domain_pattern}|{disallowed_domain_pattern}"
        else:
            combined_pattern = allowed_domain_pattern or disallowed_domain_pattern
        return re.compile(combined_pattern)
