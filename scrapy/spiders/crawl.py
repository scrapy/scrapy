"""
This modules implements the CrawlSpider which is the recommended spider to use
for scraping typical web sites that requires crawling pages.

See documentation in docs/topics/spiders.rst
"""

import copy
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request, HtmlResponse
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import Spider
from scrapy.utils.python import get_func_args
from scrapy.utils.spider import iterate_spider_output


def _identity(x):
    return x


def _identity_process_request(request, response):
    return request


def _get_method(method, spider):
    if callable(method):
        return method
    elif isinstance(method, str):
        return getattr(spider, method, None)


_default_link_extractor = LinkExtractor()


class Rule:

    def __init__(self, link_extractor=None, callback=None, cb_kwargs=None, follow=None,
                 process_links=None, process_request=None, errback=None):
        self.link_extractor = link_extractor or _default_link_extractor
        self.callback = callback
        self.errback = errback
        self.cb_kwargs = cb_kwargs or {}
        self.process_links = process_links or _identity
        self.process_request = process_request or _identity_process_request
        self.process_request_argcount = None
        self.follow = follow if follow is not None else not callback

    def _compile(self, spider):
        self.callback = _get_method(self.callback, spider)
        self.errback = _get_method(self.errback, spider)
        self.process_links = _get_method(self.process_links, spider)
        self.process_request = _get_method(self.process_request, spider)
        self.process_request_argcount = len(get_func_args(self.process_request))
        if self.process_request_argcount == 1:
            warnings.warn(
                "Rule.process_request should accept two arguments "
                "(request, response), accepting only one is deprecated",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )

    def _process_request(self, request, response):
        """
        Wrapper around the request processing function to maintain backward
        compatibility with functions that do not take a Response object
        """
        args = [request] if self.process_request_argcount == 1 else [request, response]
        return self.process_request(*args)


class CrawlSpider(Spider):

    rules = ()

    def __init__(self, *a, **kw):
        super(CrawlSpider, self).__init__(*a, **kw)
        self._compile_rules()

    def _parse(self, response, **kwargs):
        return self._parse_response(
            response=response,
            callback=self.parse_start_url,
            cb_kwargs=kwargs,
            follow=True,
        )

    def parse_start_url(self, response, **kwargs):
        return []

    def process_results(self, response, results):
        return results

    def _build_request(self, rule_index, link):
        return Request(
            url=link.url,
            callback=self._callback,
            errback=self._errback,
            meta=dict(rule=rule_index, link_text=link.text),
        )

    def _requests_to_follow(self, response):
        if not isinstance(response, HtmlResponse):
            return
        seen = set()
        for rule_index, rule in enumerate(self._rules):
            links = [lnk for lnk in rule.link_extractor.extract_links(response)
                     if lnk not in seen]
            for link in rule.process_links(links):
                seen.add(link)
                request = self._build_request(rule_index, link)
                yield rule._process_request(request, response)

    def _callback(self, response):
        rule = self._rules[response.meta['rule']]
        return self._parse_response(response, rule.callback, rule.cb_kwargs, rule.follow)

    def _errback(self, failure):
        rule = self._rules[failure.request.meta['rule']]
        return self._handle_failure(failure, rule.errback)

    def _parse_response(self, response, callback, cb_kwargs, follow=True):
        if callback:
            cb_res = callback(response, **cb_kwargs) or ()
            cb_res = self.process_results(response, cb_res)
            for request_or_item in iterate_spider_output(cb_res):
                yield request_or_item

        if follow and self._follow_links:
            for request_or_item in self._requests_to_follow(response):
                yield request_or_item

    def _handle_failure(self, failure, errback):
        if errback:
            results = errback(failure) or ()
            for request_or_item in iterate_spider_output(results):
                yield request_or_item

    def _compile_rules(self):
        self._rules = []
        for rule in self.rules:
            self._rules.append(copy.copy(rule))
            self._rules[-1]._compile(self)

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(CrawlSpider, cls).from_crawler(crawler, *args, **kwargs)
        spider._follow_links = crawler.settings.getbool('CRAWLSPIDER_FOLLOW_LINKS', True)
        return spider
