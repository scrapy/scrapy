"""
Offsite Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""
import logging
import re
import warnings

from scrapy import signals
from scrapy.http import Request
from scrapy.utils.httpobj import urlparse_cached

logger = logging.getLogger(__name__)


class OffsiteMiddleware:
    def __init__(self, stats):
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler):
        o = cls(crawler.stats)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def process_spider_output(self, response, result, spider):
        return (r for r in result or () if self._filter(r, spider))

    async def process_spider_output_async(self, response, result, spider):
        async for r in result or ():
            if self._filter(r, spider):
                yield r

    def _filter(self, request, spider) -> bool:
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
        # hostname can be None for wrong urls (like javascript links)
        host = urlparse_cached(request).hostname or ""
        return bool(regex.search(host))

    def get_host_regex(self, spider):
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

    def spider_opened(self, spider):
        self.host_regex = self.get_host_regex(spider)
        self.domains_seen = set()


class URLWarning(Warning):
    pass


class PortWarning(Warning):
    pass
