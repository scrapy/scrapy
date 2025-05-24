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
        allowed_domains_arg = getattr(spider, "allowed_domains", [])
        disallowed_domains_arg = getattr(spider, "disallowed_domains", [])
        # Filtered domains to be added to the regex pattern
        allowed_domains = []
        disallowed_domains = []

        url_pattern = re.compile(r"^https?://.*$")  # match http://example.com
        port_pattern = re.compile(r":\d+$")  # match :8080

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
                    warnings.warn(message, URLWarning)
                elif port_pattern.search(domain):
                    message = (
                        f"{domains_type} accepts only domains without ports. "
                        f"Ignoring entry {domain} in {domains_type}."
                    )
                    warnings.warn(message, PortWarning)
                else:
                    valid_domains.append(re.escape(domain))
            return valid_domains

        if allowed_domains_arg:
            allowed_domains = process_domains(allowed_domains_arg, "allowed_domains")

        if disallowed_domains_arg:
            disallowed_domains = process_domains(
                disallowed_domains_arg, "disallowed_domains"
            )

        #  match domains in the `allowed_domains` list
        if allowed_domains:
            allowed_domain_pattern = rf"^(.*\.)?({'|'.join(allowed_domains)})$"
        else:
            allowed_domain_pattern = ""

        # exclude domains in the `disallowed_domains` list
        if disallowed_domains:
            disallowed_domain_pattern = rf"^(?!.*(?:{'|'.join(disallowed_domains)}))$"
        else:
            disallowed_domain_pattern = ""

        # Concatenate the two patterns with the "|" (or) operator
        if allowed_domain_pattern and disallowed_domain_pattern:
            combined_pattern = rf"{allowed_domain_pattern}|{disallowed_domain_pattern}"
        else:
            combined_pattern = allowed_domain_pattern or disallowed_domain_pattern

        return re.compile(combined_pattern)

    def spider_opened(self, spider: Spider) -> None:
        self.host_regex: re.Pattern[str] = self.get_host_regex(spider)
        self.domains_seen: set[str] = set()


class URLWarning(Warning):
    pass


class PortWarning(Warning):
    pass
