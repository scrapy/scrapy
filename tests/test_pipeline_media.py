from __future__ import print_function
from twisted.trial import unittest
from twisted.python.failure import Failure
from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.python import log as txlog

from scrapy.http import Request, Response
from scrapy.spider import Spider
from scrapy.utils.request import request_fingerprint
from scrapy.contrib.pipeline.media import MediaPipeline
from scrapy.utils.signal import disconnect_all
from scrapy import signals
from scrapy import log


def _mocked_download_func(request, info):
    response = request.meta.get('response')
    return response() if callable(response) else response


class BaseMediaPipelineTestCase(unittest.TestCase):

    pipeline_class = MediaPipeline

    def setUp(self):
        self.spider = Spider('media.com')
        self.pipe = self.pipeline_class(download_func=_mocked_download_func)
        self.pipe.open_spider(self.spider)
        self.info = self.pipe.spiderinfo

    def tearDown(self):
        for name, signal in vars(signals).items():
            if not name.startswith('_'):
                disconnect_all(signal)

    def test_default_media_to_download(self):
        request = Request('http://url')
        assert self.pipe.media_to_download(request, self.info) is None

    def test_default_get_media_requests(self):
        item = dict(name='name')
        assert self.pipe.get_media_requests(item, self.info) is None

    def test_default_media_downloaded(self):
        request = Request('http://url')
        response = Response('http://url', body='')
        assert self.pipe.media_downloaded(response, request, self.info) is response

    def test_default_media_failed(self):
        request = Request('http://url')
        fail = Failure(Exception())
        assert self.pipe.media_failed(fail, request, self.info) is fail

    def test_default_item_completed(self):
        item = dict(name='name')
        assert self.pipe.item_completed([], item, self.info) is item

        # Check that failures are logged by default
        fail = Failure(Exception())
        results = [(True, 1), (False, fail)]

        events = []
        txlog.addObserver(events.append)
        new_item = self.pipe.item_completed(results, item, self.info)
        txlog.removeObserver(events.append)
        self.flushLoggedErrors()

        assert new_item is item
        assert len(events) == 1
        assert events[0]['logLevel'] == log.ERROR
        assert events[0]['failure'] is fail

        # disable failure logging and check again
        self.pipe.LOG_FAILED_RESULTS = False
        events = []
        txlog.addObserver(events.append)
        new_item = self.pipe.item_completed(results, item, self.info)
        txlog.removeObserver(events.append)
        self.flushLoggedErrors()
        assert new_item is item
        assert len(events) == 0

    @inlineCallbacks
    def test_default_process_item(self):
        item = dict(name='name')
        new_item = yield self.pipe.process_item(item, self.spider)
        assert new_item is item


class MockedMediaPipeline(MediaPipeline):

    def __init__(self, *args, **kwargs):
        super(MockedMediaPipeline, self).__init__(*args, **kwargs)
        self._mockcalled = []

    def download(self, request, info):
        self._mockcalled.append('download')
        return super(MockedMediaPipeline, self).download(request, info)

    def media_to_download(self, request, info):
        self._mockcalled.append('media_to_download')
        if 'result' in request.meta:
            return request.meta.get('result')
        return super(MockedMediaPipeline, self).media_to_download(request, info)

    def get_media_requests(self, item, info):
        self._mockcalled.append('get_media_requests')
        return item.get('requests')

    def media_downloaded(self, response, request, info):
        self._mockcalled.append('media_downloaded')
        return super(MockedMediaPipeline, self).media_downloaded(response, request, info)

    def media_failed(self, failure, request, info):
        self._mockcalled.append('media_failed')
        return super(MockedMediaPipeline, self).media_failed(failure, request, info)

    def item_completed(self, results, item, info):
        self._mockcalled.append('item_completed')
        item = super(MockedMediaPipeline, self).item_completed(results, item, info)
        item['results'] = results
        return item


