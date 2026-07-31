from __future__ import annotations

import tempfile
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock

import pytest
import queuelib

from scrapy.http.request import Request
from scrapy.pqueues import (
    DownloaderAwarePriorityQueue,
    ScrapyPriorityQueue,
    _decode_slot_scopes,
)
from scrapy.spiders import Spider
from scrapy.squeues import FifoMemoryQueue, PickleFifoDiskQueue
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.test import get_crawler
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
        returns."""
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
