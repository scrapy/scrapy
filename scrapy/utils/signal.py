"""Helper functions for working with signals"""

from __future__ import annotations

import asyncio
import logging
import warnings
from collections.abc import Awaitable, Callable, Generator, Sequence
from typing import Any as TypingAny

from pydispatch.dispatcher import (
    Anonymous,
    Any,
    disconnect,
    getAllReceivers,
    liveReceivers,
)
from pydispatch.robustapply import robustApply
from twisted.internet.defer import Deferred, DeferredList, inlineCallbacks
from twisted.python.failure import Failure

from scrapy.exceptions import ScrapyDeprecationWarning, StopDownload
from scrapy.utils.asyncio import is_asyncio_available
from scrapy.utils.defer import (
    _maybeDeferred_coro,
    ensure_awaitable,
    maybe_deferred_to_future,
)
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.python import global_object_name

logger = logging.getLogger(__name__)


def send_catch_log(
    signal: TypingAny = Any,
    sender: TypingAny = Anonymous,
    *arguments: TypingAny,
    **named: TypingAny,
) -> list[tuple[TypingAny, TypingAny]]:
    """Like ``pydispatcher.robust.sendRobust()`` but it also logs errors and returns
    Failures instead of exceptions.
    """
    dont_log = named.pop("dont_log", ())
    dont_log = tuple(dont_log) if isinstance(dont_log, Sequence) else (dont_log,)
    dont_log += (StopDownload,)
    spider = named.get("spider")
    responses: list[tuple[TypingAny, TypingAny]] = []
    for receiver in liveReceivers(getAllReceivers(sender, signal)):
        result: TypingAny
        try:
            response = robustApply(
                receiver, signal=signal, sender=sender, *arguments, **named
            )
            if isinstance(response, Deferred):
                logger.error(
                    "Cannot return deferreds from signal handler: %(receiver)s",
                    {"receiver": receiver},
                    extra={"spider": spider},
                )
        except dont_log:
            result = Failure()
        except Exception:
            result = Failure()
            logger.error(
                "Error caught on signal handler: %(receiver)s",
                {"receiver": receiver},
                exc_info=True,
                extra={"spider": spider},
            )
        else:
            result = response
        responses.append((receiver, result))
    return responses


def send_catch_log_deferred(
    signal: TypingAny = Any,
    sender: TypingAny = Anonymous,
    *arguments: TypingAny,
    **named: TypingAny,
) -> Deferred[list[tuple[TypingAny, TypingAny]]]:
    """Like :func:`send_catch_log` but supports :ref:`asynchronous signal handlers
    <signal-deferred>`.

    Returns a deferred that gets fired once all signal handlers have finished.
    """
    warnings.warn(
        "send_catch_log_deferred() is deprecated, use send_catch_log_async() instead",
        ScrapyDeprecationWarning,
        stacklevel=2,
    )
    return _send_catch_log_deferred(signal, sender, *arguments, **named)


@inlineCallbacks
def _send_catch_log_deferred(
    signal: TypingAny,
    sender: TypingAny,
    *arguments: TypingAny,
    **named: TypingAny,
) -> Generator[Deferred[TypingAny], TypingAny, list[tuple[TypingAny, TypingAny]]]:
    def logerror(failure: Failure, recv: TypingAny) -> Failure:
        if dont_log is None or not isinstance(failure.value, dont_log):
            logger.error(
                "Error caught on signal handler: %(receiver)s",
                {"receiver": recv},
                exc_info=failure_to_exc_info(failure),
                extra={"spider": spider},
            )
        return failure

    dont_log = named.pop("dont_log", None)
    spider = named.get("spider")
    dfds: list[Deferred[tuple[TypingAny, TypingAny]]] = []
    for receiver in liveReceivers(getAllReceivers(sender, signal)):
        d: Deferred[TypingAny] = _maybeDeferred_coro(
            robustApply,
            True,
            receiver,
            signal=signal,
            sender=sender,
            *arguments,
            **named,
        )
        d.addErrback(logerror, receiver)
        # TODO https://pylint.readthedocs.io/en/latest/user_guide/messages/warning/cell-var-from-loop.html
        d2: Deferred[tuple[TypingAny, TypingAny]] = d.addBoth(
            lambda result: (
                receiver,  # pylint: disable=cell-var-from-loop  # noqa: B023
                result,
            )
        )
        dfds.append(d2)

    results = yield DeferredList(dfds)
    return [result[1] for result in results]


async def send_catch_log_async(
    signal: TypingAny = Any,
    sender: TypingAny = Anonymous,
    *arguments: TypingAny,
    **named: TypingAny,
) -> list[tuple[TypingAny, TypingAny]]:
    """Like :func:`send_catch_log` but supports :ref:`asynchronous signal handlers
    <signal-deferred>`.

    Returns a coroutine that completes once all signal handlers have finished.

    .. versionadded:: 2.14
    """
    # note that this returns exceptions instead of Failures in the second tuple member
    if is_asyncio_available():
        return await _send_catch_log_asyncio(signal, sender, *arguments, **named)
    results = await maybe_deferred_to_future(
        _send_catch_log_deferred(signal, sender, *arguments, **named)
    )
    return [
        (receiver, result.value if isinstance(result, Failure) else result)
        for receiver, result in results
    ]


async def _send_catch_log_asyncio(
    signal: TypingAny = Any,
    sender: TypingAny = Anonymous,
    *arguments: TypingAny,
    **named: TypingAny,
) -> list[tuple[TypingAny, TypingAny]]:
    """Like :func:`send_catch_log` but supports :ref:`asynchronous signal handlers
    <signal-deferred>`.

    Returns a coroutine that completes once all signal handlers have finished.

    This function requires
    :class:`~twisted.internet.asyncioreactor.AsyncioSelectorReactor` to be
    installed.

    .. versionadded:: 2.14
    """
    dont_log = named.pop("dont_log", ())
    dont_log = tuple(dont_log) if isinstance(dont_log, Sequence) else (dont_log,)
    spider = named.get("spider")
    handlers: list[Awaitable[TypingAny]] = []
    for receiver in liveReceivers(getAllReceivers(sender, signal)):

        async def handler(receiver: Callable) -> TypingAny:
            result: TypingAny
            try:
                result = await ensure_awaitable(
                    robustApply(
                        receiver, signal=signal, sender=sender, *arguments, **named
                    ),
                    _warn=global_object_name(receiver),
                )
            except dont_log as ex:  # pylint: disable=catching-non-exception
                result = ex
            except Exception as ex:
                logger.error(
                    "Error caught on signal handler: %(receiver)s",
                    {"receiver": receiver},
                    exc_info=True,
                    extra={"spider": spider},
                )
                result = ex
            return (receiver, result)

        handlers.append(handler(receiver))

    return await asyncio.gather(*handlers, return_exceptions=True)


def disconnect_all(signal: TypingAny = Any, sender: TypingAny = Any) -> None:
    """Disconnect all signal handlers. Useful for cleaning up after running
    tests.
    """
    for receiver in liveReceivers(getAllReceivers(sender, signal)):
        disconnect(receiver, signal=signal, sender=sender)
