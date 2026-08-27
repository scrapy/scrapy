from __future__ import annotations

import logging
import re
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
    """Filter out requests for URLs outside the domains covered by the spider.

    .. versionadded:: 2.11.2

    A request is allowed if its host name is in the
    :attr:`~scrapy.Spider.allowed_domains` attribute of the spider, or is a
    subdomain of one of those domains. E.g. ``www.example.org`` also allows
    ``bob.www.example.org``, but neither ``www2.example.org`` nor
    ``example.org``. See :meth:`should_follow` to use a different policy.

    If the spider does not define :attr:`~scrapy.Spider.allowed_domains`, or
    the attribute is empty, every request is allowed.

    Filtered requests are logged as follows::

        DEBUG: Filtered offsite request to 'offsite.example': <GET http://offsite.example/some/page.html>

    Only the first request filtered for a given domain is logged, to keep the
    log readable.

    .. reqmeta:: allow_offsite

    allow_offsite
    -------------

    Requests with the ``allow_offsite`` :attr:`~scrapy.Request.meta` key set to
    ``True``, or with :attr:`~scrapy.Request.dont_filter` set to ``True``, are
    allowed regardless of their host name.
    """

    crawler: Crawler
    host_regex: re.Pattern[str]

    def __init__(self, stats: StatsCollector):
        self.stats = stats
        self.domains_seen: set[str] = set()
        self._allowed_domains: list[str] | None = None

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        o = cls(crawler.stats)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.request_scheduled, signal=signals.request_scheduled)
        o.crawler = crawler
        return o

    def spider_opened(self, spider: Spider) -> None:
        self._update_host_regex(spider)

    def _update_host_regex(self, spider: Spider) -> None:
        allowed_domains = list(getattr(spider, "allowed_domains", None) or [])
        if allowed_domains != self._allowed_domains:
            self._allowed_domains = allowed_domains
            self.host_regex = self.get_host_regex(spider)

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
        raise IgnoreRequest(f"Filtered offsite request to {domain!r}")

    def should_follow(self, request: Request, spider: Spider) -> bool:
        """Return ``True`` if *request* is on site, ``False`` if it must be
        filtered out.

        Override this method to implement a different offsite policy. For
        example, to allow the domains in
        :attr:`~scrapy.Spider.allowed_domains` but none of their subdomains:

        .. code-block:: python

            from scrapy.downloadermiddlewares.offsite import OffsiteMiddleware
            from scrapy.utils.httpobj import urlparse_cached


            class RootOnlyOffsiteMiddleware(OffsiteMiddleware):
                def should_follow(self, request, spider):
                    return urlparse_cached(request).hostname in spider.allowed_domains
        """
        self._update_host_regex(spider)
        regex = self.host_regex
        # hostname can be None for wrong urls (like javascript links)
        host = urlparse_cached(request).hostname or ""
        return bool(regex.search(host))

    def get_host_regex(self, spider: Spider) -> re.Pattern[str]:
        allowed_domains = getattr(spider, "allowed_domains", None)
        if not allowed_domains:
            return re.compile("")  # allow all by default
        domains = []
        for domain in allowed_domains:
            if domain is None:
                continue
            domains.append(re.escape(domain))
        regex = rf"^(.*\.)?({'|'.join(domains)})$"
        return re.compile(regex, re.IGNORECASE)
