# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from __future__ import division, absolute_import

import socket, errno
from twisted.trial import unittest
from twisted.internet import error
from twisted.python.runtime import platformType


class StringificationTests(unittest.SynchronousTestCase):
    """Test that the exceptions have useful stringifications.
    """

    listOfTests = [
        #(output, exception[, args[, kwargs]]),

        ("An error occurred binding to an interface.",
         error.BindError),

        ("An error occurred binding to an interface: foo.",
         error.BindError, ['foo']),

        ("An error occurred binding to an interface: foo bar.",
         error.BindError, ['foo', 'bar']),

        ("Couldn't listen on eth0:4242: Foo.",
         error.CannotListenError,
         ('eth0', 4242, socket.error('Foo'))),

        ("Message is too long to send.",
         error.MessageLengthError),

        ("Message is too long to send: foo bar.",
         error.MessageLengthError, ['foo', 'bar']),

        ("DNS lookup failed.",
         error.DNSLookupError),

        ("DNS lookup failed: foo bar.",
         error.DNSLookupError, ['foo', 'bar']),

        ("An error occurred while connecting.",
         error.ConnectError),

        ("An error occurred while connecting: someOsError.",
         error.ConnectError, ['someOsError']),

        ("An error occurred while connecting: foo.",
         error.ConnectError, [], {'string': 'foo'}),

        ("An error occurred while connecting: someOsError: foo.",
         error.ConnectError, ['someOsError', 'foo']),

        ("Couldn't bind.",
         error.ConnectBindError),

        ("Couldn't bind: someOsError.",
         error.ConnectBindError, ['someOsError']),

        ("Couldn't bind: someOsError: foo.",
         error.ConnectBindError, ['someOsError', 'foo']),

        ("Hostname couldn't be looked up.",
         error.UnknownHostError),

        ("No route to host.",
         error.NoRouteError),

        ("Connection was refused by other side.",
         error.ConnectionRefusedError),

        ("TCP connection timed out.",
         error.TCPTimedOutError),

        ("File used for UNIX socket is no good.",
         error.BadFileError),

        ("Service name given as port is unknown.",
         error.ServiceNameUnknownError),

        ("User aborted connection.",
         error.UserError),

        ("User timeout caused connection failure.",
         error.TimeoutError),

        ("An SSL error occurred.",
         error.SSLError),

        ("Connection to the other side was lost in a non-clean fashion.",
         error.ConnectionLost),

        ("Connection to the other side was lost in a non-clean fashion: foo bar.",
         error.ConnectionLost, ['foo', 'bar']),

        ("Connection was closed cleanly.",
         error.ConnectionDone),

        ("Connection was closed cleanly: foo bar.",
         error.ConnectionDone, ['foo', 'bar']),

        ("Uh.", #TODO nice docstring, you've got there.
         error.ConnectionFdescWentAway),

        ("Tried to cancel an already-called event.",
         error.AlreadyCalled),

        ("Tried to cancel an already-called event: foo bar.",
         error.AlreadyCalled, ['foo', 'bar']),

        ("Tried to cancel an already-cancelled event.",
         error.AlreadyCancelled),

        ("Tried to cancel an already-cancelled event: x 2.",
         error.AlreadyCancelled, ["x", "2"]),

        ("A process has ended without apparent errors: process finished with exit code 0.",
         error.ProcessDone,
         [None]),

        ("A process has ended with a probable error condition: process ended.",
         error.ProcessTerminated),

        ("A process has ended with a probable error condition: process ended with exit code 42.",
         error.ProcessTerminated,
         [],
         {'exitCode': 42}),

        ("A process has ended with a probable error condition: process ended by signal SIGBUS.",
         error.ProcessTerminated,
         [],
         {'signal': 'SIGBUS'}),

        ("The Connector was not connecting when it was asked to stop connecting.",
         error.NotConnectingError),

        ("The Connector was not connecting when it was asked to stop connecting: x 13.",
         error.NotConnectingError, ["x", "13"]),

        ("The Port was not listening when it was asked to stop listening.",
         error.NotListeningError),

        ("The Port was not listening when it was asked to stop listening: a 12.",
         error.NotListeningError, ["a", "12"]),
        ]

    def testThemAll(self):
        for entry in self.listOfTests:
            output = entry[0]
            exception = entry[1]
            try:
                args = entry[2]
            except IndexError:
                args = ()
            try:
                kwargs = entry[3]
            except IndexError:
                kwargs = {}

            self.assertEqual(
                str(exception(*args, **kwargs)),
                output)


    def test_connectingCancelledError(self):
        """
        L{error.ConnectingCancelledError} has an C{address} attribute.
        """
        address = object()
        e = error.ConnectingCancelledError(address)
        self.assertIs(e.address, address)



