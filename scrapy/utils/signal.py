"""Helper functions for working with signals

   Deprecated. Use instance methods of `Scrapy.dispatch.Signal` class
   instead.
"""

import logging
import warnings

from twisted.internet.defer import maybeDeferred, DeferredList, Deferred
from twisted.python.failure import Failure

from scrapy.exceptions import ScrapyDeprecationWarning


warnings.warn("`scrapy.utils.signal` is deprecated, signals are now objects of"
              " the `scrapy.dispatch.Signal` class with the utility functions"
              " available as instance method of the same.",
              ScrapyDeprecationWarning, stacklevel=2)


def send_catch_log(signal=None, sender=None, *arguments, **named):
    """Like pydispatcher.robust.sendRobust but it also logs errors and returns
    Failures instead of exceptions.
    """
    return signal.send_catch_log(sender=sender, **named)


def send_catch_log_deferred(signal=None, sender=None, *arguments, **named):
    """Like send_catch_log but supports returning deferreds on signal handlers.
    Returns a deferred that gets fired once all signal handlers deferreds were
    fired.
    """
    return signal.send_catch_log_deferred(sender=sender, **named)


def disconnect_all(signal, sender=None):
    """Disconnect all signal handlers. Useful for cleaning up after running
    tests
    """
    signal.disconnect_all(sender)
