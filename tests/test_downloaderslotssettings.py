import asyncio
import logging
import warnings
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import pytest

from scrapy import Request
from scrapy.core.downloader import Downloader
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http.request import NO_CALLBACK
from scrapy.throttler import Throttler
from scrapy.utils.asyncio import _wait_for_first, sleep
from scrapy.utils.defer import deferred_from_coro, maybe_deferred_to_future
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.mockserver.http import MockServer
from tests.spiders import MetaSpider, SimpleSpider
from tests.utils.decorators import coroutine_test


class DownloaderSlotsSettingsTestSpider(MetaSpider):
    name = "downloader_slots"

    custom_settings = {
        "DOWNLOAD_SLOTS": {
            "quotes.toscrape.com": {"concurrency": 1},
            "books.toscrape.com": {"concurrency": 2},
        },
    }

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        assert self.mockserver
        self.default_slot = urlparse(self.mockserver.url("/")).hostname
        self.times: dict[str, list[float]] = {}

    async def start(self):
        slots = [*self.custom_settings.get("DOWNLOAD_SLOTS", {}), None]
        for slot in slots:
            url = self.mockserver.url(f"/?downloader_slot={slot}")
            self.times[slot or self.default_slot] = []
            yield Request(url, callback=self.parse, meta={"download_slot": slot})

    def parse(self, response):
        slot = response.meta.get("download_slot", self.default_slot)
        self.times[slot].append(response.meta.get("download_latency"))
        url = self.mockserver.url(f"/?downloader_slot={slot}&req=2")
        yield Request(url, callback=self.not_parse, meta={"download_slot": slot})

    def not_parse(self, response):
        slot = response.meta.get("download_slot", self.default_slot)
        self.times[slot].append(response.meta.get("download_latency"))


class SlotMetaSpider(MetaSpider):
    """Crawls a single URL with a user-set ``download_slot`` meta key."""

    name = "slot_meta"

    def __init__(self, url: str = "", slot: str | None = None, **kwargs: Any):
        super().__init__(**kwargs)
        self._url = url
        self._slot = slot

    async def start(self):
        yield Request(self._url, meta={"download_slot": self._slot})

    def parse(self, response):
        pass


@coroutine_test
async def test_concurrency_key_deprecated():
    settings = {"DOWNLOAD_SLOTS": {"example.com": {"concurrency": 3}}}
    crawler = get_crawler(DefaultSpider, settings_dict=settings)
    crawler.spider = crawler._create_spider()
    with pytest.warns(ScrapyDeprecationWarning) as warns:
        downloader = Downloader(crawler)
    messages = [str(w.message) for w in warns]
    assert any("DOWNLOAD_SLOTS setting is deprecated" in m for m in messages)
    # The deprecated per-slot concurrency is translated into a throttling scope.
    scopes = Throttler._merge_download_slots(crawler.settings)
    assert scopes["example.com"]["concurrency"] == 3
    downloader.close()


@coroutine_test
async def test_download_slots_deprecated():
    settings = {"DOWNLOAD_SLOTS": {"example.com": {"concurrency": 2}}}
    crawler = get_crawler(DefaultSpider, settings_dict=settings)
    crawler.spider = crawler._create_spider()
    with pytest.warns(
        ScrapyDeprecationWarning, match="DOWNLOAD_SLOTS setting is deprecated"
    ):
        Downloader(crawler).close()


@coroutine_test
async def test_slots_deprecated():
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    request = Request("https://example.com")
    request.meta[Downloader.DOWNLOAD_SLOT] = "example.com"
    downloader.active.add(request)
    with pytest.warns(ScrapyDeprecationWarning, match="Downloader.slots is deprecated"):
        slot = downloader.slots.get("example.com")
    assert slot is not None
    assert isinstance(slot.active, set)
    assert request in slot.active
    downloader.active.discard(request)
    downloader.close()


@coroutine_test
async def test_in_downloader_middlewares():
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    request = Request("https://example.com")
    # Not being downloaded at all.
    assert downloader._in_downloader_middlewares(request) is False
    # In the downloader middlewares, holding a concurrency slot it is not using.
    downloader.active.add(request)
    assert downloader._in_downloader_middlewares(request) is True
    # In a download handler.
    downloader._in_download_handler.add(request)
    assert downloader._in_downloader_middlewares(request) is False
    downloader._in_download_handler.discard(request)
    downloader.active.discard(request)
    # Queued for a download handler slot: not in a handler, but past its
    # middlewares and waiting on nothing but the network, so not in the
    # middlewares either.
    downloader.active.add(request)
    downloader._awaiting_download_handler.add(request)
    assert downloader._in_downloader_middlewares(request) is False
    downloader._awaiting_download_handler.discard(request)
    downloader.active.discard(request)
    downloader.close()


