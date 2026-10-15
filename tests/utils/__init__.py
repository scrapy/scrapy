from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from twisted.internet.defer import Deferred

from scrapy.crawler import _CHANGING_DEFAULTS
from scrapy.settings import Settings, default_settings
from scrapy.utils.test import get_reactor_settings

if TYPE_CHECKING:
    from collections.abc import Callable

CURRENT_DEFAULTS: dict[str, Any] = {
    name: current_default for name, (current_default, _) in _CHANGING_DEFAULTS.items()
}
"""Settings whose default value will change, set to their current default
value to avoid deprecation warnings."""


def get_test_settings() -> dict[str, Any]:
    """Return settings for crawlers built without
    :func:`~scrapy.utils.test.get_crawler`."""
    return {**get_reactor_settings(), **CURRENT_DEFAULTS}


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
