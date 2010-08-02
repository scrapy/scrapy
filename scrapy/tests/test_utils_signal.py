import unittest

from twisted.python import log as txlog

from scrapy.xlib.pydispatch import dispatcher
from scrapy.utils.signal import send_catch_log
from scrapy import log

test_signal = object()

class SignalUtilsTest(unittest.TestCase):

    def test_send_catch_log(self):
        handlers_called = set()

        def test_handler_error(arg):
            handlers_called.add(test_handler_error)
            a = 1/0

        def test_handler_check(arg):
            handlers_called.add(test_handler_check)
            assert arg == 'test'
            return "OK"

        def log_received(event):
            handlers_called.add(log_received)
            assert "test_handler_error" in event['message'][0]
            assert event['logLevel'] == log.ERROR

        txlog.addObserver(log_received)
        dispatcher.connect(test_handler_error, signal=test_signal)
        dispatcher.connect(test_handler_check, signal=test_signal)
        result = send_catch_log(test_signal, arg='test')

        assert test_handler_error in handlers_called
        assert test_handler_check in handlers_called
        assert log_received in handlers_called
        self.assertEqual(result[0][0], test_handler_error)
        self.assert_(isinstance(result[0][1], Exception))
        self.assertEqual(result[1], (test_handler_check, "OK"))

        txlog.removeObserver(log_received)
        dispatcher.disconnect(test_handler_error, signal=test_signal)
        dispatcher.disconnect(test_handler_check, signal=test_signal)


if __name__ == "__main__":
    unittest.main()
