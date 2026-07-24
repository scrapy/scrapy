from __future__ import annotations

import logging
import warnings
from typing import Any, cast

import pytest

from scrapy import signals
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request, Response
from scrapy.settings import Settings, default_settings
from scrapy.throttler import (
    RequestScopes,
    Throttler,
    ThrottlingScopeManager,
    _default_scope_concurrency,
    _to_scope_dict,
    _warn_on_deprecated_concurrency,
    add_scope,
    iter_scope_quota_amounts,
    iter_scopes,
    scope_cache,
)
from scrapy.utils._headers import _parse_ratelimit_reset, _parse_retry_after
from scrapy.utils.defer import deferred_from_coro, maybe_deferred_to_future
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.test import get_crawler
from tests.spiders import SimpleSpider
from tests.utils.decorators import coroutine_test


def _manager(settings: dict[str, Any] | None = None) -> Throttler:
    crawler = get_crawler(settings_dict=settings)
    return Throttler.from_crawler(crawler)


def _scope_manager(
    settings: dict[str, Any] | None = None, config: dict[str, Any] | None = None
) -> ThrottlingScopeManager:
    crawler = get_crawler(settings_dict=settings)
    return ThrottlingScopeManager.from_crawler(crawler, config or {"id": "example.com"})


def _scope(manager: Throttler, scope_id: str) -> ThrottlingScopeManager:
    """Return the concrete scope manager for *scope_id*, for tests that inspect
    its private state (``get_scope_manager`` is only typed to return the
    protocol)."""
    manager_ = manager.get_scope_manager(scope_id)
    assert isinstance(manager_, ThrottlingScopeManager)
    return manager_


def _scope_managers(crawler: Any) -> list[ThrottlingScopeManager]:
    """Return the concrete scope managers a crawl created, for integration
    tests that inspect their private state."""
    throttler = crawler.throttler
    assert isinstance(throttler, Throttler)
    managers = list(throttler._scope_managers.values())
    assert all(isinstance(m, ThrottlingScopeManager) for m in managers)
    return cast("list[ThrottlingScopeManager]", managers)


class _FakeRobotParser:
    """A minimal robots.txt parser stub for :signal:`robots_parsed` tests.

    *delay* is returned by :meth:`crawl_delay`, unless it is an exception, in
    which case it is raised to emulate a backend-specific failure.
    """

    def __init__(self, delay: float | Exception | None):
        self._delay = delay

    def crawl_delay(self, useragent: str) -> float | None:
        if isinstance(self._delay, Exception):
            raise self._delay
        return self._delay


def _response(
    status: int = 200,
    headers: dict[str, str] | None = None,
    url: str = "http://example.com",
    meta: dict[str, Any] | None = None,
) -> Response:
    request = Request(url, meta=meta or {})
    return Response(url, status=status, headers=headers or {}, request=request)


def test_deprecated_concurrency_defaults_differ():
    """``_warn_on_deprecated_concurrency`` emits a warn-then-flip message that
    only makes sense while the two concurrency defaults differ (otherwise it
    reads "will drop from N to N"). Guard that invariant here so that lowering
    the deprecated default to match is caught by the test suite instead of
    shipping a bogus warning or aborting a crawl."""
    assert (
        default_settings.CONCURRENT_REQUESTS_PER_DOMAIN
        != default_settings.THROTTLING_SCOPE_CONCURRENCY
    )


