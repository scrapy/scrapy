from __future__ import annotations

import logging
import tempfile
from random import Random
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock

import pytest
import queuelib

from scrapy.http.request import Request
from scrapy.pqueues import (
    DownloaderAwarePriorityQueue,
    ScrapyPriorityQueue,
    ThrottlerAwarePriorityQueue,
    _decode_slot_scopes,
)
from scrapy.spiders import Spider
from scrapy.squeues import FifoMemoryQueue, PickleFifoDiskQueue
from scrapy.throttler import iter_scopes
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test
from tests.utils.downloader import MockDownloader

if TYPE_CHECKING:
    from scrapy.http.request import CallbackT


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

    def test_peek_after_draining_a_higher_priority_queue(self):
        """Draining the queue of the current priority while start requests
        remain at a different one must not leave ``curprio`` pointing at a
        priority that no queue has, which would make ``peek()`` come up empty
        with requests still queued."""
        temp_dir = tempfile.mkdtemp()
        queue = ScrapyPriorityQueue.from_crawler(
            self.crawler,
            FifoMemoryQueue,
            temp_dir,
            start_queue_cls=FifoMemoryQueue,
        )
        start_request = Request(
            "https://example.org/start", meta={"is_start_request": True}
        )
        queue.push(start_request)
        # A redirect of a start request, which REDIRECT_PRIORITY_ADJUST puts at
        # a higher priority, i.e. in a separate, non-start queue.
        queue.push(Request("https://example.org/redirect", priority=2))

        assert queue.peek().url == "https://example.org/redirect"
        assert queue.pop().url == "https://example.org/redirect"
        assert queue.peek().url == start_request.url
        assert queue.pop().url == start_request.url
        assert queue.peek() is None
        queue.close()

    def test_peek_agrees_with_pop_on_start_requests(self):
        """A start request and a non-start request at the same priority sit in
        separate queues, and ``peek()`` must report the one that ``pop()``
        returns: ThrottlerAwarePriorityQueue.pop() peeks to decide whether the
        head can be sent, and dequeues it right after."""
        temp_dir = tempfile.mkdtemp()
        queue = ScrapyPriorityQueue.from_crawler(
            self.crawler,
            FifoMemoryQueue,
            temp_dir,
            start_queue_cls=FifoMemoryQueue,
        )
        queue.push(
            Request("https://example.org/start", meta={"is_start_request": True})
        )
        queue.push(Request("https://example.org/other"))

        while len(queue):
            peeked = queue.peek()
            assert queue.pop().url == peeked.url
        queue.close()

    def test_peek_and_pop_skip_an_empty_queue_left_by_a_failed_push(self):
        """A queue is created before the request is pushed into it, so a push
        that fails (e.g. a serialization error) leaves an empty queue behind at
        that priority. Neither ``peek()`` nor ``pop()`` may let it hide the
        request that the other dict holds at the same priority."""
        temp_dir = tempfile.mkdtemp()
        queue = ScrapyPriorityQueue.from_crawler(
            self.crawler,
            PickleFifoDiskQueue,
            temp_dir,
            start_queue_cls=PickleFifoDiskQueue,
        )
        unserializable = Request(
            "https://example.org/lambda",
            callback=cast("CallbackT", lambda response: None),
        )
        with pytest.raises(ValueError, match="is not an instance method"):
            queue.push(unserializable)
        assert queue.queues[0] is not None  # the empty leftover
        assert len(queue) == 0

        start_request = Request(
            "https://example.org/start", meta={"is_start_request": True}
        )
        queue.push(start_request)
        assert len(queue) == 1
        assert queue.peek().url == start_request.url
        assert queue.pop().url == start_request.url
        assert len(queue) == 0
        assert queue.peek() is None
        assert queue.pop() is None
        queue.close()

    def test_empty_queues_are_dropped_on_refresh(self):
        """The empty leftover of a failed push is forgotten (and closed) the
        next time the current priority is refreshed, rather than kept around
        holding its storage open."""
        temp_dir = tempfile.mkdtemp()
        queue = ScrapyPriorityQueue.from_crawler(
            self.crawler, PickleFifoDiskQueue, temp_dir
        )
        with pytest.raises(ValueError, match="is not an instance method"):
            queue.push(
                Request(
                    "https://example.org/lambda",
                    callback=cast("CallbackT", lambda response: None),
                )
            )
        assert set(queue.queues) == {0}  # the empty leftover
        # A request at a different priority, whose queue emptying is what
        # triggers the refresh.
        queue.push(Request("https://example.org/1", priority=1))
        assert queue.pop().url == "https://example.org/1"
        assert queue.queues == {}
        assert queue.curprio is None
        assert queue.pop() is None
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
        throttler = self.queue._throttler
        assert throttler is not None

        req_a = Request("https://example.org/a")
        req_a.meta["throttling_scopes"] = "slot-a"
        req_b = Request("https://example.org/b")
        req_b.meta["throttling_scopes"] = "slot-b"
        req_c = Request("https://example.org/c")
        req_c.meta["throttling_scopes"] = "slot-c"

        for req in (req_a, req_b, req_c):
            self.queue.push(req)

        throttler.get_scope_manager("slot-a")._active = 1
        throttler.get_scope_manager("slot-c")._active = 1

        popped = self.queue.pop()
        assert popped.url == req_b.url

    def test_pop_prefers_the_slot_whose_busiest_scope_is_least_loaded(self):
        # A slot holding requests with several throttling scopes cannot be
        # dequeued faster than its busiest scope allows, so that is its load,
        # even when its other scopes are idle.
        throttler = self.queue._throttler
        assert throttler is not None

        req_multi = Request("https://example.org/multi")
        req_multi.meta["throttling_scopes"] = ["quiet", "busy"]
        req_single = Request("https://example.org/single")
        req_single.meta["throttling_scopes"] = "middling"

        for req in (req_multi, req_single):
            self.queue.push(req)

        throttler.get_scope_manager("busy")._active = 4
        throttler.get_scope_manager("middling")._active = 1

        # 'quiet' is idle, but 'busy' is what holds the multi-scope slot back.
        assert self.queue.pop().url == req_single.url
        assert self.queue.pop().url == req_multi.url

    def test_restored_slot_reads_the_load_of_its_scopes(self):
        # A slot restored from a previous run is never pushed to, so the scopes
        # it stands for can only come from its key; without them it would read as
        # unloaded for as long as it lasts.
        crawler = get_crawler(Spider)
        crawler.engine = Mock(downloader=MockDownloader())
        assert crawler.throttler is not None
        crawler.throttler.get_scope_manager("busy")._active = 4
        queue = DownloaderAwarePriorityQueue.from_crawler(
            crawler=crawler,
            downstream_queue_cls=FifoMemoryQueue,
            key="foo/bar",
            startprios={'["busy", "quiet"]': [0], "quiet": [0]},
        )
        try:
            assert {slot: load for load, slot in queue._slot_stats()} == {
                '["busy", "quiet"]': 0.5,
                "quiet": 0.0,
            }
        finally:
            queue.close()

    def test_contains(self):
        req = Request("https://example.org/")
        req.meta["throttling_scopes"] = "example-slot"
        assert "example-slot" not in self.queue
        self.queue.push(req)
        assert "example-slot" in self.queue
        assert "other-slot" not in self.queue

    def test_slot_scopes_are_dropped_with_their_slot(self):
        req = Request("https://example.org/")
        req.meta["throttling_scopes"] = "example-slot"
        self.queue.push(req)
        assert self.queue._slot_scopes == {"example-slot": ("example-slot",)}
        self.queue.pop()
        assert self.queue._slot_scopes == {}


