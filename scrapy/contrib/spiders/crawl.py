"""
This modules implements the CrawlSpider which is the recommended spider to use
for scraping typical web sites that requires crawling pages.

See documentation in docs/topics/spiders.rst
"""

import copy

from scrapy.http import Request
from scrapy.utils.spider import iterate_spider_output
from scrapy.contrib.spiders.init import InitSpider
from scrapy.conf import settings

class Rule(object):
    """
    A rule for crawling, which receives the following constructor arguments:

    link_extractor (required)
       A LinkExtractor which defines the policy for extracting links
    callback (optional)
       A function to use to process the page once it has been downloaded. If
       callback is omitted the page is not procesed, just crawled. If callback
       is a string (instead of callable) a method of the spider class with that
       name is used as the callback function
    cb_kwargs (optional)
       A dict specifying keyword arguments to pass to the callback function
    follow (optional)
       If True, links will be followed from the pages crawled by this rule.
       It defaults to True when no callback is specified or False when a
       callback is specified
    process_links (optional)
       Can be either a callable, or a string with the name of a method defined
       in the spider's class.
       This method will be called with the list of extracted links matching
       this rule (if any) and must return another list of links.
    """

    def __init__(self, link_extractor, callback=None, cb_kwargs=None, follow=None, process_links=None):
        self.link_extractor = link_extractor
        self.callback = callback
        self.cb_kwargs = cb_kwargs or {}
        self.process_links = process_links
        if follow is None:
            self.follow = False if callback else True
        else:
            self.follow = follow

class CrawlSpider(InitSpider):
    """
    Class for spiders that crawl over web pages and extract/parse their links
    given some crawling rules.

    These crawling rules are established by setting the 'rules' class attribute,
    which is a tuple of Rule objects.
    When the spider is running, it iterates over these rules with each response
    and do what it has to (extract links if follow=True, and return items/requests if
    there's a parsing method defined in the rule).
    """
    rules = ()

    def __init__(self):
        """Constructor takes care of compiling rules"""
        super(CrawlSpider, self).__init__()
        self._compile_rules()

    def parse(self, response):
        """This function is called by the framework core for all the
        start_urls. Do not override this function, override parse_start_url
        instead."""
        return self._response_downloaded(response, self.parse_start_url, cb_kwargs={}, follow=True)

    def parse_start_url(self, response):
        """Overrideable callback function for processing start_urls. It must
        return a list of BaseItem and/or Requests"""
        return []

    def process_results(self, response, results):
        """This overridable method is called for each result (item or request)
        returned by the spider, and it's intended to perform any last time
        processing required before returning the results to the framework core,
        for example setting the item GUIDs. It receives a list of results and
        the response which originated that results. It must return a list
        of results (Items or Requests)."""
        return results

    def _requests_to_follow(self, response):
        """
        This method iterates over each of the spider's rules, extracts the links
        matching each case, filters them (if needed), and returns a list of unique
        requests per response.
        """
        requests = []
        seen = set()
        for rule in self._rules:
            links = [l for l in rule.link_extractor.extract_links(response) if l not in seen]
            if links and rule.process_links:
                links = rule.process_links(links)
            seen = seen.union(links)
            for link in links:
                r = Request(url=link.url)
                r.meta['link_text'] = link.text
                r.deferred.addCallback(self._response_downloaded, rule.callback, cb_kwargs=rule.cb_kwargs, follow=rule.follow)
                requests.append(r)
        return requests

    def _response_downloaded(self, response, callback, cb_kwargs, follow):
        """
        This is were any response arrives, and were it's decided whether
        to extract links or not from it, and if it will be parsed or not.
        It returns a list of requests/items.
        """
        res = []

        if follow and settings.getbool('CRAWLSPIDER_FOLLOW_LINKS', True):
            res.extend(self._requests_to_follow(response))
        if callback:
            cb_res = callback(response, **cb_kwargs) or ()
            cb_res = self.process_results(response, cb_res)
            res.extend(iterate_spider_output(cb_res))
        return res

    def _compile_rules(self):
        """Compile the crawling rules"""

        def get_method(method):
            if callable(method):
                return method
            elif isinstance(method, basestring):
                return getattr(self, method, None)

        self._rules = [copy.copy(r) for r in self.rules]
        for rule in self._rules:
            rule.callback = get_method(rule.callback)
            rule.process_links = get_method(rule.process_links)