@coroutine_test
async def test_a_request_queued_for_a_download_handler_lends_nothing():
    """A request waiting for a download handler slot holds a throttling
    concurrency slot without using the network, but unlike one sitting in the
    downloader middlewares it is not waiting for any prerequisite: it reaches a
    handler on its own. Lending its slot would break no deadlock, and would let
    the borrower still be in a handler once the lender got there, putting more
    requests of the scope in a download handler at once than its concurrency
    allows."""
    crawler = get_crawler(
        DefaultSpider,
        {
            "CONCURRENT_REQUESTS": 4,
            "THROTTLING_SCOPES": {"a.example": {"concurrency": 1}},
        },
    )
    crawler.spider = crawler._create_spider()
    throttler = crawler.throttler
    assert throttler is not None
    downloader = Downloader(crawler)
    crawler.engine = SimpleNamespace(downloader=downloader)

    # Unrelated traffic takes every download handler slot.
    fillers = [Request(f"https://b.example/{i}") for i in range(4)]
    downloader.active.update(fillers)
    downloader._in_download_handler.update(fillers)

    # A request of the throttled scope takes its only concurrency slot, reaches
    # the downloader and queues for a download handler slot.
    holder = Request("https://a.example/1")
    await throttler.acquire(holder)
    downloader.active.add(holder)
    queueing = deferred_from_coro(downloader._await_download_handler(holder))
    for _ in range(10):
        await sleep(0)
    assert not queueing.called
    assert downloader._in_downloader_middlewares(holder) is False

    # A prerequisite of the same scope finds nothing to borrow.
    prerequisite = Request("https://a.example/robots.txt")
    blocked = deferred_from_coro(throttler.acquire(prerequisite, unscheduled=True))
    for _ in range(10):
        await sleep(0)
    assert not blocked.called
    assert prerequisite not in throttler._reserved
    assert crawler.stats
    assert crawler.stats.get_value("throttler/borrowed_slots") is None

    blocked.addBoth(lambda _: None)
    blocked.cancel()
    queueing.addBoth(lambda _: None)
    queueing.cancel()
    downloader.close()


@coroutine_test
async def test_a_lender_waits_for_its_loan_before_reaching_a_download_handler():
    """A slot lent to a prerequisite is lent by a request that is not using the
    network, but nothing stops that request from reaching a download handler
    again while the borrower is still in one. The download handler check does: a
    scope never has more requests in a handler at once than its concurrency
    allows."""
    crawler = get_crawler(
        DefaultSpider,
        {
            "CONCURRENT_REQUESTS": 4,
            "THROTTLING_SCOPES": {"a.example": {"concurrency": 1}},
        },
    )
    crawler.spider = crawler._create_spider()
    throttler = crawler.throttler
    assert throttler is not None
    downloader = Downloader(crawler)
    crawler.engine = SimpleNamespace(downloader=downloader)

    # A request of the scope takes its only slot and waits on the middlewares.
    lender = Request("https://a.example/1")
    await throttler.acquire(lender)
    downloader.active.add(lender)
    assert downloader._in_downloader_middlewares(lender) is True

    # Its unused slot goes to a prerequisite, which reaches the network.
    borrower = Request("https://a.example/robots.txt")
    await throttler.acquire(borrower, unscheduled=True)
    assert crawler.stats
    assert crawler.stats.get_value("throttler/borrowed_slots") == 1
    downloader.active.add(borrower)
    await downloader._await_download_handler(borrower)
    downloader._in_download_handler.add(borrower)

    # The lender's middlewares are done with it, for a reason of their own rather
    # than the borrower finishing, so it now wants the network too.
    reaching_a_handler = deferred_from_coro(downloader._await_download_handler(lender))
    for _ in range(10):
        await sleep(0)
    assert not reaching_a_handler.called, (
        "the lender joined the borrower in a download handler, above the scope "
        "concurrency"
    )
    assert throttler.download_handler_blocked(lender) is True

    # Once the loan comes back, it goes.
    downloader._leave_download_handler(borrower)
    throttler.release(borrower)
    done, _ = await _wait_for_first([reaching_a_handler], timeout=30)
    assert done, "the lender was left waiting after the borrower was done"
    await maybe_deferred_to_future(reaching_a_handler)
    assert throttler.download_handler_blocked(lender) is False
    downloader.close()


