import unittest

from scrapy.signalmanager import SignalManager
from scrapy.dispatch.utils import func_accepts_kwargs
from scrapy.signals import Signal


def receiver(**kwargs):
    pass


def receiver_no_kwargs():
    pass


class BackwardCompatibilityTest(unittest.TestCase):

    def setUp(self):
        self.signals = SignalManager()

    def test_signal_proxies(self):
        new_signal = object()
        self.signals.connect(receiver, new_signal)
        self.assertIsInstance(
            self.signals._signal_proxies[new_signal], Signal)
        self.signals.connect(receiver, new_signal)
        # Make sure _ensure_signal makes a copy only once
        self.assertEqual(len(self.signals._signal_proxies), 1)
        self.signals.disconnect(receiver, new_signal)
        self.assertFalse(
            self.signals._signal_proxies[new_signal].receivers)

    def test_disconnect_all_compatibility(self):
        # if this is working then SignalManager._ensure_signal will
        # be working fine everywhere
        new_signal = object()
        self.signals.connect(receiver, new_signal)
        self.signals.disconnect_all(new_signal)
        self.assertFalse(self.signals._signal_proxies[new_signal].receivers)
