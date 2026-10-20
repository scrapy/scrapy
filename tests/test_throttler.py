from __future__ import annotations

import asyncio
import logging
import math
import sys
import warnings
from collections import ChainMap
from time import monotonic, time
from typing import TYPE_CHECKING, Any, Self, cast
from unittest.mock import Mock
from weakref import WeakSet

import pytest
from twisted.internet.defer import Deferred

from scrapy import Spider, signals
from scrapy.core.engine import ExecutionEngine
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request, Response
from scrapy.http.request import NO_CALLBACK
from scrapy.settings import Settings, default_settings
from scrapy.throttler import (
    _APPLIED_SCOPES_META_KEY,
    RequestScopes,
    Throttler,
    ThrottlingScopeManager,
    _check_scope_concurrency,
    _default_jitter,
    _default_scope_concurrency,
    _default_scope_concurrency_setting,
    _normalize_scopes,
    _wait_for_throttler,
    _warn_on_deprecated_concurrency,
    _warn_on_deprecated_randomization,
    _warn_on_ignored_per_ip,
    _warn_on_unachievable_concurrency,
)
from scrapy.utils.asyncio import call_later, sleep
from scrapy.utils.defer import deferred_from_coro, maybe_deferred_to_future
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.test import get_crawler
from tests.spiders import MockServerSpider, SimpleSpider
from tests.utils import wait_for_first
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from scrapy.core.downloader import Downloader


def _manager(settings: dict[str, Any] | None = None) -> Throttler:
    crawler = get_crawler(settings_dict=settings)
    return Throttler.from_crawler(crawler)


def _manager_with_downloader(
    settings: dict[str, Any] | None = None,
) -> tuple[Throttler, Downloader]:
    """Return a throttler and the real :class:`~scrapy.core.downloader.Downloader`
    it sees through the crawler engine, for tests that need actual download
    handler state and the events it fires."""
    crawler = get_crawler(SimpleSpider, settings_dict=settings)
    crawler.throttler = throttler = Throttler.from_crawler(crawler)
    crawler.engine = ExecutionEngine(crawler)
    return throttler, crawler.engine.downloader


def _scope_manager(
    settings: dict[str, Any] | None = None, config: dict[str, Any] | None = None
) -> ThrottlingScopeManager:
    crawler = get_crawler(settings_dict=settings)
    return ThrottlingScopeManager.from_crawler(crawler, config or {"id": "example.com"})


