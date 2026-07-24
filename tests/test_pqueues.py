import tempfile
from unittest.mock import Mock

import pytest
import queuelib

from scrapy.http.request import Request
from scrapy.pqueues import (
    DownloaderAwarePriorityQueue,
    ScrapyPriorityQueue,
    ThrottlerAwarePriorityQueue,
)
from scrapy.spiders import Spider
from scrapy.squeues import FifoMemoryQueue, PickleFifoDiskQueue
from scrapy.throttler import iter_scopes
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.test import get_crawler
from tests.test_scheduler import MockDownloader
from tests.utils.decorators import coroutine_test


class TestPriorityQueue:
    def setup_method(self):
        self.crawler = get_crawler(Spider)
        self.spider = self.crawler._create_spider("foo")

    def test_queue_push_pop_one(self):
        temp_dir = tempfile.mkdtemp()
        queue = ScrapyPriorityQueue.from_crawler(
            self.crawler, FifoMemoryQueue, temp_dir
        )
        assert queue.pop() is None
        assert len(queue) == 0
        req1 = Request("https://example.org/1", priority=1)
        queue.push(req1)
        assert len(queue) == 1
        dequeued = queue.pop()
        assert len(queue) == 0
        assert dequeued.url == req1.url
        assert dequeued.priority == req1.priority
        assert not queue.close()

    def test_no_peek_raises(self):
        if hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            pytest.skip("queuelib.queue.FifoMemoryQueue.peek is defined")
        temp_dir = tempfile.mkdtemp()
        queue = ScrapyPriorityQueue.from_crawler(
            self.crawler, FifoMemoryQueue, temp_dir
        )
        queue.push(Request("https://example.org"))
        with pytest.raises(
            NotImplementedError,
            match="The underlying queue class does not implement 'peek'",
        ):
            queue.peek()
        queue.close()

    def test_peek(self):
        if not hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            pytest.skip("queuelib.queue.FifoMemoryQueue.peek is undefined")
        temp_dir = tempfile.mkdtemp()
        queue = ScrapyPriorityQueue.from_crawler(
            self.crawler, FifoMemoryQueue, temp_dir
        )
        assert len(queue) == 0
        assert queue.peek() is None
        req1 = Request("https://example.org/1")
        req2 = Request("https://example.org/2")
        req3 = Request("https://example.org/3")
        queue.push(req1)
        queue.push(req2)
        queue.push(req3)
        assert len(queue) == 3
        assert queue.peek().url == req1.url
        assert queue.pop().url == req1.url
        assert len(queue) == 2
        assert queue.peek().url == req2.url
        assert queue.pop().url == req2.url
        assert len(queue) == 1
        assert queue.peek().url == req3.url
        assert queue.pop().url == req3.url
        assert not queue.close()

    def test_init_prios_with_start_queue(self):
        temp_dir = tempfile.mkdtemp()
        queue = ScrapyPriorityQueue.from_crawler(
            self.crawler,
            PickleFifoDiskQueue,
            temp_dir,
            start_queue_cls=PickleFifoDiskQueue,
        )
        req = Request("https://example.org/", meta={"is_start_request": True})
        queue.push(req)
        startprios = queue.close()

        queue2 = ScrapyPriorityQueue.from_crawler(
            self.crawler,
            PickleFifoDiskQueue,
            temp_dir,
            startprios,
            start_queue_cls=PickleFifoDiskQueue,
        )
        assert len(queue2) == 1
        assert queue2.pop().url == req.url
        queue2.close()

    def test_queue_push_pop_priorities(self):
        temp_dir = tempfile.mkdtemp()
        queue = ScrapyPriorityQueue.from_crawler(
            self.crawler, FifoMemoryQueue, temp_dir, [-1, -2, -3]
        )
        assert queue.pop() is None
        assert len(queue) == 0
        req1 = Request("https://example.org/1", priority=1)
        req2 = Request("https://example.org/2", priority=2)
        req3 = Request("https://example.org/3", priority=3)
        queue.push(req1)
        queue.push(req2)
        queue.push(req3)
        assert len(queue) == 3
        dequeued = queue.pop()
        assert len(queue) == 2
        assert dequeued.url == req3.url
        assert dequeued.priority == req3.priority
        assert set(queue.close()) == {-1, -2}


