from __future__ import annotations

import gc
import weakref
from collections import Counter
from functools import partial
from typing import TYPE_CHECKING, Any

import pytest

from scrapy import signals
from scrapy.signalmanager import SignalManager
from scrapy.utils import _signal_registry as registry
from scrapy.utils.signal import send_catch_log

if TYPE_CHECKING:
    from collections.abc import Callable


class TestArgumentDelivery:
    def test_handler_gets_only_the_arguments_it_declares(self) -> None:
        received: dict[str, Any] = {}

        def handler(spider: Any = None) -> None:
            received.update(spider=spider)

        signal = object()
        sm = SignalManager(object())
        sm.connect(handler, signal)
        sm.send_catch_log(signal, spider="SPIDER")
        assert received == {"spider": "SPIDER"}

    def test_handler_with_kwargs_gets_every_argument(self) -> None:
        received: dict[str, Any] = {}

        def handler(**kwargs: Any) -> None:
            received.update(kwargs)

        signal = object()
        sm = SignalManager(object())
        sm.connect(handler, signal)
        sm.send_catch_log(signal, spider="SPIDER")
        assert received["spider"] == "SPIDER"
        assert received["signal"] is signal

    def test_keyword_only_handler(self) -> None:
        received: dict[str, Any] = {}

        def handler(*, spider: Any = None) -> None:
            received.update(spider=spider)

        signal = object()
        sm = SignalManager(object())
        sm.connect(handler, signal)
        sm.send_catch_log(signal, spider="SPIDER")
        assert received == {"spider": "SPIDER"}

    def test_partial_handler(self) -> None:
        received: dict[str, Any] = {}

        def handler(prefix: str, spider: Any = None) -> None:
            received.update(spider=f"{prefix}{spider}")

        bound = partial(handler, "p-")
        signal = object()
        sm = SignalManager(object())
        sm.connect(bound, signal)
        sm.send_catch_log(signal, spider="SPIDER")
        assert received == {"spider": "p-SPIDER"}

    def test_partial_handlers_with_different_signatures(self) -> None:
        received: dict[str, Any] = {}

        def first(prefix: str, spider: Any = None) -> None:
            received.update(spider=f"{prefix}{spider}")

        def second(prefix: str, request: Any = None) -> None:
            received.update(request=f"{prefix}{request}")

        handlers = [partial(first, "a-"), partial(second, "b-")]
        signal = object()
        sm = SignalManager(object())
        for handler in handlers:
            sm.connect(handler, signal)
        sm.send_catch_log(signal, spider="SPIDER", request="REQUEST")
        assert received == {"spider": "a-SPIDER", "request": "b-REQUEST"}

    def test_handler_that_cannot_be_introspected_gets_every_argument(self) -> None:
        assert registry.apply(dict, spider="SPIDER") == {"spider": "SPIDER"}

    def test_positional_arguments_are_not_repeated_as_keywords(self) -> None:
        received: dict[str, Any] = {}

        def handler(spider: Any, signal: Any = None) -> None:
            received.update(spider=spider, signal=signal)

        signal = object()
        sender = object()
        registry.connect(handler, signal, sender=sender)
        send_catch_log(signal, sender, "SPIDER")
        assert received == {"spider": "SPIDER", "signal": signal}

    def test_callable_object_handler(self) -> None:
        class Handler:
            def __init__(self) -> None:
                self.spider: Any = None

            def __call__(self, spider: Any = None) -> None:
                self.spider = spider

        handler = Handler()
        signal = object()
        sm = SignalManager(object())
        sm.connect(handler, signal)
        sm.send_catch_log(signal, spider="SPIDER")
        assert handler.spider == "SPIDER"


class TestSignalName:
    def test_shared_handler_tells_signals_apart_by_name(self) -> None:
        received: list[str] = []

        def handler(signal: Any = None, **kwargs: Any) -> None:
            received.append(signal.name)

        sm = SignalManager(object())
        sm.connect(handler, signals.spider_opened)
        sm.connect(handler, signals.spider_closed)
        sm.send_catch_log(signals.spider_opened)
        sm.send_catch_log(signals.spider_closed)
        assert received == ["spider_opened", "spider_closed"]


def _appending_handlers(calls: list[int], count: int) -> list[Callable[..., None]]:
    def make(n: int) -> Callable[..., None]:
        def handler(**kwargs: Any) -> None:
            calls.append(n)

        return handler

    return [make(n) for n in range(count)]


class TestDispatchOrder:
    def test_handlers_run_in_connection_order(self) -> None:
        calls: list[int] = []
        signal = object()
        sm = SignalManager(object())
        handlers = _appending_handlers(calls, 10)
        for handler in handlers:
            sm.connect(handler, signal)
        sm.send_catch_log(signal)
        assert calls == list(range(10))

    def test_order_survives_disconnect(self) -> None:
        calls: list[int] = []
        signal = object()
        sm = SignalManager(object())
        handlers = _appending_handlers(calls, 5)
        for handler in handlers:
            sm.connect(handler, signal)
        sm.disconnect(handlers[2], signal)
        sm.send_catch_log(signal)
        assert calls == [0, 1, 3, 4]