def _scope(manager: Throttler, scope_id: str) -> ThrottlingScopeManager:
    return manager.get_scope_manager(scope_id)


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
    def test_get_scopes_returns_hostname(self):
        manager = _manager()
        assert manager.get_scopes(Request("http://example.com/a")) == "example.com"

    def test_applied_scopes_meta_string(self):
        manager = _manager()
        request = Request("http://example.com/a", meta={"throttling_scopes": "api"})
        assert manager.get_applied_scopes(request) == ["api"]

    def test_applied_scopes_meta_iterable(self):
        manager = _manager()
        request = Request(
            "http://example.com/a", meta={"throttling_scopes": ["api", "users"]}
        )
        assert manager.get_applied_scopes(request) == ["api", "users"]

    def test_applied_scopes_persisted_in_meta(self):
        manager = _manager()
        request = Request("http://example.com/a")
        scopes = manager.get_applied_scopes(request)
        assert request.meta[_APPLIED_SCOPES_META_KEY] == scopes

    def test_applied_scopes_reuse_the_persisted_scopes(self):
        calls: list[str] = []

        class CountingThrottler(Throttler):
            def get_scopes(self, request: Request) -> RequestScopes:
                calls.append(request.url)
                return urlparse_cached(request).netloc

        manager = CountingThrottler(get_crawler())
        request = Request("http://example.com/a")
        assert manager.get_applied_scopes(request) == ["example.com"]
        assert calls == ["http://example.com/a"]
        # No second resolution.
        assert manager.get_applied_scopes(request) == ["example.com"]
        assert calls == ["http://example.com/a"]

    def test_applied_scopes_survive_a_disk_roundtrip(self):
        from scrapy.utils.request import request_from_dict  # noqa: PLC0415

        manager = _manager()
        request = Request(
            "http://example.com/a", meta={"throttling_scopes": ["bucket"]}
        )
        manager._resolve_scopes(request)
        # A request restored from a disk queue is a fresh object; the readiness
        # path must still recover its scopes from the persisted meta.
        restored = request_from_dict(request.to_dict())
        assert manager.get_applied_scopes(restored) == ["bucket"]

    def test_scopes_reresolved_after_cross_host_replace(self):
        # A redirect built with Request.replace() copies meta (including the
        # persisted scopes), but every resolution starts over (it never reads the
        # persisted value back), so it must not reuse the original host's scopes.
        manager = _manager()
        request = Request("http://example.com/a")
        assert manager._resolve_scopes(request) == ["example.com"]
        redirected = request.replace(url="http://other.example/a")
        assert manager._resolve_scopes(redirected) == ["other.example"]

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
            "http://example.com/a", meta={"throttling_scopes": ["b", "a"]}
        )
        # Multiple scopes yield a deterministic (sorted) JSON key.
        assert manager.get_scopes_key(request) == '["a", "b"]'

    def test_get_scopes_override_reaches_every_reader(self):
        """Overriding the scoping hook is enough: everything that needs the
        scopes of a request agrees on them, including the key that the scheduler
        groups queued requests by."""

        class NetlocThrottler(Throttler):
            def get_scopes(self, request: Request) -> RequestScopes:
                return urlparse_cached(request).netloc

        crawler = get_crawler(SimpleSpider, {"THROTTLER": NetlocThrottler})
        throttler = crawler.throttler
        assert isinstance(throttler, NetlocThrottler)
        # A port, so that the result differs from the default host-name scoping.
        request = Request("https://example.com:8080/a")

        assert throttler.get_scopes_key(request) == "example.com:8080"
        assert throttler.get_applied_scopes(request) == ["example.com:8080"]

    def test_get_scopes_override_can_extend_the_meta_key(self):
        class ExtendingThrottler(Throttler):
            def get_scopes(self, request: Request) -> RequestScopes:
                return [cast("str", super().get_scopes(request)), "extra"]

        crawler = get_crawler(SimpleSpider, {"THROTTLER": ExtendingThrottler})
        request = Request("https://example.com/a", meta={"throttling_scopes": "chosen"})
        assert crawler.throttler.get_applied_scopes(request) == ["chosen", "extra"]

    def test_release_frees_concurrency(self):
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}})
        scope = _scope(manager, "example.com")
        request = Request("http://example.com")
        scope._record_sent(now=0.0)
        manager._reserved[request] = [("example.com", scope)]
        assert scope._concurrency_blocked() is True
        manager.release(request)
        assert scope._concurrency_blocked() is False
        # Releasing again is a no-op.
        manager.release(request)
        assert scope._concurrency_blocked() is False

    def test_acquire_returns_the_delay_to_wait(self):
        manager = _manager(
            {
                "THROTTLING_SCOPES": {"example.com": {"delay": 10}},
                "DOWNLOAD_DELAY_JITTER": 0,
            }
        )
        retry = Mock()
        assert manager.acquire(Request("http://example.com/1"), retry=retry) is None
        wait = manager.acquire(Request("http://example.com/2"), retry=retry)
        assert wait is not None
        assert 9 < wait <= 10
        retry.assert_not_called()

    def test_acquire_retries_once_a_slot_frees_up(self):
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}})
        holder = Request("http://example.com/1")
        assert manager.acquire(holder, retry=Mock()) is None
        request = Request("http://example.com/2")
        retry = Mock()
        assert manager.acquire(request, retry=retry) == math.inf
        retry.assert_not_called()
        manager.release(holder)
        retry.assert_called_once_with()
        assert manager.acquire(request, retry=retry) is None

    @coroutine_test
    async def test_acquire_waits_for_freed_slot(self):
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}})
        r1 = Request("http://example.com/1")
        r2 = Request("http://example.com/2")
        await maybe_deferred_to_future(_wait_for_throttler(manager, r1))
        scope = _scope(manager, "example.com")
        assert scope._concurrency_blocked() is True
        assert scope._concurrency_blocked() is True
        # r2 must wait until r1 frees the slot, released on the next event loop
        # iteration.
        call_later(0, manager.release, r1)
        await maybe_deferred_to_future(_wait_for_throttler(manager, r2))
        assert scope._concurrency_blocked() is True
        assert r2 in manager._reserved

    @coroutine_test
    async def test_a_waiter_passes_on_a_slot_it_cannot_use(self) -> None:
        """A freed slot wakes a single waiter (see
        ``ThrottlingScopeManager._record_done``). If that waiter is one that
        another of its scopes still holds back, it must hand the slot to the next
        waiter, or the slot would sit unused until the scope frees another one.
        """
        manager = _manager(
            {
                "THROTTLING_SCOPES": {
                    "held": {"concurrency": 1},
                    "shared": {"concurrency": 1},
                }
            }
        )
        holder = Request("http://a.example/0", meta={"throttling_scopes": ["shared"]})
        await maybe_deferred_to_future(_wait_for_throttler(manager, holder))
        blocker = Request("http://a.example/1", meta={"throttling_scopes": ["held"]})
        await maybe_deferred_to_future(_wait_for_throttler(manager, blocker))

        # Waits on both scopes, and is woken first, since it registers first.
        two_scopes = Request(
            "http://a.example/2", meta={"throttling_scopes": ["held", "shared"]}
        )
        first = _wait_for_throttler(manager, two_scopes)
        await sleep(0)
        one_scope = Request(
            "http://a.example/3", meta={"throttling_scopes": ["shared"]}
        )
        second = _wait_for_throttler(manager, one_scope)
        await sleep(0)
        assert not first.called
        assert not second.called

        manager.release(holder)
        done, _ = await wait_for_first([second], timeout=30)
        assert second in done, "the freed 'shared' slot went to no one"
        assert not first.called, "the 'held' scope let the request through"

        manager.release(blocker)
        manager.release(one_scope)
        done, _ = await wait_for_first([first], timeout=30)
        assert first in done

    @coroutine_test
    async def test_dont_throttle_skips_the_gate(self):
        manager = _manager(
            {
                "THROTTLING_SCOPES": {
                    "example.com": {"concurrency": 1, "delay": 100.0}
                },
                "DOWNLOAD_DELAY_JITTER": 0,
            }
        )
        blocking = Request("http://example.com/1")
        await maybe_deferred_to_future(_wait_for_throttler(manager, blocking))
        scope = _scope(manager, "example.com")
        assert scope._concurrency_blocked() is True
        # Without dont_throttle this would wait for the scope delay and then
        # forever for the slot that `blocking` holds.
        exempt = Request("http://example.com/2", meta={"dont_throttle": True})
        await maybe_deferred_to_future(_wait_for_throttler(manager, exempt))
        # No slot was taken for it, so releasing it is a no-op and the scope
        # state stays as `blocking` left it.
        assert exempt not in manager._reserved
        manager.release(exempt)
        assert scope._concurrency_blocked() is True

    @coroutine_test
    async def test_dont_throttle_still_resolves_scopes(self):
        # Skipping throttling must not skip scope resolution: the outcome of a
        # dont_throttle request still backs off its scopes, and a middleware
        # finds them through get_applied_scopes().
        class HostScopeThrottler(Throttler):
            def get_scopes(self, request: Request) -> RequestScopes:
                return f"host:{urlparse_cached(request).hostname}"

        crawler = get_crawler()
        manager = HostScopeThrottler.from_crawler(crawler)
        request = Request("http://example.com/1", meta={"dont_throttle": True})
        await maybe_deferred_to_future(_wait_for_throttler(manager, request))
        assert manager.get_applied_scopes(request) == ["host:example.com"]
        assert request.meta[_APPLIED_SCOPES_META_KEY] == ["host:example.com"]

    def test_scope_limit_keeps_a_pending_delay(self):
        manager = _manager(
            {
                "THROTTLING_SCOPE_LIMIT": 1,
                "DOWNLOAD_DELAY": 30.0,
                "DOWNLOAD_DELAY_JITTER": 0,
            }
        )
        delayed = _scope(manager, "a.example")
        delayed._record_sent()
        delayed._record_done()
        # Creating a second scope exceeds the limit, but the first one still
        # tracks a delay that has not elapsed, so the limit is exceeded rather
        # than dropping it.
        _scope(manager, "b.example")
        assert set(manager._scope_managers) == {"a.example", "b.example"}

    @coroutine_test
    async def test_scope_limit_evicts_on_acquire(self):
        manager = _manager({"THROTTLING_SCOPE_LIMIT": 1})
        idle = _scope(manager, "idle.example")
        idle._record_sent(now=0.0)
        idle._record_done(now=0.0)
        await maybe_deferred_to_future(
            _wait_for_throttler(manager, Request("http://active.example/1"))
        )
        assert set(manager._scope_managers) == {"active.example"}

    def test_scope_limit_evicts_least_recently_used(self):
        manager = _manager({"THROTTLING_SCOPE_LIMIT": 2})
        # Use three scopes in order; each send/done leaves them idle.
        for scope_id in ("a.example", "b.example", "c.example"):
            scope = _scope(manager, scope_id)
            scope._record_sent(now=0.0)
            scope._record_done(now=0.0)
        # The limit caps live managers at 2, dropping the least-recently-used.
        assert set(manager._scope_managers) == {"b.example", "c.example"}

    def test_scope_limit_keeps_active_scopes(self):
        manager = _manager({"THROTTLING_SCOPE_LIMIT": 1})
        # Two scopes with in-flight requests cannot be evicted, so the limit is
        # exceeded rather than dropping a scope that still tracks a live send.
        for scope_id in ("a.example", "b.example"):
            _scope(manager, scope_id)._record_sent(now=0.0)
        assert set(manager._scope_managers) == {"a.example", "b.example"}

    def test_scope_limit_keeps_the_scopes_being_resolved(self):
        manager = _manager({"THROTTLING_SCOPE_LIMIT": 1})
        # Resolving the scopes of one request must not let the creation of one of
        # them evict another, or the request would record its send on a manager
        # that is no longer the one of its scope.
        slots = manager._resolve_scope_slots(["a.example", "b.example"])
        assert [scope_id for scope_id, _ in slots] == ["a.example", "b.example"]
        for scope_id, scope in slots:
            assert manager._live_scope_manager(scope_id) is scope
        assert not manager._resolving

    @coroutine_test
    async def test_scope_eviction_does_not_orphan_a_waiting_request(self) -> None:
        """A scope that holds a waiting request back on nothing can be idle, and
        hence evicted, while the request waits on another of its scopes. The
        request must record its send on the manager its scope has by then, or the
        scope would end up with two sets of counters and exceed its concurrency.
        """
        manager = _manager(
            {
                "THROTTLING_SCOPE_LIMIT": 2,
                "DOWNLOAD_DELAY_JITTER": 0,
                "THROTTLING_SCOPES": {
                    "slow": {"delay": 0.5},
                    "shared": {"concurrency": 1},
                },
            }
        )
        # Make the "slow" scope hold requests back.
        warmup = Request("http://a.example/0", meta={"throttling_scopes": ["slow"]})
        await maybe_deferred_to_future(_wait_for_throttler(manager, warmup))
        manager.release(warmup)

        waiting = Request(
            "http://a.example/1", meta={"throttling_scopes": ["slow", "shared"]}
        )
        blocked = _wait_for_throttler(manager, waiting)
        await sleep(0)
        assert not blocked.called, "the 'slow' scope let the request through"

        # Unrelated scopes are used meanwhile, pushing past the scope limit; the
        # "shared" scope holds nothing back, so it is idle and gets evicted.
        for i in range(5):
            manager.get_scope_manager(f"other-{i}")
        assert "shared" not in manager._scope_managers

        done, _ = await wait_for_first([blocked], timeout=30)
        assert done, "the throttler never let the request through"
        await maybe_deferred_to_future(blocked)

        # The send landed on the manager that the scope has now, so the scope is
        # at its concurrency of 1 and holds the next request of it back.
        assert _scope(manager, "shared")._concurrency_blocked() is True

    def test_scope_limit_disabled(self):
        manager = _manager({"THROTTLING_SCOPE_LIMIT": 0})
        for i in range(5):
            scope = _scope(manager, f"{i}.example")
            scope._record_sent(now=0.0)
            scope._record_done(now=0.0)
        assert len(manager._scope_managers) == 5


