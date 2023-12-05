# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test strerror
"""

import os
import socket
from unittest import skipIf

from twisted.internet.tcp import ECONNABORTED
from twisted.python.runtime import platform
from twisted.python.win32 import _ErrorFormatter, formatError
from twisted.trial.unittest import TestCase


class _MyWindowsException(OSError):
    """
    An exception type like L{ctypes.WinError}, but available on all platforms.
    """


class ErrorFormatingTests(TestCase):
    """
    Tests for C{_ErrorFormatter.formatError}.
    """

    probeErrorCode = ECONNABORTED
    probeMessage = "correct message value"

    def test_strerrorFormatting(self):
        """
        L{_ErrorFormatter.formatError} should use L{os.strerror} to format
        error messages if it is constructed without any better mechanism.
        """
        formatter = _ErrorFormatter(None, None, None)
        message = formatter.formatError(self.probeErrorCode)
        self.assertEqual(message, os.strerror(self.probeErrorCode))

    def test_emptyErrorTab(self):
        """
        L{_ErrorFormatter.formatError} should use L{os.strerror} to format
        error messages if it is constructed with only an error tab which does
        not contain the error code it is called with.
        """
        error = 1
        # Sanity check
        self.assertNotEqual(self.probeErrorCode, error)
        formatter = _ErrorFormatter(None, None, {error: "wrong message"})
        message = formatter.formatError(self.probeErrorCode)
        self.assertEqual(message, os.strerror(self.probeErrorCode))

    def test_errorTab(self):
        """
        L{_ErrorFormatter.formatError} should use C{errorTab} if it is supplied
        and contains the requested error code.
        """
        formatter = _ErrorFormatter(
            None, None, {self.probeErrorCode: self.probeMessage}
        )
        message = formatter.formatError(self.probeErrorCode)
        self.assertEqual(message, self.probeMessage)

    def test_formatMessage(self):
        """
        L{_ErrorFormatter.formatError} should return the return value of
        C{formatMessage} if it is supplied.
        """
        formatCalls = []

        def formatMessage(errorCode):
            formatCalls.append(errorCode)
            return self.probeMessage

        formatter = _ErrorFormatter(
            None, formatMessage, {self.probeErrorCode: "wrong message"}
        )
        message = formatter.formatError(self.probeErrorCode)
        self.assertEqual(message, self.probeMessage)
        self.assertEqual(formatCalls, [self.probeErrorCode])

    def test_winError(self):
        """
        L{_ErrorFormatter.formatError} should return the message argument from
        the exception L{winError} returns, if L{winError} is supplied.
        """
        winCalls = []

        def winError(errorCode):
            winCalls.append(errorCode)
            return _MyWindowsException(errorCode, self.probeMessage)

        formatter = _ErrorFormatter(
            winError,
            lambda error: "formatMessage: wrong message",
            {self.probeErrorCode: "errorTab: wrong message"},
        )
        message = formatter.formatError(self.probeErrorCode)
        self.assertEqual(message, self.probeMessage)

    @skipIf(platform.getType() != "win32", "Test will run only on Windows.")
    def test_fromEnvironment(self):
        """
        L{_ErrorFormatter.fromEnvironment} should create an L{_ErrorFormatter}
        instance with attributes populated from available modules.
        """
        formatter = _ErrorFormatter.fromEnvironment()

        if formatter.winError is not None:
            from ctypes import WinError

            self.assertEqual(
                formatter.formatError(self.probeErrorCode),
                WinError(self.probeErrorCode).strerror,
            )
            formatter.winError = None

        if formatter.formatMessage is not None:
            from win32api import FormatMessage  # type: ignore[import]

            self.assertEqual(
                formatter.formatError(self.probeErrorCode),
                FormatMessage(self.probeErrorCode),
            )
            formatter.formatMessage = None

        if formatter.errorTab is not None:
            from socket import errorTab

            self.assertEqual(
                formatter.formatError(self.probeErrorCode),
                errorTab[self.probeErrorCode],
            )

    @skipIf(platform.getType() != "win32", "Test will run only on Windows.")
    def test_correctLookups(self):
        """
        Given a known-good errno, make sure that formatMessage gives results
        matching either C{socket.errorTab}, C{ctypes.WinError}, or
        C{win32api.FormatMessage}.
        """
        acceptable = [socket.errorTab[ECONNABORTED]]
        try:
            from ctypes import WinError

            acceptable.append(WinError(ECONNABORTED).strerror)
        except ImportError:
            pass
        try:
            from win32api import FormatMessage

            acceptable.append(FormatMessage(ECONNABORTED))
        except ImportError:
            pass

        self.assertIn(formatError(ECONNABORTED), acceptable)