class TestDisconnect:
    def test_disconnected_handler_stops_running(self) -> None:
        calls: list[str] = []
        signal = object()
        sm = SignalManager(object())

        def kept(**kwargs: Any) -> None:
            calls.append("kept")

        def dropped(**kwargs: Any) -> None:
            calls.append("dropped")

        sm.connect(kept, signal)
        sm.connect(dropped, signal)
        sm.disconnect(dropped, signal)
        sm.send_catch_log(signal)
        assert calls == ["kept"]

    def test_every_handler_runs(self) -> None:
        calls: set[str] = set()
        signal = object()
        sm = SignalManager(object())
        handlers = []
        for name in ("a", "b", "c"):

            def handler(_name: str = name, **kwargs: Any) -> None:
                calls.add(_name)

            handlers.append(handler)
            sm.connect(handler, signal)
        sm.send_catch_log(signal)
        assert calls == {"a", "b", "c"}


class TestSenderIsolation:
    def test_handlers_only_run_for_their_sender(self) -> None:
        calls: list[str] = []

        def first_handler(**kwargs: Any) -> None:
            calls.append("first")

        def second_handler(**kwargs: Any) -> None:
            calls.append("second")

        signal = object()
        first, second = SignalManager(object()), SignalManager(object())
        first.connect(first_handler, signal)
        second.connect(second_handler, signal)
        first.send_catch_log(signal)
        assert calls == ["first"]


class TestReceiverCache:
    def test_bound_method_handler_is_not_kept_alive(self) -> None:
        class Component:
            def handler(self, spider: Any = None) -> None:
                pass

        component = Component()
        ref = weakref.ref(component)
        signal = object()
        sm = SignalManager(object())
        sm.connect(component.handler, signal)
        del component
        gc.collect()
        assert ref() is None
        assert registry.receivers(signal, sm.sender) == []

    def test_function_handler_is_not_kept_alive(self) -> None:
        def handler(spider: Any = None) -> None:
            pass

        ref = weakref.ref(handler)
        sm = SignalManager(object())
        sm.connect(handler, signals.spider_opened)
        sm.send_catch_log(signals.spider_opened, spider="SPIDER")
        del handler
        gc.collect()
        assert ref() is None

    def test_handler_that_cannot_be_weakly_referenced(self) -> None:
        received: list[Any] = []

        class Handler:
            __slots__ = ()

            def __call__(self, spider: Any = None) -> None:
                received.append(spider)

        sm = SignalManager(object())
        sm.connect(Handler(), signals.spider_opened, weak=False)
        sm.send_catch_log(signals.spider_opened, spider="SPIDER")
        assert received == ["SPIDER"]


class TestSignalStorage:
    def test_signal_that_can_be_weakly_referenced_is_not_kept_alive(self) -> None:
        class Signal:
            pass

        def handler(**kwargs: Any) -> None:
            pass

        signal = Signal()
        ref = weakref.ref(signal)
        sm = SignalManager(object())
        sm.connect(handler, signal)
        sm.send_catch_log(signal)
        del signal
        gc.collect()
        assert ref() is None


class TestMutationDuringDispatch:
    def test_handler_can_disconnect_itself(self) -> None:
        calls: list[str] = []
        signal = object()
        sm = SignalManager(object())

        def handler(**kwargs: Any) -> None:
            calls.append("handler")
            sm.disconnect(handler, signal)

        def other(**kwargs: Any) -> None:
            calls.append("other")

        sm.connect(handler, signal)
        sm.connect(other, signal)
        sm.send_catch_log(signal)
        sm.send_catch_log(signal)
        assert Counter(calls) == {"handler": 1, "other": 2}

    def test_handler_can_connect_another_handler(self) -> None:
        calls: list[str] = []
        signal = object()
        sm = SignalManager(object())
        added: list[Callable[..., None]] = []

        def late(**kwargs: Any) -> None:
            calls.append("late")

        def handler(**kwargs: Any) -> None:
            calls.append("handler")
            if not added:
                added.append(late)
                sm.connect(late, signal)

        sm.connect(handler, signal)
        sm.send_catch_log(signal)
        assert Counter(calls) == {"handler": 1}
        sm.send_catch_log(signal)
        assert Counter(calls) == {"handler": 2, "late": 1}


class TestWildcardSignal:
    def test_connecting_to_every_signal_is_rejected(self) -> None:
        def handler(**kwargs: Any) -> None:
            pass

        with pytest.raises(ValueError, match="every signal"):
            SignalManager(object()).connect(handler, registry.Any)
