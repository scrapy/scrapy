from itertools import imap
from twisted.trial import unittest

from scrapy.utils.defer import deferred_imap


class DeferTest(unittest.TestCase):
    def test_deferred_imap_1(self):
        """deferred_imap storing results"""
        seq = [1, 2, 3]
        output = list(imap(None, seq))

        dfd = deferred_imap(None, seq)
        dfd.addCallback(self.assertEqual, output)
        return dfd

    def test_deferred_imap_2(self):
        """deferred_imap not storing results"""
        seq = [1, 2, 3]
        output = list(imap(None, seq, seq))

        dfd = deferred_imap(None, seq, seq)
        dfd.addCallback(self.assertEqual, output)
        return dfd

    def test_deferred_imap_3(self):
        """deferred_imap not storing results"""
        seq = [1, 2, 3]
        output = []
        function = lambda v: output.append(v)

        dfd = deferred_imap(function, seq, store_results=False)
        dfd.addCallback(self.assertEqual, [])
        dfd.addCallback(lambda _: self.assertEqual(output, seq))
        return dfd


