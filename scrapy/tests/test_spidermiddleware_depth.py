from unittest import TestCase

from scrapy.contrib.spidermiddleware.depth import DepthMiddleware 
from scrapy.conf import settings
from scrapy.http import Response, Request
from scrapy.spider import BaseSpider
from scrapy.stats import stats


class TestDepthMiddleware(TestCase):

    def setUp(self):
        settings.disabled = False
        settings.overrides['DEPTH_LIMIT'] = 1
        settings.overrides['DEPTH_STATS'] = True

        self.spider = BaseSpider()
        self.spider.domain_name = 'scrapytest.org'

        stats.open_domain(self.spider.domain_name)

        self.mw = DepthMiddleware()
        self.assertEquals(stats.get_value('envinfo/request_depth_limit'), 1)

    def test_process_spider_output(self):
        req = Request('http://scrapytest.org')
        resp = Response('http://scrapytest.org')
        resp.request = req
        result = [Request('http://scrapytest.org')]

        out = list(self.mw.process_spider_output(resp, result, self.spider))
        self.assertEquals(out, result)

        rdc = stats.get_value('request_depth_count/1',
                              domain=self.spider.domain_name)
        self.assertEquals(rdc, 1)

        req.meta['depth'] = 1

        out2 = list(self.mw.process_spider_output(resp, result, self.spider))
        self.assertEquals(out2, [])

        rdm = stats.get_value('request_depth_max',
                              domain=self.spider.domain_name)
        self.assertEquals(rdm, 1)
 
    def tearDown(self):
        del settings.overrides['DEPTH_LIMIT']
        del settings.overrides['DEPTH_STATS']
        settings.disabled = True

        stats.close_domain(self.spider.domain_name, '')

