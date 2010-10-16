from twisted.trial import unittest
from twisted.python import failure
from twisted.internet import defer, reactor

from scrapy.settings import Settings
from scrapy.crawler import Crawler
from scrapy.http import Request, Response
from scrapy.spider import BaseSpider
from scrapy.utils.request import request_fingerprint
from scrapy.contrib.pipeline.media import MediaPipeline


class _MockedMediaPipeline(MediaPipeline):

    def download(self, request, info):
        delay = request.meta.get('delay')
        response = request.meta.get('response')
        if delay is None:
            return response
        else:
            dfd = defer.Deferred()
            reactor.callLater(delay, dfd.callback, None)
            return dfd.addCallback(lambda _: response)

    def get_media_requests(self, item, info):
        return item.get('requests')


class MediaPipelineTestCase(unittest.TestCase):

    pipeline_class = _MockedMediaPipeline

    def setUp(self):
        self.crawler = Crawler(Settings())
        self.crawler.install()
        self.spider = BaseSpider('media.com')
        self.pipe = self.pipeline_class()
        self.pipe.open_spider(self.spider)

    def tearDown(self):
        self.pipe.close_spider(self.spider)
        self.crawler.uninstall()

    @defer.inlineCallbacks
    def test_return_item_by_default(self):
        item = dict(name='sofa')
        new_item = yield self.pipe.process_item(item, self.spider)
        assert new_item is item

    @defer.inlineCallbacks
    def test_get_media_requests(self):
        # returns single Request (without callback)
        info = self.pipe.spiderinfo[self.spider]
        req = Request('http://media.com/2.gif')
        item = dict(requests=req) # pass a single item
        new_item = yield self.pipe.process_item(item, self.spider)
        assert new_item is item
        assert request_fingerprint(req) in info.downloaded

        # returns iterable of Requests
        req1 = Request('http://media.com/1.gif')
        req2 = Request('http://media.com/1.jpg')
        item = dict(requests=iter([req1, req2]))
        new_item = yield self.pipe.process_item(item, self.spider)
        assert new_item is item
        assert info.downloaded.get(request_fingerprint(req1)) is None
        assert info.downloaded.get(request_fingerprint(req2)) is None

    @defer.inlineCallbacks
    def test_requets_callback_is_called(self):
        collected = []
        response = Response('http://media.com/2.gif')
        request = Request('http://media.com/2.gif', meta=dict(response=response), callback=collected.append)
        item = dict(requests=request) # pass a single item
        yield self.pipe.process_item(item, self.spider)
        assert collected == [response]

    @defer.inlineCallbacks
    def test_requets_errback_is_called(self):
        collected = []
        fail = failure.Failure(Exception())
        req = Request('http://media.com/2.gif', meta=dict(response=fail), callback=lambda _:_, errback=collected.append)
        item = dict(requests=req) # pass a single item
        yield self.pipe.process_item(item, self.spider)
        assert collected == [fail]
