import tempfile
from unittest.mock import Mock

import pytest
import queuelib

from scrapy.core.downloader import Downloader
from scrapy.http.request import Request
from scrapy.pqueues import DownloaderAwarePriorityQueue, ScrapyPriorityQueue
from scrapy.spiders import Spider
from scrapy.squeues import FifoMemoryQueue, PickleFifoDiskQueue
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.test import get_crawler
from tests.utils.downloader import MockDownloader


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
        if not hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            pytest.skip("queuelib.queue.FifoMemoryQueue.peek is undefined")
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
        returns, since a caller may peek to decide whether to pop."""
        if not hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            pytest.skip("queuelib.queue.FifoMemoryQueue.peek is undefined")
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
        if not hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            pytest.skip("queuelib.queue.FifoMemoryQueue.peek is undefined")
        temp_dir = tempfile.mkdtemp()
        queue = ScrapyPriorityQueue.from_crawler(
            self.crawler,
            PickleFifoDiskQueue,
            temp_dir,
            start_queue_cls=PickleFifoDiskQueue,
        )
        with pytest.raises(ValueError, match="is not an instance method"):
            queue.push(
                Request("https://example.org/lambda", callback=lambda response: None)
            )
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
                Request("https://example.org/lambda", callback=lambda response: None)
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

    def test_init_prios_without_a_restorable_queue(self):
        """A priority recorded on close may have nothing to restore, e.g. if
        its only request failed to serialize. ``curprio`` must not point at it,
        or ``peek()`` raises :exc:`KeyError` on the resumed crawl."""
        temp_dir = tempfile.mkdtemp()
        queue = ScrapyPriorityQueue.from_crawler(
            self.crawler, PickleFifoDiskQueue, temp_dir
        )
        with pytest.raises(ValueError, match="is not an instance method"):
            queue.push(
                Request("https://example.org/lambda", callback=lambda response: None)
            )
        startprios = queue.close()
        assert startprios == [0]

        queue2 = ScrapyPriorityQueue.from_crawler(
            self.crawler, PickleFifoDiskQueue, temp_dir, startprios
        )
        assert len(queue2) == 0
        assert queue2.curprio is None
        assert queue2.peek() is None
        assert queue2.pop() is None
        queue2.close()

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
        req_a1.meta[Downloader.DOWNLOAD_SLOT] = "slot-a"
        req_b1 = Request("https://example.org/b1")
        req_b1.meta[Downloader.DOWNLOAD_SLOT] = "slot-b"
        req_a2 = Request("https://example.org/a2")
        req_a2.meta[Downloader.DOWNLOAD_SLOT] = "slot-a"
        req_b2 = Request("https://example.org/b2")
        req_b2.meta[Downloader.DOWNLOAD_SLOT] = "slot-b"

        for request in (req_a1, req_b1, req_a2, req_b2):
            self.queue.push(request)

        slots = [
            self.queue.pop().meta[Downloader.DOWNLOAD_SLOT],
            self.queue.pop().meta[Downloader.DOWNLOAD_SLOT],
            self.queue.pop().meta[Downloader.DOWNLOAD_SLOT],
            self.queue.pop().meta[Downloader.DOWNLOAD_SLOT],
        ]

        assert slots == ["slot-a", "slot-b", "slot-a", "slot-b"]

    def test_tie_breaking_keeps_rotation_after_selected_slot_is_deleted(self):
        # If the selected slot becomes empty, rotation should continue from
        # that slot marker to avoid restarting from the smallest slot.
        req_a1 = Request("https://example.org/a1")
        req_a1.meta[Downloader.DOWNLOAD_SLOT] = "slot-a"
        req_a2 = Request("https://example.org/a2")
        req_a2.meta[Downloader.DOWNLOAD_SLOT] = "slot-a"
        req_b1 = Request("https://example.org/b1")
        req_b1.meta[Downloader.DOWNLOAD_SLOT] = "slot-b"
        req_c1 = Request("https://example.org/c1")
        req_c1.meta[Downloader.DOWNLOAD_SLOT] = "slot-c"

        for request in (req_a1, req_a2, req_b1, req_c1):
            self.queue.push(request)

        slots = [
            self.queue.pop().meta[Downloader.DOWNLOAD_SLOT],
            self.queue.pop().meta[Downloader.DOWNLOAD_SLOT],
            self.queue.pop().meta[Downloader.DOWNLOAD_SLOT],
            self.queue.pop().meta[Downloader.DOWNLOAD_SLOT],
        ]

        assert slots == ["slot-a", "slot-b", "slot-c", "slot-a"]

    def test_pop_prefers_slot_with_fewer_active_downloads(self):
        downloader = self.queue._downloader_interface.downloader

        req_a = Request("https://example.org/a")
        req_a.meta[Downloader.DOWNLOAD_SLOT] = "slot-a"
        req_b = Request("https://example.org/b")
        req_b.meta[Downloader.DOWNLOAD_SLOT] = "slot-b"
        req_c = Request("https://example.org/c")
        req_c.meta[Downloader.DOWNLOAD_SLOT] = "slot-c"

        for req in (req_a, req_b, req_c):
            self.queue.push(req)

        downloader.increment("slot-a")
        downloader.increment("slot-c")

        popped = self.queue.pop()
        assert popped.url == req_b.url

    def test_contains(self):
        req = Request("https://example.org/")
        req.meta[Downloader.DOWNLOAD_SLOT] = "example-slot"
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