@coroutine_test
async def test_download_handler_gate_ignores_unthrottled_requests():
    crawler = get_crawler(DefaultSpider, {"CONCURRENT_REQUESTS": 4})
    crawler.spider = crawler._create_spider()
    throttler = crawler.throttler
    assert throttler is not None
    downloader = Downloader(crawler)
    crawler.engine = SimpleNamespace(downloader=downloader)
    # A request that reserved nothing (dont_throttle, or no scopes at all) has no
    # scope to exceed.
    excluded = Request("https://a.example/1", meta={"dont_throttle": True})
    await throttler.acquire(excluded)
    assert throttler.download_handler_blocked(excluded) is False
    downloader.close()


@coroutine_test
async def test_download_handler_gate_without_an_engine():
    crawler = get_crawler(
        DefaultSpider, {"THROTTLING_SCOPES": {"a.example": {"concurrency": 1}}}
    )
    crawler.spider = crawler._create_spider()
    throttler = crawler.throttler
    assert throttler is not None
    # With no engine there is no downloader, and hence no download handler to
    # hold the request off.
    request = Request("https://a.example/1")
    await throttler.acquire(request)
    assert throttler.download_handler_blocked(request) is False


@coroutine_test
async def test_download_handler_gate_logs_when_debugging(caplog):
    crawler = get_crawler(
        DefaultSpider,
        {
            "THROTTLING_SCOPES": {"a.example": {"concurrency": 1}},
            "THROTTLER_DEBUG": True,
        },
    )
    crawler.spider = crawler._create_spider()
    throttler = crawler.throttler
    assert throttler is not None
    downloader = Downloader(crawler)
    crawler.engine = SimpleNamespace(downloader=downloader)

    # Two requests hold a slot of a scope that has room for one, which is what
    # lending a slot out leads to (see
    # test_a_lender_waits_for_its_loan_before_reaching_a_download_handler), and
    # the borrower is on the network.
    lender = Request("https://a.example/1")
    borrower = Request("https://a.example/robots.txt")
    await throttler.acquire(lender)
    downloader.active.add(lender)
    await throttler.acquire(borrower, unscheduled=True)
    downloader._in_download_handler.add(borrower)

    with caplog.at_level(logging.DEBUG, logger="scrapy.throttler"):
        assert throttler.download_handler_blocked(lender) is True
    assert "Holding" in caplog.text
    downloader.close()


class UnscheduledFloodSpider(MetaSpider):
    """Send many requests without going through the scheduler at once, like a
    media pipeline does for the files of an item."""

    name = "unscheduled_flood"
    request_count = 8

    custom_settings = {
        "CONCURRENT_REQUESTS": 2,
        # High enough that per-scope throttling is not what bounds anything.
        "THROTTLING_SCOPE_CONCURRENCY": 100,
    }

    peak_in_download_handler = 0

    async def start(self):
        assert self.mockserver
        yield Request(self.mockserver.url("/status?n=200"), callback=self.parse)

    async def parse(self, response):
        assert self.mockserver
        assert self.crawler.engine
        downloader = self.crawler.engine.downloader

        async def watch() -> None:
            for _ in range(100):
                type(self).peak_in_download_handler = max(
                    type(self).peak_in_download_handler,
                    len(downloader._in_download_handler),
                )
                await sleep(0.02)

        watcher = asyncio.ensure_future(watch())
        await asyncio.gather(
            *(
                self.crawler.engine.download_async(
                    Request(
                        self.mockserver.url(f"/delay?n=0.2&i={i}"),
                        callback=NO_CALLBACK,
                        dont_filter=True,
                    )
                )
                for i in range(self.request_count)
            )
        )
        await watcher


