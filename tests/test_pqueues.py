import tempfile
from typing import Any
from unittest.mock import Mock

import pytest
import queuelib

from scrapy.core.downloader import Downloader
from scrapy.http.request import Request
from scrapy.pqueues import DownloaderAwarePriorityQueue, ScrapyPriorityQueue, _path_safe
from scrapy.spiders import Spider
from scrapy.squeues import FifoMemoryQueue, PickleFifoDiskQueue
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.test import get_crawler
from tests.utils.downloader import MockDownloader


def _pop(queue: ScrapyPriorityQueue | DownloaderAwarePriorityQueue) -> Request:
    request = queue.pop()
    assert request is not None
    return request


def _peek(queue: ScrapyPriorityQueue | DownloaderAwarePriorityQueue) -> Request:
    request = queue.peek()
    assert request is not None
    return request


class TestPriorityQueue:
    def setup_method(self):
        self.crawler = get_crawler(Spider)
        self.spider = self.crawler._create_spider("foo")

    def test_queue_push_pop_one(self):
        temp_dir = tempfile.mkdtemp()
        queue = build_from_crawler(
            ScrapyPriorityQueue, self.crawler, FifoMemoryQueue, temp_dir
        )
        assert queue.pop() is None
        assert len(queue) == 0
        req1 = Request("https://example.org/1", priority=1)
        queue.push(req1)
        assert len(queue) == 1
        dequeued = _pop(queue)
        assert len(queue) == 0
        assert dequeued.url == req1.url
        assert dequeued.priority == req1.priority
        assert not queue.close()

    def test_no_peek_raises(self):
        if hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            pytest.skip("queuelib.queue.FifoMemoryQueue.peek is defined")
        temp_dir = tempfile.mkdtemp()
        queue = build_from_crawler(
            ScrapyPriorityQueue, self.crawler, FifoMemoryQueue, temp_dir
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
        queue = build_from_crawler(
            ScrapyPriorityQueue, self.crawler, FifoMemoryQueue, temp_dir
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
        assert _peek(queue).url == req1.url
        assert _pop(queue).url == req1.url
        assert len(queue) == 2
        assert _peek(queue).url == req2.url
        assert _pop(queue).url == req2.url
        assert len(queue) == 1
        assert _peek(queue).url == req3.url
        assert _pop(queue).url == req3.url
        assert not queue.close()

    def test_init_prios_with_start_queue(self):
        temp_dir = tempfile.mkdtemp()
        queue = build_from_crawler(
            ScrapyPriorityQueue,
            self.crawler,
            PickleFifoDiskQueue,
            temp_dir,
            start_queue_cls=PickleFifoDiskQueue,
        )
        req = Request("https://example.org/", meta={"is_start_request": True})
        queue.push(req)
        startprios = queue.close()

        queue2 = build_from_crawler(
            ScrapyPriorityQueue,
            self.crawler,
            PickleFifoDiskQueue,
            temp_dir,
            startprios,
            start_queue_cls=PickleFifoDiskQueue,
        )
        assert len(queue2) == 1
        assert _pop(queue2).url == req.url
        queue2.close()

    def test_queue_push_pop_priorities(self):
        temp_dir = tempfile.mkdtemp()
        queue = build_from_crawler(
            ScrapyPriorityQueue, self.crawler, FifoMemoryQueue, temp_dir, [-1, -2, -3]
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
        dequeued = _pop(queue)
        assert len(queue) == 2
        assert dequeued.url == req3.url
        assert dequeued.priority == req3.priority
        assert set(queue.close()) == {-1, -2}


class TestDownloaderAwarePriorityQueue:
    def setup_method(self):
        crawler = get_crawler(Spider)
        self.downloader = MockDownloader()
        crawler.engine = Mock(downloader=self.downloader)
        self.queue = build_from_crawler(
            DownloaderAwarePriorityQueue,
            crawler,
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
        assert _pop(self.queue).url == req1.url
        assert len(self.queue) == 2
        assert _pop(self.queue).url == req2.url
        assert len(self.queue) == 1
        assert _pop(self.queue).url == req3.url
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
        assert _peek(self.queue).url == req1.url
        assert _pop(self.queue).url == req1.url
        assert len(self.queue) == 2
        assert _peek(self.queue).url == req2.url
        assert _pop(self.queue).url == req2.url
        assert len(self.queue) == 1
        assert _peek(self.queue).url == req3.url
        assert _pop(self.queue).url == req3.url
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
            _pop(self.queue).meta[Downloader.DOWNLOAD_SLOT],
            _pop(self.queue).meta[Downloader.DOWNLOAD_SLOT],
            _pop(self.queue).meta[Downloader.DOWNLOAD_SLOT],
            _pop(self.queue).meta[Downloader.DOWNLOAD_SLOT],
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
            _pop(self.queue).meta[Downloader.DOWNLOAD_SLOT],
            _pop(self.queue).meta[Downloader.DOWNLOAD_SLOT],
            _pop(self.queue).meta[Downloader.DOWNLOAD_SLOT],
            _pop(self.queue).meta[Downloader.DOWNLOAD_SLOT],
        ]

        assert slots == ["slot-a", "slot-b", "slot-c", "slot-a"]

    def test_pop_prefers_slot_with_fewer_active_downloads(self):
        req_a = Request("https://example.org/a")
        req_a.meta[Downloader.DOWNLOAD_SLOT] = "slot-a"
        req_b = Request("https://example.org/b")
        req_b.meta[Downloader.DOWNLOAD_SLOT] = "slot-b"
        req_c = Request("https://example.org/c")
        req_c.meta[Downloader.DOWNLOAD_SLOT] = "slot-c"

        for req in (req_a, req_b, req_c):
            self.queue.push(req)

        self.downloader.increment("slot-a")
        self.downloader.increment("slot-c")

        popped = _pop(self.queue)
        assert popped.url == req_b.url

    def test_contains(self):
        req = Request("https://example.org/")
        req.meta[Downloader.DOWNLOAD_SLOT] = "example-slot"
        assert "example-slot" not in self.queue
        self.queue.push(req)
        assert "example-slot" in self.queue
        assert "other-slot" not in self.queue


def test_slot_directory_removed_when_slot_drains(tmp_path):
    crawler = get_crawler(Spider)
    crawler.spider = crawler._create_spider("foo")
    crawler.engine = Mock(downloader=MockDownloader())
    queue = build_from_crawler(
        DownloaderAwarePriorityQueue,
        crawler,
        downstream_queue_cls=PickleFifoDiskQueue,
        key=str(tmp_path),
    )
    request = Request("https://example.org/1")
    slot_dir = tmp_path / _path_safe("example.org")

    queue.push(request)
    assert slot_dir.is_dir()

    assert _pop(queue).url == request.url
    assert not slot_dir.exists()

    queue.push(request)
    assert slot_dir.is_dir()
    queue.close()


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
    def make_url(index: int) -> str:
        return f"https://toscrape.com/{index}"

    def make_request(index: int, data: dict[str, Any]) -> Request:
        meta: dict[str, Any] = {}
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
    while popped := queue.pop():
        actual_output_urls.append(popped.url)

    assert actual_output_urls == expected_output_urls