class TestUnscheduledRequests:
    """Requests sent without going through the scheduler, i.e. through
    engine.download_async(), can be prerequisites of a request that is sitting in
    the downloader middlewares holding a slot of the same scope, so they can
    borrow such an unused slot and they get freed slots before the scheduler
    does."""

    @staticmethod
    def _hold_in_middlewares(
        monkeypatch: pytest.MonkeyPatch, manager: Throttler, *requests: Request
    ) -> None:
        """Make *requests* look like the downloader middlewares are processing
        them, which is otherwise the downloader's business."""
        held = set(requests)
        monkeypatch.setattr(
            manager, "_in_downloader_middlewares", lambda request: request in held
        )

    @staticmethod
    async def _acquire(manager: Throttler, request: Request, **kwargs: Any) -> None:
        # The wait is bounded so that a request that is never let through fails
        # the test instead of hanging it.
        acquired = _wait_for_throttler(manager, request, **kwargs)
        done, _ = await wait_for_first([acquired], timeout=30)
        assert done, f"the throttler never let {request} through"
        await maybe_deferred_to_future(acquired)

    @staticmethod
    async def _finish_waiting(blocked: Deferred[None]) -> None:
        """Wait for an unscheduled request passed to :func:`~scrapy.throttler._wait_for_throttler` to
        get through, bounded so that a request that never does fails the test
        instead of hanging it."""
        done, _ = await wait_for_first([blocked], timeout=30)
        assert done, "the unscheduled request was never let through"
        await maybe_deferred_to_future(blocked)

    @staticmethod
    async def _stop_waiting(blocked: Deferred[None]) -> None:
        """Stop waiting for an unscheduled request that is meant to stay
        blocked, so that it does not outlive the test."""
        blocked.addBoth(lambda _: None)  # swallow the cancellation
        blocked.cancel()
        await sleep(0)

    @coroutine_test
    async def test_borrows_the_slot_of_a_holder_in_the_middlewares(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}})
        holder = Request("http://example.com/1")
        await self._acquire(manager, holder)
        scope = _scope(manager, "example.com")
        assert scope._concurrency_blocked() is True
        self._hold_in_middlewares(monkeypatch, manager, holder)
        # The holder is not using the slot it took, and its middlewares may well
        # be waiting for this very request, so this one borrows it instead of
        # waiting for a slot that would never free up.
        prerequisite = Request("http://example.com/robots.txt")
        await self._acquire(manager, prerequisite, unscheduled=True)
        assert prerequisite in manager._reserved

    @coroutine_test
    async def test_does_not_borrow_while_a_holder_is_in_a_download_handler(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 2}}})
        in_middlewares = Request("http://example.com/1")
        in_handler = Request("http://example.com/2")
        await self._acquire(manager, in_middlewares)
        await self._acquire(manager, in_handler)
        self._hold_in_middlewares(monkeypatch, manager, in_middlewares)
        # One of the holders is in a download handler, so it will free its slot
        # on its own and there is nothing to break: this request waits for it.
        prerequisite = Request("http://example.com/3")
        call_later(0, manager.release, in_handler)
        await self._acquire(manager, prerequisite, unscheduled=True)
        assert manager.crawler.stats
        assert manager.crawler.stats.get_value("throttler/borrowed_slots") is None

    @coroutine_test
    async def test_does_not_borrow_from_a_holder_outside_the_downloader(self) -> None:
        """A concurrency slot is reserved before its request reaches the
        downloader, and released after it leaves, so a holder outside the
        downloader is not in a download handler either. It is not in the
        downloader middlewares though: it needs no help to reach a handler, or is
        already done with one. Treating it as being in the middlewares would let
        unscheduled requests that nothing is waiting for borrow slots without
        limit."""
        manager, downloader = _manager_with_downloader(
            {"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}}
        )
        holder = Request("http://example.com/1")
        await self._acquire(manager, holder)
        assert holder not in downloader.active
        assert manager._in_downloader_middlewares(holder) is False

        prerequisite = Request("http://example.com/2")
        blocked = _wait_for_throttler(manager, prerequisite, unscheduled=True)
        assert prerequisite not in manager._reserved
        assert manager.crawler.stats
        assert manager.crawler.stats.get_value("throttler/borrowed_slots") is None
        await self._stop_waiting(blocked)
        downloader.close()

    @coroutine_test
    async def test_borrows_once_a_holder_reaches_the_downloader(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A concurrency slot is reserved before its request reaches the
        downloader, so a holder still on its way there is not in the downloader
        middlewares yet; it gets there on arrival, without freeing any slot."""
        manager, downloader = _manager_with_downloader(
            {"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}}
        )
        holder = Request("http://example.com/1")
        await self._acquire(manager, holder)
        assert holder not in downloader.active
        assert _scope(manager, "example.com")._concurrency_blocked() is True

        prerequisite = Request("http://example.com/2")
        blocked = _wait_for_throttler(manager, prerequisite, unscheduled=True)
        assert prerequisite not in manager._reserved, (
            "the holder is still on its way to the downloader"
        )

        # Let the holder into the downloader, where the middlewares keep it
        # instead of handing it to a download handler.
        held: Deferred[None] = Deferred()

        async def hold(download_func: Any, request: Request) -> None:
            await maybe_deferred_to_future(held)

        monkeypatch.setattr(downloader.middleware, "download_async", hold)
        fetching = downloader.fetch(holder)
        fetching.addBoth(lambda _: None)

        await self._finish_waiting(blocked)
        assert prerequisite in manager._reserved
        assert manager.crawler.stats
        assert manager.crawler.stats.get_value("throttler/borrowed_slots") == 1
        held.callback(None)  # let the holder leave the downloader
        downloader.close()

    @coroutine_test
    async def test_does_not_borrow_without_a_downloader(self) -> None:
        # Without an engine there is no download handler state to tell a holder
        # that is using its slot from one that is not, so nothing is lent.
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}})
        await self._acquire(manager, Request("http://example.com/1"))
        prerequisite = Request("http://example.com/2")
        blocked = _wait_for_throttler(manager, prerequisite, unscheduled=True)
        assert not blocked.called
        assert prerequisite not in manager._reserved
        assert manager.crawler.stats
        assert manager.crawler.stats.get_value("throttler/borrowed_slots") is None
        await self._stop_waiting(blocked)

    @coroutine_test
    async def test_borrows_once_a_holder_leaves_the_download_handler(self) -> None:
        """A holder that gets its response and moves on to the downloader
        middlewares stops using its slot without freeing it, e.g. because those
        middlewares are now waiting for this very unscheduled request."""
        manager, downloader = _manager_with_downloader(
            {"THROTTLING_SCOPES": {"example.com": {"concurrency": 2}}}
        )
        in_middlewares = Request("http://example.com/1")
        in_handler = Request("http://example.com/2")
        await self._acquire(manager, in_middlewares)
        await self._acquire(manager, in_handler)
        downloader.active.update({in_middlewares, in_handler})
        downloader._in_download_handler.add(in_handler)

        prerequisite = Request("http://example.com/3")
        blocked = _wait_for_throttler(manager, prerequisite, unscheduled=True)
        assert not blocked.called, (
            "a holder is in a download handler, so nothing to lend"
        )

        downloader._leave_download_handler(in_handler)
        await self._finish_waiting(blocked)
        assert prerequisite in manager._reserved
        assert manager.crawler.stats
        assert manager.crawler.stats.get_value("throttler/borrowed_slots") == 1
        downloader.close()

    @coroutine_test
    async def test_borrows_at_nesting_depth_two(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}})
        holder = Request("http://example.com/1")
        await self._acquire(manager, holder)
        self._hold_in_middlewares(monkeypatch, manager, holder)
        first = Request("http://example.com/2")
        await self._acquire(manager, first, unscheduled=True)
        # The borrower is now in the downloader middlewares too, and its own
        # middlewares download a request of their own: it can borrow in turn, so
        # that nesting of any depth cannot deadlock.
        self._hold_in_middlewares(monkeypatch, manager, holder, first)
        second = Request("http://example.com/3")
        await self._acquire(manager, second, unscheduled=True)
        assert second in manager._reserved
        assert manager.crawler.stats
        assert manager.crawler.stats.get_value("throttler/borrowed_slots") == 2

    @coroutine_test
    async def test_scheduler_yields_a_free_slot_to_an_unscheduled_waiter(self) -> None:
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}})
        holder = Request("http://example.com/1")
        await self._acquire(manager, holder)
        waiting = Request("http://example.com/2")
        blocked = _wait_for_throttler(manager, waiting, unscheduled=True)
        scheduled = Request("http://example.com/3")
        scheduling = _wait_for_throttler(manager, scheduled)
        await sleep(0)
        manager.release(holder)
        # The freed slot goes to the unscheduled request, which has a claim on
        # it, rather than to the request from the scheduler.
        await self._finish_waiting(blocked)
        assert waiting in manager._reserved
        assert scheduled not in manager._reserved
        # Once it is served it no longer holds a claim on the scope.
        manager.release(waiting)
        done, _ = await wait_for_first([scheduling], timeout=30)
        assert done, "the throttler never let the scheduled request through"
        await maybe_deferred_to_future(scheduling)

    @coroutine_test
    async def test_scheduler_keeps_a_slot_the_unscheduled_waiter_cannot_use(
        self,
    ) -> None:
        manager = _manager(
            {"THROTTLING_SCOPES": {scope: {"concurrency": 1} for scope in "ab"}}
        )
        blocker = Request("http://example.com/1", meta={"throttling_scopes": "b"})
        await self._acquire(manager, blocker)
        waiting = Request(
            "http://example.com/2", meta={"throttling_scopes": ["a", "b"]}
        )
        blocked = _wait_for_throttler(manager, waiting, unscheduled=True)
        # The unscheduled request is waiting for scope b, so it cannot use a free
        # slot of scope a: the scheduler gets it.
        scheduled = Request("http://example.com/3", meta={"throttling_scopes": "a"})
        await self._acquire(manager, scheduled)
        assert scheduled in manager._reserved
        await self._stop_waiting(blocked)

    @coroutine_test
    async def test_a_waiter_claim_only_looks_at_the_scopes_holding_it_back(
        self,
    ) -> None:
        manager = _manager(
            {
                "THROTTLING_SCOPES": {"full": {"concurrency": 1}},
                "THROTTLING_SCOPE_LIMIT": 4,
            }
        )
        blocker = Request("http://example.com/1", meta={"throttling_scopes": "full"})
        await self._acquire(manager, blocker)
        waiting = Request(
            "http://example.com/2",
            meta={"throttling_scopes": ["evicted", "free", "shared", "full"]},
        )
        blocked = _wait_for_throttler(manager, waiting, unscheduled=True)
        # A new scope pushes past the scope limit while the waiter is blocked on
        # "full", dropping "evicted", the coldest idle scope of the waiter.
        manager.get_scope_manager("other")
        assert "evicted" not in manager._scope_managers
        # An evicted scope has no state to hold the waiter back, and "free" lets
        # it through, so only "full" decides: the waiter cannot use a free slot
        # of "shared" and the scheduler gets it.
        scheduled = Request(
            "http://example.com/3", meta={"throttling_scopes": "shared"}
        )
        await self._acquire(manager, scheduled)
        assert scheduled in manager._reserved
        await self._stop_waiting(blocked)

    @coroutine_test
    async def test_the_same_request_waiting_twice_reserves_once(self) -> None:
        """Downloading the same Request object twice at once is unsupported, but
        it must not record two sends that a single release() undoes: that would
        leave the scope one concurrency slot short for the rest of the crawl,
        with nothing to ever free it again."""
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 2}}})
        blockers = [Request("http://example.com/1"), Request("http://example.com/2")]
        for blocker in blockers:
            await self._acquire(manager, blocker)
        shared = Request("http://example.com/3")
        first = _wait_for_throttler(manager, shared, unscheduled=True)
        second = _wait_for_throttler(manager, shared, unscheduled=True)
        for blocker in blockers:
            manager.release(blocker)
        await self._finish_waiting(first)
        await self._finish_waiting(second)
        manager.release(shared)
        assert _scope(manager, "example.com")._active == 0

    @coroutine_test
    async def test_waiters_are_forgotten_once_served(self) -> None:
        manager = _manager()
        request = Request("http://example.com/1")
        await self._acquire(manager, request, unscheduled=True)
        assert not manager._unscheduled_waiters

    @coroutine_test
    async def test_a_served_waiter_does_not_forget_the_others(self) -> None:
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}})
        holder = Request("http://example.com/1")
        await self._acquire(manager, holder)
        first = Request("http://example.com/2")
        second = Request("http://example.com/3")
        first_blocked = _wait_for_throttler(manager, first, unscheduled=True)
        second_blocked = _wait_for_throttler(manager, second, unscheduled=True)
        assert len(manager._unscheduled_waiters["example.com"]) == 2
        manager.release(holder)
        await wait_for_first([first_blocked, second_blocked])
        # Whichever of the two took the freed slot, forgetting it must not
        # forget the other one, which is still waiting for the scope.
        served = [
            request for request in (first, second) if request in manager._reserved
        ]
        assert len(served) == 1
        pending = second if served[0] is first else first
        assert pending in manager._unscheduled_waiters["example.com"]
        manager.release(served[0])
        await maybe_deferred_to_future(first_blocked)
        await maybe_deferred_to_future(second_blocked)
        assert not manager._unscheduled_waiters

    @coroutine_test
    async def test_a_shared_waiter_entry_is_only_forgotten_once(self) -> None:
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 2}}})
        holders = [Request("http://example.com/1"), Request("http://example.com/2")]
        for holder in holders:
            await self._acquire(manager, holder)
        # The same request object can be sent unscheduled twice concurrently, e.g.
        # by two middlewares awaiting the same prerequisite. Both waits share a
        # single waiter entry, so the second one to be served finds it gone.
        request = Request("http://example.com/3")
        first_blocked = _wait_for_throttler(manager, request, unscheduled=True)
        second_blocked = _wait_for_throttler(manager, request, unscheduled=True)
        assert len(manager._unscheduled_waiters["example.com"]) == 1
        for holder in holders:
            manager.release(holder)
        await maybe_deferred_to_future(first_blocked)
        await maybe_deferred_to_future(second_blocked)
        assert not manager._unscheduled_waiters

    @coroutine_test
    async def test_does_not_borrow_from_a_scope_without_holders(self) -> None:
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}})
        scope = _scope(manager, "example.com")
        # The scope is full but the throttler is not tracking any holder for it,
        # so there is no unused slot to borrow: instead of assuming that an
        # untracked holder is in the downloader middlewares, the unscheduled
        # request waits for a slot.
        scope._record_sent()
        assert scope._concurrency_blocked() is True
        prerequisite = Request("http://example.com/1")
        call_later(0, scope._record_done)
        await self._acquire(manager, prerequisite, unscheduled=True)
        assert manager.crawler.stats
        assert manager.crawler.stats.get_value("throttler/borrowed_slots") is None

    @coroutine_test
    async def test_borrow_debug_logging(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        manager = _manager(
            {
                "THROTTLING_SCOPES": {"example.com": {"concurrency": 1}},
                "THROTTLER_DEBUG": True,
            }
        )
        holder = Request("http://example.com/1")
        await self._acquire(manager, holder)
        self._hold_in_middlewares(monkeypatch, manager, holder)
        prerequisite = Request("http://example.com/robots.txt")
        with caplog.at_level(logging.DEBUG, logger="scrapy.throttler"):
            await self._acquire(manager, prerequisite, unscheduled=True)
        assert "borrow a concurrency slot" in caplog.text
        assert prerequisite in manager._reserved

    @coroutine_test
    async def test_a_free_slot_is_yielded_to_a_waiter_only_once(self) -> None:
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}})
        # Recreate the transient state in which an unscheduled request is waiting
        # for a slot that has just freed up but has not been retried yet to
        # take it.
        waiting = Request("http://example.com/1")
        manager._resolve_scopes(waiting)
        manager._unscheduled_waiters["example.com"] = WeakSet([waiting])
        # A request from the scheduler yields control so that the waiter gets
        # the slot first, but only once, so that a claim that no one takes
        # cannot make it spin.
        scheduled = Request("http://example.com/2")
        await self._acquire(manager, scheduled)
        assert scheduled in manager._reserved

    @coroutine_test
    async def test_a_waiter_under_its_own_delay_has_no_claim(self) -> None:
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}})
        waiting = Request("http://example.com/1", meta={"delay": 1000.0})
        manager._resolve_scopes(waiting)
        manager._unscheduled_waiters["example.com"] = WeakSet([waiting])
        # The waiter cannot use a free slot until its own delay elapses, so it
        # has no claim on it and the scheduler may take it.
        scheduled = Request("http://example.com/2")
        await self._acquire(manager, scheduled)
        assert scheduled in manager._reserved


class TestThrottlingScopeManager:
    def test_no_delay_by_default(self):
        scope = _scope_manager()
        scope._record_sent(now=0.0)
        assert scope._can_send(now=0.0) == 0

    def test_base_delay_enforced(self):
        scope = _scope_manager({"DOWNLOAD_DELAY_JITTER": 0}, {"id": "x", "delay": 2.0})
        scope._record_sent(now=10.0)
        assert scope._can_send(now=10.0) == pytest.approx(2.0)
        assert scope._can_send(now=11.0) == pytest.approx(1.0)
        assert scope._can_send(now=12.0) == 0

    def test_base_delay_defaults_to_download_delay(self):
        # With no explicit scope "delay", the base delay is DOWNLOAD_DELAY.
        scope = _scope_manager(
            {"DOWNLOAD_DELAY": 2.0, "DOWNLOAD_DELAY_JITTER": 0}, {"id": "x"}
        )
        assert scope._base_delay == pytest.approx(2.0)

    def test_scope_delay_overrides_download_delay(self):
        # An explicit scope "delay" overrides DOWNLOAD_DELAY.
        scope = _scope_manager(
            {"DOWNLOAD_DELAY": 2.0, "DOWNLOAD_DELAY_JITTER": 0},
            {"id": "x", "delay": 0.0},
        )
        assert scope._base_delay == pytest.approx(0.0)

    def test_set_base_delay_raises_only(self):
        scope = _scope_manager({"DOWNLOAD_DELAY_JITTER": 0}, {"id": "x", "delay": 5.0})
        scope.set_base_delay(2.0)  # lower -> ignored
        assert scope._base_delay == 5.0
        scope.set_base_delay(8.0)  # higher -> applied
        assert scope._base_delay == 8.0

    def test_default_scope_concurrency(self):
        scope = _scope_manager()
        assert scope._concurrency == 8

    def test_scope_concurrency_setting(self):
        # THROTTLING_SCOPE_CONCURRENCY governs scopes that set no concurrency of
        # their own (here a bare "custom" group name).
        scope = _scope_manager(
            settings={"THROTTLING_SCOPE_CONCURRENCY": 3}, config={"id": "custom"}
        )
        assert scope._concurrency == 3

    def test_concurrency_limit(self):
        scope = _scope_manager(config={"id": "x", "concurrency": 2})
        scope._record_sent(now=0.0)
        # Concurrency is enforced via _concurrency_blocked(), not _can_send().
        assert scope._can_send(now=0.0) == 0
        assert scope._concurrency_blocked() is False
        scope._record_sent(now=0.0)
        # Two in flight, limit reached -> blocked.
        assert scope._can_send(now=0.0) == 0
        assert scope._concurrency_blocked() is True
        scope._record_done(now=0.0)
        assert scope._concurrency_blocked() is False

    def test_record_done_fires_slot_available_event(self):
        scope = _scope_manager(config={"id": "x", "concurrency": 1})
        scope._record_sent(now=0.0)
        event = scope._slot_available_event()
        assert not event.called
        scope._record_done(now=0.0)
        assert event.called

    def test_record_done_fires_one_event_per_freed_slot(self):
        scope = _scope_manager(config={"id": "x", "concurrency": 2})
        scope._record_sent(now=0.0)
        scope._record_sent(now=0.0)
        events = [scope._slot_available_event() for _ in range(3)]
        scope._record_done(now=0.0)
        assert [event.called for event in events] == [True, False, False]
        scope._record_done(now=0.0)
        assert [event.called for event in events] == [True, True, False]

    def test_set_concurrency_fires_slot_available_event(self):
        scope = _scope_manager(config={"id": "x", "concurrency": 1})
        scope._record_sent(now=0.0)
        event = scope._slot_available_event()
        assert not event.called
        scope.set_concurrency(5)
        assert event.called

    def test_discard_slot_available_event(self):
        scope = _scope_manager(config={"id": "x", "concurrency": 1})
        event = scope._slot_available_event()
        scope._discard_slot_available_event(event)
        scope._discard_slot_available_event(event)  # idempotent
        scope._record_sent(now=0.0)
        scope._record_done(now=0.0)
        assert not event.called

    def test_set_concurrency_rejects_negative(self):
        scope = _scope_manager(config={"id": "x", "concurrency": 4})
        with pytest.raises(ValueError, match="must be 0 or higher"):
            scope.set_concurrency(-1)
        assert scope._concurrency == 4
        scope.set_concurrency(5)
        assert scope._concurrency == 5

    @pytest.mark.parametrize(
        ("global_concurrency", "expected"), [(16, 16), (0, sys.maxsize)]
    )
    def test_set_concurrency_zero(self, global_concurrency, expected):
        scope = _scope_manager(
            {"CONCURRENT_REQUESTS": global_concurrency},
            {"id": "x", "concurrency": 4},
        )
        scope.set_concurrency(0)
        assert scope.get_concurrency() == expected


class TestThrottlerScopeLoad:
    @coroutine_test
    async def test_get_scope_load(self):
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 4}}})
        assert manager.get_scope_load("example.com") == 0.0
        request = Request("http://example.com/1")
        await maybe_deferred_to_future(_wait_for_throttler(manager, request))
        assert manager.get_scope_load("example.com") == pytest.approx(0.25)

    @coroutine_test
    async def test_get_scope_load_uses_the_default_concurrency(self):
        manager = _manager({"THROTTLING_SCOPE_CONCURRENCY": 8})
        # A scope that sets no concurrency of its own is limited by the default.
        await maybe_deferred_to_future(
            _wait_for_throttler(manager, Request("http://example.com/1"))
        )
        assert manager.get_scope_load("example.com") == pytest.approx(1 / 8)

    @coroutine_test
    async def test_get_scope_load_creates_no_scope_manager(self):
        # DownloaderAwarePriorityQueue asks for the load of every queued scope on
        # every pop, which on a broad crawl means every pending domain, so merely
        # asking must not build (or LRU-touch) a scope manager.
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}})
        assert manager.get_scope_load("example.com") == 0.0
        assert not manager._scope_managers


class TestScopeHelpers:
    def test_normalize_scopes(self):
        assert _normalize_scopes(None) == []
        assert _normalize_scopes("a") == ["a"]
        assert _normalize_scopes(["a", "b"]) == ["a", "b"]

    def test_one_shot_iterables_are_materialized(self):
        # The persisted scopes must stay re-iterable and serializable.
        class GeneratorThrottler(Throttler):
            def get_scopes(self, request: Request) -> RequestScopes:
                return (scope for scope in ("a", "b"))

        manager = GeneratorThrottler(get_crawler())
        request = Request("http://example.com/a")
        assert manager._resolve_scopes(request) == ["a", "b"]
        assert manager.get_applied_scopes(request) == ["a", "b"]


class TestThrottlerEdges:
    @coroutine_test
    async def test_acquire_without_scopes(self):
        manager = _manager()
        request = Request("http://example.com/a", meta={"throttling_scopes": []})
        # No scopes resolve, so acquire() returns without reserving anything.
        await maybe_deferred_to_future(_wait_for_throttler(manager, request))
        assert request not in manager._reserved

    def test_get_scope_load_does_not_create_a_scope(self):
        # A priority queue asks for the load of every queued scope on every pop,
        # so an unknown scope must report no load without getting a scope manager
        # (which on a broad crawl would mean one per pending domain).
        manager = _manager({"CONCURRENT_REQUESTS": 0})
        assert manager.get_scope_load("example.com") == 0.0
        assert "example.com" not in manager._scope_managers

    @coroutine_test
    async def test_acquire_logs_and_waits_for_delay(self):
        manager = _manager(
            {
                "THROTTLING_SCOPES": {"example.com": {"delay": 0.02}},
                "DOWNLOAD_DELAY_JITTER": 0,
                "THROTTLER_DEBUG": True,
            }
        )
        r1 = Request("http://example.com/1")
        r2 = Request("http://example.com/2")
        await maybe_deferred_to_future(_wait_for_throttler(manager, r1))
        # r2 must wait out the per-scope delay accrued by r1 before it proceeds.
        await maybe_deferred_to_future(_wait_for_throttler(manager, r2))
        assert r2 in manager._reserved

    @coroutine_test
    async def test_acquire_logs_while_waiting_for_slot(self):
        manager = _manager(
            {
                "THROTTLING_SCOPES": {"example.com": {"concurrency": 1}},
                "THROTTLER_DEBUG": True,
            }
        )
        r1 = Request("http://example.com/1")
        r2 = Request("http://example.com/2")
        await maybe_deferred_to_future(_wait_for_throttler(manager, r1))
        call_later(0, manager.release, r1)
        # r2 is concurrency-blocked and waits, with debug logging, for the slot.
        await maybe_deferred_to_future(_wait_for_throttler(manager, r2))
        assert r2 in manager._reserved

    @pytest.mark.parametrize("debug", [False, True])
    @coroutine_test
    async def test_delay_meta(self, debug: bool) -> None:
        delay = 0.2
        manager = _manager({"THROTTLER_DEBUG": debug})
        request = Request("http://example.com/a", meta={"delay": delay})

        async def held() -> float:
            start = monotonic()
            await maybe_deferred_to_future(_wait_for_throttler(manager, request))
            manager.release(request)
            return monotonic() - start

        delayed = await held()
        assert "delay" not in request.meta
        # Acquiring the same request again does not hold it again, but setting
        # the key again does.
        assert await held() < delay
        request.meta["delay"] = delay
        assert await held() >= delay
        assert delayed >= delay
        assert request.meta["delayed"] == [delay, delay]

    @coroutine_test
    async def test_delay_meta_stale_deadline(self) -> None:
        delay = 0.2
        manager = _manager()
        # A deadline from a different run of the crawl, restored from a disk
        # queue, is capped at the delay.
        request = Request(
            "http://example.com/a",
            meta={"_delay_deadline": (delay, time() + 10 * delay)},
        )
        start = monotonic()
        await maybe_deferred_to_future(_wait_for_throttler(manager, request))
        assert delay <= monotonic() - start < 2 * delay

    @coroutine_test
    async def test_wait_discards_the_events_that_did_not_wake_it(self):
        manager = _manager(
            {
                "THROTTLING_SCOPES": {
                    "a": {"concurrency": 1},
                    "b": {"concurrency": 1},
                }
            }
        )
        holder_a = Request("http://example.com/1", meta={"throttling_scopes": "a"})
        holder_b = Request("http://example.com/2", meta={"throttling_scopes": "b"})
        await maybe_deferred_to_future(_wait_for_throttler(manager, holder_a))
        await maybe_deferred_to_future(_wait_for_throttler(manager, holder_b))
        request = Request(
            "http://example.com/3", meta={"throttling_scopes": ["a", "b"]}
        )
        acquired = _wait_for_throttler(manager, request)
        manager.release(holder_a)
        # Still held back by b, the request waits for its event once.
        assert len(_scope(manager, "b")._slot_available._waiters) == 1
        manager.release(holder_b)
        await maybe_deferred_to_future(acquired)
        assert _scope(manager, "a")._slot_available._waiters == []
        assert _scope(manager, "b")._slot_available._waiters == []

    @coroutine_test
    async def test_unscheduled_wait_discards_the_middlewares_event(self):
        manager, downloader = _manager_with_downloader(
            {"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}}
        )
        holder = Request("http://example.com/1")
        await maybe_deferred_to_future(_wait_for_throttler(manager, holder))
        acquired = _wait_for_throttler(
            manager, Request("http://example.com/2"), unscheduled=True
        )
        manager.release(holder)
        await maybe_deferred_to_future(acquired)
        assert downloader._downloader_middlewares_entry._waiters == []
        downloader.close()

    @coroutine_test
    async def test_unscheduled_wait_discards_the_slot_event(self):
        manager, downloader = _manager_with_downloader(
            {"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}}
        )
        holder = Request("http://example.com/1")
        await maybe_deferred_to_future(_wait_for_throttler(manager, holder))
        downloader.active.add(holder)
        downloader._in_download_handler.add(holder)
        acquired = _wait_for_throttler(
            manager, Request("http://example.com/2"), unscheduled=True
        )
        # Back in the middlewares, the holder lends its slot, so the wait ends
        # without the scope freeing one.
        downloader._leave_download_handler(holder)
        await maybe_deferred_to_future(acquired)
        assert _scope(manager, "example.com")._slot_available._waiters == []
        downloader.close()

    @coroutine_test
    async def test_unscheduled_wait_without_an_engine(self):
        # There is no downloader to watch before the crawl starts, so the wait
        # relies on the scope events alone.
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}})
        holder = Request("http://example.com/1")
        await maybe_deferred_to_future(_wait_for_throttler(manager, holder))
        acquired = _wait_for_throttler(
            manager, Request("http://example.com/2"), unscheduled=True
        )
        manager.release(holder)
        await maybe_deferred_to_future(acquired)
        assert _scope(manager, "example.com")._slot_available._waiters == []

    @coroutine_test
    async def test_cancelled_wait_ignores_its_events_fired_in_the_same_batch(self):
        manager, downloader = _manager_with_downloader(
            {"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}}
        )
        holder = Request("http://example.com/1")
        await maybe_deferred_to_future(_wait_for_throttler(manager, holder))
        request = Request("http://example.com/2")
        acquisitions: list[Deferred[None]] = []

        def cancel_and_release(_: None) -> None:
            acquisitions[0].cancel()
            manager.release(holder)

        # Registered first, so it runs before the wait it cancels gets the same
        # middlewares event.
        downloader._downloader_middlewares_event().addCallback(cancel_and_release)
        acquisitions.append(_wait_for_throttler(manager, request, unscheduled=True))
        acquisitions[0].addErrback(lambda _: None)
        downloader.close()
        assert request not in manager._reserved
        assert _scope(manager, "example.com")._active == 0

    @coroutine_test
    async def test_cancelled_wait_does_not_take_a_freed_slot(self):
        manager = _manager({"THROTTLING_SCOPES": {"example.com": {"concurrency": 1}}})
        holder = Request("http://example.com/1")
        await maybe_deferred_to_future(_wait_for_throttler(manager, holder))
        request = Request("http://example.com/2")
        acquired = _wait_for_throttler(manager, request)
        acquired.addErrback(lambda _: None)
        acquired.cancel()
        manager.release(holder)
        assert request not in manager._reserved
        assert _scope(manager, "example.com")._active == 0

    @coroutine_test
    async def test_acquire_raises_what_get_scopes_raises(self):
        class FailingThrottler(Throttler):
            def get_scopes(self, request: Request) -> RequestScopes:
                raise ValueError("no scopes")

        manager = FailingThrottler.from_crawler(get_crawler())
        with pytest.raises(ValueError, match="no scopes"):
            await maybe_deferred_to_future(
                _wait_for_throttler(manager, Request("http://example.com/1"))
            )

    def test_scope_limit_disabled(self):
        manager = _manager({"THROTTLING_SCOPE_LIMIT": 0})
        for scope_id in ("a.example", "b.example", "c.example"):
            scope = _scope(manager, scope_id)
            scope._record_sent(now=0.0)
            scope._record_done(now=0.0)
        # No limit: idle scopes are kept regardless.
        assert len(manager._scope_managers) == 3


class TestThrottlingScopeManagerEdges:
    def test_jitter_disabled(self):
        scope = _scope_manager(config={"id": "x", "jitter": 0})
        assert scope._apply_jitter(4.0, scope._jitter) == pytest.approx(4.0)

    @pytest.mark.parametrize(("value", "expected"), [(0.2, 0.2), ("0.2", 0.2)])
    def test_jitter_from_settings(self, value: Any, expected: float):
        scope = _scope_manager({"DOWNLOAD_DELAY_JITTER": value}, {"id": "x"})
        assert scope._jitter == pytest.approx(expected)

    def test_jitter_above_one_does_not_go_below_zero(self):
        scope = _scope_manager(config={"id": "x", "delay": 2.0, "jitter": 3.0})
        assert min(scope._effective_delay() for _ in range(100)) >= 0.0

    def test_effective_delay_randomized(self):
        scope = _scope_manager(
            {"DOWNLOAD_DELAY_JITTER": 0.5}, {"id": "x", "delay": 2.0}
        )
        scope._record_sent(now=0.0)
        # A randomized base delay lands within [0.5, 1.5] * delay.
        assert 1.0 <= scope._can_send(now=0.0) <= 3.0

    def test_record_done_without_active(self):
        scope = _scope_manager(config={"id": "x"})
        # Calling _record_done() with nothing in flight is a harmless no-op.
        scope._record_done(now=0.0)
        assert scope._active == 0

    def test_is_idle_with_active_requests(self):
        scope = _scope_manager(config={"id": "x"})
        scope._record_sent(now=0.0)
        # An in-flight request keeps the scope from being evicted.
        assert scope._is_idle(now=10_000.0) is False

    def test_is_idle_when_never_used(self):
        scope = _scope_manager(config={"id": "x"})
        assert scope._is_idle(now=0.0) is True

    def test_is_idle_with_a_pending_delay(self):
        scope = _scope_manager(config={"id": "x", "delay": 10.0, "jitter": 0})
        scope._record_sent(now=0.0)
        scope._record_done(now=0.0)
        # The delay is state that eviction would drop, so the scope is not idle
        # until it has elapsed.
        assert scope._is_idle(now=5.0) is False
        assert scope._is_idle(now=11.0) is True

    def test_get_load_is_relative_to_the_limit(self):
        scope = _scope_manager(config={"id": "x", "concurrency": 4})
        scope._record_sent(now=0.0)
        assert scope._get_load() == pytest.approx(0.25)
        # Borrowing (see Throttler._borrow_slots) can push a scope past its
        # limit, and the load reflects that rather than being clipped at 1.
        for _ in range(4):
            scope._record_sent(now=0.0)
        assert scope._get_load() == pytest.approx(1.25)


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
        # Neither setting is set explicitly: the per-domain default (8) is kept
        # for backward compatibility over the scope default (1).
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

    def test_per_domain_reaches_the_scope_manager(self):
        # The bridge checked above in isolation, but through a crawler: the
        # deprecated setting must still be what a scope of the resulting
        # throttler is limited by.
        with pytest.warns(ScrapyDeprecationWarning, match="is deprecated"):
            crawler = get_crawler(SimpleSpider, {"CONCURRENT_REQUESTS_PER_DOMAIN": 3})
        manager = crawler.throttler.get_scope_manager("example.com")
        assert manager.get_concurrency() == 3

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

    def test_unachievable_concurrency_warning(self, caplog):
        settings = self._settings(scope=100)
        settings.set("CONCURRENT_REQUESTS", 16, priority="spider")
        with caplog.at_level(logging.WARNING):
            _warn_on_unachievable_concurrency(settings, {})
        assert "THROTTLING_SCOPE_CONCURRENCY=100" in caplog.text

    def test_no_unachievable_concurrency_warning_without_a_global_limit(self, caplog):
        # A CONCURRENT_REQUESTS of 0 caps nothing, so no per-scope limit is out
        # of reach.
        settings = self._settings(scope=100)
        settings.set("CONCURRENT_REQUESTS", 0, priority="spider")
        with caplog.at_level(logging.WARNING):
            _warn_on_unachievable_concurrency(settings, {"a": {"concurrency": 100}})
        assert not caplog.text

    def test_unachievable_concurrency_warning_ignores_the_overridden_setting(
        self, caplog
    ):
        # THROTTLING_SCOPE_CONCURRENCY overrides the deprecated per-domain
        # setting, so the latter's (default, unreachable) value is not in effect
        # and must not be reported as an offender.
        settings = self._settings(scope=2)
        settings.set("CONCURRENT_REQUESTS", 4, priority="spider")
        assert settings.getint("CONCURRENT_REQUESTS_PER_DOMAIN") == 8
        with caplog.at_level(logging.WARNING):
            _warn_on_unachievable_concurrency(settings, {})
        assert not caplog.text

    def test_unachievable_concurrency_warning_names_the_effective_setting(self, caplog):
        # The deprecated setting is the one in effect here, so it is the one
        # reported.
        settings = self._settings(per_domain=100)
        settings.set("CONCURRENT_REQUESTS", 16, priority="spider")
        with caplog.at_level(logging.WARNING):
            _warn_on_unachievable_concurrency(settings, {})
        assert "CONCURRENT_REQUESTS_PER_DOMAIN=100" in caplog.text
        assert "THROTTLING_SCOPE_CONCURRENCY" not in caplog.text

    def test_unachievable_scope_concurrency_warning(self, caplog):
        # The merged per-scope configuration is what is reported, so a limit
        # coming from the deprecated DOWNLOAD_SLOTS setting is covered too.
        settings = Settings()
        settings.set("CONCURRENT_REQUESTS", 4, priority="spider")
        settings.set("DOWNLOAD_SLOTS", {"a": {"concurrency": 50}}, priority="spider")
        with caplog.at_level(logging.WARNING):
            _warn_on_unachievable_concurrency(
                settings, Throttler._merge_download_slots(settings)
            )
        assert "the concurrency of throttling scope 'a'=50" in caplog.text


class TestJitterBridging:
    def _settings(self, **kwargs: Any) -> Settings:
        settings = Settings()
        for name, value in kwargs.items():
            settings.set(name, value, priority="spider")
        return settings

    def test_default_when_neither_set(self):
        assert _default_jitter(Settings()) == 0.5

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (True, 0.5),
            (False, 0.0),
            # Every spelling that RANDOMIZE_DOWNLOAD_DELAY has ever accepted as
            # a boolean keeps meaning the same ±50%, or none.
            (1, 0.5),
            (0, 0.0),
            ("1", 0.5),
            ("0", 0.0),
            ("True", 0.5),
            ("false", 0.0),
        ],
    )
    def test_randomize_maps_to_a_magnitude(self, value: Any, expected: float):
        settings = self._settings(RANDOMIZE_DOWNLOAD_DELAY=value)
        assert _default_jitter(settings) == pytest.approx(expected)

    def test_jitter_wins_when_higher_priority(self):
        settings = self._settings(DOWNLOAD_DELAY_JITTER=0.2)
        settings.set("RANDOMIZE_DOWNLOAD_DELAY", False, priority="default")
        assert _default_jitter(settings) == pytest.approx(0.2)

    def test_jitter_wins_on_explicit_tie(self):
        settings = self._settings(
            RANDOMIZE_DOWNLOAD_DELAY=False, DOWNLOAD_DELAY_JITTER=0.2
        )
        assert _default_jitter(settings) == pytest.approx(0.2)

    def test_randomize_reaches_the_scope_manager(self):
        with pytest.warns(ScrapyDeprecationWarning, match="is deprecated"):
            crawler = get_crawler(SimpleSpider, {"RANDOMIZE_DOWNLOAD_DELAY": False})
        assert crawler.throttler.get_scope_manager("example.com")._jitter == 0.0

    def test_warns_when_randomize_set(self):
        settings = self._settings(RANDOMIZE_DOWNLOAD_DELAY=True)
        with pytest.warns(
            ScrapyDeprecationWarning,
            match="RANDOMIZE_DOWNLOAD_DELAY setting is deprecated",
        ):
            _warn_on_deprecated_randomization(settings)

    @pytest.mark.parametrize("settings_dict", [{}, {"DOWNLOAD_DELAY_JITTER": 0}])
    def test_no_warning_otherwise(self, settings_dict: dict[str, Any]):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            _warn_on_deprecated_randomization(self._settings(**settings_dict))


class TestIgnoredPerIPConcurrency:
    def test_warns_when_set(self):
        with pytest.warns(
            ScrapyDeprecationWarning, match="no longer has any effect"
        ) as records:
            get_crawler(SimpleSpider, {"CONCURRENT_REQUESTS_PER_IP": 2})
        assert sum("CONCURRENT_REQUESTS_PER_IP" in str(r.message) for r in records) == 1

    def test_silent_when_unset(self):
        settings = Settings()
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            _warn_on_ignored_per_ip(settings)


class TestScopeConcurrencyValidation:
    @pytest.mark.parametrize(
        "setting",
        ["THROTTLING_SCOPE_CONCURRENCY", "CONCURRENT_REQUESTS_PER_DOMAIN"],
    )
    def test_rejects_a_negative_default(self, setting):
        # Whichever of the two settings is in effect (see
        # _default_scope_concurrency_setting) is the one checked and named.
        settings = Settings()
        settings.set(setting, -1, priority="spider")
        assert _default_scope_concurrency_setting(settings) == setting
        with pytest.raises(ValueError, match=f"{setting} must be 0 or higher"):
            _check_scope_concurrency(settings, {})

    @pytest.mark.parametrize(
        "settings",
        [
            {"THROTTLING_SCOPES": {"example.com": {"concurrency": -1}}},
            # A limit bridged in from the deprecated setting is checked too.
            {"DOWNLOAD_SLOTS": {"example.com": {"concurrency": -1}}},
        ],
        ids=["throttling-scopes", "download-slots"],
    )
    def test_rejects_a_negative_scope_limit(self, settings):
        with pytest.raises(
            ValueError,
            match=r"concurrency of throttling scope 'example\.com' must be 0 or higher",
        ):
            _manager(settings)

    def test_accepts_one(self):
        manager = _manager({"THROTTLING_SCOPE_CONCURRENCY": 1})
        assert _scope(manager, "example.com")._concurrency == 1

    @pytest.mark.parametrize(
        ("global_concurrency", "expected"), [(16, 16), (0, sys.maxsize)]
    )
    @pytest.mark.parametrize(
        "settings",
        [
            {"THROTTLING_SCOPE_CONCURRENCY": 0},
            {"THROTTLING_SCOPES": {"example.com": {"concurrency": 0}}},
        ],
        ids=["default", "scope"],
    )
    def test_zero_means_no_limit(self, settings, global_concurrency, expected):
        manager = _manager({**settings, "CONCURRENT_REQUESTS": global_concurrency})
        assert _scope(manager, "example.com").get_concurrency() == expected


class TestScopeConfigValidation:
    @pytest.mark.parametrize("setting", ["THROTTLING_SCOPES", "DOWNLOAD_SLOTS"])
    @pytest.mark.parametrize("config", [1, "concurrency=1", ["concurrency", 1], None])
    def test_rejects_a_non_mapping_entry(self, setting, config):
        # Every reader of these settings expects a mapping per scope, so a
        # malformed entry is named here instead of failing deeper in.
        with pytest.raises(
            TypeError,
            match=rf"{setting}\['example\.com'\] must be a mapping",
        ):
            _manager({setting: {"example.com": config}})

    def test_accepts_any_mapping(self):
        manager = _manager(
            {"THROTTLING_SCOPES": {"example.com": ChainMap({"delay": 2.0})}}
        )
        assert _scope(manager, "example.com").get_base_delay() == 2.0


class _SharedPrerequisiteMiddleware:
    """Downloader middleware that needs a shared resource from the same host
    before it can hand over a response, e.g. a refreshed session token: the
    first response fetches it, later ones wait for that same fetch."""

    def __init__(self, crawler: Any) -> None:
        self.crawler = crawler
        self._prerequisite: Any = None

    @classmethod
    def from_crawler(cls, crawler: Any) -> Self:
        return cls(crawler)

    async def process_response(self, request: Request, response: Response) -> Response:
        if request.meta.get("is_prerequisite"):
            return response
        if self._prerequisite is None:
            self._prerequisite = Deferred()
            prerequisite_request = Request(
                self.crawler.spider.prerequisite_url,
                meta={"is_prerequisite": True, "dont_obey_robotstxt": True},
                callback=NO_CALLBACK,
                dont_filter=True,
            )
            fetched = await self.crawler.engine.download_async(prerequisite_request)
            waiting, self._prerequisite = self._prerequisite, fetched
            waiting.callback(fetched)
        elif isinstance(self._prerequisite, Deferred):
            await maybe_deferred_to_future(self._prerequisite)
        return response


class _DownloadHandlerPeakExtension:
    """Records, for the whole crawl, the highest number of requests of a single
    :ref:`throttling scope <throttling-scopes>` that a download handler is
    working on at once."""

    def __init__(self, crawler: Any) -> None:
        self.crawler = crawler
        self.peak: dict[str, int] = {}
        self._sampler: asyncio.Future[None] | None = None
        crawler.signals.connect(self._opened, signal=signals.spider_opened)
        crawler.signals.connect(self._closed, signal=signals.spider_closed)

    @classmethod
    def from_crawler(cls, crawler: Any) -> Self:
        return cls(crawler)

    def _opened(self) -> None:
        self._sampler = asyncio.ensure_future(self._sample())

    def _closed(self) -> None:
        if self._sampler is not None:
            self._sampler.cancel()

    async def _sample(self) -> None:
        downloader = self.crawler.engine.downloader
        while True:
            counts: dict[str, int] = {}
            for request in list(downloader._in_download_handler):
                key = request.meta.get(downloader.DOWNLOAD_SLOT, "")
                counts[key] = counts.get(key, 0) + 1
            for key, count in counts.items():
                self.peak[key] = max(self.peak.get(key, 0), count)
            await sleep(0.005)


class _UnscheduledFloodSpider(Spider):
    """Sends many requests to one host without going through the scheduler at
    once, like a media pipeline does for the files of an item. None of them is a
    prerequisite of a request sitting in the downloader middlewares, so none of
    them has any claim on a concurrency slot of the scope they share."""

    name = "unscheduled_flood"
    request_count = 8

    async def start(self) -> AsyncIterator[Request]:
        yield Request(self.seed_url, dont_filter=True)  # type: ignore[attr-defined]

    async def parse(self, response: Response) -> None:
        await asyncio.gather(
            *(
                self.crawler.engine.download_async(
                    Request(
                        self.url_template.format(i=i),  # type: ignore[attr-defined]
                        callback=NO_CALLBACK,
                        dont_filter=True,
                    )
                )
                for i in range(self.request_count)
            )
        )


class _TwoRequestSpider(Spider):
    name = "two_requests"

    async def start(self) -> AsyncIterator[Request]:
        yield Request(self.fast_url, dont_filter=True)  # type: ignore[attr-defined]
        yield Request(self.slow_url, dont_filter=True)  # type: ignore[attr-defined]

    def parse(self, response: Response) -> None:
        return


class _DelaySpider(MockServerSpider):
    name = "delay_meta"
    custom_settings = {"CONCURRENT_REQUESTS": 1}

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.times: list[float] = []
        self.start_time: float = monotonic()

    async def start(self) -> AsyncIterator[Request]:
        assert self.mockserver
        # The slow request keeps the delayed one waiting for its turn for longer
        # than its delay.
        yield Request(self.mockserver.url("/delay?n=1"))
        yield Request(self.mockserver.url("/status?n=200"), meta={"delay": 0.9})

    def parse(self, response: Response) -> None:
        self.times.append(monotonic() - self.start_time)


class TestThrottlerIntegration:
    @coroutine_test
    async def test_delay_meta_countdown_starts_when_scheduled(self, mockserver):
        crawler = get_crawler(_DelaySpider)
        await crawler.crawl_async(mockserver=mockserver)
        spider = crawler.spider
        assert isinstance(spider, _DelaySpider)
        assert len(spider.times) == 2
        # The delay ran while the request waited for its turn, so it was sent as
        # soon as it got one, rather than 0.9s later.
        assert spider.times[1] < spider.times[0] + 0.5

    @coroutine_test
    async def test_robotstxt_does_not_wait_for_a_concurrency_slot(self, mockserver):
        """A robots.txt request is downloaded from a downloader middleware,
        while the request that triggered it is holding the only concurrency
        slot of the very same scope and waiting for it, so it has to borrow
        that unused slot."""
        crawler = get_crawler(
            SimpleSpider,
            {
                "ROBOTSTXT_OBEY": True,
                "THROTTLING_SCOPE_CONCURRENCY": 1,
            },
        )
        crawl = deferred_from_coro(
            crawler.crawl_async(mockserver.url("/status?n=200"), mockserver=mockserver)
        )
        # A bounded wait, so that a regression fails instead of hanging.
        done, _ = await wait_for_first([crawl], timeout=30)
        assert done, "the crawl deadlocked in the throttler"
        await maybe_deferred_to_future(crawl)
        assert crawler.stats
        assert crawler.stats.get_value("robotstxt/request_count") == 1
        assert crawler.stats.get_value("response_received_count") == 2
        assert crawler.stats.get_value("throttler/borrowed_slots") == 1

    @coroutine_test
    async def test_response_prerequisite_does_not_wait_for_a_concurrency_slot(
        self, mockserver
    ):
        """Every concurrency slot of a scope is held by a request whose
        ``process_response`` chain is waiting for the same request sent from a
        downloader middleware, and the last of them only started waiting after
        that request had already found the scope full."""
        crawler = get_crawler(
            _TwoRequestSpider,
            {
                "THROTTLING_SCOPE_CONCURRENCY": 2,
                "DOWNLOADER_MIDDLEWARES": {_SharedPrerequisiteMiddleware: 1000},
            },
        )
        crawl = deferred_from_coro(
            crawler.crawl_async(
                # A staggered pair, so that one response is being processed by
                # the downloader middlewares while the other is still in a
                # download handler.
                fast_url=mockserver.url("/delay?n=0&b=0"),
                slow_url=mockserver.url("/delay?n=1&b=0"),
                prerequisite_url=mockserver.url("/status?n=200"),
                mockserver=mockserver,
            )
        )
        # A bounded wait, so that a regression fails instead of hanging.
        done, _ = await wait_for_first([crawl], timeout=30)
        assert done, "the crawl deadlocked in the throttler"
        await maybe_deferred_to_future(crawl)
        assert crawler.stats
        assert crawler.stats.get_value("response_received_count") == 3
        assert crawler.stats.get_value("throttler/borrowed_slots") == 1

    @pytest.mark.only_asyncio  # the sampling extension needs an asyncio loop
    @coroutine_test
    async def test_borrowing_keeps_the_concurrency_limit_in_handlers(self, mockserver):
        """A concurrency slot is only lent while none of the requests holding one
        is in a download handler, so an unscheduled request that no request in the
        downloader middlewares is waiting for cannot borrow past the limit: the
        target host never sees more than the configured concurrency, however many
        unscheduled requests pile up.
        """
        concurrency = 2
        crawler = get_crawler(
            _UnscheduledFloodSpider,
            {
                # High enough that the scope limit, not this one, is what bounds
                # the flood.
                "CONCURRENT_REQUESTS": 16,
                "THROTTLING_SCOPE_CONCURRENCY": concurrency,
                "DOWNLOAD_DELAY": 0,
                "EXTENSIONS": {_DownloadHandlerPeakExtension: 0},
            },
        )
        await crawler.crawl_async(
            seed_url=mockserver.url("/status?n=200"),
            # Slow enough that any overlap spans many sampling intervals.
            url_template=mockserver.url("/delay?n=0.3&b=0&i={i}"),
            mockserver=mockserver,
        )
        assert crawler.stats
        assert (
            crawler.stats.get_value("downloader/request_count")
            == _UnscheduledFloodSpider.request_count + 1
        ), "not every unscheduled request went out"
        assert crawler.extensions is not None
        extension = next(
            e
            for e in crawler.extensions.middlewares
            if isinstance(e, _DownloadHandlerPeakExtension)
        )
        assert extension.peak, "no download handler activity was sampled"
        assert max(extension.peak.values()) <= concurrency, extension.peak
