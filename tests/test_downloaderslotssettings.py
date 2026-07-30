import asyncio
import warnings
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import pytest
from twisted.internet.defer import Deferred

from scrapy import Request
from scrapy.core.downloader import Downloader
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http.request import NO_CALLBACK
from scrapy.throttler import Throttler
from scrapy.utils.asyncio import wait_for_first
from scrapy.utils.defer import deferred_from_coro, maybe_deferred_to_future
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.mockserver.http import MockServer
from tests.spiders import MetaSpider, SimpleSpider
from tests.utils import async_sleep
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
async def test_is_parked():
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    request = Request("https://example.com")
    # Not being downloaded at all.
    assert downloader._is_parked(request) is False
    # In the downloader middlewares, holding a concurrency slot it is not using.
    downloader.active.add(request)
    assert downloader._is_parked(request) is True
    # On the wire.
    downloader._transferring.add(request)
    assert downloader._is_parked(request) is False
    downloader._transferring.discard(request)
    downloader.active.discard(request)
    # Queued for a transfer slot: not on the wire, but past its middlewares and
    # waiting on nothing but the network, so not parked either.
    downloader.active.add(request)
    downloader._awaiting_transfer.add(request)
    assert downloader._is_parked(request) is False
    downloader._awaiting_transfer.discard(request)
    downloader.active.discard(request)
    downloader.close()


@coroutine_test
async def test_a_request_queued_for_a_transfer_slot_lends_nothing():
    """A request waiting for a transfer slot holds a throttling concurrency slot
    without using the network, but unlike a parked one it is not waiting for any
    prerequisite: it gets to the wire on its own. Lending its slot would break no
    deadlock, and would let the borrower still be transferring once the lender
    got there, putting more requests of the scope on the wire at once than its
    concurrency allows."""
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

    # Unrelated traffic takes every transfer slot.
    fillers = [Request(f"https://b.example/{i}") for i in range(4)]
    downloader.active.update(fillers)
    downloader._transferring.update(fillers)

    # A request of the throttled scope takes its only concurrency slot, reaches
    # the downloader and queues for a transfer slot.
    holder = Request("https://a.example/1")
    await throttler.acquire(holder)
    downloader.active.add(holder)
    queueing = deferred_from_coro(downloader._acquire_wire(holder))
    for _ in range(10):
        await async_sleep(0)
    assert not queueing.called
    assert downloader._is_parked(holder) is False

    # A prerequisite of the same scope finds nothing to borrow.
    prerequisite = Request("https://a.example/robots.txt")
    blocked = deferred_from_coro(throttler.acquire(prerequisite, off_cycle=True))
    for _ in range(10):
        await async_sleep(0)
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
async def test_a_lender_waits_for_its_loan_before_going_on_the_wire():
    """A slot lent to a prerequisite is lent by a request that is not using the
    network, but nothing stops that request from reaching the network again while
    the borrower is still on it. The wire gate does: a scope never has more
    requests transferring at once than its concurrency allows."""
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

    # A request of the scope takes its only slot and parks on the middlewares.
    lender = Request("https://a.example/1")
    await throttler.acquire(lender)
    downloader.active.add(lender)
    assert downloader._is_parked(lender) is True

    # Its unused slot goes to a prerequisite, which reaches the network.
    borrower = Request("https://a.example/robots.txt")
    await throttler.acquire(borrower, off_cycle=True)
    assert crawler.stats
    assert crawler.stats.get_value("throttler/borrowed_slots") == 1
    downloader.active.add(borrower)
    await downloader._acquire_wire(borrower)
    downloader._transferring.add(borrower)

    # The lender's middlewares are done with it, for a reason of their own rather
    # than the borrower finishing, so it now wants the network too.
    going_on_the_wire = deferred_from_coro(downloader._acquire_wire(lender))
    for _ in range(10):
        await async_sleep(0)
    assert not going_on_the_wire.called, (
        "the lender joined the borrower on the wire, above the scope concurrency"
    )
    assert throttler.wire_blocked(lender) is True

    # Once the loan comes back, it goes.
    downloader._end_transfer(borrower)
    throttler.release(borrower)
    done, _ = await wait_for_first([going_on_the_wire], timeout=30)
    assert done, "the lender was left waiting after the borrower was done"
    await maybe_deferred_to_future(going_on_the_wire)
    assert throttler.wire_blocked(lender) is False
    downloader.close()


@coroutine_test
async def test_wire_gate_ignores_unthrottled_requests():
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
    assert throttler.wire_blocked(excluded) is False
    downloader.close()


