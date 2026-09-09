from __future__ import annotations

import signal
from typing import TYPE_CHECKING, Any

import pytest

from scrapy.utils.ossignal import install_shutdown_handlers

if TYPE_CHECKING:
    from collections.abc import Generator
    from types import FrameType

SHUTDOWN_SIGNALS = [
    getattr(signal, name)
    for name in ("SIGTERM", "SIGINT", "SIGBREAK")
    if hasattr(signal, name)
]


@pytest.fixture(autouse=True)
def restore_handlers() -> Generator[None]:
    handlers = {sig: signal.getsignal(sig) for sig in SHUTDOWN_SIGNALS}
    try:
        yield
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


def shutdown(signum: int, frame: FrameType | None) -> Any:
    pass


def test_install() -> None:
    install_shutdown_handlers(shutdown)
    for sig in SHUTDOWN_SIGNALS:
        assert signal.getsignal(sig) is shutdown


def test_keeps_custom_sigint_handler() -> None:
    def custom(signum: int, frame: FrameType | None) -> Any:
        pass

    signal.signal(signal.SIGINT, custom)
    install_shutdown_handlers(shutdown, override_sigint=False)
    assert signal.getsignal(signal.SIGINT) is custom
    assert signal.getsignal(signal.SIGTERM) is shutdown


def test_overrides_default_sigint_handler() -> None:
    signal.signal(signal.SIGINT, signal.default_int_handler)
    install_shutdown_handlers(shutdown, override_sigint=False)
    assert signal.getsignal(signal.SIGINT) is shutdown
