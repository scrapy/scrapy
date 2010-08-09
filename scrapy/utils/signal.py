"""Helper functinos for working with signals"""

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
        except dont_log:
            result = Failure()
        except Exception:
            result = Failure()
            log.err(result, "Signal handler error", spider=spider)
        else:
            result = response
        responses.append((receiver, result))
    return responses

def disconnect_all(signal=Any, sender=Any):
    """Disconnect all signal handlers. Useful for cleaning up after running
    tests
    """
    for receiver in liveReceivers(getAllReceivers(sender, signal)):
        disconnect(receiver, signal=signal, sender=sender)
