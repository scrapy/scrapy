from __future__ import annotations

import logging

import pytest

from scrapy import signals
from scrapy.exceptions import DownloadTimeoutError
from scrapy.http import Request, Response
from scrapy.throttling import ThrottlingManager, ThrottlingScopeManager
from scrapy.utils.defer import deferred_from_coro, maybe_deferred_to_future
from scrapy.utils.test import get_crawler
from tests.spiders import SimpleSpider
from tests.utils.decorators import coroutine_test


def _manager(settings=None):
    crawler = get_crawler(settings_dict=settings)
    return ThrottlingManager.from_crawler(crawler)


def _scope_manager(settings=None, config=None):
    crawler = get_crawler(settings_dict=settings)
    return ThrottlingScopeManager.from_crawler(crawler, config or {"id": "example.com"})


class _FakeRobotParser:
    """A minimal robots.txt parser stub for :signal:`robots_parsed` tests.

    *delay* is returned by :meth:`crawl_delay`, unless it is an exception, in
    which case it is raised to emulate a backend-specific failure.
    """

    def __init__(self, delay):
        self._delay = delay

    def crawl_delay(self, useragent):
        if isinstance(self._delay, Exception):
            raise self._delay
        return self._delay


def _response(status=200, headers=None, url="http://example.com", meta=None):
    request = Request(url, meta=meta or {})
    return Response(url, status=status, headers=headers or {}, request=request)


