from unittest import TestCase

from scrapy.spidermiddlewares.urllength import UrlLengthMiddleware
from scrapy.http import Response, Request
from scrapy.spiders import Spider


class TestUrlLengthMiddleware(TestCase):

    def test_process_spider_output(self):
        res = Response('http://scrapytest.org')

        short_url_req = Request('http://scrapytest.org/')
        long_url_req = Request('http://scrapytest.org/this_is_a_long_url')
        reqs = [short_url_req, long_url_req]

        mw = UrlLengthMiddleware(maxlength=25)
        spider = Spider('foo')
        out = list(mw.process_spider_output(res, reqs, spider))
        self.assertEquals(out, [short_url_req])

