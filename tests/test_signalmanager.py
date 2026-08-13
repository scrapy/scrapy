from scrapy.signalmanager import SignalManager


class TestSignalManager:
    def test_disconnect_all(self):
        signal = object()
        sender = object()
        sm = SignalManager(sender)

        calls = []

        def handler():
            calls.append(1)

        sm.connect(handler, signal)
        sm.send_catch_log(signal)
        assert calls == [1]

        sm.disconnect_all(signal)
        sm.send_catch_log(signal)
        assert calls == [1]  # handler no longer called after disconnect_all
