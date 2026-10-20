from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from scrapy import signals
from scrapy.signalmanager import SignalManager

if TYPE_CHECKING:
    from collections.abc import Callable


def test_disconnect_all() -> None:
    signal = object()
    sender = object()
    sm = SignalManager(sender)

    calls = []

    def handler():
        calls.append(1)

    sm.connect(handler, signal)
    sm.send_catch_log(signal)
    assert calls == [1]

    sm.disconnect_all(signal)
    sm.send_catch_log(signal)
    assert calls == [1]  # handler no longer called after disconnect_all


class TestUnknownArgumentWarning:
    def test_warns(self) -> None:
        def handler(spider: Any, cheese: Any = None, *, ham: Any = None) -> None:
            pass

        with pytest.warns(
            UserWarning,
            match=r"handler declares cheese, ham, which scrapy\.signals\.spider_opened does not send",
        ) as record:
            SignalManager().connect(handler, signals.spider_opened)
        assert record[0].filename == __file__

    def test_callable_instance(self) -> None:
        class Handler:
            def __call__(self, cheese: Any = None) -> None:
                pass

        with pytest.warns(UserWarning, match=r"Handler object at .* declares cheese"):
            SignalManager().connect(Handler(), signals.spider_opened)

    @pytest.mark.filterwarnings("error")
    @pytest.mark.parametrize(
        ("handler", "signal"),
        [
            (lambda spider, signal, sender: None, signals.spider_opened),
            (lambda cheese, **kwargs: None, signals.spider_opened),
            (lambda cheese: None, object()),
            (type, signals.spider_opened),
        ],
    )
    def test_no_warning(self, handler: Callable[..., Any], signal: object) -> None:
        SignalManager().connect(handler, signal)


def test_every_signal_declares_its_arguments() -> None:
    defined = {v for v in vars(signals).values() if type(v) is object}
    assert defined == set(signals._signal_args)