class TestDownloaderAwarePriorityQueue:
    def setup_method(self):
        crawler = get_crawler(Spider)
        crawler.engine = Mock(downloader=MockDownloader())
        self.queue = DownloaderAwarePriorityQueue.from_crawler(
            crawler=crawler,
            downstream_queue_cls=FifoMemoryQueue,
            key="foo/bar",
        )

    def teardown_method(self):
        self.queue.close()

    def test_push_pop(self):
        assert len(self.queue) == 0
        assert self.queue.pop() is None
        req1 = Request("http://www.example.com/1")
        req2 = Request("http://www.example.com/2")
        req3 = Request("http://www.example.com/3")
        self.queue.push(req1)
        self.queue.push(req2)
        self.queue.push(req3)
        assert len(self.queue) == 3
        assert self.queue.pop().url == req1.url
        assert len(self.queue) == 2
        assert self.queue.pop().url == req2.url
        assert len(self.queue) == 1
        assert self.queue.pop().url == req3.url
        assert len(self.queue) == 0
        assert self.queue.pop() is None

    def test_no_peek_raises(self):
        if hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            pytest.skip("queuelib.queue.FifoMemoryQueue.peek is defined")
        self.queue.push(Request("https://example.org"))
        with pytest.raises(
            NotImplementedError,
            match="The underlying queue class does not implement 'peek'",
        ):
            self.queue.peek()

    def test_peek(self):
        if not hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            pytest.skip("queuelib.queue.FifoMemoryQueue.peek is undefined")
        assert len(self.queue) == 0
        req1 = Request("https://example.org/1")
        req2 = Request("https://example.org/2")
        req3 = Request("https://example.org/3")
        self.queue.push(req1)
        self.queue.push(req2)
        self.queue.push(req3)
        assert len(self.queue) == 3
        assert self.queue.peek().url == req1.url
        assert self.queue.pop().url == req1.url
        assert len(self.queue) == 2
        assert self.queue.peek().url == req2.url
        assert self.queue.pop().url == req2.url
        assert len(self.queue) == 1
        assert self.queue.peek().url == req3.url
        assert self.queue.pop().url == req3.url
        assert self.queue.peek() is None

    def test_tie_breaking_rotates_slots(self):
        # No active downloads are tracked in the downloader, so every slot has
        # the same score and tie-breaking must not starve a slot.
        req_a1 = Request("https://example.org/a1")
        req_a1.meta["throttling_scopes"] = "slot-a"
        req_b1 = Request("https://example.org/b1")
        req_b1.meta["throttling_scopes"] = "slot-b"
        req_a2 = Request("https://example.org/a2")
        req_a2.meta["throttling_scopes"] = "slot-a"
        req_b2 = Request("https://example.org/b2")
        req_b2.meta["throttling_scopes"] = "slot-b"

        for request in (req_a1, req_b1, req_a2, req_b2):
            self.queue.push(request)

        slots = [
            self.queue.pop().meta["throttling_scopes"],
            self.queue.pop().meta["throttling_scopes"],
            self.queue.pop().meta["throttling_scopes"],
            self.queue.pop().meta["throttling_scopes"],
        ]

        assert slots == ["slot-a", "slot-b", "slot-a", "slot-b"]

    def test_tie_breaking_keeps_rotation_after_selected_slot_is_deleted(self):
        # If the selected slot becomes empty, rotation should continue from
        # that slot marker to avoid restarting from the smallest slot.
        req_a1 = Request("https://example.org/a1")
        req_a1.meta["throttling_scopes"] = "slot-a"
        req_a2 = Request("https://example.org/a2")
        req_a2.meta["throttling_scopes"] = "slot-a"
        req_b1 = Request("https://example.org/b1")
        req_b1.meta["throttling_scopes"] = "slot-b"
        req_c1 = Request("https://example.org/c1")
        req_c1.meta["throttling_scopes"] = "slot-c"

        for request in (req_a1, req_a2, req_b1, req_c1):
            self.queue.push(request)

        slots = [
            self.queue.pop().meta["throttling_scopes"],
            self.queue.pop().meta["throttling_scopes"],
            self.queue.pop().meta["throttling_scopes"],
            self.queue.pop().meta["throttling_scopes"],
        ]

        assert slots == ["slot-a", "slot-b", "slot-c", "slot-a"]

    def test_pop_prefers_slot_with_fewer_active_downloads(self):
        throttler = self.queue._downloader_interface._throttler
        assert throttler is not None

        req_a = Request("https://example.org/a")
        req_a.meta["throttling_scopes"] = "slot-a"
        req_b = Request("https://example.org/b")
        req_b.meta["throttling_scopes"] = "slot-b"
        req_c = Request("https://example.org/c")
        req_c.meta["throttling_scopes"] = "slot-c"

        for req in (req_a, req_b, req_c):
            self.queue.push(req)

        throttler._get_scope_manager("slot-a")._active = 1
        throttler._get_scope_manager("slot-c")._active = 1

        popped = self.queue.pop()
        assert popped.url == req_b.url

    def test_contains(self):
        req = Request("https://example.org/")
        req.meta["throttling_scopes"] = "example-slot"
        assert "example-slot" not in self.queue
        self.queue.push(req)
        assert "example-slot" in self.queue
        assert "other-slot" not in self.queue


