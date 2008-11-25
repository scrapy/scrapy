"""
This module contains the basic crawling spider that you can use to inherit your
spider from.
"""

from scrapy.http import Request
from scrapy.spider import BaseSpider
from scrapy.item import ScrapedItem

class CrawlSpider(BaseSpider):
    """
    This is the base class for crawling spiders. It is based on a list of
    crawling rules (stored in the "rules" attribute) which specify how links
    are extracted and followed, and how pages are processed (by using a
    callback function).

    For more info about rules see the Rule class.
    """

    def parse(self, response):
        """Method called by the framework core for all the start_urls. Do not
        override this function, override parse_start_url instead.
        """
        if response.url in self.start_urls:
            return self._parse_wrapper(response, self.parse_start_url, cb_kwargs={}, follow=True) 
        else:
            return self.parse_url(response)

    def parse_start_url(self, response):
        """Callback function for processing start_urls. It must return a list
        of ScrapedItems and/or Requests.
        """
        return []

    def _requests_to_follow(self, response):
        requests = []
        seen = set()
        for rule in self.rules:
            callback = rule.callback if callable(rule.callback) else getattr(self, rule.callback, None)
            links = [l for l in rule.link_extractor.extract_urls(response) if l not in seen]
            seen.union(links)
            for link in links:
                r = Request(url=link.url, link_text=link.text)
                r.append_callback(self._parse_wrapper, callback, cb_kwargs=rule.cb_kwargs, follow=rule.follow)
                requests.append(r)
        return requests

    def _parse_wrapper(self, response, callback, cb_kwargs, follow):
        res = []
        if follow:
            res.extend(self._requests_to_follow(response))
        if callback:
            res.extend(callback(response, **cb_kwargs) or ())
        return res


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
    """
    
    def __init__(self, link_extractor, callback=None, cb_kwargs=None, follow=None):
        self.link_extractor = link_extractor
        self.callback = callback
        self.cb_kwargs = cb_kwargs or {}
        if follow is None:
            self.follow = False if callback else True
        else:
            self.follow = follow 
