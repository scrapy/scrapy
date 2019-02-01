"""
This modules implements the CrawlSpider which is the recommended spider to use
for scraping typical web sites that requires crawling pages.

See documentation in docs/topics/spiders.rst
"""

import copy
import six

from scrapy.http import Request, HtmlResponse
from scrapy.utils.spider import iterate_spider_output
from scrapy.spiders import Spider


def identity(x):
    return x


class Rule(object):
    """``link_extractor`` is a :ref:`Link Extractor <topics-link-extractors>` object which
    defines how links will be extracted from each crawled page.

    ``callback`` is a callable or a string (in which case a method from the spider
    object with that name will be used) to be called for each link extracted with
    the specified link_extractor. This callback receives a response as its first
    argument and must return a list containing :class:`~scrapy.item.Item` and/or
    :class:`Request <scrapy.Request>` objects (or any subclass of them).

    .. warning:: When writing crawl spider rules, avoid using ``parse`` as
        callback, since the :class:`CrawlSpider` uses the ``parse`` method
        itself to implement its logic. So if you override the ``parse`` method,
        the crawl spider will no longer work.

    ``cb_kwargs`` is a dict containing the keyword arguments to be passed to the
    callback function.

    ``follow`` is a boolean which specifies if links should be followed from each
    response extracted with this rule. If ``callback`` is None ``follow`` defaults
    to ``True``, otherwise it defaults to ``False``.

    ``process_links`` is a callable, or a string (in which case a method from the
    spider object with that name will be used) which will be called for each list
    of links extracted from each response using the specified ``link_extractor``.
    This is mainly used for filtering purposes.

    ``process_request`` is a callable, or a string (in which case a method from
    the spider object with that name will be used) which will be called with
    every request extracted by this rule, and must return a request or None (to
    filter out the request).
    """

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


class CrawlSpider(Spider):
    """This is the most commonly used spider for crawling regular websites, as it
    provides a convenient mechanism for following links by defining a set of rules.
    It may not be the best suited for your particular web sites or project, but
    it's generic enough for several cases, so you can start from it and override it
    as needed for more custom functionality, or just implement your own spider.

    Apart from the attributes inherited from Spider (that you must
    specify), this class supports a new attribute and an overrideable method:
    """

    #: Which is a list of one (or more) :class:`Rule` objects.  Each :class:`Rule`
    #: defines a certain behaviour for crawling the site. Rules objects are
    #: described below. If multiple rules match the same link, the first one
    #: will be used, according to the order they're defined in this attribute.
    rules = ()

    def __init__(self, *a, **kw):
        super(CrawlSpider, self).__init__(*a, **kw)
        self._compile_rules()

    def parse(self, response):
        return self._parse_response(response, self.parse_start_url, cb_kwargs={}, follow=True)

    def parse_start_url(self, response):
        """This method is called for the start_urls responses. It allows to parse
        the initial responses and must return either an
        :class:`~scrapy.item.Item` object, a :class:`Request <scrapy.Request>`
        object, or an iterable containing any of them."""
        return []

    def process_results(self, response, results):
        return results

    def _build_request(self, rule, link):
        r = Request(url=link.url, callback=self._response_downloaded)
        r.meta.update(rule=rule, link_text=link.text)
        return r

    def _requests_to_follow(self, response):
        if not isinstance(response, HtmlResponse):
            return
        seen = set()
        for n, rule in enumerate(self._rules):
            links = [lnk for lnk in rule.link_extractor.extract_links(response)
                     if lnk not in seen]
            if links and rule.process_links:
                links = rule.process_links(links)
            for link in links:
                seen.add(link)
                r = self._build_request(n, link)
                yield rule.process_request(r)

    def _response_downloaded(self, response):
        rule = self._rules[response.meta['rule']]
        return self._parse_response(response, rule.callback, rule.cb_kwargs, rule.follow)

    def _parse_response(self, response, callback, cb_kwargs, follow=True):
        if callback:
            cb_res = callback(response, **cb_kwargs) or ()
            cb_res = self.process_results(response, cb_res)
            for requests_or_item in iterate_spider_output(cb_res):
                yield requests_or_item

        if follow and self._follow_links:
            for request_or_item in self._requests_to_follow(response):
                yield request_or_item

    def _compile_rules(self):
        def get_method(method):
            if callable(method):
                return method
            elif isinstance(method, six.string_types):
                return getattr(self, method, None)

        self._rules = [copy.copy(r) for r in self.rules]
        for rule in self._rules:
            rule.callback = get_method(rule.callback)
            rule.process_links = get_method(rule.process_links)
            rule.process_request = get_method(rule.process_request)

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(CrawlSpider, cls).from_crawler(crawler, *args, **kwargs)
        spider._follow_links = crawler.settings.getbool(
            'CRAWLSPIDER_FOLLOW_LINKS', True)
        return spider

    def set_crawler(self, crawler):
        super(CrawlSpider, self).set_crawler(crawler)
        self._follow_links = crawler.settings.getbool('CRAWLSPIDER_FOLLOW_LINKS', True)
