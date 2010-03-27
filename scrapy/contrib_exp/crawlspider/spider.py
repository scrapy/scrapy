"""CrawlSpider v2"""
from scrapy.spider import BaseSpider
from scrapy.utils.spider import iterate_spider_output

from .matchers import UrlListMatcher
from .rules import Rule, RulesManager
from .reqext import SgmlRequestExtractor
from .reqgen import RequestGenerator
from .reqproc import Canonicalize, FilterDupes

class CrawlSpider(BaseSpider):
    """CrawlSpider v2"""

    request_extractors = None
    request_processors = None
    rules = []

    def __init__(self):
        """Initialize dispatcher"""
        super(CrawlSpider, self).__init__()

        # auto follow start urls
        if self.start_urls:
            _matcher = UrlListMatcher(self.start_urls)
            # append new rule using type from current self.rules
            rules = self.rules + type(self.rules)([
                            Rule(_matcher, follow=True)
                        ])
        else:
            rules = self.rules

        # set defaults if not set
        if self.request_extractors is None:
            # default link extractor. Extracts all links from response
            self.request_extractors = [ SgmlRequestExtractor() ]

        if self.request_processors is None:
            # default proccessor. Filter duplicates requests
            self.request_processors = [ FilterDupes() ]


        # wrap rules
        self._rulesman = RulesManager(rules, spider=self)
        # generates new requests with given callback
        self._reqgen = RequestGenerator(self.request_extractors,
                                        self.request_processors,
                                        callback=self.parse)

    def parse(self, response):
        """Dispatch callback and generate requests"""
        # get rule for response
        rule = self._rulesman.get_rule_from_response(response)

        if rule:
            # dispatch callback if set
            if rule.callback:
                output = iterate_spider_output(rule.callback(response))
                for req_or_item in output:
                    yield req_or_item

            if rule.follow:
                for req in self._reqgen.generate_requests(response):
                    # only dispatch request if has matching rule
                    if self._rulesman.get_rule_from_request(req):
                         yield req
        else:
             self.log("No rule for response %s" % response, level=log.WARNING)