@pytest.mark.parametrize(
    ("slot", "expected"),
    [
        # No scope, a single scope, and several scopes, as get_scopes_key()
        # encodes them.
        ("", ()),
        ("example.com", ("example.com",)),
        ('["a", "b"]', ("a", "b")),
        # Keys that only look like an encoded scope list are single scopes.
        ("[not json", ("[not json",)),
        ("[1, 2]", ("[1, 2]",)),
        ('["a", "b"] and more', ('["a", "b"] and more',)),
    ],
)
def test_slot_scopes(slot: str, expected: tuple[str, ...]) -> None:
    assert _decode_slot_scopes(slot) == expected


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
    def _queue(self, crawler, key="", start_queue_cls=None, downstream_queue_cls=None):
        return build_from_crawler(
            ThrottlerAwarePriorityQueue,
            crawler,
            downstream_queue_cls=downstream_queue_cls or FifoMemoryQueue,
            key=key,
            start_queue_cls=start_queue_cls,
        )

    async def _push(self, queue, crawler, request):
        scope_set = frozenset(iter_scopes(await crawler.throttler.get_scopes(request)))
        queue.push(request, scope_set)

    @staticmethod
    def _assert_bands(queue):
        """The band index must always match what a fresh scan would build: a
        scope set filed in the wrong band, or in none, is one whose requests
        _select() would never hand out."""
        expected = {}
        for scope_set, pqueue in queue.pqueues.items():
            head = pqueue.peek()
            if head is None:
                continue
            expected.setdefault(pqueue.priority(head), {})[scope_set] = None
        assert queue._bands == expected
        assert queue._band_of == {
            scope_set: band
            for band, members in expected.items()
            for scope_set in members
        }

    @staticmethod
    def _assert_optimal_selection(queue, throttler):
        """Visiting candidates band by band, and stopping early, must still land
        on a best ``(priority, load)`` candidate: the same one an exhaustive scan
        of every pending scope set would settle for."""
        best = None
        for scope_set, pqueue in queue.pqueues.items():
            head = pqueue.peek()
            if head is None or not throttler.is_ready(head):
                continue
            load = max(
                (throttler.get_scope_load(scope_id) for scope_id in scope_set),
                default=0.0,
            )
            key = (pqueue.priority(head), load)
            if best is None or key < best:
                best = key
        selected = queue._select()
        if best is None:
            assert selected is None
            return
        assert selected is not None
        scope_set, pqueue = selected
        head = pqueue.peek()
        load = max(
            (throttler.get_scope_load(scope_id) for scope_id in scope_set),
            default=0.0,
        )
        assert (pqueue.priority(head), load) == best

    @coroutine_test
    async def test_band_index_tracks_every_push_and_pop(self):
        # A randomized mix of priorities, scope sets and start requests, with
        # pops interleaved and some requests left in flight so that scope loads
        # vary, checking after every operation that the index is intact, that
        # selection stays optimal, and that everything comes back out in the end.
        random = Random(0)
        crawler = get_crawler(Spider, {"THROTTLING_SCOPE_CONCURRENCY": 4})
        throttler = crawler.throttler
        queue = self._queue(crawler, start_queue_cls=FifoMemoryQueue)
        pushed, popped, in_flight = [], [], []
        for i in range(400):
            roll = random.random()
            if pushed and roll < 0.4:
                request = queue.pop()
                if request is not None:
                    popped.append(request.url)
                    # Hold some of them, so scopes sit at assorted loads and the
                    # load tie-break gets exercised rather than always seeing 0.
                    in_flight.append(request)
            elif in_flight and roll < 0.5:
                throttler.release(in_flight.pop(random.randrange(len(in_flight))))
            else:
                url = f"http://d{random.randrange(6)}.example.com/{i}"
                pushed.append(url)
                await self._push(
                    queue,
                    crawler,
                    Request(
                        url,
                        priority=random.choice([-1, 0, 0, 0, 2]),
                        meta={"is_start_request": random.random() < 0.3},
                    ),
                )
            self._assert_bands(queue)
            self._assert_optimal_selection(queue, throttler)
        for request in in_flight:
            throttler.release(request)
        while (request := queue.pop()) is not None:
            popped.append(request.url)
            throttler.release(request)
            self._assert_bands(queue)
        assert sorted(popped) == sorted(pushed)
        assert queue._bands == {}
        assert queue._band_of == {}
        queue.close()

    @coroutine_test
    async def test_band_index_ignores_a_queue_left_empty_by_a_failed_push(self):
        # A push that fails to serialize leaves an empty queue behind; it has no
        # head, so it belongs to no band and _select() passes over it.
        crawler = get_crawler(Spider)
        temp_dir = tempfile.mkdtemp()
        queue = self._queue(
            crawler, key=temp_dir, downstream_queue_cls=PickleFifoDiskQueue
        )
        with pytest.raises(ValueError, match="is not an instance method"):
            await self._push(
                queue,
                crawler,
                Request("http://a.com/1", callback=cast("CallbackT", lambda r: None)),
            )
        assert queue.pqueues  # the empty leftover
        assert queue._bands == {}
        assert queue.pop() is None
        self._assert_bands(queue)
        queue.close()

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
    async def test_pop_after_draining_a_higher_priority_queue(self):
        """This queue peeks at every scope-set queue on every pop, so a
        scope-set queue left in a state that only pop() can recover from would
        break the whole crawl, not just that queue."""
        crawler = get_crawler(Spider)
        queue = self._queue(crawler, start_queue_cls=FifoMemoryQueue)
        await self._push(
            queue,
            crawler,
            Request("http://a.com/start", meta={"is_start_request": True}),
        )
        await self._push(queue, crawler, Request("http://a.com/redirect", priority=2))

        assert queue.pop().url == "http://a.com/redirect"
        assert queue.pop().url == "http://a.com/start"
        assert queue.pop() is None
        assert len(queue) == 0

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
    async def test_delayed_unserializable_request_dropped(self, caplog):
        # A held-back request defers disk serialization until it is promoted; a
        # non-serializable one is dropped with a warning and a stat bump instead
        # of taking the disk queue down. Dropping is the standalone behavior:
        # under a scheduler it goes to on_unstorable instead (see
        # test_delayed_unserializable_falls_back_to_memory).
        crawler = get_crawler(Spider, settings_dict={"RANDOMIZE_DOWNLOAD_DELAY": False})
        temp_dir = tempfile.mkdtemp()
        queue = build_from_crawler(
            ThrottlerAwarePriorityQueue,
            crawler,
            downstream_queue_cls=PickleFifoDiskQueue,
            key=temp_dir,
        )
        request = Request(
            "http://example.com/slow",
            meta={"delay": 1000.0},
            callback=cast("CallbackT", lambda response: None),
        )
        await self._push(queue, crawler, request)
        assert len(queue) == 1  # held in memory

        with caplog.at_level(logging.WARNING):
            queue._promote_ready(queue._delayed[0][0])

        assert "Unable to serialize request" in caplog.text
        assert crawler.stats is not None
        assert crawler.stats.get_value("scheduler/unserializable") == 1
        assert len(queue) == 0
        queue.close()

    @coroutine_test
    async def test_delayed_unserializable_request_dropped_without_stats(
        self, caplog, monkeypatch
    ):
        # Same as above (no fallback set), but without a stats collector to
        # count the drop.
        crawler = get_crawler(Spider, settings_dict={"RANDOMIZE_DOWNLOAD_DELAY": False})
        temp_dir = tempfile.mkdtemp()
        queue = build_from_crawler(
            ThrottlerAwarePriorityQueue,
            crawler,
            downstream_queue_cls=PickleFifoDiskQueue,
            key=temp_dir,
        )
        request = Request(
            "http://example.com/slow",
            meta={"delay": 1000.0},
            callback=cast("CallbackT", lambda response: None),
        )
        await self._push(queue, crawler, request)
        monkeypatch.setattr(crawler, "stats", None)

        with caplog.at_level(logging.WARNING):
            queue._promote_ready(queue._delayed[0][0])

        assert "Unable to serialize request" in caplog.text
        assert len(queue) == 0
        queue.close()

    @coroutine_test
    async def test_get_next_request_delay_keeps_minimum_over_delayed(self):
        crawler = get_crawler(
            Spider,
            settings_dict={
                "THROTTLING_SCOPES": {"a.com": {"delay": 10.0}},
                "RANDOMIZE_DOWNLOAD_DELAY": False,
            },
        )
        queue = self._queue(crawler)
        await self._push(queue, crawler, Request("http://a.com/1"))
        await self._push(queue, crawler, Request("http://a.com/2"))
        await self._push(
            queue, crawler, Request("http://b.com/1", meta={"delay": 1000.0})
        )
        # Popping the first a.com request makes the second one wait out the
        # per-scope delay.
        assert queue.pop().url == "http://a.com/1"
        # The held-back request is due much later than that, so it does not
        # lower the running minimum.
        assert queue.get_next_request_delay() == pytest.approx(10.0, abs=1.0)

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

    # A state written by another priority queue class has slot names where this
    # one expects scope set keys. A name that is not JSON at all is one case; one
    # that happens to be (a number, a quoted string) is another, and would
    # otherwise be read as a scope set of its own.
    @pytest.mark.parametrize("slot", ["a.com", "123", '"a.com"'])
    def test_foreign_slot_startprios_keys(self, slot: str):
        crawler = get_crawler(Spider)
        with pytest.raises(ValueError, match="same priority queue class"):
            build_from_crawler(
                ThrottlerAwarePriorityQueue,
                crawler,
                downstream_queue_cls=FifoMemoryQueue,
                key="",
                startprios={slot: [1]},
            )
