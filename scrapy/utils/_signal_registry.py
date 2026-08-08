from __future__ import annotations

import inspect
import warnings
from typing import TYPE_CHECKING
from typing import Any as TypingAny
from weakref import WeakKeyDictionary

from blinker import ANY, Signal

from scrapy import signals as _builtin_signals
from scrapy.utils.python import global_object_name

if TYPE_CHECKING:
    from collections.abc import Callable

#: Sender that matches receivers connected to any sender.
Any = ANY

#: Default sender of signals sent without one.
Anonymous = object()

#: Arguments that every signal sends, on top of its own.
_COMMON_ARGS = frozenset({"signal", "sender"})


class _OrderedSet(dict[TypingAny, TypingAny]):
    """Insertion-ordered set covering the subset of the ``set`` API that
    :attr:`blinker.Signal.set_class` requires.

    Receivers run in the order they were connected, which components rely on:
    :class:`~scrapy.extensions.logcount.LogCount` and
    :class:`~scrapy.extensions.logstats.LogStats` share a priority, so only
    connection order puts the log counter in place before the first log message.
    """

    def add(self, item: TypingAny) -> None:
        self[item] = None

    def discard(self, item: TypingAny) -> None:
        self.pop(item, None)

    def copy(self) -> _OrderedSet:
        return _OrderedSet(self)

    def __or__(self, other: TypingAny) -> _OrderedSet:
        return _OrderedSet({**self, **other})


class _Signal(Signal):
    set_class = _OrderedSet  # type: ignore[assignment]


# Signals are usually module-level constants, but a signal that goes out of scope
# should not keep its receivers alive. Signals that cannot be weakly referenced,
# such as strings, are keyed by value instead.
_signals: WeakKeyDictionary[TypingAny, _Signal] = WeakKeyDictionary()
_signals_by_value: dict[TypingAny, _Signal] = {}


def _signal_for(signal: TypingAny) -> _Signal:
    try:
        return _signals[signal]
    except KeyError:
        obj = _signals[signal] = _Signal()
        return obj
    except TypeError:
        pass
    try:
        return _signals_by_value[signal]
    except KeyError:
        obj = _signals_by_value[signal] = _Signal()
        return obj


# Keyed by the underlying function rather than by the receiver, so that a bound
# method does not keep its instance alive, and so that every instance of a
# component shares one entry.
_accepted_args: dict[TypingAny, frozenset[str] | None] = {}


def _cache_key(receiver: TypingAny) -> TypingAny:
    func = getattr(receiver, "__func__", None)
    if func is not None:
        return func
    if inspect.isroutine(receiver):
        return receiver
    return type(receiver)


def _accepted(receiver: TypingAny) -> frozenset[str] | None:
    """Return the names of the arguments *receiver* accepts, or ``None`` if it
    accepts arbitrary keyword arguments.
    """
    key = _cache_key(receiver)
    try:
        return _accepted_args[key]
    except KeyError:
        pass
    names = _introspect(receiver)
    _accepted_args[key] = names
    return names


def _introspect(receiver: TypingAny) -> frozenset[str] | None:
    try:
        parameters = inspect.signature(receiver).parameters.values()
    except (TypeError, ValueError):
        # Callables that cannot be introspected, e.g. some built-ins.
        return None
    if any(p.kind is p.VAR_KEYWORD for p in parameters):
        return None
    return frozenset(
        p.name
        for p in parameters
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
    )


def _warn_unknown_args(receiver: TypingAny, signal: TypingAny) -> None:
    sent = _builtin_signals._signal_args.get(signal)
    if sent is None:
        return
    accepted = _accepted(receiver)
    if accepted is None:
        return
    unknown = accepted - sent - _COMMON_ARGS
    if not unknown:
        return
    names = ", ".join(sorted(unknown))
    warnings.warn(
        f"Signal handler {global_object_name(receiver)} declares"
        f" {names}, which {_signal_name(signal)} does not send. Handlers"
        f" only receive the arguments of their signal, so those arguments always"
        f" get their default value.",
        stacklevel=4,
    )


def _signal_name(signal: TypingAny) -> str:
    for name, value in vars(_builtin_signals).items():
        if value is signal:
            return f"scrapy.signals.{name}"
    return repr(signal)


def connect(
    receiver: Callable[..., TypingAny],
    signal: TypingAny,
    sender: TypingAny = Any,
    weak: bool = True,
) -> None:
    if signal is Any:
        raise ValueError(
            "Connecting a receiver to every signal at once is not supported."
            " Connect it to each signal that it handles instead."
        )
    _warn_unknown_args(receiver, signal)
    _signal_for(signal).connect(receiver, sender=sender, weak=weak)


def disconnect(
    receiver: Callable[..., TypingAny],
    signal: TypingAny,
    sender: TypingAny = Any,
) -> None:
    _signal_for(signal).disconnect(receiver, sender=sender)


def receivers(signal: TypingAny, sender: TypingAny) -> list[Callable[..., TypingAny]]:
    """Return the live receivers of *signal* for *sender*, in connection order."""
    return list(_signal_for(signal).receivers_for(sender))


def apply(
    receiver: Callable[..., TypingAny],
    *arguments: TypingAny,
    **named: TypingAny,
) -> TypingAny:
    """Call *receiver* with *arguments* and the entries of *named* that it accepts."""
    accepted = _accepted(receiver)
    if accepted is not None:
        if arguments:
            accepted = accepted - _positional_names(receiver, len(arguments))
        named = {k: v for k, v in named.items() if k in accepted}
    return receiver(*arguments, **named)


def _positional_names(receiver: TypingAny, count: int) -> frozenset[str]:
    """Return the names of the first *count* parameters of *receiver*, which
    positional arguments bind and keyword arguments therefore must not repeat.
    """
    parameters = list(inspect.signature(receiver).parameters.values())
    return frozenset(
        p.name
        for p in parameters[:count]
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    )
