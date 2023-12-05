# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
The L{_response} module contains constants for all standard HTTP codes, along
with a mapping to the corresponding phrases.
"""


import string

from twisted.trial import unittest
from twisted.web import _responses


class ResponseTests(unittest.TestCase):
    def test_constants(self):
        """
        All constants besides C{RESPONSES} defined in L{_response} are
        integers and are keys in C{RESPONSES}.
        """
        for sym in dir(_responses):
            if sym == "RESPONSES":
                continue
            if all((c == "_" or c in string.ascii_uppercase) for c in sym):
                val = getattr(_responses, sym)
                self.assertIsInstance(val, int)
                self.assertIn(val, _responses.RESPONSES)
