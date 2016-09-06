from twisted.trial import unittest
from twisted.internet import defer

from scrapy.dispatch import Signal
from scrapy.utils.signal import send_catch_log, send_catch_log_deferred


class SendCatchLogTest(unittest.TestCase):
    """
    Since the function here are simply a pass through, the actual tests live
    in test_dispatcher, so this is just a sanity test.
    """
    @defer.inlineCallbacks
    def test_send_catch_log(self):
        test_signal = Signal()
        handlers_called = set()

        test_signal.connect(self.ok_handler)
        result = yield defer.maybeDeferred(
            self._get_result, test_signal, arg='test',
            handlers_called=handlers_called
        )

        assert self.ok_handler in handlers_called
        test_signal.disconnect(self.ok_handler)

    def _get_result(self, signal, *a, **kw):
        return send_catch_log(signal, *a, **kw)

    def ok_handler(self, arg, handlers_called, **kw):
        handlers_called.add(self.ok_handler)


class SendCatchLogDeferredTest(SendCatchLogTest):

    def _get_result(self, signal, *a, **kw):
        return send_catch_log_deferred(signal, *a, **kw)
