# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for implementations of L{IReactorSocket}.

Generally only tests for failure cases are found here.  Success cases for
this interface are tested elsewhere.  For example, the success case for
I{AF_INET} is in L{twisted.internet.test.test_tcp}, since that case should
behave exactly the same as L{IReactorTCP.listenTCP}.
"""

import errno, socket

from zope.interface import verify

from twisted.python.log import err
from twisted.internet.interfaces import IReactorSocket
from twisted.internet.error import UnsupportedAddressFamily
from twisted.internet.protocol import DatagramProtocol, ServerFactory
from twisted.internet.test.reactormixins import (
    ReactorBuilder, needsRunningReactor)



class IReactorSocketVerificationTestsBuilder(ReactorBuilder):
    """
    Builder for testing L{IReactorSocket} implementations for required
    methods and method signatures.

    L{ReactorBuilder} already runs L{IReactorSocket.providedBy} to
    ensure that these tests will only be run on reactor classes that
    claim to implement L{IReactorSocket}.

    These tests ensure that reactors which claim to provide the
    L{IReactorSocket} interface actually have all the required methods
    and that those methods have the expected number of arguments.

    These tests will be skipped for reactors which do not claim to
    provide L{IReactorSocket}.
    """
    requiredInterfaces = [IReactorSocket]


    def test_provider(self):
        """
        The reactor instance returned by C{buildReactor} provides
        L{IReactorSocket}.
        """
        reactor = self.buildReactor()
        self.assertTrue(
            verify.verifyObject(IReactorSocket, reactor))



class AdoptStreamPortErrorsTestsBuilder(ReactorBuilder):
    """
    Builder for testing L{IReactorSocket.adoptStreamPort} implementations.

    Generally only tests for failure cases are found here.  Success cases for
    this interface are tested elsewhere.  For example, the success case for
    I{AF_INET} is in L{twisted.internet.test.test_tcp}, since that case should
    behave exactly the same as L{IReactorTCP.listenTCP}.
    """
    requiredInterfaces = [IReactorSocket]

    def test_invalidDescriptor(self):
        """
        An implementation of L{IReactorSocket.adoptStreamPort} raises
        L{socket.error} if passed an integer which is not associated with a
        socket.
        """
        reactor = self.buildReactor()

        probe = socket.socket()
        fileno = probe.fileno()
        probe.close()

        exc = self.assertRaises(
            socket.error,
            reactor.adoptStreamPort, fileno, socket.AF_INET, ServerFactory())
        self.assertEqual(exc.args[0], errno.EBADF)


    def test_invalidAddressFamily(self):
        """
        An implementation of L{IReactorSocket.adoptStreamPort} raises
        L{UnsupportedAddressFamily} if passed an address family it does not
        support.
        """
        reactor = self.buildReactor()

        port = socket.socket()
        port.listen(1)
        self.addCleanup(port.close)

        arbitrary = 2 ** 16 + 7

        self.assertRaises(
            UnsupportedAddressFamily,
            reactor.adoptStreamPort, port.fileno(), arbitrary, ServerFactory())


    def test_stopOnlyCloses(self):
        """
        When the L{IListeningPort} returned by
        L{IReactorSocket.adoptStreamPort} is stopped using
        C{stopListening}, the underlying socket is closed but not
        shutdown.  This allows another process which still has a
        reference to it to continue accepting connections over it.
        """
        reactor = self.buildReactor()

        portSocket = socket.socket()
        self.addCleanup(portSocket.close)

        portSocket.listen(1)
        portSocket.setblocking(False)

        # The file descriptor is duplicated by adoptStreamPort
        port = reactor.adoptStreamPort(
            portSocket.fileno(), portSocket.family, ServerFactory())
        d = port.stopListening()
        def stopped(ignored):
            # Should still be possible to accept a connection on
            # portSocket.  If it was shutdown, the exception would be
            # EINVAL instead.
            exc = self.assertRaises(socket.error, portSocket.accept)
            self.assertEqual(exc.args[0], errno.EAGAIN)
        d.addCallback(stopped)
        d.addErrback(err, "Failed to accept on original port.")

        needsRunningReactor(
            reactor,
            lambda: d.addCallback(lambda ignored: reactor.stop()))

        reactor.run()



class AdoptStreamConnectionErrorsTestsBuilder(ReactorBuilder):
    """
    Builder for testing L{IReactorSocket.adoptStreamConnection}
    implementations.

    Generally only tests for failure cases are found here.  Success cases for
    this interface are tested elsewhere.  For example, the success case for
    I{AF_INET} is in L{twisted.internet.test.test_tcp}, since that case should
    behave exactly the same as L{IReactorTCP.listenTCP}.
    """
    requiredInterfaces = [IReactorSocket]

    def test_invalidAddressFamily(self):
        """
        An implementation of L{IReactorSocket.adoptStreamConnection} raises
        L{UnsupportedAddressFamily} if passed an address family it does not
        support.
        """
        reactor = self.buildReactor()

        connection = socket.socket()
        self.addCleanup(connection.close)

        arbitrary = 2 ** 16 + 7

        self.assertRaises(
            UnsupportedAddressFamily,
            reactor.adoptStreamConnection, connection.fileno(), arbitrary,
            ServerFactory())



class AdoptDatagramPortErrorsTestsBuilder(ReactorBuilder):
    """
    Builder for testing L{IReactorSocket.adoptDatagramPort} implementations.
    """
    requiredInterfaces = [IReactorSocket]


    def test_invalidDescriptor(self):
        """
        An implementation of L{IReactorSocket.adoptDatagramPort} raises
        L{socket.error} if passed an integer which is not associated with a
        socket.
        """
        reactor = self.buildReactor()

        probe = socket.socket()
        fileno = probe.fileno()
        probe.close()

        exc = self.assertRaises(
            socket.error,
            reactor.adoptDatagramPort, fileno, socket.AF_INET,
            DatagramProtocol())
        self.assertEqual(exc.args[0], errno.EBADF)


    def test_invalidAddressFamily(self):
        """
        An implementation of L{IReactorSocket.adoptDatagramPort} raises
        L{UnsupportedAddressFamily} if passed an address family it does not
        support.
        """
        reactor = self.buildReactor()

        port = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(port.close)

        arbitrary = 2 ** 16 + 7

        self.assertRaises(
            UnsupportedAddressFamily,
            reactor.adoptDatagramPort, port.fileno(), arbitrary,
            DatagramProtocol())


    def test_stopOnlyCloses(self):
        """
        When the L{IListeningPort} returned by
        L{IReactorSocket.adoptDatagramPort} is stopped using
        C{stopListening}, the underlying socket is closed but not
        shutdown.  This allows another process which still has a
        reference to it to continue reading and writing to it.
        """
        reactor = self.buildReactor()

        portSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(portSocket.close)

        portSocket.setblocking(False)

        # The file descriptor is duplicated by adoptDatagramPort
        port = reactor.adoptDatagramPort(
            portSocket.fileno(), portSocket.family, DatagramProtocol())
        d = port.stopListening()
        def stopped(ignored):
            # Should still be possible to recv on portSocket.  If
            # it was shutdown, the exception would be EINVAL instead.
            exc = self.assertRaises(socket.error, portSocket.recvfrom, 1)
            self.assertEqual(exc.args[0], errno.EAGAIN)
        d.addCallback(stopped)
        d.addErrback(err, "Failed to read on original port.")

        needsRunningReactor(
            reactor,
            lambda: d.addCallback(lambda ignored: reactor.stop()))

        reactor.run()



globals().update(IReactorSocketVerificationTestsBuilder.makeTestCaseClasses())
globals().update(AdoptStreamPortErrorsTestsBuilder.makeTestCaseClasses())
globals().update(AdoptStreamConnectionErrorsTestsBuilder.makeTestCaseClasses())
globals().update(AdoptDatagramPortErrorsTestsBuilder.makeTestCaseClasses())
