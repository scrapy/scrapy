# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.textattributes}.
"""

from twisted.trial import unittest
from twisted.python._textattributes import DefaultFormattingState



class DefaultFormattingStateTests(unittest.TestCase):
    """
    Tests for L{twisted.python._textattributes.DefaultFormattingState}.
    """
    def test_equality(self):
        """
        L{DefaultFormattingState}s are always equal to other
        L{DefaultFormattingState}s.
        """
        self.assertEqual(
            DefaultFormattingState(),
            DefaultFormattingState())
        self.assertNotEqual(
            DefaultFormattingState(),
            'hello')