@pytest.mark.parametrize(
    ("input_", "output"),
    [
        # By default, start requests are FIFO, other requests are LIFO.
        ([{}, {}], [2, 1]),
        ([{"start": True}, {"start": True}], [1, 2]),
        # Priority matters.
        ([{"priority": 1}, {"start": True}], [1, 2]),
        ([{}, {"start": True, "priority": 1}], [2, 1]),
        # For the same priority, start requests pop last.
        ([{}, {"start": True}], [1, 2]),
        ([{"start": True}, {}], [2, 1]),
    ],
)
def test_pop_order(input_, output):
    def make_url(index):
        return f"https://toscrape.com/{index}"

    def make_request(index, data):
        meta = {}
        if data.get("start", False):
            meta["is_start_request"] = True
        return Request(
            url=make_url(index),
            priority=data.get("priority", 0),
            meta=meta,
        )

    input_requests = [
        make_request(index, data) for index, data in enumerate(input_, start=1)
    ]
    expected_output_urls = [make_url(index) for index in output]

    crawler = get_crawler(Spider)
    settings = crawler.settings
    queue = build_from_crawler(
        ScrapyPriorityQueue,
        crawler,
        downstream_queue_cls=load_object(settings["SCHEDULER_MEMORY_QUEUE"]),
        key="",
        start_queue_cls=load_object(settings["SCHEDULER_START_MEMORY_QUEUE"]),
    )

    for request in input_requests:
        queue.push(request)

    actual_output_urls = []
    while request := queue.pop():
        actual_output_urls.append(request.url)

    assert actual_output_urls == expected_output_urls


