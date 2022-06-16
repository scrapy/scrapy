import asyncio

from pydispatch import dispatcher
from pytest import mark
from testfixtures import LogCapture
from twisted.internet import defer, reactor
from twisted.python.failure import Failure
from twisted.trial import unittest

from scrapy.utils.signal import send_catch_log, send_catch_log_deferred
from scrapy.utils.test import get_from_asyncio_queue


class SendCatchLogTest(unittest.TestCase):

    @defer.inlineCallbacks
    def test_send_catch_log(self):
        test_signal = object()
        handlers_called = set()

        dispatcher.connect(self.error_handler, signal=test_signal)
        dispatcher.connect(self.ok_handler, signal=test_signal)
        with LogCapture() as log:
            result = yield defer.maybeDeferred(
                self._get_result, test_signal, arg='test',
                handlers_called=handlers_called
            )

        assert self.error_handler in handlers_called
        assert self.ok_handler in handlers_called
        self.assertEqual(len(log.records), 1)
        record = log.records[0]
        self.assertIn('error_handler', record.getMessage())
        self.assertEqual(record.levelname, 'ERROR')
        self.assertEqual(result[0][0], self.error_handler)
        self.assertIsInstance(result[0][1], Failure)
        self.assertEqual(result[1], (self.ok_handler, "OK"))

        dispatcher.disconnect(self.error_handler, signal=test_signal)
        dispatcher.disconnect(self.ok_handler, signal=test_signal)

    def _get_result(self, signal, *a, **kw):
        return send_catch_log(signal, *a, **kw)

    def error_handler(self, arg, handlers_called):
        handlers_called.add(self.error_handler)
        1 / 0

    def ok_handler(self, arg, handlers_called):
        handlers_called.add(self.ok_handler)
        assert arg == 'test'
        return "OK"


class SendCatchLogDeferredTest(SendCatchLogTest):

    def _get_result(self, signal, *a, **kw):
        return send_catch_log_deferred(signal, *a, **kw)


class SendCatchLogDeferredTest2(SendCatchLogDeferredTest):

    def ok_handler(self, arg, handlers_called):
        handlers_called.add(self.ok_handler)
        assert arg == 'test'
        d = defer.Deferred()
        reactor.callLater(0, d.callback, "OK")
        return d


@mark.usefixtures('reactor_pytest')
class SendCatchLogDeferredAsyncDefTest(SendCatchLogDeferredTest):

    async def ok_handler(self, arg, handlers_called):
        handlers_called.add(self.ok_handler)
        assert arg == 'test'
        await defer.succeed(42)
        return "OK"

    def test_send_catch_log(self):
        return super().test_send_catch_log()


@mark.only_asyncio()
class SendCatchLogDeferredAsyncioTest(SendCatchLogDeferredTest):

    async def ok_handler(self, arg, handlers_called):
        handlers_called.add(self.ok_handler)
        assert arg == 'test'
        await asyncio.sleep(0.2)
        return await get_from_asyncio_queue("OK")

    def test_send_catch_log(self):
        return super().test_send_catch_log()


class SendCatchLogTest2(unittest.TestCase):

    def test_error_logged_if_deferred_not_supported(self):
        def test_handler():
            return defer.Deferred()

        test_signal = object()
        dispatcher.connect(test_handler, test_signal)
        with LogCapture() as log:
            send_catch_log(test_signal)
        self.assertEqual(len(log.records), 1)
        self.assertIn("Cannot return deferreds from signal handler", str(log))
        dispatcher.disconnect(test_handler, test_signal)