class TestThrottler:
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
        # get_scopes is deterministic per request, so a second call yields the
        # same scopes.
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
    async def test_get_scopes_persisted_in_meta(self):
        from scrapy.throttler import _RESOLVED_SCOPES_META_KEY  # noqa: PLC0415

        manager = _manager()
        request = Request("http://example.com/a")
        scopes = await manager.get_scopes(request)
        assert request.meta[_RESOLVED_SCOPES_META_KEY] == scopes

    @coroutine_test
    async def test_scope_cache_works_without_crawler(self):
        # scope_cache only persists to meta; it needs nothing from the manager.
        from scrapy.throttler import _RESOLVED_SCOPES_META_KEY  # noqa: PLC0415

        class CrawlerlessManager:
            @scope_cache
            async def get_scopes(self, request: Request) -> RequestScopes:
                return "scope"

        request = Request("http://example.com/a")
        assert await CrawlerlessManager().get_scopes(request) == "scope"
        assert request.meta[_RESOLVED_SCOPES_META_KEY] == "scope"

    @coroutine_test
    async def test_get_resolved_scopes_reuses_persisted_scopes(self):
        # Once get_scopes has resolved and persisted the scopes, the synchronous
        # get_resolved_scopes accessor reuses them instead of resolving again.
        calls: list[str] = []

        class CountingManager(Throttler):
            @scope_cache
            async def get_scopes(self, request: Request) -> RequestScopes:
                calls.append(request.url)
                return urlparse_cached(request).netloc

        manager = CountingManager(get_crawler())
        request = Request("http://example.com/a")
        await manager.get_scopes(request)
        assert calls == ["http://example.com/a"]
        assert list(iter_scopes(manager.get_resolved_scopes(request))) == [
            "example.com"
        ]
        # No second resolution.
        assert calls == ["http://example.com/a"]

    @coroutine_test
    async def test_get_scopes_survives_disk_roundtrip(self):
        from scrapy.utils.request import request_from_dict  # noqa: PLC0415

        manager = _manager()
        request = Request(
            "http://example.com/a", meta={"throttling_scopes": {"bucket": 3.0}}
        )
        await manager.get_scopes(request)
        # A request restored from a disk queue is a fresh object; the synchronous
        # readiness path must still recover its scopes (with quota values) from
        # the persisted meta, without re-running get_scopes.
        restored = request_from_dict(request.to_dict())
        assert manager._cached_scope_quota_amounts(restored) == [("bucket", 3.0)]

    @coroutine_test
    async def test_get_scopes_reresolved_after_cross_host_replace(self):
        # A redirect built with Request.replace() copies meta (including the
        # persisted scopes), but get_scopes always re-resolves (it never reads
        # the persisted value back), so it must not reuse the original host's
        # scopes.
        manager = _manager()
        request = Request("http://example.com/a")
        assert await manager.get_scopes(request) == "example.com"
        redirected = request.replace(url="http://other.example/a")
        assert await manager.get_scopes(redirected) == "other.example"

    def test_scope_manager_class_in_config(self):
        manager = _manager(
            {"THROTTLING_SCOPES": {"example.com": {"manager": ThrottlingScopeManager}}}
        )
        scope = manager.get_scope_manager("example.com")
        assert isinstance(scope, ThrottlingScopeManager)

    def test_get_scopes_key_single(self):
        manager = _manager()
        assert manager.get_scopes_key(Request("http://example.com/a")) == "example.com"

    def test_get_scopes_key_empty(self):
        manager = _manager()
        request = Request("http://example.com/a", meta={"throttling_scopes": []})
        assert manager.get_scopes_key(request) == ""

    def test_get_scopes_key_multiple(self):
        manager = _manager()
        request = Request(
            "http://example.com/a", meta={"throttling_scopes": {"b": 1.0, "a": 2.0}}
        )
        # Multiple scopes yield a deterministic (sorted) JSON key.
        assert manager.get_scopes_key(request) == '["a", "b"]'

    def test_release_frees_concurrency(self):
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}})
        scope = _scope(manager, "example.com")
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
        scope = _scope(manager, "example.com")
        assert scope.concurrency_blocked() is True
        assert scope.concurrency_blocked() is True
        # acquire(r2) must block until r1 frees the slot; release it on the next
        # event loop tick so the event-driven wait wakes up.
        call_later(0, manager.release, r1)
        await maybe_deferred_to_future(deferred_from_coro(manager.acquire(r2)))
        assert scope.concurrency_blocked() is True
        assert r2 in manager._reserved

    def test_reconcile_quota_without_backoff(self):
        manager = _manager({"THROTTLING_SCOPES": {"cost": {"quota": 100.0}}})
        scope = _scope(manager, "cost")
        manager.reconcile_quota("cost", consumed=5.0)
        # Quota was reconciled but no backoff step was applied.
        assert scope._consumed == pytest.approx(5.0)
        assert scope._delay == scope._base_delay
        assert scope._max_unsafe is None

    def test_back_off_and_reconcile_quota(self):
        manager = _manager({"THROTTLING_SCOPES": {"cost": {"quota": 100.0}}})
        scope = _scope(manager, "cost")
        manager.back_off("cost", delay=5.0)
        manager.reconcile_quota("cost", consumed=2.0)
        assert scope._consumed == pytest.approx(2.0)
        assert scope._delay > scope._base_delay

    @pytest.mark.parametrize(
        ("settings", "parser_delay", "expected_base_delay"),
        [
            ({"ROBOTSTXT_OBEY": True, "RANDOMIZE_DOWNLOAD_DELAY": False}, 3.0, 3.0),
            ({"ROBOTSTXT_OBEY": True, "THROTTLER_ROBOTSTXT_OBEY": False}, 3.0, 0.0),
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
        scope = _scope(manager, "example.com")
        assert scope._base_delay == expected_base_delay

    def test_apply_robots_crawl_delay(self):
        manager = _manager({"ROBOTSTXT_OBEY": True, "RANDOMIZE_DOWNLOAD_DELAY": False})
        manager._apply_robots_crawl_delay("example.com", 3.0)
        scope = _scope(manager, "example.com")
        assert scope._base_delay == 3.0
        assert scope.can_send(now=0) == 0  # nothing sent yet
        scope.record_sent(now=0)
        assert scope.can_send(now=0) == pytest.approx(3.0)

    def test_apply_robots_crawl_delay_capped(self):
        manager = _manager(
            {"ROBOTSTXT_OBEY": True, "THROTTLER_ROBOTSTXT_MAX_DELAY": 2.0}
        )
        manager._apply_robots_crawl_delay("example.com", 30.0)
        assert _scope(manager, "example.com")._base_delay == 2.0

    def test_apply_robots_crawl_delay_disabled(self):
        manager = _manager({"ROBOTSTXT_OBEY": True, "THROTTLER_ROBOTSTXT_OBEY": False})
        manager._apply_robots_crawl_delay("example.com", 3.0)
        assert _scope(manager, "example.com")._base_delay == 0.0

    def test_apply_robots_crawl_delay_ignored(self, caplog):
        manager = _manager(
            {
                "ROBOTSTXT_OBEY": True,
                "THROTTLING_SCOPES": {
                    "example.com": {"delay": 0.5, "ignore_robots_txt": True}
                },
            }
        )
        with caplog.at_level(logging.WARNING, logger="scrapy.throttler"):
            manager._apply_robots_crawl_delay("example.com", 3.0)
        # No warning is logged and the crawl-delay is not applied.
        assert "Crawl-delay" not in caplog.text
        assert _scope(manager, "example.com")._base_delay == 0.5

    def test_scope_eviction(self):
        manager = _manager({"THROTTLING_SCOPE_MAX_IDLE": 100.0})
        scope = _scope(manager, "example.com")
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
        scope = _scope(manager, "example.com")
        scope.record_backoff(delay=10_000.0, now=0.0)
        manager._last_eviction = None
        manager._maybe_evict(now=5_000.0)
        # Still in backoff (in_backoff_until far in the future), so not evicted
        # even though it has been idle for longer than THROTTLING_SCOPE_MAX_IDLE.
        assert "example.com" in manager._scope_managers

    def test_reserve_evicts_idle_scopes(self):
        # A throttler-aware scheduler reserves every request before the engine
        # reaches acquire() (which fast-paths reserved requests), so reserve()
        # must be the hook that evicts idle scope managers; otherwise they pile
        # up unbounded on broad crawls.
        manager = _manager({"THROTTLING_SCOPE_MAX_IDLE": 1.0})
        idle = _scope(manager, "idle.example")
        # Make it look long-idle: a finished send in the distant monotonic past.
        idle.record_sent(now=0.0)
        idle.record_done(now=0.0)
        assert "idle.example" in manager._scope_managers
        manager.reserve(Request("http://active.example/1"))
        assert "idle.example" not in manager._scope_managers
        assert "active.example" in manager._scope_managers

    def test_scope_limit_evicts_least_recently_used(self):
        manager = _manager({"THROTTLING_SCOPE_LIMIT": 2})
        # Use three scopes in order; each send/done leaves them idle.
        for scope_id in ("a.example", "b.example", "c.example"):
            scope = _scope(manager, scope_id)
            scope.record_sent(now=0.0)
            scope.record_done(now=0.0)
        # The limit caps live managers at 2, dropping the least-recently-used.
        assert set(manager._scope_managers) == {"b.example", "c.example"}

    def test_scope_limit_keeps_active_scopes(self):
        manager = _manager({"THROTTLING_SCOPE_LIMIT": 1})
        # Two scopes with in-flight requests cannot be evicted, so the limit is
        # exceeded rather than dropping a scope that still tracks a live send.
        for scope_id in ("a.example", "b.example"):
            _scope(manager, scope_id).record_sent(now=0.0)
        assert set(manager._scope_managers) == {"a.example", "b.example"}

    def test_scope_limit_disabled(self):
        manager = _manager({"THROTTLING_SCOPE_LIMIT": 0})
        for i in range(5):
            scope = _scope(manager, f"{i}.example")
            scope.record_sent(now=0.0)
            scope.record_done(now=0.0)
        assert len(manager._scope_managers) == 5


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

    def test_base_delay_defaults_to_download_delay(self):
        # With no explicit scope "delay", the base delay is DOWNLOAD_DELAY.
        scope = _scope_manager(
            {"DOWNLOAD_DELAY": 2.0, "RANDOMIZE_DOWNLOAD_DELAY": False}, {"id": "x"}
        )
        assert scope._base_delay == pytest.approx(2.0)

    def test_scope_delay_overrides_download_delay(self):
        # An explicit scope "delay" overrides DOWNLOAD_DELAY.
        scope = _scope_manager(
            {"DOWNLOAD_DELAY": 2.0, "RANDOMIZE_DOWNLOAD_DELAY": False},
            {"id": "x", "delay": 0.0},
        )
        assert scope._base_delay == pytest.approx(0.0)

    def test_exponential_backoff(self):
        scope = _scope_manager({"DOWNLOAD_DELAY": 0.0})
        scope.record_backoff(now=0.0)
        assert scope._delay == pytest.approx(1.0)
        scope.record_backoff(now=0.0)
        assert scope._delay == pytest.approx(2.0)
        scope.record_backoff(now=0.0)
        assert scope._delay == pytest.approx(4.0)

    def test_backoff_cap(self):
        scope = _scope_manager(
            {"DOWNLOAD_DELAY": 0.0, "BACKOFF_MAX_DELAY": 5.0},
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

    def test_uncapped_backoff_delay(self):
        # cap=False (used by trusted back_off() calls) ignores BACKOFF_MAX_DELAY.
        scope = _scope_manager({"BACKOFF_MAX_DELAY": 10.0})
        scope.record_backoff(delay=999.0, now=0.0, cap=False)
        assert scope.can_send(now=0.0) == pytest.approx(999.0)

    def test_recovery_bisects_toward_ideal(self):
        scope = _scope_manager({"DOWNLOAD_DELAY": 0.0})
        # No safe delay known yet: growth is exponential (1 -> 2 -> 4 -> 8), and
        # the last delay to trigger is remembered as _max_unsafe.
        for _ in range(4):
            scope.record_backoff(now=0.0)
        assert scope._delay == pytest.approx(8.0)
        assert scope._max_unsafe == pytest.approx(4.0)
        assert scope._min_safe is None
        # A quiet window proves 8.0 is safe -> it becomes _min_safe, and the
        # delay probes halfway down toward _max_unsafe: (4 + 8) / 2 = 6.
        scope.can_send(now=60.0)
        assert scope._min_safe == pytest.approx(8.0)
        assert scope._delay == pytest.approx(6.0)
        # The probe at 6.0 triggers: _max_unsafe rises to it and the delay jumps
        # straight back up to the known-safe delay (8.0) rather than creeping.
        scope.record_backoff(now=60.0)
        assert scope._max_unsafe == pytest.approx(6.0)
        assert scope._delay == pytest.approx(8.0)

    def test_recovery_reaches_base_and_resets(self):
        scope = _scope_manager({"DOWNLOAD_DELAY": 0.0})
        scope.record_backoff(now=0.0)
        assert scope._delay > scope._base_delay
        # Enough quiet windows bring the delay back within one step of the base
        # delay, at which point the backoff state is fully cleared.
        scope.can_send(now=600.0)
        assert scope._delay == pytest.approx(0.0)
        assert scope._max_unsafe is None
        assert scope._min_safe is None

    def test_recovery_tracks_a_more_permissive_server(self):
        # A delay that used to trigger stops doing so (the server's ideal delay
        # dropped): _max_unsafe must not pin the delay above the new ideal.
        scope = _scope_manager({"DOWNLOAD_DELAY": 0.0})
        for _ in range(4):
            scope.record_backoff(now=0.0)
        assert scope._max_unsafe == pytest.approx(4.0)
        # Many quiet windows in a row: the delay keeps probing down, _max_unsafe
        # is retired once reached, and recovery converges all the way to base.
        scope.can_send(now=6000.0)
        assert scope._delay == pytest.approx(0.0)
        assert scope._max_unsafe is None

    def test_backoff_escapes_stale_safe_delay(self):
        # Once a delay that recovery had marked safe starts triggering again
        # (the server got stricter), the stale _min_safe is dropped and growth
        # goes back to exponential to find a working delay quickly.
        scope = _scope_manager({"DOWNLOAD_DELAY": 0.0})
        for _ in range(4):
            scope.record_backoff(now=0.0)
        scope.can_send(now=60.0)  # _min_safe = 8.0, delay = 6.0
        assert scope._min_safe == pytest.approx(8.0)
        # A trigger at or above _min_safe means it is no longer safe: drop it
        # and resume exponential growth (8.0 * 2 = 16.0).
        scope._delay = 8.0
        scope.record_backoff(now=60.0)
        assert scope._min_safe is None
        assert scope._delay == pytest.approx(16.0)

    def test_backoff_disabled(self):
        # With backoff disabled for the scope, triggers (including hard delays)
        # are ignored: the delay stays at the base and no gate is applied.
        scope = _scope_manager(
            {"DOWNLOAD_DELAY": 0.0},
            {"id": "x", "backoff": {"enabled": False}},
        )
        scope.record_backoff(now=0.0)
        assert scope._delay == pytest.approx(0.0)
        assert scope.can_send(now=0.0) == 0
        scope.record_backoff(delay=999.0, now=0.0)
        assert scope.can_send(now=0.0) == 0

    def test_backoff_enabled_by_default(self):
        scope = _scope_manager({"DOWNLOAD_DELAY": 0.0}, {"id": "x"})
        scope.record_backoff(now=0.0)
        assert scope._delay == pytest.approx(1.0)

    def test_per_scope_backoff_override(self):
        scope = _scope_manager(
            {"DOWNLOAD_DELAY": 0.0, "BACKOFF_MAX_DELAY": 100.0},
            {"id": "x", "backoff": {"max_delay": 5.0}},
        )
        for _ in range(5):
            scope.record_backoff(now=0.0)
        assert scope._delay == pytest.approx(5.0)

    def test_set_base_delay_raises_only(self):
        scope = _scope_manager(
            {"RANDOMIZE_DOWNLOAD_DELAY": False}, {"id": "x", "delay": 5.0}
        )
        scope.set_base_delay(2.0)  # lower -> ignored
        assert scope._base_delay == 5.0
        scope.set_base_delay(8.0)  # higher -> applied
        assert scope._base_delay == 8.0
        assert scope._delay == 8.0

    def test_zero_base_delay_first_step_uses_seed(self):
        # With a zero base delay the first step starts from the positive seed,
        # not zero (which would pin the delay at zero, disabling backoff).
        scope = _scope_manager({"DOWNLOAD_DELAY": 0.0})
        scope.record_backoff(now=0.0)
        assert scope._delay == pytest.approx(1.0)

    def test_default_scope_concurrency(self):
        scope = _scope_manager()
        assert scope._concurrency == 8

    def test_no_scope_concurrency_limit_when_zero(self):
        # THROTTLING_SCOPE_CONCURRENCY governs scopes that are neither a domain
        # nor an IP (here a bare "custom" group name).
        scope = _scope_manager(
            settings={"THROTTLING_SCOPE_CONCURRENCY": 0}, config={"id": "custom"}
        )
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

    def test_record_done_fires_slot_available_event(self):
        scope = _scope_manager(config={"id": "x", "concurrency": 1})
        scope.record_sent(now=0.0)
        event = scope.slot_available_event()
        assert not event.called
        scope.record_done(now=0.0)
        assert event.called

    def test_zero_quota_window_keeps_quota_reset(self):
        # A non-positive quota window must not make _maybe_reset_quota spin
        # forever; the quota stays continuously reset instead.
        scope = _scope_manager(config={"id": "x", "quota": 10.0, "window": 0})
        scope.record_sent(now=0.0, quota_amount=10.0)
        assert scope.can_send(now=1.0, quota_amount=5.0) == 0.0
        assert scope._consumed == 0.0

    def test_set_concurrency_fires_slot_available_event(self):
        scope = _scope_manager(config={"id": "x", "concurrency": 1})
        scope.record_sent(now=0.0)
        event = scope.slot_available_event()
        assert not event.called
        scope.set_concurrency(5)
        assert event.called

    def test_discard_slot_available_event(self):
        scope = _scope_manager(config={"id": "x", "concurrency": 1})
        event = scope.slot_available_event()
        scope.discard_slot_available_event(event)
        scope.discard_slot_available_event(event)  # idempotent
        scope.record_sent(now=0.0)
        scope.record_done(now=0.0)
        assert not event.called

    def test_fire_slot_waiters_skips_already_fired(self):
        scope = _scope_manager(config={"id": "x", "concurrency": 1})
        scope.record_sent(now=0.0)
        event = scope.slot_available_event()
        event.callback(None)  # fired out-of-band before the slot frees up
        # record_done() fires the waiters; the already-fired one is skipped
        # rather than called a second time (which would raise).
        scope.record_done(now=0.0)
        assert event.called

    def test_set_concurrency_clamps_to_one(self):
        scope = _scope_manager(config={"id": "x", "concurrency": 4})
        # A concurrency below 1 is clamped up to 1.
        scope.set_concurrency(0)
        assert scope._concurrency == 1
        scope.set_concurrency(5)
        assert scope._concurrency == 5

    def test_quota_blocks_when_exhausted(self):
        scope = _scope_manager(config={"id": "x", "quota": 10.0, "window": 60.0})
        scope.record_sent(now=0.0, quota_amount=6.0)
        assert scope.can_send(now=0.0, quota_amount=3.0) == 0  # 9 <= 10
        scope.record_sent(now=0.0, quota_amount=3.0)
        # 9 spent; a 3.0 request would exceed the quota -> wait for the window.
        assert scope.can_send(now=0.0, quota_amount=3.0) == pytest.approx(60.0)
        # The window resets and quota is available again.
        assert scope.can_send(now=60.0, quota_amount=3.0) == 0

    def test_quota_allows_oversized_request(self):
        scope = _scope_manager(config={"id": "x", "quota": 10.0})
        # A single request larger than the whole quota is still allowed.
        assert scope.can_send(now=0.0, quota_amount=999.0) == 0

    def test_quota_reconcile_consumed_delta(self):
        scope = _scope_manager(config={"id": "x", "quota": 10.0})
        scope.record_sent(now=0.0, quota_amount=2.0)
        assert scope._consumed == pytest.approx(2.0)
        # The response reports it actually consumed 0.5 more than estimated.
        scope.reconcile_quota(consumed=0.5, now=0.0)
        assert scope._consumed == pytest.approx(2.5)

    def test_quota_reconcile_remaining(self):
        scope = _scope_manager(config={"id": "x", "quota": 10.0})
        scope.record_sent(now=0.0, quota_amount=2.0)
        scope.reconcile_quota(remaining=3.0, now=0.0)
        assert scope._consumed == pytest.approx(7.0)


class TestThrottlerReadiness:
    """The synchronous readiness API used by a throttler-aware scheduler."""

    @coroutine_test
    async def test_is_ready_unconstrained_scope(self):
        manager = _manager()
        request = Request("http://example.com/a")
        # A scope with no configured delay/concurrency/quota is always ready.
        assert await manager.get_scopes(request) == "example.com"
        assert manager.is_ready(request) is True

    @coroutine_test
    async def test_is_ready_without_cached_scopes(self):
        # is_ready falls back to synchronous resolution when get_scopes was not
        # called first (e.g. for a request restored from disk).
        manager = _manager()
        request = Request("http://example.com/a")
        assert manager.is_ready(request) is True

    @coroutine_test
    async def test_reserve_blocks_scope_by_base_delay(self):
        manager = _manager(
            {
                "THROTTLING_SCOPES": {"example.com": {"delay": 100.0}},
                "RANDOMIZE_DOWNLOAD_DELAY": False,
            }
        )
        first = Request("http://example.com/1")
        second = Request("http://example.com/2")
        await manager.get_scopes(first)
        await manager.get_scopes(second)
        assert manager.is_ready(first) is True
        manager.reserve(first)
        # The base delay now blocks any further request for the scope.
        assert manager.is_ready(second) is False
        assert manager.get_time_until_ready(second) == pytest.approx(100.0, abs=1.0)

    @coroutine_test
    async def test_delay_blocks_until_deadline(self):
        manager = _manager({"THROTTLER_DEBUG": True})
        request = Request("http://example.com/a", meta={"delay": 100.0})
        await manager.get_scopes(request)
        # The per-request delay holds back the request even though its scope is
        # otherwise unconstrained.
        assert manager.is_ready(request) is False
        assert manager.get_time_until_ready(request) == pytest.approx(100.0, abs=1.0)
        # The deadline is computed once and reused by later polls.
        deadline = request.meta["_throttler_delay_deadline"]
        assert manager.is_ready(request) is False
        assert request.meta["_throttler_delay_deadline"] == deadline

    @coroutine_test
    async def test_delay_not_reapplied_once_consumed(self):
        # A request whose delay was already honored (e.g. promoted out of a
        # throttler-aware queue's holding area, or restored on resume) is
        # ready, so it cannot re-block its scope set on a stale deadline.
        manager = _manager()
        request = Request(
            "http://example.com/a",
            meta={"delay": 100.0, "_throttler_delayed": True},
        )
        await manager.get_scopes(request)
        assert manager.is_ready(request) is True
        assert manager.get_request_delay(request) == 0.0

    @coroutine_test
    async def test_get_request_delay(self):
        manager = _manager()
        assert manager.get_request_delay(
            Request("http://example.com/a", meta={"delay": 100.0})
        ) == pytest.approx(100.0, abs=1.0)
        # A request without a per-request delay is not held individually.
        assert manager.get_request_delay(Request("http://example.com/b")) == 0.0

    @coroutine_test
    async def test_back_off_delay(self):
        manager = _manager({"THROTTLER_DEBUG": True, "RANDOMIZE_DOWNLOAD_DELAY": False})
        request = Request("http://example.com/a")
        await manager.get_scopes(request)
        assert manager.is_ready(request) is True
        # A component can delay a whole scope on demand, like a Retry-After
        # response header does.
        manager.back_off("example.com", delay=50.0, cap=False)
        assert manager.is_ready(request) is False
        assert manager.get_time_until_ready(request) == pytest.approx(50.0, abs=1.0)

    @coroutine_test
    async def test_back_off_uncapped_delay_bypasses_max_delay(self):
        # BACKOFF_MAX_DELAY caps untrusted input (headers), but a cap=False
        # back_off() is a trusted call, so it may exceed the cap.
        manager = _manager(
            {"BACKOFF_MAX_DELAY": 30.0, "RANDOMIZE_DOWNLOAD_DELAY": False}
        )
        request = Request("http://example.com/a")
        await manager.get_scopes(request)
        manager.back_off("example.com", delay=1000.0, cap=False)
        assert manager.get_time_until_ready(request) == pytest.approx(1000.0, abs=1.0)

    @coroutine_test
    async def test_reserve_blocks_on_concurrency(self):
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}})
        first = Request("http://example.com/1")
        second = Request("http://example.com/2")
        await manager.get_scopes(first)
        await manager.get_scopes(second)
        manager.reserve(first)
        assert manager.is_ready(second) is False
        # Pure concurrency blocking is not time-gated.
        assert manager.get_time_until_ready(second) is None
        manager.release(first)
        assert manager.is_ready(second) is True

    @coroutine_test
    async def test_acquire_noop_when_reserved(self):
        manager = _manager(
            {
                "THROTTLING_SCOPES": {"example.com": {"delay": 100.0}},
                "RANDOMIZE_DOWNLOAD_DELAY": False,
            }
        )
        request = Request("http://example.com/1")
        await manager.get_scopes(request)
        manager.reserve(request)
        # A reserved request fast-paths through acquire() without re-recording
        # the send or waiting for the delay.
        await manager.acquire(request)
        scope = _scope(manager, "example.com")
        assert scope._active == 1  # reserve recorded exactly one send

    @coroutine_test
    async def test_get_scope_load(self):
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 4}}})
        assert manager.get_scope_load("example.com") == 0.0
        request = Request("http://example.com/1")
        await manager.get_scopes(request)
        manager.reserve(request)
        assert manager.get_scope_load("example.com") == pytest.approx(0.25)

    def test_get_scope_load_falls_back_to_global_concurrency(self):
        manager = _manager({"CONCURRENT_REQUESTS": 8})
        # A scope with no explicit concurrency limit uses CONCURRENT_REQUESTS.
        request = Request("http://example.com/1")
        manager.reserve(request)
        assert manager.get_scope_load("example.com") == pytest.approx(1 / 8)


