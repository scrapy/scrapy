"""Helper functions for working with signals"""

from twisted.internet.defer import maybeDeferred, DeferredList, Deferred
from twisted.python.failure import Failure

from scrapy.xlib.pydispatch.dispatcher import Any, Anonymous, liveReceivers, \
    getAllReceivers, disconnect
from scrapy.xlib.pydispatch.robustapply import robustApply

from scrapy import log

def send_catch_log(signal=Any, sender=Anonymous, *arguments, **named):
    """Like pydispatcher.robust.sendRobust but it also logs errors and returns
    Failures instead of exceptions.
    """
    dont_log = named.pop('dont_log', None)
    spider = named.get('spider', None)
    responses = []
    for receiver in liveReceivers(getAllReceivers(sender, signal)):
        try:
            response = robustApply(receiver, signal=signal, sender=sender,
                *arguments, **named)
            if isinstance(response, Deferred):
                log.msg(format="Cannot return deferreds from signal handler: %(receiver)s",
                        level=log.ERROR, spider=spider, receiver=receiver)
        except dont_log:
            result = Failure()
        except Exception:
            result = Failure()
            log.err(result, "Error caught on signal handler: %s" % receiver, \
                spider=spider)
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
            log.err(failure, "Error caught on signal handler: %s" % recv, \
                spider=spider)
        return failure

    dont_log = named.pop('dont_log', None)
    spider = named.get('spider', None)
    dfds = []
    for receiver in liveReceivers(getAllReceivers(sender, signal)):
        d = maybeDeferred(robustApply, receiver, signal=signal, sender=sender,
                *arguments, **named)
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