class SubclassingTests(unittest.SynchronousTestCase):
    """
    Some exceptions are subclasses of other exceptions.
    """

    def test_connectionLostSubclassOfConnectionClosed(self):
        """
        L{error.ConnectionClosed} is a superclass of L{error.ConnectionLost}.
        """
        self.assertTrue(issubclass(error.ConnectionLost,
                                   error.ConnectionClosed))


    def test_connectionDoneSubclassOfConnectionClosed(self):
        """
        L{error.ConnectionClosed} is a superclass of L{error.ConnectionDone}.
        """
        self.assertTrue(issubclass(error.ConnectionDone,
                                   error.ConnectionClosed))


    def test_invalidAddressErrorSubclassOfValueError(self):
        """
        L{ValueError} is a superclass of L{error.InvalidAddressError}.
        """
        self.assertTrue(issubclass(error.InvalidAddressError,
                                   ValueError))




class GetConnectErrorTests(unittest.SynchronousTestCase):
    """
    Given an exception instance thrown by C{socket.connect},
    L{error.getConnectError} returns the appropriate high-level Twisted
    exception instance.
    """

    def assertErrnoException(self, errno, expectedClass):
        """
        When called with a tuple with the given errno,
        L{error.getConnectError} returns an exception which is an instance of
        the expected class.
        """
        e = (errno, "lalala")
        result = error.getConnectError(e)
        self.assertCorrectException(errno, "lalala", result, expectedClass)


    def assertCorrectException(self, errno, message, result, expectedClass):
        """
        The given result of L{error.getConnectError} has the given attributes
        (C{osError} and C{args}), and is an instance of the given class.
        """

        # Want exact class match, not inherited classes, so no isinstance():
        self.assertEqual(result.__class__, expectedClass)
        self.assertEqual(result.osError, errno)
        self.assertEqual(result.args, (message,))


    def test_errno(self):
        """
        L{error.getConnectError} converts based on errno for C{socket.error}.
        """
        self.assertErrnoException(errno.ENETUNREACH, error.NoRouteError)
        self.assertErrnoException(errno.ECONNREFUSED, error.ConnectionRefusedError)
        self.assertErrnoException(errno.ETIMEDOUT, error.TCPTimedOutError)
        if platformType == "win32":
            self.assertErrnoException(errno.WSAECONNREFUSED, error.ConnectionRefusedError)
            self.assertErrnoException(errno.WSAENETUNREACH, error.NoRouteError)


    def test_gaierror(self):
        """
        L{error.getConnectError} converts to a L{error.UnknownHostError} given
        a C{socket.gaierror} instance.
        """
        result = error.getConnectError(socket.gaierror(12, "hello"))
        self.assertCorrectException(12, "hello", result, error.UnknownHostError)


    def test_nonTuple(self):
        """
        L{error.getConnectError} converts to a L{error.ConnectError} given
        an argument that cannot be unpacked.
        """
        e = Exception()
        result = error.getConnectError(e)
        self.assertCorrectException(None, e, result, error.ConnectError)