class TestParseRateHeaders:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (b"\xff\xfe", None),  # undecodable bytes
            ("garbage-not-a-date", None),  # neither a number nor a valid date
            # A naive HTTP date (no timezone) in the past is treated as UTC and
            # yields no positive delay.
            ("Wed, 21 Oct 2015 07:28:00", None),
        ],
        ids=["undecodable", "garbage", "naive-past-date"],
    )
    def test_parse_retry_after(self, value, expected):
        assert _parse_retry_after(_response(headers={"Retry-After": value})) == expected

    @pytest.mark.parametrize(
        "value",
        [b"\xff\xfe", "not-a-number"],
        ids=["undecodable", "non-numeric"],
    )
    def test_parse_ratelimit_reset_invalid(self, value):
        assert (
            _parse_ratelimit_reset(_response(headers={"RateLimit-Reset": value}))
            is None
        )


class TestScopeHelpers:
    def test_iter_scopes(self):
        assert list(iter_scopes(None)) == []
        assert list(iter_scopes("a")) == ["a"]
        assert list(iter_scopes({"a": 1.0, "b": 2.0})) == ["a", "b"]
        assert list(iter_scopes(["a", "b"])) == ["a", "b"]

    def test_iter_scope_quota_amounts(self):
        assert list(iter_scope_quota_amounts(None)) == []
        assert list(iter_scope_quota_amounts("a")) == [("a", None)]
        assert list(iter_scope_quota_amounts({"a": 1.0})) == [("a", 1.0)]
        assert list(iter_scope_quota_amounts(["a", "b"])) == [("a", None), ("b", None)]

    def test_to_scope_dict(self):
        assert _to_scope_dict({"a": 1}) == {"a": 1}
        assert _to_scope_dict(None) == {}
        assert _to_scope_dict("a") == {"a": None}
        assert _to_scope_dict(["a", "b"]) == {"a": None, "b": None}
        with pytest.raises(TypeError):
            _to_scope_dict(123)  # type: ignore[arg-type]

    def test_add_scope_without_value(self):
        # add_scope always returns a {scope_id: quota} dict, using None as the
        # quota of scopes added without one.
        assert add_scope(None, "a") == {"a": None}
        assert add_scope("a", "b") == {"a": None, "b": None}

    def test_add_scope_with_value(self):
        assert add_scope(None, "a", 2.0) == {"a": 2.0}
        assert add_scope({"a": None}, "b", 3.0) == {"a": None, "b": 3.0}

    def test_add_scope_with_value_rejects_existing_entry(self):
        with pytest.raises(TypeError):
            add_scope({"a": 1.0}, "a", 2.0)


