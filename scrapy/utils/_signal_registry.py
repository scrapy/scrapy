from __future__ import annotations

import inspect
import warnings
from itertools import takewhile
from typing import TYPE_CHECKING
from typing import Any as TypingAny
from weakref import WeakKeyDictionary

from blinker import ANY, Signal

from scrapy import signals as _builtin_signals
from scrapy.utils.python import global_object_name

if TYPE_CHECKING:
    from collections.abc import Callable, MutableMapping

Any = ANY
"""Sender that matches receivers connected to any sender."""

Anonymous = object()
"""Default sender of signals sent without one."""

_COMMON_ARGS = frozenset({"signal", "sender"})
"""Arguments that every signal sends, on top of its own."""


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
        store: MutableMapping[TypingAny, _Signal] = _signals
    except TypeError:
        store = _signals_by_value
        if (obj := store.get(signal)) is not None:
            return obj
    # setdefault() so that concurrent first uses of a signal agree on one object.
    return store.setdefault(signal, _Signal())


_Parameters = tuple[frozenset[str], tuple[str, ...]]

# Weak keys, so that the cache does not keep receivers alive. Bound methods are
# keyed by their underlying function, so that they do not keep their instance
# alive either, and every instance of a component shares one entry.
_parameters_cache: WeakKeyDictionary[TypingAny, _Parameters | None] = (
    WeakKeyDictionary()
)


def _parameters(receiver: TypingAny) -> _Parameters | None:
    """Return the names of the arguments *receiver* accepts and of its leading
    positional parameters, or ``None`` if it accepts arbitrary keyword
    arguments.
    """
    key = getattr(receiver, "__func__", receiver)
    try:
        return _parameters_cache[key]
    except KeyError:
        pass
    except TypeError:
        # Receivers that cannot be weakly referenced.
        return _introspect(receiver)
    result = _parameters_cache[key] = _introspect(receiver)
    return result


def _introspect(receiver: TypingAny) -> _Parameters | None:
    try:
        parameters = inspect.signature(receiver).parameters.values()
    except (TypeError, ValueError):
        # Callables that cannot be introspected, e.g. some built-ins.
        return None
    if any(p.kind is p.VAR_KEYWORD for p in parameters):
        return None
    positional_kinds = (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )
    accepted = frozenset(
        p.name
        for p in parameters
        if p.kind in (*positional_kinds, inspect.Parameter.KEYWORD_ONLY)
    )
    positional = tuple(
        p.name for p in takewhile(lambda p: p.kind in positional_kinds, parameters)
    )
    return accepted, positional


def _warn_unknown_args(receiver: TypingAny, signal: TypingAny) -> None:
    sent = _builtin_signals._signal_args.get(signal)
    if sent is None:
        return
    parameters = _parameters(receiver)
    if parameters is None:
        return
    unknown = parameters[0] - sent - _COMMON_ARGS
    if not unknown:
        return
    names = ", ".join(sorted(unknown))
    try:
        receiver_name = global_object_name(receiver)
    except AttributeError:
        receiver_name = repr(receiver)
    warnings.warn(
        f"Signal handler {receiver_name} declares"
        f" {names}, which {signal!r} does not send. Handlers"
        f" only receive the arguments of their signal, so those arguments always"
        f" get their default value.",
        stacklevel=4,
    )


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
    parameters = _parameters(receiver)
    if parameters is not None:
        accepted, positional = parameters
        if arguments:
            # Positional arguments bind the leading parameters, which keyword
            # arguments therefore must not repeat.
            accepted = accepted.difference(positional[: len(arguments)])
        named = {k: v for k, v in named.items() if k in accepted}
    return receiver(*arguments, **named)