class TestThrottlingManager:
    @coroutine_test
    async def test_get_scopes_returns_netloc(self):
        manager = _manager()
        assert (
            await manager.get_scopes(Request("http://example.com/a")) == "example.com"
        )

    @coroutine_test
    async def test_get_scopes_cached(self):
        manager = _manager()
        request = Request("http://example.com/a")
        first = await manager.get_scopes(request)
        # A second call returns the cached value (same object identity for dicts,
        # equal value for strings).
        assert await manager.get_scopes(request) == first

    @coroutine_test
    async def test_get_scopes_meta_string(self):
        manager = _manager()
        request = Request("http://example.com/a", meta={"throttling_scopes": "api"})
        assert await manager.get_scopes(request) == "api"

    @coroutine_test
    async def test_get_scopes_meta_dict(self):
        manager = _manager()
        request = Request(
            "http://example.com/a", meta={"throttling_scopes": {"api": 2.0}}
        )
        assert await manager.get_scopes(request) == {"api": 2.0}

    @coroutine_test
    async def test_get_initial_backoff_none(self):
        manager = _manager()
        assert await manager.get_initial_backoff() is None

    def test_scope_manager_class_in_config(self):
        manager = _manager(
            {"THROTTLING_SCOPES": {"example.com": {"manager": ThrottlingScopeManager}}}
        )
        scope = manager._get_scope_manager("example.com")
        assert isinstance(scope, ThrottlingScopeManager)

    def test_release_frees_concurrency(self):
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}})
        scope = manager._get_scope_manager("example.com")
        request = Request("http://example.com")
        scope.record_sent(now=0.0)
        manager._reserved[request] = [(scope, None)]
        assert scope.concurrency_blocked() is True
        manager.release(request)
        assert scope.concurrency_blocked() is False
        # Releasing again is a no-op.
        manager.release(request)
        assert scope.concurrency_blocked() is False

    @coroutine_test
    async def test_acquire_waits_for_freed_slot(self):
        from scrapy.utils.asyncio import call_later  # noqa: PLC0415

        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}})
        r1 = Request("http://example.com/1")
        r2 = Request("http://example.com/2")
        # Drive acquire() the way the engine does, so it runs as a real task that
        # can await the slot event under the asyncio reactor.
        await maybe_deferred_to_future(deferred_from_coro(manager.acquire(r1)))
        scope = manager._get_scope_manager("example.com")
        assert scope.concurrency_blocked() is True
        assert scope.concurrency_blocked() is True
        # acquire(r2) must block until r1 frees the slot; release it on the next
        # event loop tick so the event-driven wait wakes up.
        call_later(0, manager.release, r1)
        await maybe_deferred_to_future(deferred_from_coro(manager.acquire(r2)))
        assert scope.concurrency_blocked() is True
        assert r2 in manager._reserved

    def test_apply_backoff_reconciles_quota_without_backoff(self):
        manager = _manager({"THROTTLING_SCOPES": {"cost": {"quota": 100.0}}})
        scope = manager._get_scope_manager("cost")
        manager._apply_backoff({"cost": {"consumed": 5.0}})
        # Quota was reconciled but no backoff step was applied.
        assert scope._consumed == pytest.approx(5.0)
        assert scope._backoff_level == 0

    def test_apply_backoff_delay_and_consumed(self):
        manager = _manager({"THROTTLING_SCOPES": {"cost": {"quota": 100.0}}})
        scope = manager._get_scope_manager("cost")
        manager._apply_backoff({"cost": {"delay": 5.0, "consumed": 2.0}})
        assert scope._consumed == pytest.approx(2.0)
        assert scope._backoff_level == 1

    @coroutine_test
    async def test_response_backoff_non_backoff_code(self):
        manager = _manager()
        assert await manager.get_response_backoff(_response(status=200)) is None

    @coroutine_test
    async def test_response_backoff_429_without_header(self):
        manager = _manager()
        assert (
            await manager.get_response_backoff(_response(status=429)) == "example.com"
        )

    @pytest.mark.parametrize(
        ("header", "expected_delay"),
        [
            ({"Retry-After": "7"}, 7.0),
            ({"RateLimit-Reset": "12"}, 12.0),
        ],
        ids=["retry-after", "ratelimit-reset"],
    )
    @coroutine_test
    async def test_response_backoff_delay_header(self, header, expected_delay):
        manager = _manager()
        data = await manager.get_response_backoff(_response(status=429, headers=header))
        assert data == {"example.com": {"delay": expected_delay}}

    @coroutine_test
    async def test_response_backoff_retry_after_http_date(self):
        manager = _manager()
        # A date far in the past yields no positive delay.
        data = await manager.get_response_backoff(
            _response(
                status=503,
                headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"},
            )
        )
        assert data == "example.com"

    @coroutine_test
    async def test_response_backoff_max_of_both_headers(self):
        manager = _manager()
        data = await manager.get_response_backoff(
            _response(
                status=429,
                headers={"Retry-After": "5", "RateLimit-Reset": "9"},
            )
        )
        assert data == {"example.com": {"delay": 9.0}}

    @coroutine_test
    async def test_response_backoff_dont_track(self):
        manager = _manager()
        response = _response(status=429, meta={"throttling_dont_track": True})
        assert await manager.get_response_backoff(response) is None

    @pytest.mark.parametrize(
        ("exception", "expected"),
        [
            (DownloadTimeoutError(), "example.com"),
            (ValueError(), None),
        ],
        ids=["tracked", "untracked"],
    )
    @coroutine_test
    async def test_exception_backoff(self, exception, expected):
        manager = _manager()
        request = Request("http://example.com")
        assert await manager.get_exception_backoff(request, exception) == expected

    @coroutine_test
    async def test_exception_backoff_dont_track(self):
        manager = _manager()
        request = Request("http://example.com", meta={"throttling_dont_track": True})
        assert (
            await manager.get_exception_backoff(request, DownloadTimeoutError()) is None
        )

    @pytest.mark.parametrize(
        ("settings", "parser_delay", "expected_base_delay"),
        [
            ({"ROBOTSTXT_OBEY": True, "RANDOMIZE_DOWNLOAD_DELAY": False}, 3.0, 3.0),
            ({"ROBOTSTXT_OBEY": True, "THROTTLING_ROBOTSTXT_OBEY": False}, 3.0, 0.0),
            ({"ROBOTSTXT_OBEY": True}, None, 0.0),
            ({"ROBOTSTXT_OBEY": True}, ValueError(), 0.0),
        ],
        ids=["applies-delay", "obey-disabled", "no-delay", "backend-error"],
    )
    def test_robots_parsed_signal(self, settings, parser_delay, expected_base_delay):
        manager = _manager(settings)
        manager.crawler.signals.send_catch_log(
            signal=signals.robots_parsed,
            robotparser=_FakeRobotParser(parser_delay),
            request=Request("http://example.com/page"),
        )
        scope = manager._get_scope_manager("example.com")
        assert scope._base_delay == expected_base_delay

    def test_apply_robots_crawl_delay(self):
        manager = _manager({"ROBOTSTXT_OBEY": True, "RANDOMIZE_DOWNLOAD_DELAY": False})
        manager.apply_robots_crawl_delay("example.com", 3.0)
        scope = manager._get_scope_manager("example.com")
        assert scope._base_delay == 3.0
        assert scope.can_send(now=0) == 0  # nothing sent yet
        scope.record_sent(now=0)
        assert scope.can_send(now=0) == pytest.approx(3.0)

    def test_apply_robots_crawl_delay_capped(self):
        manager = _manager(
            {"ROBOTSTXT_OBEY": True, "THROTTLING_ROBOTSTXT_MAX_DELAY": 2.0}
        )
        manager.apply_robots_crawl_delay("example.com", 30.0)
        assert manager._get_scope_manager("example.com")._base_delay == 2.0

    def test_apply_robots_crawl_delay_disabled(self):
        manager = _manager({"ROBOTSTXT_OBEY": True, "THROTTLING_ROBOTSTXT_OBEY": False})
        manager.apply_robots_crawl_delay("example.com", 3.0)
        assert manager._get_scope_manager("example.com")._base_delay == 0.0

    def test_apply_robots_crawl_delay_sets_concurrency(self):
        manager = _manager({"ROBOTSTXT_OBEY": True})
        manager.apply_robots_crawl_delay("example.com", 3.0)
        assert manager._get_scope_manager("example.com")._concurrency == 1

    def test_apply_robots_crawl_delay_warns_on_conflict(self, caplog):
        manager = _manager(
            {
                "ROBOTSTXT_OBEY": True,
                "THROTTLING_SCOPES": {"example.com": {"concurrency": 8}},
            }
        )
        with caplog.at_level(logging.WARNING, logger="scrapy.throttling"):
            manager.apply_robots_crawl_delay("example.com", 3.0)
        assert "Crawl-delay" in caplog.text
        # The configured value takes precedence (crawl-delay not applied).
        assert manager._get_scope_manager("example.com")._base_delay == 0.0

    def test_apply_robots_crawl_delay_ignored(self, caplog):
        manager = _manager(
            {
                "ROBOTSTXT_OBEY": True,
                "THROTTLING_SCOPES": {
                    "example.com": {"concurrency": 8, "ignore_robots_txt": True}
                },
            }
        )
        with caplog.at_level(logging.WARNING, logger="scrapy.throttling"):
            manager.apply_robots_crawl_delay("example.com", 3.0)
        # No warning is logged and the crawl-delay is not applied.
        assert "Crawl-delay" not in caplog.text
        assert manager._get_scope_manager("example.com")._base_delay == 0.0

    def test_scope_eviction(self):
        manager = _manager({"THROTTLING_SCOPE_MAX_IDLE": 100.0})
        scope = manager._get_scope_manager("example.com")
        scope.record_sent(now=0.0)
        scope.record_done(now=0.0)
        # Not idle yet.
        manager._last_eviction = None
        manager._maybe_evict(now=50.0)
        assert "example.com" in manager._scope_managers
        # Idle past the threshold.
        manager._last_eviction = None
        manager._maybe_evict(now=201.0)
        assert "example.com" not in manager._scope_managers

    def test_scope_eviction_skips_active_backoff(self):
        manager = _manager(
            {"THROTTLING_SCOPE_MAX_IDLE": 100.0, "BACKOFF_MAX_DELAY": 100_000.0}
        )
        scope = manager._get_scope_manager("example.com")
        scope.record_backoff(delay=10_000.0, now=0.0)
        manager._last_eviction = None
        manager._maybe_evict(now=5_000.0)
        # Still in backoff (in_backoff_until far in the future), so not evicted
        # even though it has been idle for longer than THROTTLING_SCOPE_MAX_IDLE.
        assert "example.com" in manager._scope_managers