class TestThrottlerEdges:
    @coroutine_test
    async def test_acquire_without_scopes(self):
        manager = _manager()
        request = Request("http://example.com/a", meta={"throttling_scopes": []})
        # No scopes resolve, so acquire() returns without reserving anything.
        await manager.acquire(request)
        assert request not in manager._reserved

    def test_get_scope_load_without_concurrency_limit(self):
        manager = _manager({"CONCURRENT_REQUESTS": 0})
        # CONCURRENT_REQUESTS is 0, so the load denominator is 0 and the load is
        # reported as 0 instead of raising.
        assert manager.get_scope_load("example.com") == 0.0

    @coroutine_test
    async def test_acquire_logs_and_waits_for_delay(self):
        manager = _manager(
            {
                "THROTTLING_SCOPES": {"example.com": {"delay": 0.02}},
                "RANDOMIZE_DOWNLOAD_DELAY": False,
                "THROTTLER_DEBUG": True,
            }
        )
        r1 = Request("http://example.com/1")
        r2 = Request("http://example.com/2")
        await maybe_deferred_to_future(deferred_from_coro(manager.acquire(r1)))
        # r2 must wait out the per-scope delay accrued by r1 before it proceeds.
        await maybe_deferred_to_future(deferred_from_coro(manager.acquire(r2)))
        assert r2 in manager._reserved

    @coroutine_test
    async def test_acquire_logs_while_waiting_for_slot(self):
        from scrapy.utils.asyncio import call_later  # noqa: PLC0415

        manager = _manager(
            {
                "THROTTLING_SCOPES": {"example.com": {"concurrency": 1}},
                "THROTTLER_DEBUG": True,
            }
        )
        r1 = Request("http://example.com/1")
        r2 = Request("http://example.com/2")
        await maybe_deferred_to_future(deferred_from_coro(manager.acquire(r1)))
        call_later(0, manager.release, r1)
        # r2 is concurrency-blocked and waits, with debug logging, for the slot.
        await maybe_deferred_to_future(deferred_from_coro(manager.acquire(r2)))
        assert r2 in manager._reserved

    @coroutine_test
    async def test_delay_request(self):
        manager = _manager({"THROTTLER_DEBUG": True})
        request = Request("http://example.com/a", meta={"delay": 0.01})
        await manager._delay_request(request)
        assert request.meta["_throttler_delayed"] is True
        # A second call is a no-op (the request was already delayed).
        await manager._delay_request(request)

    @coroutine_test
    async def test_delay_request_without_debug(self):
        # Same as above but with debug logging off, so the delay is applied
        # without emitting the debug message.
        manager = _manager()
        request = Request("http://example.com/a", meta={"delay": 0.01})
        await manager._delay_request(request)
        assert request.meta["_throttler_delayed"] is True

    @coroutine_test
    async def test_wait_for_slot_discards_unfired_events(self):
        from scrapy.utils.asyncio import call_later  # noqa: PLC0415

        manager = _manager()
        m1 = _scope_manager(config={"id": "a", "concurrency": 1})
        m2 = _scope_manager(config={"id": "b", "concurrency": 1})
        m1.record_sent(now=0.0)
        m2.record_sent(now=0.0)
        # Free m1's slot on the next tick so the wait wakes up with m1's event
        # fired while m2's event is still pending.
        call_later(0, m1.record_done)
        await manager._wait_for_slot([m1, m2])
        # The still-pending m2 event is discarded from its waiter list.
        assert m2._slot_waiters == []

    def test_back_off_debug_logging(self, caplog):
        manager = _manager({"THROTTLER_DEBUG": True})
        with caplog.at_level(logging.DEBUG, logger="scrapy.throttler"):
            manager.back_off("example.com")
        assert "Backoff for scope" in caplog.text
        scope = _scope(manager, "example.com")
        assert scope._delay > scope._base_delay

    def test_on_robots_parsed_disabled(self):
        manager = _manager({"THROTTLER_ROBOTSTXT_OBEY": False})
        # With obeying disabled, the handler returns without touching any scope.
        manager._on_robots_parsed(_FakeRobotParser(5.0), Request("http://example.com"))
        assert not manager._scope_managers

    def test_apply_robots_crawl_delay_warns_on_delay_conflict(self, caplog):
        manager = _manager(
            {
                "ROBOTSTXT_OBEY": True,
                "THROTTLING_SCOPES": {"example.com": {"delay": 0.5}},
            }
        )
        with caplog.at_level(logging.WARNING, logger="scrapy.throttler"):
            manager._apply_robots_crawl_delay("example.com", 3.0)
        assert "Crawl-delay" in caplog.text
        # The configured value takes precedence (crawl-delay not applied).
        assert _scope(manager, "example.com")._base_delay == 0.5

    def test_apply_robots_crawl_delay_debug_logging(self, caplog):
        manager = _manager({"ROBOTSTXT_OBEY": True, "THROTTLER_DEBUG": True})
        with caplog.at_level(logging.DEBUG, logger="scrapy.throttler"):
            manager._apply_robots_crawl_delay("example.com", 3.0)
        assert "Crawl-delay" in caplog.text

    def test_maybe_evict_disabled(self):
        manager = _manager({"THROTTLING_SCOPE_MAX_IDLE": 0})
        scope = _scope(manager, "example.com")
        scope.record_sent(now=0.0)
        scope.record_done(now=0.0)
        # Eviction disabled (max idle <= 0): the scope is kept regardless.
        manager._maybe_evict(now=10_000.0)
        assert "example.com" in manager._scope_managers


