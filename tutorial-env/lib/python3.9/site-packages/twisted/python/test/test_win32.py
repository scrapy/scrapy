# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.win32}.
"""

from twisted.python import reflect, win32
from twisted.trial import unittest


class CommandLineQuotingTests(unittest.TestCase):
    """
    Tests for L{cmdLineQuote}.
    """

    def test_argWithoutSpaces(self):
        """
        Calling C{cmdLineQuote} with an argument with no spaces returns
        the argument unchanged.
        """
        self.assertEqual(win32.cmdLineQuote("an_argument"), "an_argument")

    def test_argWithSpaces(self):
        """
        Calling C{cmdLineQuote} with an argument containing spaces returns
        the argument surrounded by quotes.
        """
        self.assertEqual(win32.cmdLineQuote("An Argument"), '"An Argument"')

    def test_emptyStringArg(self):
        """
        Calling C{cmdLineQuote} with an empty string returns a quoted empty
        string.
        """
        self.assertEqual(win32.cmdLineQuote(""), '""')


class DeprecationTests(unittest.TestCase):
    """
    Tests for deprecated (Fake)WindowsError.
    """

    def test_deprecation_FakeWindowsError(self):
        """Importing C{FakeWindowsError} triggers a L{DeprecationWarning}."""

        self.assertWarns(
            DeprecationWarning,
            "twisted.python.win32.FakeWindowsError was deprecated in Twisted 21.2.0: "
            "Catch OSError and check presence of 'winerror' attribute.",
            reflect.__file__,
            lambda: reflect.namedAny("twisted.python.win32.FakeWindowsError"),
        )

    def test_deprecation_WindowsError(self):
        """Importing C{WindowsError} triggers a L{DeprecationWarning}."""

        self.assertWarns(
            DeprecationWarning,
            "twisted.python.win32.WindowsError was deprecated in Twisted 21.2.0: "
            "Catch OSError and check presence of 'winerror' attribute.",
            reflect.__file__,
            lambda: reflect.namedAny("twisted.python.win32.WindowsError"),
        )