@pytest.mark.only_asyncio
@coroutine_test
async def test_unscheduled_requests_are_bound_by_concurrent_requests():
    with MockServer() as mockserver:
        crawler = get_crawler(UnscheduledFloodSpider)
        await crawler.crawl_async(mockserver=mockserver)
    assert crawler.stats
    # Every request went out, but never more than CONCURRENT_REQUESTS at a time.
    assert (
        crawler.stats.get_value("downloader/request_count")
        == UnscheduledFloodSpider.request_count + 1
    )
    assert UnscheduledFloodSpider.peak_in_download_handler == 2


@coroutine_test
async def test_unlimited_concurrent_requests():
    """A CONCURRENT_REQUESTS of 0 means no global limit, so neither the engine
    nor the downloader holds anything back."""
    crawler = get_crawler(DefaultSpider, {"CONCURRENT_REQUESTS": 0})
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    assert downloader.needs_backout() is False
    downloader.active.update(Request(f"https://example.com/{i}") for i in range(100))
    assert downloader.needs_backout() is False
    assert downloader._download_handler_slots_full() is False
    downloader.active.clear()
    downloader.close()

    with MockServer() as mockserver:
        crawler = get_crawler(SimpleSpider, settings_dict={"CONCURRENT_REQUESTS": 0})
        crawl = deferred_from_coro(
            crawler.crawl_async(mockserver.url("/status?n=200"), mockserver=mockserver)
        )
        # A bounded wait, so that a regression fails instead of hanging.
        done, _ = await _wait_for_first([crawl], timeout=30)
        assert done, "the crawl stalled instead of running without a limit"
        await maybe_deferred_to_future(crawl)
    assert crawler.stats
    assert crawler.stats.get_value("response_received_count") == 1


@coroutine_test
async def test_download_handler_slots_do_not_deadlock_on_robotstxt():
    """With room for a single request in a download handler, a request sitting in
    the downloader middlewares while they download its robots.txt holds no
    download handler slot, so the robots.txt request can be handled and the crawl
    goes on."""
    with MockServer() as mockserver:
        crawler = get_crawler(
            SimpleSpider,
            settings_dict={
                "CONCURRENT_REQUESTS": 1,
                "ROBOTSTXT_OBEY": True,
            },
        )
        crawl = deferred_from_coro(
            crawler.crawl_async(mockserver.url("/status?n=200"), mockserver=mockserver)
        )
        # A bounded wait, so that a regression fails instead of hanging.
        done, _ = await _wait_for_first([crawl], timeout=30)
        assert done, "the crawl deadlocked waiting for a download handler slot"
        await maybe_deferred_to_future(crawl)
    assert crawler.stats
    assert crawler.stats.get_value("robotstxt/request_count") == 1
    assert crawler.stats.get_value("response_received_count") == 2


@coroutine_test
async def test_downloader_middlewares_event():
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    request = Request("https://example.com")
    downloader._in_download_handler.add(request)
    event = downloader._downloader_middlewares_event()
    assert not event.called
    # Leaving the download handler puts the request back in the downloader
    # middlewares for as long as they process its outcome.
    downloader._leave_download_handler(request)
    assert event.called
    assert request not in downloader._in_download_handler
    downloader.close()


@coroutine_test
async def test_discard_downloader_middlewares_event():
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    event = downloader._downloader_middlewares_event()
    downloader._discard_downloader_middlewares_event(event)
    assert downloader._downloader_middlewares_entry._waiters == []
    # Discarding an event that is no longer tracked is a no-op.
    downloader._discard_downloader_middlewares_event(event)
    # The dropped event is not fired by a later request reaching the
    # middlewares.
    request = Request("https://example.com")
    downloader._in_download_handler.add(request)
    downloader._leave_download_handler(request)
    assert not event.called
    downloader.close()


@coroutine_test
async def test_close_releases_download_handler_waiters():
    crawler = get_crawler(DefaultSpider, {"CONCURRENT_REQUESTS": 1})
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    downloader._in_download_handler.add(Request("https://example.com/1"))
    waiting = deferred_from_coro(
        downloader._await_download_handler(Request("https://example.com/2"))
    )
    await sleep(0)
    assert not waiting.called, "the only download handler slot is taken"
    # No request will ever leave a download handler now, so the wait ends
    # instead of being left hanging.
    downloader.close()
    done, _ = await _wait_for_first([waiting], timeout=30)
    assert done, "closing the downloader left a download handler slot wait hanging"
    await maybe_deferred_to_future(waiting)


