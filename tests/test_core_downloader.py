from twisted.trial import unittest

from scrapy.core.downloader import Slot


class SlotTest(unittest.TestCase):
    def test_repr(self):
        slot = Slot(concurrency=8, delay=0.1, randomize_delay=True)
        self.assertEqual(
            repr(slot),
            "Slot(concurrency=8, delay=0.10, randomize_delay=True)",
        )
