from __future__ import annotations

import asyncio
import contextlib
import os
import socket
from pathlib import Path
from typing import TYPE_CHECKING

from twisted.internet.defer import Deferred

from scrapy.settings import Settings, default_settings
from scrapy.utils.asyncio import is_asyncio_available
from scrapy.utils.defer import maybe_deferred_to_future

if TYPE_CHECKING:
    from collections.abc import Callable


def twisted_sleep(seconds: float):
    from twisted.internet import reactor

    d: Deferred[None] = Deferred()
    reactor.callLater(seconds, d.callback, None)
    return d


async def async_sleep(seconds: float) -> None:
    if is_asyncio_available():
        await asyncio.sleep(seconds)
    else:
        await maybe_deferred_to_future(twisted_sleep(seconds))


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
