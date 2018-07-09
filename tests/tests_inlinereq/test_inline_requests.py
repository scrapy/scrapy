from inline_requests import inline_requests
from scrapy.http import Request, Response


def test_inline_requests():

    class MySpider(object):
        @inline_requests
        def parse(self, response):
            yield Request('http://example/1')
            yield Request('http://example/2')

    spider = MySpider()
    out = [req.url for req in _consume(spider.parse, Response('http://example'))]
    assert out == [
        'http://example/1',
        'http://example/2',
    ]


def test_inline_request_callback_is_none():
    class MySpider(object):
        @inline_requests
        def parse(self, response):
            resp = yield Request('http://example/1')
            assert resp.request.callback is None
            assert resp.request.errback is None

    spider = MySpider()
    out = [req.url for req in _consume(spider.parse, Response('http://example.com'))]
    assert out == ['http://example/1']


def _consume(callback, *args):
    req = next(callback(*args))
    while req:
        yield req
        try:
            resp = Response(req.url, request=req)
            req = next(req.callback(resp))
        except (TypeError, StopIteration):
            break