@coroutine_test
async def test_await_download_handler_after_close():
    crawler = get_crawler(DefaultSpider, {"CONCURRENT_REQUESTS": 1})
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    downloader._in_download_handler.add(Request("https://example.com/1"))
    downloader.close()
    # A closed downloader does not hold anything back before a download
    # handler.
    await downloader._await_download_handler(Request("https://example.com/2"))


@coroutine_test
async def test_deprecated_downloader_properties():
    crawler = get_crawler(
        DefaultSpider,
        settings_dict={
            "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
            "RANDOMIZE_DOWNLOAD_DELAY": True,
        },
    )
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    with pytest.warns(
        ScrapyDeprecationWarning, match="Downloader.domain_concurrency is deprecated"
    ):
        assert downloader.domain_concurrency == 4
    with pytest.warns(
        ScrapyDeprecationWarning, match="Downloader.randomize_delay is deprecated"
    ):
        assert downloader.randomize_delay is True
    downloader.close()


@coroutine_test
async def test_deprecated_slot_view():
    crawler = get_crawler(
        DefaultSpider,
        settings_dict={
            "THROTTLING_SCOPES": {
                "example.com": {"delay": 2.0, "concurrency": 3, "jitter": 0.5}
            }
        },
    )
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    request = Request("https://example.com")
    request.meta[Downloader.DOWNLOAD_SLOT] = "example.com"
    downloader.active.add(request)

    with pytest.warns(ScrapyDeprecationWarning, match="Downloader.slots is deprecated"):
        slots = downloader.slots
    assert list(slots) == ["example.com"]
    assert len(slots) == 1
    assert "example.com" in slots
    with pytest.raises(KeyError):
        slots["missing"]

    slot = slots["example.com"]
    assert repr(slot) == "_DeprecatedSlotView('example.com')"
    assert slot.delay == 2.0
    assert slot.randomize_delay is True
    assert slot.lastseen == 0.0
    assert request in slot.active
    assert slot.free_transfer_slots() == 3
    assert 1.0 <= slot.download_delay() <= 3.0
    with pytest.warns(ScrapyDeprecationWarning, match="Slot.concurrency is deprecated"):
        assert slot.concurrency == 3
    # The delay setter writes through to the scope manager.
    slot.delay = 5.0
    assert slot.delay == 5.0
    slot.close()

    downloader.active.discard(request)
    downloader.close()


@coroutine_test
async def test_deprecated_slot_view_without_randomization():
    crawler = get_crawler(
        DefaultSpider,
        settings_dict={
            "THROTTLING_SCOPES": {"example.com": {"delay": 2.0}},
            "RANDOMIZE_DOWNLOAD_DELAY": False,
        },
    )
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    request = Request("https://example.com")
    request.meta[Downloader.DOWNLOAD_SLOT] = "example.com"
    downloader.active.add(request)

    with pytest.warns(ScrapyDeprecationWarning, match="Downloader.slots is deprecated"):
        slots = downloader.slots
    slot = slots["example.com"]
    # Without randomization the reported delay is the plain scope delay.
    assert slot.randomize_delay is False
    assert slot.download_delay() == 2.0

    downloader.active.discard(request)
    downloader.close()


@coroutine_test
async def test_get_slot_key_deprecated():
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    with pytest.warns(
        ScrapyDeprecationWarning,
        match=r"Downloader\.get_slot_key\(\) is deprecated",
    ):
        assert downloader.get_slot_key(Request("https://example.com")) == "example.com"
    request = Request("https://example.com")
    request.meta[Downloader.DOWNLOAD_SLOT] = "custom"
    with pytest.warns(
        ScrapyDeprecationWarning,
        match=r"Downloader\.get_slot_key\(\) is deprecated",
    ):
        assert downloader.get_slot_key(request) == "custom"
    downloader.close()


@coroutine_test
async def test_download_slot_meta_deprecated():
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    request = Request("https://example.com")
    request.meta["download_slot"] = "custom"
    with pytest.warns(
        ScrapyDeprecationWarning, match="'download_slot' request meta key is deprecated"
    ):
        key = downloader._get_slot_key(request)
    downloader.close()
    assert key == "custom"


