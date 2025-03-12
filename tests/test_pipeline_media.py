from __future__ import annotations

import warnings

import pytest
from testfixtures import LogCapture
from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.python.failure import Failure
from twisted.trial import unittest

from scrapy import signals
from scrapy.http import Request, Response
from scrapy.http.request import NO_CALLBACK
from scrapy.pipelines.files import FileException
from scrapy.pipelines.media import MediaPipeline
from scrapy.spiders import Spider
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.signal import disconnect_all
from scrapy.utils.test import get_crawler


def _mocked_download_func(request, info):
    assert request.callback is NO_CALLBACK
    response = request.meta.get("response")
    return response() if callable(response) else response


class UserDefinedPipeline(MediaPipeline):
    def media_to_download(self, request, info, *, item=None):
        pass

    def get_media_requests(self, item, info):
        pass

    def media_downloaded(self, response, request, info, *, item=None):
        return {}

    def media_failed(self, failure, request, info):
        return failure

    def file_path(self, request, response=None, info=None, *, item=None):
        return ""


class TestBaseMediaPipeline(unittest.TestCase):
    pipeline_class = UserDefinedPipeline
    settings = None

    def setUp(self):
        spider_cls = Spider
        self.spider = spider_cls("media.com")
        crawler = get_crawler(spider_cls, self.settings)
        self.pipe = self.pipeline_class.from_crawler(crawler)
        self.pipe.download_func = _mocked_download_func
        self.pipe.open_spider(self.spider)
        self.info = self.pipe.spiderinfo
        self.fingerprint = crawler.request_fingerprinter.fingerprint

    def tearDown(self):
        for name, signal in vars(signals).items():
            if not name.startswith("_"):
                disconnect_all(signal)

    def test_modify_media_request(self):
        request = Request("http://url")
        self.pipe._modify_media_request(request)
        assert request.meta == {"handle_httpstatus_all": True}

    def test_should_remove_req_res_references_before_caching_the_results(self):
        """Regression test case to prevent a memory leak in the Media Pipeline.

        The memory leak is triggered when an exception is raised when a Response
        scheduled by the Media Pipeline is being returned. For example, when a
        FileException('download-error') is raised because the Response status
        code is not 200 OK.

        It happens because we are keeping a reference to the Response object
        inside the FileException context. This is caused by the way Twisted
        return values from inline callbacks. It raises a custom exception
        encapsulating the original return value.

        The solution is to remove the exception context when this context is a
        _DefGen_Return instance, the BaseException used by Twisted to pass the
        returned value from those inline callbacks.

        Maybe there's a better and more reliable way to test the case described
        here, but it would be more complicated and involve running - or at least
        mocking - some async steps from the Media Pipeline. The current test
        case is simple and detects the problem very fast. On the other hand, it
        would not detect another kind of leak happening due to old object
        references being kept inside the Media Pipeline cache.

        This problem does not occur in Python 2.7 since we don't have Exception
        Chaining (https://www.python.org/dev/peps/pep-3134/).
        """
        # Create sample pair of Request and Response objects
        request = Request("http://url")
        response = Response("http://url", body=b"", request=request)

        # Simulate the Media Pipeline behavior to produce a Twisted Failure
        try:
            # Simulate a Twisted inline callback returning a Response
            raise StopIteration(response)
        except StopIteration as exc:
            def_gen_return_exc = exc
            try:
                # Simulate the media_downloaded callback raising a FileException
                # This usually happens when the status code is not 200 OK
                raise FileException("download-error")
            except Exception as exc:
                file_exc = exc
                # Simulate Twisted capturing the FileException
                # It encapsulates the exception inside a Twisted Failure
                failure = Failure(file_exc)

        # The Failure should encapsulate a FileException ...
        assert failure.value == file_exc
        # ... and it should have the StopIteration exception set as its context
        assert failure.value.__context__ == def_gen_return_exc

        # Let's calculate the request fingerprint and fake some runtime data...
        fp = self.fingerprint(request)
        info = self.pipe.spiderinfo
        info.downloading.add(fp)
        info.waiting[fp] = []

        # When calling the method that caches the Request's result ...
        self.pipe._cache_result_and_execute_waiters(failure, fp, info)
        # ... it should store the Twisted Failure ...
        assert info.downloaded[fp] == failure
        # ... encapsulating the original FileException ...
        assert info.downloaded[fp].value == file_exc
        # ... but it should not store the StopIteration exception on its context
        context = getattr(info.downloaded[fp].value, "__context__", None)
        assert context is None

    def test_default_item_completed(self):
        item = {"name": "name"}
        assert self.pipe.item_completed([], item, self.info) is item

        # Check that failures are logged by default
        fail = Failure(Exception())
        results = [(True, 1), (False, fail)]

        with LogCapture() as log:
            new_item = self.pipe.item_completed(results, item, self.info)

        assert new_item is item
        assert len(log.records) == 1
        record = log.records[0]
        assert record.levelname == "ERROR"
        assert record.exc_info == failure_to_exc_info(fail)

        # disable failure logging and check again
        self.pipe.LOG_FAILED_RESULTS = False
        with LogCapture() as log:
            new_item = self.pipe.item_completed(results, item, self.info)
        assert new_item is item
        assert len(log.records) == 0

    @inlineCallbacks
    def test_default_process_item(self):
        item = {"name": "name"}
        new_item = yield self.pipe.process_item(item, self.spider)
        assert new_item is item


