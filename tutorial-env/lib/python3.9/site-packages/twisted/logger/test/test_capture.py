# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._capture}.
"""

from twisted.logger import Logger, LogLevel
from twisted.trial.unittest import TestCase
from .._capture import capturedLogs


class LogCaptureTests(TestCase):
    """
    Tests for L{LogCaptureTests}.
    """

    log = Logger()

    def test_capture(self) -> None:
        """
        Events logged within context are captured.
        """
        foo = object()

        with capturedLogs() as captured:
            self.log.debug("Capture this, please", foo=foo)
            self.log.info("Capture this too, please", foo=foo)

        self.assertTrue(len(captured) == 2)
        self.assertEqual(captured[0]["log_format"], "Capture this, please")
        self.assertEqual(captured[0]["log_level"], LogLevel.debug)
        self.assertEqual(captured[0]["foo"], foo)
        self.assertEqual(captured[1]["log_format"], "Capture this too, please")
        self.assertEqual(captured[1]["log_level"], LogLevel.info)
        self.assertEqual(captured[1]["foo"], foo)
