# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet.serialport}.
"""

from twisted.internet.error import ConnectionDone
from twisted.internet.protocol import Protocol
from twisted.python.failure import Failure
from twisted.trial import unittest

try:
    from twisted.internet import serialport as _serialport
except ImportError:
    serialport = None
else:
    serialport = _serialport


class DoNothing:
    """
    Object with methods that do nothing.
    """

    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, attr):
        return lambda *args, **kwargs: None


class SerialPortTests(unittest.TestCase):
    """
    Minimal testing for Twisted's serial port support.

    See ticket #2462 for the eventual full test suite.
    """

    if serialport is None:
        skip = "Serial port support is not available."

    def test_connectionMadeLost(self):
        """
        C{connectionMade} and C{connectionLost} are called on the protocol by
        the C{SerialPort}.
        """
        # Serial port that doesn't actually connect to anything:
        class DummySerialPort(serialport.SerialPort):
            _serialFactory = DoNothing

            def _finishPortSetup(self):
                pass  # override default win32 actions

        events = []

        class SerialProtocol(Protocol):
            def connectionMade(self):
                events.append("connectionMade")

            def connectionLost(self, reason):
                events.append(("connectionLost", reason))

        # Creation of port should result in connectionMade call:
        port = DummySerialPort(SerialProtocol(), "", reactor=DoNothing())
        self.assertEqual(events, ["connectionMade"])

        # Simulate reactor calling connectionLost on the SerialPort:
        f = Failure(ConnectionDone())
        port.connectionLost(f)
        self.assertEqual(events, ["connectionMade", ("connectionLost", f)])