class MockedMediaPipeline(UserDefinedPipeline):
    def __init__(self, *args, crawler=None, **kwargs):
        super().__init__(*args, crawler=crawler, **kwargs)
        self._mockcalled = []

    def download(self, request, info):
        self._mockcalled.append("download")
        return super().download(request, info)

    def media_to_download(self, request, info, *, item=None):
        self._mockcalled.append("media_to_download")
        if "result" in request.meta:
            return request.meta.get("result")
        return super().media_to_download(request, info)

    def get_media_requests(self, item, info):
        self._mockcalled.append("get_media_requests")
        return item.get("requests")

    def media_downloaded(self, response, request, info, *, item=None):
        self._mockcalled.append("media_downloaded")
        return super().media_downloaded(response, request, info)

    def media_failed(self, failure, request, info):
        self._mockcalled.append("media_failed")
        return super().media_failed(failure, request, info)

    def item_completed(self, results, item, info):
        self._mockcalled.append("item_completed")
        item = super().item_completed(results, item, info)
        item["results"] = results
        return item


class TestMediaPipeline(TestBaseMediaPipeline):
    pipeline_class = MockedMediaPipeline

    def _errback(self, result):
        self.pipe._mockcalled.append("request_errback")
        return result

    @inlineCallbacks
    def test_result_succeed(self):
        rsp = Response("http://url1")
        req = Request(
            "http://url1",
            meta={"response": rsp},
            errback=self._errback,
        )
        item = {"requests": req}
        new_item = yield self.pipe.process_item(item, self.spider)
        assert new_item["results"] == [(True, {})]
        assert self.pipe._mockcalled == [
            "get_media_requests",
            "media_to_download",
            "media_downloaded",
            "item_completed",
        ]

    @inlineCallbacks
    def test_result_failure(self):
        self.pipe.LOG_FAILED_RESULTS = False
        fail = Failure(Exception())
        req = Request(
            "http://url1",
            meta={"response": fail},
            errback=self._errback,
        )
        item = {"requests": req}
        new_item = yield self.pipe.process_item(item, self.spider)
        assert new_item["results"] == [(False, fail)]
        assert self.pipe._mockcalled == [
            "get_media_requests",
            "media_to_download",
            "media_failed",
            "request_errback",
            "item_completed",
        ]

    @inlineCallbacks
    def test_mix_of_success_and_failure(self):
        self.pipe.LOG_FAILED_RESULTS = False
        rsp1 = Response("http://url1")
        req1 = Request("http://url1", meta={"response": rsp1})
        fail = Failure(Exception())
        req2 = Request("http://url2", meta={"response": fail})
        item = {"requests": [req1, req2]}
        new_item = yield self.pipe.process_item(item, self.spider)
        assert new_item["results"] == [(True, {}), (False, fail)]
        m = self.pipe._mockcalled
        # only once
        assert m[0] == "get_media_requests"  # first hook called
        assert m.count("get_media_requests") == 1
        assert m.count("item_completed") == 1
        assert m[-1] == "item_completed"  # last hook called
        # twice, one per request
        assert m.count("media_to_download") == 2
        # one to handle success and other for failure
        assert m.count("media_downloaded") == 1
        assert m.count("media_failed") == 1

    @inlineCallbacks
    def test_get_media_requests(self):
        # returns single Request (without callback)
        req = Request("http://url")
        item = {"requests": req}  # pass a single item
        new_item = yield self.pipe.process_item(item, self.spider)
        assert new_item is item
        assert self.fingerprint(req) in self.info.downloaded

        # returns iterable of Requests
        req1 = Request("http://url1")
        req2 = Request("http://url2")
        item = {"requests": iter([req1, req2])}
        new_item = yield self.pipe.process_item(item, self.spider)
        assert new_item is item
        assert self.fingerprint(req1) in self.info.downloaded
        assert self.fingerprint(req2) in self.info.downloaded

    @inlineCallbacks
    def test_results_are_cached_across_multiple_items(self):
        rsp1 = Response("http://url1")
        req1 = Request("http://url1", meta={"response": rsp1})
        item = {"requests": req1}
        new_item = yield self.pipe.process_item(item, self.spider)
        assert new_item is item
        assert new_item["results"] == [(True, {})]

        # rsp2 is ignored, rsp1 must be in results because request fingerprints are the same
        req2 = Request(
            req1.url, meta={"response": Response("http://donot.download.me")}
        )
        item = {"requests": req2}
        new_item = yield self.pipe.process_item(item, self.spider)
        assert new_item is item
        assert self.fingerprint(req1) == self.fingerprint(req2)
        assert new_item["results"] == [(True, {})]

    @inlineCallbacks
    def test_results_are_cached_for_requests_of_single_item(self):
        rsp1 = Response("http://url1")
        req1 = Request("http://url1", meta={"response": rsp1})
        req2 = Request(
            req1.url, meta={"response": Response("http://donot.download.me")}
        )
        item = {"requests": [req1, req2]}
        new_item = yield self.pipe.process_item(item, self.spider)
        assert new_item is item
        assert new_item["results"] == [(True, {}), (True, {})]

    @inlineCallbacks
    def test_wait_if_request_is_downloading(self):
        def _check_downloading(response):
            fp = self.fingerprint(req1)
            assert fp in self.info.downloading
            assert fp in self.info.waiting
            assert fp not in self.info.downloaded
            assert len(self.info.waiting[fp]) == 2
            return response

        rsp1 = Response("http://url")

        def rsp1_func():
            dfd = Deferred().addCallback(_check_downloading)
            reactor.callLater(0.1, dfd.callback, rsp1)
            return dfd

        def rsp2_func():
            pytest.fail("it must cache rsp1 result and must not try to redownload")

        req1 = Request("http://url", meta={"response": rsp1_func})
        req2 = Request(req1.url, meta={"response": rsp2_func})
        item = {"requests": [req1, req2]}
        new_item = yield self.pipe.process_item(item, self.spider)
        assert new_item["results"] == [(True, {}), (True, {})]

    @inlineCallbacks
    def test_use_media_to_download_result(self):
        req = Request("http://url", meta={"result": "ITSME", "response": self.fail})
        item = {"requests": req}
        new_item = yield self.pipe.process_item(item, self.spider)
        assert new_item["results"] == [(True, "ITSME")]
        assert self.pipe._mockcalled == [
            "get_media_requests",
            "media_to_download",
            "item_completed",
        ]

    def test_key_for_pipe(self):
        assert (
            self.pipe._key_for_pipe("IMAGES", base_class_name="MediaPipeline")
            == "MOCKEDMEDIAPIPELINE_IMAGES"
        )


