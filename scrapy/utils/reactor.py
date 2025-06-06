from __future__ import annotations

import asyncio
import sys
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Generic, TypeVar
from warnings import catch_warnings, filterwarnings

from twisted.internet import asyncioreactor, error
from twisted.internet.defer import Deferred

from scrapy.utils.misc import load_object

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop, AbstractEventLoopPolicy
    from collections.abc import Callable

    from twisted.internet.base import DelayedCall
    from twisted.internet.protocol import ServerFactory
    from twisted.internet.tcp import Port

    # typing.ParamSpec requires Python 3.10
    from typing_extensions import ParamSpec

    _P = ParamSpec("_P")

_T = TypeVar("_T")


def listen_tcp(portrange: list[int], host: str, factory: ServerFactory) -> Port:  # type: ignore[return]  # pylint: disable=inconsistent-return-statements
    """Like reactor.listenTCP but tries different ports in a range."""
    from twisted.internet import reactor

    if len(portrange) > 2:
        raise ValueError(f"invalid portrange: {portrange}")
    if not portrange:
        return reactor.listenTCP(0, factory, interface=host)
    if len(portrange) == 1:
        return reactor.listenTCP(portrange[0], factory, interface=host)
    for x in range(portrange[0], portrange[1] + 1):  # noqa: RET503
        try:
            return reactor.listenTCP(x, factory, interface=host)
        except error.CannotListenError:
            if x == portrange[1]:
                raise


class CallLaterOnce(Generic[_T]):
    """Schedule a function to be called in the next reactor loop, but only if
    it hasn't been already scheduled since the last time it ran.
    """

    def __init__(self, func: Callable[_P, _T], *a: _P.args, **kw: _P.kwargs):
        self._func: Callable[_P, _T] = func
        self._a: tuple[Any, ...] = a
        self._kw: dict[str, Any] = kw
        self._call: DelayedCall | None = None
        self._deferreds: list[Deferred] = []

    def schedule(self, delay: float = 0) -> None:
        from twisted.internet import reactor

        if self._call is None:
            self._call = reactor.callLater(delay, self)

    def cancel(self) -> None:
        if self._call:
            self._call.cancel()

    def __call__(self) -> _T:
        from twisted.internet import reactor

        self._call = None
        result = self._func(*self._a, **self._kw)

        for d in self._deferreds:
            reactor.callLater(0, d.callback, None)
        self._deferreds = []

        return result

    async def wait(self):
        from scrapy.utils.defer import maybe_deferred_to_future

        d = Deferred()
        self._deferreds.append(d)
        await maybe_deferred_to_future(d)


def set_asyncio_event_loop_policy() -> None:
    """The policy functions from asyncio often behave unexpectedly,
    so we restrict their use to the absolutely essential case.
    This should only be used to install the reactor.
    """
    _get_asyncio_event_loop_policy()


def _get_asyncio_event_loop_policy() -> AbstractEventLoopPolicy:
    policy = asyncio.get_event_loop_policy()
    if sys.platform == "win32" and not isinstance(
        policy, asyncio.WindowsSelectorEventLoopPolicy
    ):
        policy = asyncio.WindowsSelectorEventLoopPolicy()
        asyncio.set_event_loop_policy(policy)
    return policy


def install_reactor(reactor_path: str, event_loop_path: str | None = None) -> None:
    """Installs the :mod:`~twisted.internet.reactor` with the specified
    import path. Also installs the asyncio event loop with the specified import
    path if the asyncio reactor is enabled"""
    reactor_class = load_object(reactor_path)
    if reactor_class is asyncioreactor.AsyncioSelectorReactor:
        set_asyncio_event_loop_policy()
        with suppress(error.ReactorAlreadyInstalledError):
            event_loop = set_asyncio_event_loop(event_loop_path)
            asyncioreactor.install(eventloop=event_loop)
    else:
        *module, _ = reactor_path.split(".")
        installer_path = [*module, "install"]
        installer = load_object(".".join(installer_path))
        with suppress(error.ReactorAlreadyInstalledError):
            installer()


def _get_asyncio_event_loop() -> AbstractEventLoop:
    return set_asyncio_event_loop(None)


def set_asyncio_event_loop(event_loop_path: str | None) -> AbstractEventLoop:
    """Sets and returns the event loop with specified import path."""
    if event_loop_path is not None:
        event_loop_class: type[AbstractEventLoop] = load_object(event_loop_path)
        event_loop = _get_asyncio_event_loop()
        if not isinstance(event_loop, event_loop_class):
            event_loop = event_loop_class()
            asyncio.set_event_loop(event_loop)
    else:
        try:
            with catch_warnings():
                # In Python 3.10.9, 3.11.1, 3.12 and 3.13, a DeprecationWarning
                # is emitted about the lack of a current event loop, because in
                # Python 3.14 and later `get_event_loop` will raise a
                # RuntimeError in that event. Because our code is already
                # prepared for that future behavior, we ignore the deprecation
                # warning.
                filterwarnings(
                    "ignore",
                    message="There is no current event loop",
                    category=DeprecationWarning,
                )
                event_loop = asyncio.get_event_loop()
        except RuntimeError:
            # `get_event_loop` raises RuntimeError when called with no asyncio
            # event loop yet installed in the following scenarios:
            # - Previsibly on Python 3.14 and later.
            #   https://github.com/python/cpython/issues/100160#issuecomment-1345581902
            event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(event_loop)
    return event_loop


def verify_installed_reactor(reactor_path: str) -> None:
    """Raises :exc:`Exception` if the installed
    :mod:`~twisted.internet.reactor` does not match the specified import
    path."""
    from twisted.internet import reactor

    reactor_class = load_object(reactor_path)
    if not reactor.__class__ == reactor_class:
        raise RuntimeError(
            "The installed reactor "
            f"({reactor.__module__}.{reactor.__class__.__name__}) does not "
            f"match the requested one ({reactor_path})"
        )


def verify_installed_asyncio_event_loop(loop_path: str) -> None:
    from twisted.internet import reactor

    loop_class = load_object(loop_path)
    if isinstance(reactor._asyncioEventloop, loop_class):
        return
    installed = (
        f"{reactor._asyncioEventloop.__class__.__module__}"
        f".{reactor._asyncioEventloop.__class__.__qualname__}"
    )
    specified = f"{loop_class.__module__}.{loop_class.__qualname__}"
    raise RuntimeError(
        "Scrapy found an asyncio Twisted reactor already "
        f"installed, and its event loop class ({installed}) does "
        "not match the one specified in the ASYNCIO_EVENT_LOOP "
        f"setting ({specified})"
    )


def is_reactor_installed() -> bool:
    return "twisted.internet.reactor" in sys.modules


def is_asyncio_reactor_installed() -> bool:
    """Check whether the installed reactor is :class:`~twisted.internet.asyncioreactor.AsyncioSelectorReactor`.

    Raise a :exc:`RuntimeError` if no reactor is installed.

    .. versionchanged:: 2.13
       In earlier Scrapy versions this function silently installed the default
       reactor if there was no reactor installed. Now it raises an exception to
       prevent silent problems in this case.
    """
    if not is_reactor_installed():
        raise RuntimeError(
            "is_asyncio_reactor_installed() called without an installed reactor."
        )

    from twisted.internet import reactor

    return isinstance(reactor, asyncioreactor.AsyncioSelectorReactor)