class MediaPipelineTestCase(BaseMediaPipelineTestCase):

    pipeline_class = MockedMediaPipeline

    @inlineCallbacks
    def test_result_succeed(self):
        cb = lambda _: self.pipe._mockcalled.append('request_callback') or _
        eb = lambda _: self.pipe._mockcalled.append('request_errback') or _
        rsp = Response('http://url1')
        req = Request('http://url1', meta=dict(response=rsp), callback=cb, errback=eb)
        item = dict(requests=req)
        new_item = yield self.pipe.process_item(item, self.spider)
        self.assertEqual(new_item['results'], [(True, rsp)])
        self.assertEqual(self.pipe._mockcalled,
                ['get_media_requests', 'media_to_download',
                    'media_downloaded', 'request_callback', 'item_completed'])

    @inlineCallbacks
    def test_result_failure(self):
        self.pipe.LOG_FAILED_RESULTS = False
        cb = lambda _: self.pipe._mockcalled.append('request_callback') or _
        eb = lambda _: self.pipe._mockcalled.append('request_errback') or _
        fail = Failure(Exception())
        req = Request('http://url1', meta=dict(response=fail), callback=cb, errback=eb)
        item = dict(requests=req)
        new_item = yield self.pipe.process_item(item, self.spider)
        self.assertEqual(new_item['results'], [(False, fail)])
        self.assertEqual(self.pipe._mockcalled,
                ['get_media_requests', 'media_to_download',
                    'media_failed', 'request_errback', 'item_completed'])

    @inlineCallbacks
    def test_mix_of_success_and_failure(self):
        self.pipe.LOG_FAILED_RESULTS = False
        rsp1 = Response('http://url1')
        req1 = Request('http://url1', meta=dict(response=rsp1))
        fail = Failure(Exception())
        req2 = Request('http://url2', meta=dict(response=fail))
        item = dict(requests=[req1, req2])
        new_item = yield self.pipe.process_item(item, self.spider)
        self.assertEqual(new_item['results'], [(True, rsp1), (False, fail)])
        m = self.pipe._mockcalled
        # only once
        self.assertEqual(m[0], 'get_media_requests') # first hook called
        self.assertEqual(m.count('get_media_requests'), 1)
        self.assertEqual(m.count('item_completed'), 1)
        self.assertEqual(m[-1], 'item_completed') # last hook called
        # twice, one per request
        self.assertEqual(m.count('media_to_download'), 2)
        # one to handle success and other for failure
        self.assertEqual(m.count('media_downloaded'), 1)
        self.assertEqual(m.count('media_failed'), 1)

    @inlineCallbacks
    def test_get_media_requests(self):
        # returns single Request (without callback)
        req = Request('http://url')
        item = dict(requests=req) # pass a single item
        new_item = yield self.pipe.process_item(item, self.spider)
        assert new_item is item
        assert request_fingerprint(req) in self.info.downloaded

        # returns iterable of Requests
        req1 = Request('http://url1')
        req2 = Request('http://url2')
        item = dict(requests=iter([req1, req2]))
        new_item = yield self.pipe.process_item(item, self.spider)
        assert new_item is item
        assert request_fingerprint(req1) in self.info.downloaded
        assert request_fingerprint(req2) in self.info.downloaded

    @inlineCallbacks
    def test_results_are_cached_across_multiple_items(self):
        rsp1 = Response('http://url1')
        req1 = Request('http://url1', meta=dict(response=rsp1))
        item = dict(requests=req1)
        new_item = yield self.pipe.process_item(item, self.spider)
        self.assertTrue(new_item is item)
        self.assertEqual(new_item['results'], [(True, rsp1)])

        # rsp2 is ignored, rsp1 must be in results because request fingerprints are the same
        req2 = Request(req1.url, meta=dict(response=Response('http://donot.download.me')))
        item = dict(requests=req2)
        new_item = yield self.pipe.process_item(item, self.spider)
        self.assertTrue(new_item is item)
        self.assertEqual(request_fingerprint(req1), request_fingerprint(req2))
        self.assertEqual(new_item['results'], [(True, rsp1)])

    @inlineCallbacks
    def test_results_are_cached_for_requests_of_single_item(self):
        rsp1 = Response('http://url1')
        req1 = Request('http://url1', meta=dict(response=rsp1))
        req2 = Request(req1.url, meta=dict(response=Response('http://donot.download.me')))
        item = dict(requests=[req1, req2])
        new_item = yield self.pipe.process_item(item, self.spider)
        self.assertTrue(new_item is item)
        self.assertEqual(new_item['results'], [(True, rsp1), (True, rsp1)])

    @inlineCallbacks
    def test_wait_if_request_is_downloading(self):
        def _check_downloading(response):
            fp = request_fingerprint(req1)
            self.assertTrue(fp in self.info.downloading)
            self.assertTrue(fp in self.info.waiting)
            self.assertTrue(fp not in self.info.downloaded)
            self.assertEqual(len(self.info.waiting[fp]), 2)
            return response

        rsp1 = Response('http://url')
        def rsp1_func():
            dfd = Deferred().addCallback(_check_downloading)
            reactor.callLater(.1, dfd.callback, rsp1)
            return dfd

        def rsp2_func():
            self.fail('it must cache rsp1 result and must not try to redownload')

        req1 = Request('http://url', meta=dict(response=rsp1_func))
        req2 = Request(req1.url, meta=dict(response=rsp2_func))
        item = dict(requests=[req1, req2])
        new_item = yield self.pipe.process_item(item, self.spider)
        self.assertEqual(new_item['results'], [(True, rsp1), (True, rsp1)])

    @inlineCallbacks
    def test_use_media_to_download_result(self):
        req = Request('http://url', meta=dict(result='ITSME', response=self.fail))
        item = dict(requests=req)
        new_item = yield self.pipe.process_item(item, self.spider)
        self.assertEqual(new_item['results'], [(True, 'ITSME')])
        self.assertEqual(self.pipe._mockcalled, \
                ['get_media_requests', 'media_to_download', 'item_completed'])