class TestMediaPipelineAllowRedirectSettings:
    def _assert_request_no3xx(self, pipeline_class, settings):
        pipe = pipeline_class(crawler=get_crawler(None, settings))
        request = Request("http://url")
        pipe._modify_media_request(request)

        assert "handle_httpstatus_list" in request.meta
        for status, check in [
            (200, True),
            # These are the status codes we want
            # the downloader to handle itself
            (301, False),
            (302, False),
            (302, False),
            (307, False),
            (308, False),
            # we still want to get 4xx and 5xx
            (400, True),
            (404, True),
            (500, True),
        ]:
            if check:
                assert status in request.meta["handle_httpstatus_list"]
            else:
                assert status not in request.meta["handle_httpstatus_list"]

    def test_subclass_standard_setting(self):
        self._assert_request_no3xx(UserDefinedPipeline, {"MEDIA_ALLOW_REDIRECTS": True})

    def test_subclass_specific_setting(self):
        self._assert_request_no3xx(
            UserDefinedPipeline, {"USERDEFINEDPIPELINE_MEDIA_ALLOW_REDIRECTS": True}
        )


class TestBuildFromCrawler:
    def setup_method(self):
        self.crawler = get_crawler(None, {"FILES_STORE": "/foo"})

    def test_simple(self):
        class Pipeline(UserDefinedPipeline):
            pass

        with warnings.catch_warnings(record=True) as w:
            pipe = Pipeline.from_crawler(self.crawler)
            assert pipe.crawler == self.crawler
            assert pipe._fingerprinter
            assert len(w) == 0

    def test_has_old_init(self):
        class Pipeline(UserDefinedPipeline):
            def __init__(self):
                super().__init__()
                self._init_called = True

        with warnings.catch_warnings(record=True) as w:
            pipe = Pipeline.from_crawler(self.crawler)
            assert pipe.crawler == self.crawler
            assert pipe._fingerprinter
            assert len(w) == 2
            assert pipe._init_called

    def test_has_from_settings(self):
        class Pipeline(UserDefinedPipeline):
            _from_settings_called = False

            @classmethod
            def from_settings(cls, settings):
                o = cls()
                o._from_settings_called = True
                return o

        with warnings.catch_warnings(record=True) as w:
            pipe = Pipeline.from_crawler(self.crawler)
            assert pipe.crawler == self.crawler
            assert pipe._fingerprinter
            assert len(w) == 2
            assert pipe._from_settings_called

    def test_has_from_settings_and_from_crawler(self):
        class Pipeline(UserDefinedPipeline):
            _from_settings_called = False
            _from_crawler_called = False

            @classmethod
            def from_settings(cls, settings):
                o = cls()
                o._from_settings_called = True
                return o

            @classmethod
            def from_crawler(cls, crawler):
                o = super().from_crawler(crawler)
                o._from_crawler_called = True
                return o

        with warnings.catch_warnings(record=True) as w:
            pipe = Pipeline.from_crawler(self.crawler)
            assert pipe.crawler == self.crawler
            assert pipe._fingerprinter
            assert len(w) == 2
            assert pipe._from_settings_called
            assert pipe._from_crawler_called

    def test_has_from_settings_and_init(self):
        class Pipeline(UserDefinedPipeline):
            _from_settings_called = False

            def __init__(self, store_uri, settings):
                super().__init__()
                self._init_called = True

            @classmethod
            def from_settings(cls, settings):
                store_uri = settings["FILES_STORE"]
                o = cls(store_uri, settings=settings)
                o._from_settings_called = True
                return o

        with warnings.catch_warnings(record=True) as w:
            pipe = Pipeline.from_crawler(self.crawler)
            assert pipe.crawler == self.crawler
            assert pipe._fingerprinter
            assert len(w) == 2
            assert pipe._from_settings_called
            assert pipe._init_called

    def test_has_from_crawler_and_init(self):
        class Pipeline(UserDefinedPipeline):
            _from_crawler_called = False

            def __init__(self, store_uri, settings, *, crawler):
                super().__init__(crawler=crawler)
                self._init_called = True

            @classmethod
            def from_crawler(cls, crawler):
                settings = crawler.settings
                store_uri = settings["FILES_STORE"]
                o = cls(store_uri, settings=settings, crawler=crawler)
                o._from_crawler_called = True
                return o

        with warnings.catch_warnings(record=True) as w:
            pipe = Pipeline.from_crawler(self.crawler)
            assert pipe.crawler == self.crawler
            assert pipe._fingerprinter
            assert len(w) == 0
            assert pipe._from_crawler_called
            assert pipe._init_called

    def test_has_from_crawler(self):
        class Pipeline(UserDefinedPipeline):
            _from_crawler_called = False

            @classmethod
            def from_crawler(cls, crawler):
                settings = crawler.settings
                o = super().from_crawler(crawler)
                o._from_crawler_called = True
                o.store_uri = settings["FILES_STORE"]
                return o

        with warnings.catch_warnings(record=True) as w:
            pipe = Pipeline.from_crawler(self.crawler)
            # this and the next assert will fail as MediaPipeline.from_crawler() wasn't called
            assert pipe.crawler == self.crawler
            assert pipe._fingerprinter
            assert len(w) == 0
            assert pipe._from_crawler_called
