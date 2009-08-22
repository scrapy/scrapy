import unittest

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

        def log_received(message, level):
            handlers_called.add(log_received)
            assert "test_handler_error" in message
            assert level == log.ERROR

        dispatcher.connect(log_received, signal=log.logmessage_received)
        dispatcher.connect(test_handler_error, signal=test_signal)
        dispatcher.connect(test_handler_check, signal=test_signal)
        send_catch_log(test_signal, arg='test')

        assert test_handler_error in handlers_called
        assert test_handler_check in handlers_called
        assert log_received in handlers_called

        dispatcher.disconnect(log_received, signal=log.logmessage_received)
        dispatcher.disconnect(test_handler_error, signal=test_signal)
        dispatcher.disconnect(test_handler_check, signal=test_signal)


if __name__ == "__main__":
    unittest.main()