class TestThrottlingScopeManagerEdges:
    def test_jitter_as_range(self):
        scope = _scope_manager(config={"id": "x", "jitter": [0.0, 0.0]})
        # A [low, high] jitter range of [0, 0] leaves the value unchanged.
        assert scope._apply_jitter(4.0, scope._jitter) == pytest.approx(4.0)

    def test_effective_delay_randomized(self):
        scope = _scope_manager(
            {"RANDOMIZE_DOWNLOAD_DELAY": True}, {"id": "x", "delay": 2.0}
        )
        scope.record_sent(now=0.0)
        # A randomized base delay lands within [0.5, 1.5] * delay.
        assert 1.0 <= scope.can_send(now=0.0) <= 3.0

    def test_record_done_without_active(self):
        scope = _scope_manager(config={"id": "x"})
        # Calling record_done() with nothing in flight is a harmless no-op.
        scope.record_done(now=0.0)
        assert scope._active == 0

    def test_reconcile_quota_no_change(self):
        scope = _scope_manager(config={"id": "x", "quota": 10.0})
        scope.record_sent(now=0.0, quota_amount=4.0)
        # Neither consumed nor remaining given: the estimate is left untouched.
        scope.reconcile_quota(now=0.0)
        assert scope._consumed == pytest.approx(4.0)

    def test_set_base_delay_during_backoff(self):
        scope = _scope_manager({"DOWNLOAD_DELAY": 0.0}, {"id": "x"})
        scope.record_backoff(now=0.0)
        backoff_delay = scope._delay
        # Raising the base delay mid-backoff updates the base but not the current
        # (higher) backoff delay.
        scope.set_base_delay(0.5)
        assert scope._base_delay == 0.5
        assert scope._delay == backoff_delay

    def test_record_sent_clears_expired_backoff(self):
        scope = _scope_manager(config={"id": "x"})
        scope.record_backoff(delay=5.0, now=0.0)
        assert scope._in_backoff_until == pytest.approx(5.0)
        scope.record_sent(now=10.0)
        # The hard backoff window has passed, so it is cleared.
        assert scope._in_backoff_until is None

    def test_reconcile_quota_without_quota(self):
        scope = _scope_manager(config={"id": "x"})
        # No quota configured, so reconciliation is a no-op.
        scope.reconcile_quota(consumed=5.0, now=0.0)
        assert scope._consumed == 0.0

    def test_is_idle_with_active_requests(self):
        scope = _scope_manager(config={"id": "x"})
        scope.record_sent(now=0.0)
        # An in-flight request keeps the scope from being evicted.
        assert scope.is_idle(now=10_000.0, max_idle=1.0) is False

    def test_is_idle_when_never_used(self):
        scope = _scope_manager(config={"id": "x"})
        # A scope that was never used (no last_seen) is idle.
        assert scope.is_idle(now=0.0, max_idle=1.0) is True

    def test_get_load_with_zero_limit(self):
        # No scope concurrency limit and CONCURRENT_REQUESTS=0 leaves a zero
        # denominator; the load is reported as 0 instead of dividing by zero.
        scope = _scope_manager(
            {
                "CONCURRENT_REQUESTS": 0,
                "CONCURRENT_REQUESTS_PER_DOMAIN": 0,
                "THROTTLING_SCOPE_CONCURRENCY": 0,
            },
            {"id": "x"},
        )
        assert scope._concurrency is None
        scope.record_sent(now=0.0)
        assert scope.get_load() == 0.0