@coroutine_test
async def test_inherited_download_slot_meta_not_deprecated():
    """The downloader sets download_slot on every request it handles, and a
    redirect inherits it along with the rest of its meta, so it must not be
    reported as a deprecated user-set value."""
    with MockServer() as mockserver:
        crawler = get_crawler(SimpleSpider)
        url = mockserver.url(f"/redirect-to?goto={mockserver.url('/status?n=200')}")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            await crawler.crawl_async(url, mockserver=mockserver)
    assert crawler.stats
    assert crawler.stats.get_value("response_received_count") == 1
    assert crawler.stats.get_value("downloader/request_count") == 2
    assert not [
        str(w.message)
        for w in caught
        if "'download_slot' request meta key is deprecated" in str(w.message)
    ]


@coroutine_test
async def test_cross_host_redirect_gets_the_scope_of_its_own_host():
    """The download_slot the downloader records is bookkeeping, not intent, so a
    redirect that inherits it must still be throttled under its own host rather
    than under the host of the request it came from."""
    with MockServer() as mockserver:
        crawler = get_crawler(SimpleSpider)
        # Same server under a different host name, so the redirect crosses hosts.
        target = mockserver.url("/status?n=200").replace("127.0.0.1", "localhost")
        url = mockserver.url(f"/redirect-to?goto={target}")
        await crawler.crawl_async(url, mockserver=mockserver)
    assert crawler.stats
    assert crawler.stats.get_value("downloader/request_count") == 2
    throttler = crawler.throttler
    assert isinstance(throttler, Throttler)
    assert set(throttler._scope_managers) == {"127.0.0.1", "localhost"}


@coroutine_test
async def test_user_download_slot_survives_a_cross_host_redirect():
    """Unlike the value the downloader records, a download_slot a user set is
    intent, so it keeps applying to the requests derived from that one, even
    across hosts."""
    with MockServer() as mockserver:
        crawler = get_crawler(SlotMetaSpider)
        target = mockserver.url("/status?n=200").replace("127.0.0.1", "localhost")
        url = mockserver.url(f"/redirect-to?goto={target}")
        with pytest.warns(
            ScrapyDeprecationWarning,
            match="'download_slot' request meta key is deprecated",
        ):
            await crawler.crawl_async(url, slot="custom", mockserver=mockserver)
    assert crawler.stats
    assert crawler.stats.get_value("downloader/request_count") == 2
    throttler = crawler.throttler
    assert isinstance(throttler, Throttler)
    assert set(throttler._scope_managers) == {"custom"}


@coroutine_test
async def test_delay_deprecated():
    settings = {
        "DOWNLOAD_SLOTS": {"example.com": {"delay": 2, "randomize_delay": False}}
    }
    crawler = get_crawler(DefaultSpider, settings_dict=settings)
    crawler.spider = crawler._create_spider()
    with pytest.warns(ScrapyDeprecationWarning) as warns:
        downloader = Downloader(crawler)
    messages = [str(w.message) for w in warns]
    assert any("DOWNLOAD_SLOTS setting is deprecated" in m for m in messages)
    # The deprecated per-slot delay/randomize_delay are translated into a
    # throttling scope.
    assert crawler.throttler is not None
    scope = crawler.throttler.get_scope_manager("example.com")
    assert scope.get_base_delay() == 2.0
    downloader.close()


@pytest.mark.parametrize(
    "priority_queue_class",
    [
        "scrapy.pqueues.ScrapyPriorityQueue",
        "scrapy.pqueues.DownloaderAwarePriorityQueue",
    ],
)
@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
@coroutine_test
async def test_none_slot_with_priority_queue(
    mockserver: MockServer, priority_queue_class: str
) -> None:
    """Test specific cases for None slot handling with different priority queues."""
    crawler = get_crawler(
        DownloaderSlotsSettingsTestSpider,
        settings_dict={"SCHEDULER_PRIORITY_QUEUE": priority_queue_class},
    )
    await crawler.crawl_async(mockserver=mockserver)
    assert isinstance(crawler.spider, DownloaderSlotsSettingsTestSpider)

    assert hasattr(crawler.spider, "times")
    assert None not in crawler.spider.times
    assert crawler.spider.default_slot in crawler.spider.times
    assert len(crawler.spider.times[crawler.spider.default_slot]) == 2

    assert crawler.stats
    stats = crawler.stats
    assert stats.get_value("spider_exceptions", 0) == 0
    assert stats.get_value("downloader/exception_count", 0) == 0