class TestThrottlerAwarePriorityQueue:
    def _queue(self, crawler, key=""):
        return build_from_crawler(
            ThrottlerAwarePriorityQueue,
            crawler,
            downstream_queue_cls=FifoMemoryQueue,
            key=key,
        )

    async def _push(self, queue, crawler, request):
        scope_set = frozenset(iter_scopes(await crawler.throttler.get_scopes(request)))
        queue.push(request, scope_set)

    @coroutine_test
    async def test_partitions_by_scope_set(self):
        crawler = get_crawler(Spider)
        queue = self._queue(crawler)
        await self._push(queue, crawler, Request("http://a.com/1"))
        await self._push(queue, crawler, Request("http://a.com/2"))
        await self._push(queue, crawler, Request("http://b.com/1"))
        # Two distinct scope sets -> two internal queues, three requests.
        assert len(queue.pqueues) == 2
        assert len(queue) == 3

    @coroutine_test
    async def test_pop_skips_blocked_scope(self):
        crawler = get_crawler(
            Spider,
            settings_dict={
                "THROTTLING_SCOPES": {"slow.com": {"delay": 1000.0}},
                "RANDOMIZE_DOWNLOAD_DELAY": False,
            },
        )
        queue = self._queue(crawler)
        await self._push(queue, crawler, Request("http://slow.com/1"))
        await self._push(queue, crawler, Request("http://slow.com/2"))
        await self._push(queue, crawler, Request("http://fast.com/1"))
        # The first slow request is sendable (no delay accrued yet); after it is
        # popped (and reserved), the second slow request is blocked, but the
        # fast one is still served.
        popped = [queue.pop(), queue.pop(), queue.pop()]
        urls = [r.url if r else None for r in popped]
        assert "http://fast.com/1" in urls
        assert "http://slow.com/1" in urls
        # The blocked second slow request stays in the queue.
        assert None in urls
        assert len(queue) == 1
        delay = queue.get_next_request_delay()
        assert delay is not None
        assert delay == pytest.approx(1000.0, abs=1.0)

    @coroutine_test
    async def test_pop_holds_request_with_delay(self):
        crawler = get_crawler(Spider, settings_dict={"RANDOMIZE_DOWNLOAD_DELAY": False})
        queue = self._queue(crawler)
        await self._push(
            queue,
            crawler,
            Request("http://slow.com/1", meta={"delay": 1000.0}),
        )
        await self._push(queue, crawler, Request("http://fast.com/1"))
        # The delayed request is held back even though its scope is otherwise
        # unconstrained; the request without a delay is served.
        popped = [queue.pop(), queue.pop()]
        urls = [r.url if r else None for r in popped]
        assert "http://fast.com/1" in urls
        assert None in urls
        assert len(queue) == 1
        delay = queue.get_next_request_delay()
        assert delay is not None
        assert delay == pytest.approx(1000.0, abs=1.0)

    @coroutine_test
    async def test_delayed_request_does_not_block_scope_set(self):
        crawler = get_crawler(Spider, settings_dict={"RANDOMIZE_DOWNLOAD_DELAY": False})
        queue = self._queue(crawler)
        # Both requests share the same (example.com) scope set; only the first
        # carries a per-request delay.
        await self._push(
            queue,
            crawler,
            Request("http://example.com/slow", meta={"delay": 1000.0}),
        )
        await self._push(queue, crawler, Request("http://example.com/fast"))
        # The delayed request is held aside, so the other request in the same
        # scope set is served right away instead of being stuck behind it.
        assert queue.pop().url == "http://example.com/fast"
        # The delayed request is not lost, just not poppable yet.
        assert queue.pop() is None
        assert len(queue) == 1
        assert queue.get_next_request_delay() == pytest.approx(1000.0, abs=1.0)

    @coroutine_test
    async def test_delayed_request_promoted_when_due(self):
        crawler = get_crawler(Spider, settings_dict={"RANDOMIZE_DOWNLOAD_DELAY": False})
        queue = self._queue(crawler)
        request = Request("http://example.com/slow", meta={"delay": 1000.0})
        await self._push(queue, crawler, request)
        assert queue.pop() is None  # held back by its per-request delay
        # Once the delay elapses the request is promoted into its scope-set
        # queue, served, and flagged so the delay is not applied a second time.
        queue._promote_ready(queue._delayed[0][0])
        popped = queue.pop()
        assert popped is request
        assert popped.meta["_throttler_delayed"] is True
        assert len(queue) == 0

    @coroutine_test
    async def test_delayed_request_persisted_on_close(self):
        # With a JOBDIR (disk queue), a request held back by its per-request
        # delay must not be lost on a graceful stop: close() flushes it to disk
        # so it is restored on resume.
        crawler = get_crawler(Spider, settings_dict={"RANDOMIZE_DOWNLOAD_DELAY": False})
        temp_dir = tempfile.mkdtemp()
        queue = build_from_crawler(
            ThrottlerAwarePriorityQueue,
            crawler,
            downstream_queue_cls=PickleFifoDiskQueue,
            key=temp_dir,
        )
        await self._push(
            queue,
            crawler,
            Request("http://example.com/slow", meta={"delay": 1000.0}),
        )
        assert len(queue) == 1  # held in memory, not yet in any scope-set queue
        state = queue.close()  # graceful stop

        resumed = build_from_crawler(
            ThrottlerAwarePriorityQueue,
            crawler,
            downstream_queue_cls=PickleFifoDiskQueue,
            key=temp_dir,
            startprios=state,
        )
        assert len(resumed) == 1
        popped = resumed.pop()
        assert popped is not None
        assert popped.url == "http://example.com/slow"
        # Its delay is marked consumed, so it does not re-block on resume.
        assert popped.meta["_throttler_delayed"] is True
        resumed.close()

    @coroutine_test
    async def test_least_loaded_first(self):
        crawler = get_crawler(
            Spider,
            settings_dict={
                "THROTTLING_SCOPES": {
                    "a.com": {"concurrency": 4},
                    "b.com": {"concurrency": 4},
                }
            },
        )
        queue = self._queue(crawler)
        # Make a.com busier than b.com.
        busy = Request("http://a.com/0")
        await crawler.throttler.get_scopes(busy)
        crawler.throttler.reserve(busy)
        await self._push(queue, crawler, Request("http://a.com/1"))
        await self._push(queue, crawler, Request("http://b.com/1"))
        # Equal priority, so the lower-load scope (b.com) is served first.
        assert queue.pop().url == "http://b.com/1"

    @coroutine_test
    async def test_priority_beats_load(self):
        crawler = get_crawler(
            Spider,
            settings_dict={
                "THROTTLING_SCOPES": {
                    "a.com": {"concurrency": 4},
                    "b.com": {"concurrency": 4},
                }
            },
        )
        queue = self._queue(crawler)
        # Make a.com busier than b.com.
        busy = Request("http://a.com/0")
        await crawler.throttler.get_scopes(busy)
        crawler.throttler.reserve(busy)
        # The a.com request has higher priority, and a.com still has room, so it
        # is served first despite a.com being the busier scope.
        await self._push(queue, crawler, Request("http://a.com/1", priority=10))
        await self._push(queue, crawler, Request("http://b.com/1"))
        assert queue.pop().url == "http://a.com/1"

    @coroutine_test
    async def test_empty_and_close(self):
        crawler = get_crawler(Spider)
        queue = self._queue(crawler)
        assert queue.pop() is None
        assert queue.get_next_request_delay() is None
        await self._push(queue, crawler, Request("http://a.com/1"))
        assert queue.close() != {}

    @coroutine_test
    async def test_get_next_request_delay_zero_when_ready(self):
        crawler = get_crawler(Spider)
        queue = self._queue(crawler)
        await self._push(queue, crawler, Request("http://a.com/1"))
        # A sendable head means no wait is needed.
        assert queue.get_next_request_delay() == 0.0

    @coroutine_test
    async def test_get_next_request_delay_ignores_empty_queues(self):
        crawler = get_crawler(Spider)
        queue = self._queue(crawler)
        # An empty (but still registered) internal queue is skipped.
        queue.pqueues[frozenset({"a.com"})] = queue._pqfactory(frozenset({"a.com"}))
        assert queue.get_next_request_delay() is None

    @coroutine_test
    async def test_get_next_request_delay_keeps_minimum(self):
        crawler = get_crawler(
            Spider,
            settings_dict={
                "THROTTLING_SCOPES": {
                    "a.com": {"delay": 10.0},
                    "b.com": {"delay": 1000.0},
                },
                "RANDOMIZE_DOWNLOAD_DELAY": False,
            },
        )
        queue = self._queue(crawler)
        # Two requests per scope so a blocked head remains after the first one
        # (sendable, since no delay has accrued yet) is popped and reserved.
        await self._push(queue, crawler, Request("http://a.com/1"))
        await self._push(queue, crawler, Request("http://a.com/2"))
        await self._push(queue, crawler, Request("http://b.com/1"))
        await self._push(queue, crawler, Request("http://b.com/2"))
        queue.pop()
        queue.pop()
        # Both scopes are now time-blocked; the smaller per-scope delay wins,
        # so the larger one exercises the "not below the running minimum" branch.
        delay = queue.get_next_request_delay()
        assert delay == pytest.approx(10.0, abs=1.0)

    @coroutine_test
    async def test_pop_handles_drained_selected_queue(self):
        crawler = get_crawler(Spider)
        queue = self._queue(crawler)
        await self._push(queue, crawler, Request("http://a.com/1"))
        inner = next(iter(queue.pqueues.values()))
        # _select() still reports a sendable head, but pop() yields nothing: the
        # request-is-None guard must not try to reserve a missing request.
        inner.pop = lambda: None
        assert queue.pop() is None

    def test_non_dict_slot_startprios(self):
        crawler = get_crawler(Spider)
        with pytest.raises(ValueError, match="slot_startprios"):
            build_from_crawler(
                ThrottlerAwarePriorityQueue,
                crawler,
                downstream_queue_cls=FifoMemoryQueue,
                key="",
                startprios=[1, 2, 3],
            )
