# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Whitebox tests for TCP APIs.
"""


import errno
import os
import socket

try:
    import resource
except ImportError:
    resource = None  # type: ignore[assignment]

from unittest import skipIf

from twisted.internet import interfaces, reactor
from twisted.internet.defer import gatherResults, maybeDeferred
from twisted.internet.protocol import Protocol, ServerFactory
from twisted.internet.tcp import (
    _ACCEPT_ERRORS,
    EAGAIN,
    ECONNABORTED,
    EINPROGRESS,
    EMFILE,
    ENFILE,
    ENOBUFS,
    ENOMEM,
    EPERM,
    EWOULDBLOCK,
    Port,
)
from twisted.python import log
from twisted.python.runtime import platform
from twisted.trial.unittest import TestCase


@skipIf(
    not interfaces.IReactorFDSet.providedBy(reactor),
    "This test only applies to reactors that implement IReactorFDset",
)
class PlatformAssumptionsTests(TestCase):
    """
    Test assumptions about platform behaviors.
    """

    socketLimit = 8192

    def setUp(self):
        self.openSockets = []
        if resource is not None:
            # On some buggy platforms we might leak FDs, and the test will
            # fail creating the initial two sockets we *do* want to
            # succeed. So, we make the soft limit the current number of fds
            # plus two more (for the two sockets we want to succeed). If we've
            # leaked too many fds for that to work, there's nothing we can
            # do.
            from twisted.internet.process import _listOpenFDs

            newLimit = len(_listOpenFDs()) + 2
            self.originalFileLimit = resource.getrlimit(resource.RLIMIT_NOFILE)
            resource.setrlimit(
                resource.RLIMIT_NOFILE, (newLimit, self.originalFileLimit[1])
            )
            self.socketLimit = newLimit + 100

    def tearDown(self):
        while self.openSockets:
            self.openSockets.pop().close()
        if resource is not None:
            # `macOS` implicitly lowers the hard limit in the setrlimit call
            # above.  Retrieve the new hard limit to pass in to this
            # setrlimit call, so that it doesn't give us a permission denied
            # error.
            currentHardLimit = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
            newSoftLimit = min(self.originalFileLimit[0], currentHardLimit)
            resource.setrlimit(resource.RLIMIT_NOFILE, (newSoftLimit, currentHardLimit))

    def socket(self):
        """
        Create and return a new socket object, also tracking it so it can be
        closed in the test tear down.
        """
        s = socket.socket()
        self.openSockets.append(s)
        return s

    @skipIf(
        platform.getType() == "win32",
        "Windows requires an unacceptably large amount of resources to "
        "provoke this behavior in the naive manner.",
    )
    def test_acceptOutOfFiles(self):
        """
        Test that the platform accept(2) call fails with either L{EMFILE} or
        L{ENOBUFS} when there are too many file descriptors open.
        """
        # Make a server to which to connect
        port = self.socket()
        port.bind(("127.0.0.1", 0))
        serverPortNumber = port.getsockname()[1]
        port.listen(5)

        # Make a client to use to connect to the server
        client = self.socket()
        client.setblocking(False)

        # Use up all the rest of the file descriptors.
        for i in range(self.socketLimit):
            try:
                self.socket()
            except OSError as e:
                if e.args[0] in (EMFILE, ENOBUFS):
                    # The desired state has been achieved.
                    break
                else:
                    # Some unexpected error occurred.
                    raise
        else:
            self.fail("Could provoke neither EMFILE nor ENOBUFS from platform.")

        # Non-blocking connect is supposed to fail, but this is not true
        # everywhere (e.g. freeBSD)
        self.assertIn(
            client.connect_ex(("127.0.0.1", serverPortNumber)), (0, EINPROGRESS)
        )

        # Make sure that the accept call fails in the way we expect.
        exc = self.assertRaises(socket.error, port.accept)
        self.assertIn(exc.args[0], (EMFILE, ENOBUFS))


@skipIf(
    not interfaces.IReactorFDSet.providedBy(reactor),
    "This test only applies to reactors that implement IReactorFDset",
)
class SelectReactorTests(TestCase):
    """
    Tests for select-specific failure conditions.
    """

    def setUp(self):
        self.ports = []
        self.messages = []
        log.addObserver(self.messages.append)

    def tearDown(self):
        log.removeObserver(self.messages.append)
        return gatherResults([maybeDeferred(p.stopListening) for p in self.ports])

    def port(self, portNumber, factory, interface):
        """
        Create, start, and return a new L{Port}, also tracking it so it can
        be stopped in the test tear down.
        """
        p = Port(portNumber, factory, interface=interface)
        p.startListening()
        self.ports.append(p)
        return p

    def _acceptFailureTest(self, socketErrorNumber):
        """
        Test behavior in the face of an exception from C{accept(2)}.

        On any exception which indicates the platform is unable or unwilling
        to allocate further resources to us, the existing port should remain
        listening, a message should be logged, and the exception should not
        propagate outward from doRead.

        @param socketErrorNumber: The errno to simulate from accept.
        """

        class FakeSocket:
            """
            Pretend to be a socket in an overloaded system.
            """

            def accept(self):
                raise OSError(socketErrorNumber, os.strerror(socketErrorNumber))

        factory = ServerFactory()
        port = self.port(0, factory, interface="127.0.0.1")
        self.patch(port, "socket", FakeSocket())

        port.doRead()

        expectedFormat = "Could not accept new connection ({acceptError})"
        expectedErrorCode = errno.errorcode[socketErrorNumber]
        matchingMessages = [
            (
                msg.get("log_format") == expectedFormat
                and msg.get("acceptError") == expectedErrorCode
            )
            for msg in self.messages
        ]
        self.assertGreater(
            len(matchingMessages),
            0,
            "Log event for failed accept not found in " "%r" % (self.messages,),
        )

    def test_tooManyFilesFromAccept(self):
        """
        C{accept(2)} can fail with C{EMFILE} when there are too many open file
        descriptors in the process.  Test that this doesn't negatively impact
        any other existing connections.

        C{EMFILE} mainly occurs on Linux when the open file rlimit is
        encountered.
        """
        return self._acceptFailureTest(EMFILE)

    def test_noBufferSpaceFromAccept(self):
        """
        Similar to L{test_tooManyFilesFromAccept}, but test the case where
        C{accept(2)} fails with C{ENOBUFS}.

        This mainly occurs on Windows and FreeBSD, but may be possible on
        Linux and other platforms as well.
        """
        return self._acceptFailureTest(ENOBUFS)

    def test_connectionAbortedFromAccept(self):
        """
        Similar to L{test_tooManyFilesFromAccept}, but test the case where
        C{accept(2)} fails with C{ECONNABORTED}.

        It is not clear whether this is actually possible for TCP
        connections on modern versions of Linux.
        """
        return self._acceptFailureTest(ECONNABORTED)

    @skipIf(platform.getType() == "win32", "Windows accept(2) cannot generate ENFILE")
    def test_noFilesFromAccept(self):
        """
        Similar to L{test_tooManyFilesFromAccept}, but test the case where
        C{accept(2)} fails with C{ENFILE}.

        This can occur on Linux when the system has exhausted (!) its supply
        of inodes.
        """
        return self._acceptFailureTest(ENFILE)

    @skipIf(platform.getType() == "win32", "Windows accept(2) cannot generate ENOMEM")
    def test_noMemoryFromAccept(self):
        """
        Similar to L{test_tooManyFilesFromAccept}, but test the case where
        C{accept(2)} fails with C{ENOMEM}.

        On Linux at least, this can sensibly occur, even in a Python program
        (which eats memory like no ones business), when memory has become
        fragmented or low memory has been filled (d_alloc calls
        kmem_cache_alloc calls kmalloc - kmalloc only allocates out of low
        memory).
        """
        return self._acceptFailureTest(ENOMEM)

    @skipIf(
        os.environ.get("INFRASTRUCTURE") == "AZUREPIPELINES",
        "Hangs on Azure Pipelines due to firewall",
    )
    def test_acceptScaling(self):
        """
        L{tcp.Port.doRead} increases the number of consecutive
        C{accept} calls it performs if all of the previous C{accept}
        calls succeed; otherwise, it reduces the number to the amount
        of successful calls.
        """
        factory = ServerFactory()
        factory.protocol = Protocol
        port = self.port(0, factory, interface="127.0.0.1")
        self.addCleanup(port.stopListening)

        clients = []

        def closeAll():
            for client in clients:
                client.close()

        self.addCleanup(closeAll)

        def connect():
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect(("127.0.0.1", port.getHost().port))
            return client

        clients.append(connect())
        port.numberAccepts = 1
        port.doRead()
        self.assertGreater(port.numberAccepts, 1)

        clients.append(connect())
        port.doRead()
        # There was only one outstanding client connection, so only
        # one accept(2) was possible.
        self.assertEqual(port.numberAccepts, 1)

        port.doRead()
        # There were no outstanding client connections, so only one
        # accept should be tried next.
        self.assertEqual(port.numberAccepts, 1)

    @skipIf(platform.getType() == "win32", "Windows accept(2) cannot generate EPERM")
    def test_permissionFailure(self):
        """
        C{accept(2)} returning C{EPERM} is treated as a transient
        failure and the call retried no more than the maximum number
        of consecutive C{accept(2)} calls.
        """
        maximumNumberOfAccepts = 123
        acceptCalls = [0]

        class FakeSocketWithAcceptLimit:
            """
            Pretend to be a socket in an overloaded system whose
            C{accept} method can only be called
            C{maximumNumberOfAccepts} times.
            """

            def accept(oself):
                acceptCalls[0] += 1
                if acceptCalls[0] > maximumNumberOfAccepts:
                    self.fail("Maximum number of accept calls exceeded.")
                raise OSError(EPERM, os.strerror(EPERM))

        # Verify that FakeSocketWithAcceptLimit.accept() fails the
        # test if the number of accept calls exceeds the maximum.
        for _ in range(maximumNumberOfAccepts):
            self.assertRaises(socket.error, FakeSocketWithAcceptLimit().accept)

        self.assertRaises(self.failureException, FakeSocketWithAcceptLimit().accept)

        acceptCalls = [0]

        factory = ServerFactory()
        port = self.port(0, factory, interface="127.0.0.1")
        port.numberAccepts = 123
        self.patch(port, "socket", FakeSocketWithAcceptLimit())

        # This should not loop infinitely.
        port.doRead()

        # This is scaled down to 1 because no accept(2)s returned
        # successfully.
        self.assertEquals(port.numberAccepts, 1)

    def test_unknownSocketErrorRaise(self):
        """
        A C{socket.error} raised by C{accept(2)} whose C{errno} is
        unknown to the recovery logic is logged.
        """
        knownErrors = list(_ACCEPT_ERRORS)
        knownErrors.extend([EAGAIN, EPERM, EWOULDBLOCK])
        # Windows has object()s stubs for some errnos.
        unknownAcceptError = (
            max(error for error in knownErrors if isinstance(error, int)) + 1
        )

        class FakeSocketWithUnknownAcceptError:
            """
            Pretend to be a socket in an overloaded system whose
            C{accept} method can only be called
            C{maximumNumberOfAccepts} times.
            """

            def accept(oself):
                raise OSError(unknownAcceptError, "unknown socket error message")

        factory = ServerFactory()
        port = self.port(0, factory, interface="127.0.0.1")
        self.patch(port, "socket", FakeSocketWithUnknownAcceptError())

        port.doRead()

        failures = self.flushLoggedErrors(socket.error)
        self.assertEqual(1, len(failures))
        self.assertEqual(failures[0].value.args[0], unknownAcceptError)
