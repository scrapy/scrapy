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

# 爬取一般网站常用的spider，定义了一些规则(rule)来提供跟进link的方便的机制。
class CrawlSpider(Spider):

	# Rule对象集合。定义了提取需要跟进url的一些规则。
    rules = ()

    def __init__(self, *a, **kw):
        super(CrawlSpider, self).__init__(*a, **kw)
        self._compile_rules()

	# 1. 首先调用parse()来处理start_urls中返回的response对象
    # 2. parse()则将这些response对象传递给了_parse_response()函数处理，并设置回调函数为parse_start_url()
	# 3. follow=True表示跟进标志位为True
	# 4. #parse将返回item和跟进的Request对象 
	def parse(self, response):
        return self._parse_response(response, self.parse_start_url, cb_kwargs={}, follow=True)

	# 1. 处理start_url中返回的response，如果有需要，可以重写。
    def parse_start_url(self, response):
        return []

    def process_results(self, response, results):
        return results

    def _build_request(self, rule, link):
		# 构造Request对象，并将Rule规则中定义的回调函数作为这个Request对象的回调函数
        r = Request(url=link.url, callback=self._response_downloaded)
        r.meta.update(rule=rule, link_text=link.text)
        return r

	# 从response中抽取符合任一用户定义'规则'的链接，并构造成Resquest对象返回
    def _requests_to_follow(self, response):
        if not isinstance(response, HtmlResponse):
            return
        seen = set()
		# 抽取之内的所有链接，只要通过任意一个'规则'，即表示合法 
        for n, rule in enumerate(self._rules):
            links = [lnk for lnk in rule.link_extractor.extract_links(response)
                     if lnk not in seen]
			# 使用用户指定的process_links处理每个连接		 
            if links and rule.process_links:
                links = rule.process_links(links)
			# 将链接加入seen集合，为每个链接生成Request对象，并设置回调函数为_repsonse_downloaded()
            for link in links:
                seen.add(link)
                r = self._build_request(n, link)
				# 对每个Request调用process_request()函数。该函数默认为indentify，即不做任何处理，直接返回该Request.
                yield rule.process_request(r)

	# 处理通过rule提取出的连接，并返回item以及request
    def _response_downloaded(self, response):
        rule = self._rules[response.meta['rule']]
        return self._parse_response(response, rule.callback, rule.cb_kwargs, rule.follow)

	# 解析response对象，会用callback解析处理它，并返回request或Item对象
    def _parse_response(self, response, callback, cb_kwargs, follow=True):
		# 首先判断是否设置了回调函数。(该回调函数可能是rule中的解析函数，也可能是 parse_start_url函数)  
        # 如果设置了回调函数(parse_start_url())，那么首先用parse_start_url()处理response对象，然后再交给process_results处理。返回cb_res的一个列表
        if callback:
			# 如果是parse调用，则会解析成Request对象
			# 如果是rule回调，则会解析成Item对象
            cb_res = callback(response, **cb_kwargs) or ()
            cb_res = self.process_results(response, cb_res)
            for requests_or_item in iterate_spider_output(cb_res):
                yield requests_or_item

		# 如果需要跟进，那么使用定义的Rule规则提取并返回这些Request对象
        if follow and self._follow_links:
			# 返回每个Request对象
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
