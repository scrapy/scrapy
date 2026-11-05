from __future__ import annotations

import contextlib
import os
import socket
from pathlib import Path
from typing import TYPE_CHECKING, Any

from twisted.internet.defer import Deferred

from scrapy.settings import Settings, default_settings
from scrapy.utils.asyncio import call_later
from scrapy.utils.defer import maybe_deferred_to_future

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


def twisted_sleep(seconds: float):
    from twisted.internet import reactor

    d: Deferred[None] = Deferred()
    reactor.callLater(seconds, d.callback, None)
    return d


def get_script_run_env() -> dict[str, str]:
    """Return a OS environment dict suitable to run scripts shipped with tests."""

    tests_path = Path(__file__).parent.parent
    pythonpath = str(tests_path) + os.pathsep + os.environ.get("PYTHONPATH", "")
    env = os.environ.copy()
    env["PYTHONPATH"] = pythonpath
    return env


def ipv6_loopback_available() -> bool:
    """Return True if the IPv6 loopback address (``::1``) can be bound on this host.

    Meant to be used in skip conditions::

        @pytest.mark.skipif(
            not ipv6_loopback_available(), reason="IPv6 loopback is not available"
        )
    """
    if not getattr(socket, "has_ipv6", False):
        return False
    try:
        with contextlib.closing(
            socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        ) as s:
            with contextlib.suppress(OSError, AttributeError):
                s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            s.bind(("::1", 0))
        return True
    except OSError:
        return False


class OneShotLoop:
    """Test stub for create_looping_call: run once immediately, no background task."""

    def __init__(self, func: Callable[[], None]):
        self.func = func
        self.running = False

    def start(self, _interval: float, now: bool = True) -> None:
        self.running = True
        if now:
            self.func()

    def stop(self) -> None:
        self.running = False


def assert_option_is_default(settings: Settings, key: str) -> None:
    assert isinstance(settings, Settings)
    assert settings[key] == getattr(default_settings, key)


async def wait_for_first(
    deferreds: Sequence[Deferred[Any]],
    *,
    timeout: float | None = None,  # noqa: ASYNC109
) -> tuple[set[Deferred[Any]], set[Deferred[Any]]]:
    """Wait for the first of *deferreds* to fire, or until *timeout* seconds pass.

    Returns ``(done, pending)`` — two sets partitioning the input
    :class:`~twisted.internet.defer.Deferred` objects — mirroring the API of
    :func:`asyncio.wait`.

    Deferreds in the ``pending`` set are not cancelled, and their results are
    left untouched; the caller is responsible for any cleanup. They are however
    subscribed to, so passing the same deferred to more than one call leaves it
    carrying a callback per call: pass each deferred to a single call, and get a
    fresh one for the next.

    A deferred that fails counts as done and its failure is **not** re-raised
    here (it stays on the deferred for the caller to inspect or handle), exactly
    as a failed awaitable lands in the ``done`` set of :func:`asyncio.wait`.

    Returns ``(set(), set())`` immediately when *deferreds* is empty.

    Works transparently in asyncio-reactor, non-asyncio-reactor, and
    reactorless modes.

    *timeout* is a guard against a wait that hangs.
    """
    if not deferreds:
        return set(), set()

    # Fire a single signal Deferred as soon as any input Deferred completes,
    # whether it succeeds or fails. Unlike a DeferredList with fireOnOneErrback
    # (which would raise the first failure into this coroutine), _fire passes
    # each result through untouched, so a failure just marks its Deferred as done
    # and stays there for the caller — matching
    # asyncio.wait(return_when=FIRST_COMPLETED).
    signal: Deferred[None] = Deferred()

    def _fire(result: Any = None) -> Any:
        if not signal.called:
            signal.callback(None)
        return result

    for d in deferreds:
        d.addBoth(_fire)

    # Firing the signal on timeout ends the wait with everything still pending,
    # instead of raising.
    timer = None if timeout is None else call_later(timeout, _fire)
    try:
        await maybe_deferred_to_future(signal)
    finally:
        if timer is not None:
            timer.cancel()

    return (
        {d for d in deferreds if d.called},
        {d for d in deferreds if not d.called},
    )
