"""Helper functions for working with signals"""
import collections.abc
import logging
from typing import Any as TypingAny
from typing import List, Tuple

from pydispatch.dispatcher import (
    Anonymous,
    Any,
    disconnect,
    getAllReceivers,
    liveReceivers,
)
from pydispatch.robustapply import robustApply
from twisted.internet.defer import Deferred, DeferredList
from twisted.python.failure import Failure

from scrapy.exceptions import StopDownload
from scrapy.utils.defer import maybeDeferred_coro
from scrapy.utils.log import failure_to_exc_info

logger = logging.getLogger(__name__)


def send_catch_log(
    signal=Any, sender=Anonymous, *arguments, **named
) -> List[Tuple[TypingAny, TypingAny]]:
    """Like pydispatcher.robust.sendRobust but it also logs errors and returns
    Failures instead of exceptions.
    """
    dont_log = named.pop("dont_log", ())
    dont_log = (
        tuple(dont_log)
        if isinstance(dont_log, collections.abc.Sequence)
        else (dont_log,)
    )
    dont_log += (StopDownload,)
    spider = named.get("spider", None)
    responses: List[Tuple[TypingAny, TypingAny]] = []
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


def send_catch_log_deferred(signal=Any, sender=Anonymous, *arguments, **named):
    """Like send_catch_log but supports returning deferreds on signal handlers.
    Returns a deferred that gets fired once all signal handlers deferreds were
    fired.
    """

    def logerror(failure, recv):
        if dont_log is None or not isinstance(failure.value, dont_log):
            logger.error(
                "Error caught on signal handler: %(receiver)s",
                {"receiver": recv},
                exc_info=failure_to_exc_info(failure),
                extra={"spider": spider},
            )
        return failure

    dont_log = named.pop("dont_log", None)
    spider = named.get("spider", None)
    dfds = []
    for receiver in liveReceivers(getAllReceivers(sender, signal)):
        d = maybeDeferred_coro(
            robustApply, receiver, signal=signal, sender=sender, *arguments, **named
        )
        d.addErrback(logerror, receiver)
        d.addBoth(lambda result: (receiver, result))
        dfds.append(d)
    d = DeferredList(dfds)
    d.addCallback(lambda out: [x[1] for x in out])
    return d


def disconnect_all(signal=Any, sender=Any):
    """Disconnect all signal handlers. Useful for cleaning up after running
    tests
    """
    for receiver in liveReceivers(getAllReceivers(sender, signal)):
        disconnect(receiver, signal=signal, sender=sender)
