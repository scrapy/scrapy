from scrapy.http import Request
from scrapy.spider import BaseSpider
from scrapy.item import ScrapedItem

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
    link_filter (optional)
       Can be either a callable, or a string with the name of a method defined
       in the spider's class.
       This method will be called with the list of extracted links matching
       this rule (if any) and must return another list of links.
    """

    def __init__(self, link_extractor, callback=None, cb_kwargs=None, follow=None, link_filter=None):
        self.link_extractor = link_extractor
        self.callback = callback
        self.cb_kwargs = cb_kwargs or {}
        self.link_filter = link_filter
        if follow is None:
            self.follow = False if callback else True
        else:
            self.follow = follow

class CrawlSpider(BaseSpider):
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
        def _get_method(method):
            if isinstance(method, basestring):
                return getattr(self, method, None)
            elif method and callable(method):
                return method

        super(CrawlSpider, self).__init__()
        if not hasattr(self, 'rules'):
            return
        for rule in self.rules:
            rule.callback = _get_method(rule.callback)
            rule.link_filter = _get_method(rule.link_filter)

    def parse(self, response):
        """This function is called by the core for all the start_urls. Do not
        override this function, override parse_start_url instead."""
        if response.url in self.start_urls:
            return self._parse_wrapper(response, self.parse_start_url, cb_kwargs={}, follow=True)
        else:
            return self.parse_url(response)

    def parse_start_url(self, response):
        """Callback function for processing start_urls. It must return a list
        of ScrapedItems and/or Requests."""
        return []

    def scraped_item(self, response, item):
        """
        This method is called for each item returned by the spider, and it's intended
        to do anything that it's needed before returning the item to the core, specially
        setting its GUID.
        It receives and returns an item
        """
        return item

    def _requests_to_follow(self, response):
        """
        This method iterates over each of the spider's rules, extracts the links
        matching each case, filters them (if needed), and returns a list of unique
        requests per response.
        """
        requests = []
        seen = set()
        for rule in self.rules:
            links = [link for link in rule.link_extractor.extract_urls(response) if link not in seen]
            if rule.link_filter:
                links = rule.link_filter(links)
            seen = seen.union(links)
            for link in links:
                r = Request(url=link.url, link_text=link.text)
                r.append_callback(self._parse_wrapper, rule.callback, cb_kwargs=rule.cb_kwargs, follow=rule.follow)
                requests.append(r)
        return requests

    def _parse_wrapper(self, response, callback, cb_kwargs, follow):
        """
        This is were any response (except the ones from the start urls) arrives, and
        were it's decided whether to extract links or not from it, and if it will
        be parsed or not.
        It returns a list of requests/items.
        """
        res = []
        if follow:
            res.extend(self._requests_to_follow(response))
        if callback:
            cb_res = callback(response, **cb_kwargs) or ()
            for entry in cb_res:
                if isinstance(entry, ScrapedItem):
                    entry = self.scraped_item(response, entry)
            res.extend(cb_res)
        return res

    def parse_url(self, response):
        """
        This method is called whenever you run scrapy with the 'parse' command
        over an URL.
        """
        ret = set()
        for rule in self.rules:
            links = [link for link in rule.link_extractor.extract_urls(response) if link not in ret]
            if rule.link_filter:
                links = rule.link_filter(links)
            ret = ret.union(links)
            
            if rule.callback and rule.link_extractor.match(response.url):
                ret = ret.union(rule.callback(response))
        return list(ret)

