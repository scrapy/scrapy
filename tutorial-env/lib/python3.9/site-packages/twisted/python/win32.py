# -*- test-case-name: twisted.python.test.test_win32 -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Win32 utilities.

See also twisted.python.shortcut.

@var O_BINARY: the 'binary' mode flag on Windows, or 0 on other platforms, so it
    may safely be OR'ed into a mask for os.open.
"""

import os
import re

from incremental import Version

from twisted.python.deprecate import deprecatedModuleAttribute

# https://docs.microsoft.com/en-us/windows/win32/debug/system-error-codes
ERROR_FILE_NOT_FOUND = 2
ERROR_PATH_NOT_FOUND = 3
ERROR_INVALID_NAME = 123
ERROR_DIRECTORY = 267

O_BINARY = getattr(os, "O_BINARY", 0)


class FakeWindowsError(OSError):
    """
    Stand-in for sometimes-builtin exception on platforms for which it
    is missing.
    """


deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Catch OSError and check presence of 'winerror' attribute.",
    "twisted.python.win32",
    "FakeWindowsError",
)


try:
    WindowsError: OSError = WindowsError
except NameError:
    WindowsError = FakeWindowsError

deprecatedModuleAttribute(
    Version("Twisted", 21, 2, 0),
    "Catch OSError and check presence of 'winerror' attribute.",
    "twisted.python.win32",
    "WindowsError",
)


_cmdLineQuoteRe = re.compile(r'(\\*)"')
_cmdLineQuoteRe2 = re.compile(r"(\\+)\Z")


def cmdLineQuote(s):
    """
    Internal method for quoting a single command-line argument.

    @param s: an unquoted string that you want to quote so that something that
        does cmd.exe-style unquoting will interpret it as a single argument,
        even if it contains spaces.
    @type s: C{str}

    @return: a quoted string.
    @rtype: C{str}
    """
    quote = ((" " in s) or ("\t" in s) or ('"' in s) or s == "") and '"' or ""
    return (
        quote
        + _cmdLineQuoteRe2.sub(r"\1\1", _cmdLineQuoteRe.sub(r'\1\1\\"', s))
        + quote
    )


def quoteArguments(arguments):
    """
    Quote an iterable of command-line arguments for passing to CreateProcess or
    a similar API.  This allows the list passed to C{reactor.spawnProcess} to
    match the child process's C{sys.argv} properly.

    @param arguments: an iterable of C{str}, each unquoted.

    @return: a single string, with the given sequence quoted as necessary.
    """
    return " ".join([cmdLineQuote(a) for a in arguments])


class _ErrorFormatter:
    """
    Formatter for Windows error messages.

    @ivar winError: A callable which takes one integer error number argument
        and returns a L{WindowsError} instance for that error (like
        L{ctypes.WinError}).

    @ivar formatMessage: A callable which takes one integer error number
        argument and returns a C{str} giving the message for that error (like
        U{win32api.FormatMessage<http://
        timgolden.me.uk/pywin32-docs/win32api__FormatMessage_meth.html>}).

    @ivar errorTab: A mapping from integer error numbers to C{str} messages
        which correspond to those erorrs (like I{socket.errorTab}).
    """

    def __init__(self, WinError, FormatMessage, errorTab):
        self.winError = WinError
        self.formatMessage = FormatMessage
        self.errorTab = errorTab

    @classmethod
    def fromEnvironment(cls):
        """
        Get as many of the platform-specific error translation objects as
        possible and return an instance of C{cls} created with them.
        """
        try:
            from ctypes import WinError
        except ImportError:
            WinError = None
        try:
            from win32api import FormatMessage  # type: ignore[import]
        except ImportError:
            FormatMessage = None
        try:
            from socket import errorTab
        except ImportError:
            errorTab = None
        return cls(WinError, FormatMessage, errorTab)

    def formatError(self, errorcode):
        """
        Returns the string associated with a Windows error message, such as the
        ones found in socket.error.

        Attempts direct lookup against the win32 API via ctypes and then
        pywin32 if available), then in the error table in the socket module,
        then finally defaulting to C{os.strerror}.

        @param errorcode: the Windows error code
        @type errorcode: C{int}

        @return: The error message string
        @rtype: C{str}
        """
        if self.winError is not None:
            return self.winError(errorcode).strerror
        if self.formatMessage is not None:
            return self.formatMessage(errorcode)
        if self.errorTab is not None:
            result = self.errorTab.get(errorcode)
            if result is not None:
                return result
        return os.strerror(errorcode)


formatError = _ErrorFormatter.fromEnvironment().formatError