class TestConcurrencyBridging:
    def _settings(
        self, per_domain: int | None = None, scope: int | None = None
    ) -> Settings:
        settings = Settings()
        if per_domain is not None:
            settings.set(
                "CONCURRENT_REQUESTS_PER_DOMAIN", per_domain, priority="spider"
            )
        if scope is not None:
            settings.set("THROTTLING_SCOPE_CONCURRENCY", scope, priority="spider")
        return settings

    def test_default_when_neither_set(self):
        # Neither setting is set explicitly: the historical per-domain default
        # (8) is kept for backward compatibility over the scope default (1).
        assert _default_scope_concurrency(Settings()) == 8

    def test_per_domain_wins_when_higher_priority(self):
        settings = self._settings(per_domain=5)
        assert _default_scope_concurrency(settings) == 5

    def test_scope_wins_when_higher_priority(self):
        settings = self._settings(scope=3)
        assert _default_scope_concurrency(settings) == 3

    def test_scope_wins_on_explicit_tie(self):
        # Both set at the same (higher-than-default) priority: the new setting
        # wins.
        settings = self._settings(per_domain=5, scope=3)
        assert _default_scope_concurrency(settings) == 3

    def test_warns_when_per_domain_set(self):
        settings = self._settings(per_domain=5)
        with pytest.warns(
            ScrapyDeprecationWarning,
            match="CONCURRENT_REQUESTS_PER_DOMAIN setting is deprecated",
        ):
            _warn_on_deprecated_concurrency(settings)

    def test_warns_when_neither_set(self):
        with pytest.warns(ScrapyDeprecationWarning, match="effective per-scope"):
            _warn_on_deprecated_concurrency(Settings())

    def test_no_warning_when_scope_set(self):
        settings = self._settings(scope=3)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            _warn_on_deprecated_concurrency(settings)