class OffCycleFloodSpider(MetaSpider):
    """Send many requests outside the scheduling cycle at once, like a media
    pipeline does for the files of an item."""

    name = "off_cycle_flood"
    request_count = 8

    custom_settings = {
        "CONCURRENT_REQUESTS": 2,
        # High enough that per-scope throttling is not what bounds anything.
        "THROTTLING_SCOPE_CONCURRENCY": 100,
    }

    peak_transferring = 0

    async def start(self):
        assert self.mockserver
        yield Request(self.mockserver.url("/status?n=200"), callback=self.parse)

    async def parse(self, response):
        assert self.mockserver
        assert self.crawler.engine
        downloader = self.crawler.engine.downloader

        async def watch() -> None:
            for _ in range(100):
                type(self).peak_transferring = max(
                    type(self).peak_transferring, len(downloader._transferring)
                )
                await async_sleep(0.02)

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
async def test_off_cycle_requests_are_bound_by_concurrent_requests():
    with MockServer() as mockserver:
        crawler = get_crawler(OffCycleFloodSpider)
        await crawler.crawl_async(mockserver=mockserver)
    assert crawler.stats
    # Every request went out, but never more than CONCURRENT_REQUESTS at a time.
    assert (
        crawler.stats.get_value("downloader/request_count")
        == OffCycleFloodSpider.request_count + 1
    )
    assert OffCycleFloodSpider.peak_transferring == 2


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
    assert downloader._transfer_slots_full() is False
    downloader.active.clear()
    downloader.close()

    with MockServer() as mockserver:
        crawler = get_crawler(SimpleSpider, settings_dict={"CONCURRENT_REQUESTS": 0})
        crawl = deferred_from_coro(
            crawler.crawl_async(mockserver.url("/status?n=200"), mockserver=mockserver)
        )
        # A bounded wait, so that a regression fails instead of hanging.
        done, _ = await wait_for_first([crawl], timeout=30)
        assert done, "the crawl stalled instead of running without a limit"
        await maybe_deferred_to_future(crawl)
    assert crawler.stats
    assert crawler.stats.get_value("response_received_count") == 1


@coroutine_test
async def test_transfer_slots_do_not_deadlock_on_robotstxt():
    """With room for a single transfer, a request parked on the downloader
    middlewares while they download its robots.txt holds no transfer slot, so
    the robots.txt request can be transferred and the crawl goes on."""
    with MockServer() as mockserver:
        crawler = get_crawler(
            SimpleSpider,
            settings_dict={"CONCURRENT_REQUESTS": 1, "ROBOTSTXT_OBEY": True},
        )
        crawl = deferred_from_coro(
            crawler.crawl_async(mockserver.url("/status?n=200"), mockserver=mockserver)
        )
        # A bounded wait, so that a regression fails instead of hanging.
        done, _ = await wait_for_first([crawl], timeout=30)
        assert done, "the crawl deadlocked waiting for a transfer slot"
        await maybe_deferred_to_future(crawl)
    assert crawler.stats
    assert crawler.stats.get_value("robotstxt/request_count") == 1
    assert crawler.stats.get_value("response_received_count") == 2


@coroutine_test
async def test_fire_transfer_waiters_skips_already_fired():
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    waiter: Deferred[None] = Deferred()
    downloader._transfer_waiters.append(waiter)
    waiter.callback(None)  # fired out-of-band before a slot freed up
    # The already-fired waiter is skipped rather than called a second time
    # (which would raise).
    downloader._fire_transfer_waiters()
    assert downloader._transfer_waiters == []
    downloader.close()


@coroutine_test
async def test_parked_event():
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    request = Request("https://example.com")
    downloader._transferring.add(request)
    event = downloader._parked_event()
    assert not event.called
    # Leaving the wire parks the request for as long as the downloader
    # middlewares process its outcome.
    downloader._end_transfer(request)
    assert event.called
    assert request not in downloader._transferring
    downloader.close()


@coroutine_test
async def test_discard_parked_event():
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    event = downloader._parked_event()
    downloader._discard_parked_event(event)
    assert downloader._parked_waiters == []
    # Discarding an event that is no longer tracked is a no-op.
    downloader._discard_parked_event(event)
    # The dropped event is not fired by a later request being parked.
    request = Request("https://example.com")
    downloader._transferring.add(request)
    downloader._end_transfer(request)
    assert not event.called
    downloader.close()


@coroutine_test
async def test_close_releases_transfer_slot_waiters():
    crawler = get_crawler(DefaultSpider, {"CONCURRENT_REQUESTS": 1})
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    downloader._transferring.add(Request("https://example.com/1"))
    waiting = deferred_from_coro(downloader._acquire_transfer_slot())
    await async_sleep(0)
    assert not waiting.called, "the only transfer slot is taken"
    # Nothing will ever leave the transferring set now, so the wait ends
    # instead of being left hanging.
    downloader.close()
    done, _ = await wait_for_first([waiting], timeout=30)
    assert done, "closing the downloader left a transfer slot wait hanging"
    await maybe_deferred_to_future(waiting)


@coroutine_test
async def test_acquire_transfer_slot_after_close():
    crawler = get_crawler(DefaultSpider, {"CONCURRENT_REQUESTS": 1})
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    downloader._transferring.add(Request("https://example.com/1"))
    downloader.close()
    # A closed downloader does not hold anything back at the transfer gate.
    await downloader._acquire_transfer_slot()


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
