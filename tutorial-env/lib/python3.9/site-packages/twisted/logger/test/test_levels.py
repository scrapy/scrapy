# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._levels}.
"""

from twisted.trial import unittest
from .._levels import InvalidLogLevelError, LogLevel


class LogLevelTests(unittest.TestCase):
    """
    Tests for L{LogLevel}.
    """

    def test_levelWithName(self) -> None:
        """
        Look up log level by name.
        """
        for level in LogLevel.iterconstants():
            self.assertIs(LogLevel.levelWithName(level.name), level)

    def test_levelWithInvalidName(self) -> None:
        """
        You can't make up log level names.
        """
        bogus = "*bogus*"
        try:
            LogLevel.levelWithName(bogus)
        except InvalidLogLevelError as e:
            self.assertIs(e.level, bogus)
        else:
            self.fail("Expected InvalidLogLevelError.")
