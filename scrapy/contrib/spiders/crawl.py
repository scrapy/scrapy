"""
This modules implements the CrawlSpider which is the recommended spider to use
for scraping typical web sites that requires crawling pages.

See documentation in docs/topics/spiders.rst
"""

import copy
from functools import partial

from scrapy.http import Request
from scrapy.utils.spider import iterate_spider_output
from scrapy.spider import BaseSpider
from scrapy.conf import settings

def identity(x):
    return x

class Rule(object):

    def __init__(self, link_extractor, callback=None, cb_kwargs=None, follow=None, process_links=None, process_request=identity):
        self.link_extractor = link_extractor
        self.callback = callback
        self.cb_kwargs = cb_kwargs or {}
        self.process_links = process_links
        self.process_request = process_request
        if follow is None:
            self.follow = False if callback else True
        else:
            self.follow = follow

class CrawlSpider(BaseSpider):

    rules = ()

    def __init__(self, *a, **kw):
        super(CrawlSpider, self).__init__(*a, **kw)
        self._compile_rules()

    def parse(self, response):
        return self._response_downloaded(response, self.parse_start_url, cb_kwargs={}, follow=True)

    def parse_start_url(self, response):
        return []

    def process_results(self, response, results):
        return results

    def _requests_to_follow(self, response):
        seen = set()
        for rule in self._rules:
            links = [l for l in rule.link_extractor.extract_links(response) if l not in seen]
            if links and rule.process_links:
                links = rule.process_links(links)
            seen = seen.union(links)
            for link in links:
                callback = partial(self._response_downloaded, callback=rule.callback, \
                    cb_kwargs=rule.cb_kwargs, follow=rule.follow)
                r = Request(url=link.url, callback=callback)
                r.meta['link_text'] = link.text
                yield rule.process_request(r)

    def _response_downloaded(self, response, callback, cb_kwargs, follow):
        if callback:
            cb_res = callback(response, **cb_kwargs) or ()
            cb_res = self.process_results(response, cb_res)
            for requests_or_item in iterate_spider_output(cb_res):
                yield requests_or_item

        if follow and settings.getbool('CRAWLSPIDER_FOLLOW_LINKS', True):
            for request_or_item in self._requests_to_follow(response):
                yield request_or_item
                

    def _compile_rules(self):
        def get_method(method):
            if callable(method):
                return method
            elif isinstance(method, basestring):
                return getattr(self, method, None)

        self._rules = [copy.copy(r) for r in self.rules]
        for rule in self._rules:
            rule.callback = get_method(rule.callback)
            rule.process_links = get_method(rule.process_links)
            rule.process_request = get_method(rule.process_request)