class TestThrottlerIntegration:
    @coroutine_test
    async def test_backoff_recorded_on_429(self, mockserver):
        crawler = get_crawler(SimpleSpider, {"RETRY_ENABLED": False})
        await crawler.crawl_async(
            mockserver.url("/status?n=429"), mockserver=mockserver
        )
        managers = _scope_managers(crawler)
        assert managers, "no throttling scope was created"
        assert any(m._delay > m._base_delay for m in managers)

    @coroutine_test
    async def test_backoff_recorded_on_download_error(self, mockserver):
        crawler = get_crawler(SimpleSpider, {"RETRY_ENABLED": False})
        # A dropped connection raises a DownloadFailedError, which the engine
        # routes through the throttler before re-raising.
        await crawler.crawl_async(
            mockserver.url("/drop?abort=1"), mockserver=mockserver
        )
        managers = _scope_managers(crawler)
        assert managers, "no throttling scope was created"
        assert any(m._delay > m._base_delay for m in managers)

    @coroutine_test
    async def test_no_backoff_on_200(self, mockserver):
        crawler = get_crawler(SimpleSpider)
        await crawler.crawl_async(
            mockserver.url("/status?n=200"), mockserver=mockserver
        )
        assert all(m._delay == m._base_delay for m in _scope_managers(crawler))