class TestThrottlingScopeManager:
    def test_no_delay_by_default(self):
        scope = _scope_manager()
        scope.record_sent(now=0.0)
        assert scope.can_send(now=0.0) == 0

    def test_base_delay_enforced(self):
        scope = _scope_manager(
            {"RANDOMIZE_DOWNLOAD_DELAY": False}, {"id": "x", "delay": 2.0}
        )
        scope.record_sent(now=10.0)
        assert scope.can_send(now=10.0) == pytest.approx(2.0)
        assert scope.can_send(now=11.0) == pytest.approx(1.0)
        assert scope.can_send(now=12.0) == 0

    def test_exponential_backoff(self):
        scope = _scope_manager(
            {
                "BACKOFF_MIN_DELAY": 1.0,
                "BACKOFF_DELAY_FACTOR": 2.0,
                "BACKOFF_JITTER": 0,
            },
        )
        scope.record_backoff(now=0.0)
        assert scope._delay == pytest.approx(1.0)
        scope.record_backoff(now=0.0)
        assert scope._delay == pytest.approx(2.0)
        scope.record_backoff(now=0.0)
        assert scope._delay == pytest.approx(4.0)

    def test_backoff_cap(self):
        scope = _scope_manager(
            {
                "BACKOFF_MIN_DELAY": 1.0,
                "BACKOFF_DELAY_FACTOR": 10.0,
                "BACKOFF_MAX_DELAY": 5.0,
                "BACKOFF_JITTER": 0,
            },
        )
        for _ in range(5):
            scope.record_backoff(now=0.0)
        assert scope._delay == pytest.approx(5.0)

    @pytest.mark.parametrize(
        ("max_delay", "backoff_delay", "expected"),
        [
            (100.0, 20.0, 20.0),
            (10.0, 999.0, 10.0),
        ],
        ids=["within-cap", "capped"],
    )
    def test_retry_after_delay(self, max_delay, backoff_delay, expected):
        scope = _scope_manager({"BACKOFF_MAX_DELAY": max_delay})
        scope.record_backoff(delay=backoff_delay, now=0.0)
        assert scope.can_send(now=0.0) == pytest.approx(expected)

    def test_recovery_after_window(self):
        scope = _scope_manager(
            {
                "BACKOFF_MIN_DELAY": 1.0,
                "BACKOFF_DELAY_FACTOR": 2.0,
                "BACKOFF_WINDOW": 60.0,
                "BACKOFF_JITTER": 0,
            },
        )
        scope.record_backoff(now=0.0)
        scope.record_backoff(now=0.0)
        assert scope._delay == pytest.approx(2.0)
        # One window passes with no new backoff -> one step down.
        scope.can_send(now=60.0)
        assert scope._backoff_level == 1
        assert scope._delay == pytest.approx(1.0)
        # Another window -> back to base (0).
        scope.can_send(now=120.0)
        assert scope._backoff_level == 0
        assert scope._delay == pytest.approx(0.0)

    def test_per_scope_backoff_override(self):
        scope = _scope_manager(
            {"BACKOFF_MIN_DELAY": 1.0, "BACKOFF_DELAY_FACTOR": 2.0},
            {
                "id": "x",
                "backoff": {"min_delay": 5.0, "delay_factor": 3.0, "jitter": 0},
            },
        )
        scope.record_backoff(now=0.0)
        assert scope._delay == pytest.approx(5.0)
        scope.record_backoff(now=0.0)
        assert scope._delay == pytest.approx(15.0)

    def test_set_base_delay_raises_only(self):
        scope = _scope_manager(
            {"RANDOMIZE_DOWNLOAD_DELAY": False}, {"id": "x", "delay": 5.0}
        )
        scope.set_base_delay(2.0)  # lower -> ignored
        assert scope._base_delay == 5.0
        scope.set_base_delay(8.0)  # higher -> applied
        assert scope._base_delay == 8.0
        assert scope._delay == 8.0

    def test_min_delay_first_step(self):
        scope = _scope_manager(
            {"BACKOFF_MIN_DELAY": 3.0, "BACKOFF_DELAY_FACTOR": 2.0, "BACKOFF_JITTER": 0}
        )
        scope.record_backoff(now=0.0)
        assert scope._delay == pytest.approx(3.0)

    def test_no_scope_concurrency_limit_by_default(self):
        scope = _scope_manager()
        assert scope._concurrency is None
        for _ in range(100):
            scope.record_sent(now=0.0)
        assert scope.can_send(now=0.0) == 0
        assert scope.concurrency_blocked() is False

    def test_concurrency_limit(self):
        scope = _scope_manager(config={"id": "x", "concurrency": 2})
        scope.record_sent(now=0.0)
        # Concurrency is enforced via concurrency_blocked(), not can_send().
        assert scope.can_send(now=0.0) == 0
        assert scope.concurrency_blocked() is False
        scope.record_sent(now=0.0)
        # Two in flight, limit reached -> blocked.
        assert scope.can_send(now=0.0) == 0
        assert scope.concurrency_blocked() is True
        scope.record_done(now=0.0)
        assert scope.concurrency_blocked() is False

    def test_record_done_fires_slot_event(self):
        scope = _scope_manager(config={"id": "x", "concurrency": 1})
        scope.record_sent(now=0.0)
        event = scope.slot_event()
        assert not event.called
        scope.record_done(now=0.0)
        assert event.called

    def test_set_concurrency_fires_slot_event(self):
        scope = _scope_manager(config={"id": "x", "concurrency": 1})
        scope.record_sent(now=0.0)
        event = scope.slot_event()
        assert not event.called
        scope.set_concurrency(5)
        assert event.called

    def test_discard_slot_event(self):
        scope = _scope_manager(config={"id": "x", "concurrency": 1})
        event = scope.slot_event()
        scope.discard_slot_event(event)
        scope.discard_slot_event(event)  # idempotent
        scope.record_sent(now=0.0)
        scope.record_done(now=0.0)
        assert not event.called

    def test_set_concurrency_respects_min(self):
        scope = _scope_manager(config={"id": "x", "min_concurrency": 3})
        scope.set_concurrency(1)
        assert scope._concurrency == 3
        scope.set_concurrency(5)
        assert scope._concurrency == 5

    def test_quota_blocks_when_exhausted(self):
        scope = _scope_manager(config={"id": "x", "quota": 10.0, "window": 60.0})
        scope.record_sent(now=0.0, amount=6.0)
        assert scope.can_send(now=0.0, amount=3.0) == 0  # 9 <= 10
        scope.record_sent(now=0.0, amount=3.0)
        # 9 spent; a 3.0 request would exceed the quota -> wait for the window.
        assert scope.can_send(now=0.0, amount=3.0) == pytest.approx(60.0)
        # The window resets and quota is available again.
        assert scope.can_send(now=60.0, amount=3.0) == 0

    def test_quota_allows_oversized_request(self):
        scope = _scope_manager(config={"id": "x", "quota": 10.0})
        # A single request larger than the whole quota is still allowed.
        assert scope.can_send(now=0.0, amount=999.0) == 0

    def test_quota_reconcile_consumed_delta(self):
        scope = _scope_manager(config={"id": "x", "quota": 10.0})
        scope.record_sent(now=0.0, amount=2.0)
        assert scope._consumed == pytest.approx(2.0)
        # The response reports it actually consumed 0.5 more than estimated.
        scope.reconcile_quota(consumed=0.5, now=0.0)
        assert scope._consumed == pytest.approx(2.5)

    def test_quota_reconcile_remaining(self):
        scope = _scope_manager(config={"id": "x", "quota": 10.0})
        scope.record_sent(now=0.0, amount=2.0)
        scope.reconcile_quota(remaining=3.0, now=0.0)
        assert scope._consumed == pytest.approx(7.0)

    def test_rampup_lowers_delay_when_quiet(self):
        scope = _scope_manager(
            {"BACKOFF_WINDOW": 10.0, "RANDOMIZE_DOWNLOAD_DELAY": False},
            {
                "id": "x",
                "delay": 4.0,
                "rampup": {"delay_factor": 0.5, "min_delay": 0.5},
            },
        )
        scope.can_send(now=0.0)  # start the rampup window
        # A quiet window (no backoff) lowers the delay.
        scope.can_send(now=10.0)
        assert scope._delay == pytest.approx(2.0)
        scope.can_send(now=20.0)
        assert scope._delay == pytest.approx(1.0)

    def test_rampup_raises_concurrency_at_min_delay(self):
        scope = _scope_manager(
            {"BACKOFF_WINDOW": 10.0},
            {"id": "x", "delay": 0.0, "rampup": True, "min_concurrency": 1},
        )
        assert scope._concurrency == 1
        scope.can_send(now=0.0)
        scope.can_send(now=10.0)
        assert scope._concurrency == 2

    def test_rampup_holds_when_target_met(self):
        scope = _scope_manager(
            {"BACKOFF_WINDOW": 10.0, "RAMPUP_BACKOFF_TARGET": 1},
            {"id": "x", "delay": 0.0, "rampup": True, "min_concurrency": 1},
        )
        scope.can_send(now=0.0)
        scope.record_backoff(now=1.0)  # one trigger == target -> hold, do not probe
        scope.can_send(now=10.0)
        assert scope._concurrency == 1


class TestThrottlingIntegration:
    @coroutine_test
    async def test_backoff_recorded_on_429(self, mockserver):
        crawler = get_crawler(SimpleSpider, {"RETRY_ENABLED": False})
        await crawler.crawl_async(
            mockserver.url("/status?n=429"), mockserver=mockserver
        )
        throttler = crawler.throttler
        assert throttler is not None
        managers = throttler._scope_managers
        assert managers, "no throttling scope was created"
        assert any(manager._backoff_level >= 1 for manager in managers.values())

    @coroutine_test
    async def test_no_backoff_on_200(self, mockserver):
        crawler = get_crawler(SimpleSpider)
        await crawler.crawl_async(
            mockserver.url("/status?n=200"), mockserver=mockserver
        )
        throttler = crawler.throttler
        assert throttler is not None
        assert all(
            manager._backoff_level == 0
            for manager in throttler._scope_managers.values()
        )
