# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.protocol.socks}, an implementation of the SOCKSv4 and
SOCKSv4a protocols.
"""

import socket
import struct

from twisted.internet import address, defer
from twisted.internet.error import DNSLookupError
from twisted.protocols import socks
from twisted.python.compat import iterbytes
from twisted.test import proto_helpers
from twisted.trial import unittest


class StringTCPTransport(proto_helpers.StringTransport):
    stringTCPTransport_closing = False
    peer = None

    def getPeer(self):
        return self.peer

    def getHost(self):
        return address.IPv4Address("TCP", "2.3.4.5", 42)

    def loseConnection(self):
        self.stringTCPTransport_closing = True


class FakeResolverReactor:
    """
    Bare-bones reactor with deterministic behavior for the resolve method.
    """

    def __init__(self, names):
        """
        @type names: L{dict} containing L{str} keys and L{str} values.
        @param names: A hostname to IP address mapping. The IP addresses are
            stringified dotted quads.
        """
        self.names = names

    def resolve(self, hostname):
        """
        Resolve a hostname by looking it up in the C{names} dictionary.
        """
        try:
            return defer.succeed(self.names[hostname])
        except KeyError:
            return defer.fail(
                DNSLookupError(
                    "FakeResolverReactor couldn't find " + hostname.decode("utf-8")
                )
            )


class SOCKSv4Driver(socks.SOCKSv4):
    # last SOCKSv4Outgoing instantiated
    driver_outgoing = None

    # last SOCKSv4IncomingFactory instantiated
    driver_listen = None

    def connectClass(self, host, port, klass, *args):
        # fake it
        proto = klass(*args)
        proto.transport = StringTCPTransport()
        proto.transport.peer = address.IPv4Address("TCP", host, port)
        proto.connectionMade()
        self.driver_outgoing = proto
        return defer.succeed(proto)

    def listenClass(self, port, klass, *args):
        # fake it
        factory = klass(*args)
        self.driver_listen = factory
        if port == 0:
            port = 1234
        return defer.succeed(("6.7.8.9", port))


class ConnectTests(unittest.TestCase):
    """
    Tests for SOCKS and SOCKSv4a connect requests using the L{SOCKSv4} protocol.
    """

    def setUp(self):
        self.sock = SOCKSv4Driver()
        self.sock.transport = StringTCPTransport()
        self.sock.connectionMade()
        self.sock.reactor = FakeResolverReactor({b"localhost": "127.0.0.1"})

    def tearDown(self):
        outgoing = self.sock.driver_outgoing
        if outgoing is not None:
            self.assertTrue(
                outgoing.transport.stringTCPTransport_closing,
                "Outgoing SOCKS connections need to be closed.",
            )

    def test_simple(self):
        self.sock.dataReceived(
            struct.pack("!BBH", 4, 1, 34)
            + socket.inet_aton("1.2.3.4")
            + b"fooBAR"
            + b"\0"
        )
        sent = self.sock.transport.value()
        self.sock.transport.clear()
        self.assertEqual(
            sent, struct.pack("!BBH", 0, 90, 34) + socket.inet_aton("1.2.3.4")
        )
        self.assertFalse(self.sock.transport.stringTCPTransport_closing)
        self.assertIsNotNone(self.sock.driver_outgoing)

        # pass some data through
        self.sock.dataReceived(b"hello, world")
        self.assertEqual(self.sock.driver_outgoing.transport.value(), b"hello, world")

        # the other way around
        self.sock.driver_outgoing.dataReceived(b"hi there")
        self.assertEqual(self.sock.transport.value(), b"hi there")

        self.sock.connectionLost("fake reason")

    def test_socks4aSuccessfulResolution(self):
        """
        If the destination IP address has zeros for the first three octets and
        non-zero for the fourth octet, the client is attempting a v4a
        connection.  A hostname is specified after the user ID string and the
        server connects to the address that hostname resolves to.

        @see: U{http://en.wikipedia.org/wiki/SOCKS#SOCKS_4a_protocol}
        """
        # send the domain name "localhost" to be resolved
        clientRequest = (
            struct.pack("!BBH", 4, 1, 34)
            + socket.inet_aton("0.0.0.1")
            + b"fooBAZ\0"
            + b"localhost\0"
        )

        # Deliver the bytes one by one to exercise the protocol's buffering
        # logic. FakeResolverReactor's resolve method is invoked to "resolve"
        # the hostname.
        for byte in iterbytes(clientRequest):
            self.sock.dataReceived(byte)

        sent = self.sock.transport.value()
        self.sock.transport.clear()

        # Verify that the server responded with the address which will be
        # connected to.
        self.assertEqual(
            sent, struct.pack("!BBH", 0, 90, 34) + socket.inet_aton("127.0.0.1")
        )
        self.assertFalse(self.sock.transport.stringTCPTransport_closing)
        self.assertIsNotNone(self.sock.driver_outgoing)

        # Pass some data through and verify it is forwarded to the outgoing
        # connection.
        self.sock.dataReceived(b"hello, world")
        self.assertEqual(self.sock.driver_outgoing.transport.value(), b"hello, world")

        # Deliver some data from the output connection and verify it is
        # passed along to the incoming side.
        self.sock.driver_outgoing.dataReceived(b"hi there")
        self.assertEqual(self.sock.transport.value(), b"hi there")

        self.sock.connectionLost("fake reason")

    def test_socks4aFailedResolution(self):
        """
        Failed hostname resolution on a SOCKSv4a packet results in a 91 error
        response and the connection getting closed.
        """
        # send the domain name "failinghost" to be resolved
        clientRequest = (
            struct.pack("!BBH", 4, 1, 34)
            + socket.inet_aton("0.0.0.1")
            + b"fooBAZ\0"
            + b"failinghost\0"
        )

        # Deliver the bytes one by one to exercise the protocol's buffering
        # logic. FakeResolverReactor's resolve method is invoked to "resolve"
        # the hostname.
        for byte in iterbytes(clientRequest):
            self.sock.dataReceived(byte)

        # Verify that the server responds with a 91 error.
        sent = self.sock.transport.value()
        self.assertEqual(
            sent, struct.pack("!BBH", 0, 91, 0) + socket.inet_aton("0.0.0.0")
        )

        # A failed resolution causes the transport to drop the connection.
        self.assertTrue(self.sock.transport.stringTCPTransport_closing)
        self.assertIsNone(self.sock.driver_outgoing)

    def test_accessDenied(self):
        self.sock.authorize = lambda code, server, port, user: 0
        self.sock.dataReceived(
            struct.pack("!BBH", 4, 1, 4242)
            + socket.inet_aton("10.2.3.4")
            + b"fooBAR"
            + b"\0"
        )
        self.assertEqual(
            self.sock.transport.value(),
            struct.pack("!BBH", 0, 91, 0) + socket.inet_aton("0.0.0.0"),
        )
        self.assertTrue(self.sock.transport.stringTCPTransport_closing)
        self.assertIsNone(self.sock.driver_outgoing)

    def test_eofRemote(self):
        self.sock.dataReceived(
            struct.pack("!BBH", 4, 1, 34)
            + socket.inet_aton("1.2.3.4")
            + b"fooBAR"
            + b"\0"
        )
        self.sock.transport.clear()

        # pass some data through
        self.sock.dataReceived(b"hello, world")
        self.assertEqual(self.sock.driver_outgoing.transport.value(), b"hello, world")

        # now close it from the server side
        self.sock.driver_outgoing.transport.loseConnection()
        self.sock.driver_outgoing.connectionLost("fake reason")

    def test_eofLocal(self):
        self.sock.dataReceived(
            struct.pack("!BBH", 4, 1, 34)
            + socket.inet_aton("1.2.3.4")
            + b"fooBAR"
            + b"\0"
        )
        self.sock.transport.clear()

        # pass some data through
        self.sock.dataReceived(b"hello, world")
        self.assertEqual(self.sock.driver_outgoing.transport.value(), b"hello, world")

        # now close it from the client side
        self.sock.connectionLost("fake reason")


class BindTests(unittest.TestCase):
    """
    Tests for SOCKS and SOCKSv4a bind requests using the L{SOCKSv4} protocol.
    """

    def setUp(self):
        self.sock = SOCKSv4Driver()
        self.sock.transport = StringTCPTransport()
        self.sock.connectionMade()
        self.sock.reactor = FakeResolverReactor({b"localhost": "127.0.0.1"})

    ##     def tearDown(self):
    ##         # TODO ensure the listen port is closed
    ##         listen = self.sock.driver_listen
    ##         if listen is not None:
    ##             self.assert_(incoming.transport.stringTCPTransport_closing,
    ##                     "Incoming SOCKS connections need to be closed.")

    def test_simple(self):
        self.sock.dataReceived(
            struct.pack("!BBH", 4, 2, 34)
            + socket.inet_aton("1.2.3.4")
            + b"fooBAR"
            + b"\0"
        )
        sent = self.sock.transport.value()
        self.sock.transport.clear()
        self.assertEqual(
            sent, struct.pack("!BBH", 0, 90, 1234) + socket.inet_aton("6.7.8.9")
        )
        self.assertFalse(self.sock.transport.stringTCPTransport_closing)
        self.assertIsNotNone(self.sock.driver_listen)

        # connect
        incoming = self.sock.driver_listen.buildProtocol(("1.2.3.4", 5345))
        self.assertIsNotNone(incoming)
        incoming.transport = StringTCPTransport()
        incoming.connectionMade()

        # now we should have the second reply packet
        sent = self.sock.transport.value()
        self.sock.transport.clear()
        self.assertEqual(
            sent, struct.pack("!BBH", 0, 90, 0) + socket.inet_aton("0.0.0.0")
        )
        self.assertFalse(self.sock.transport.stringTCPTransport_closing)

        # pass some data through
        self.sock.dataReceived(b"hello, world")
        self.assertEqual(incoming.transport.value(), b"hello, world")

        # the other way around
        incoming.dataReceived(b"hi there")
        self.assertEqual(self.sock.transport.value(), b"hi there")

        self.sock.connectionLost("fake reason")

    def test_socks4a(self):
        """
        If the destination IP address has zeros for the first three octets and
        non-zero for the fourth octet, the client is attempting a v4a
        connection.  A hostname is specified after the user ID string and the
        server connects to the address that hostname resolves to.

        @see: U{http://en.wikipedia.org/wiki/SOCKS#SOCKS_4a_protocol}
        """
        # send the domain name "localhost" to be resolved
        clientRequest = (
            struct.pack("!BBH", 4, 2, 34)
            + socket.inet_aton("0.0.0.1")
            + b"fooBAZ\0"
            + b"localhost\0"
        )

        # Deliver the bytes one by one to exercise the protocol's buffering
        # logic. FakeResolverReactor's resolve method is invoked to "resolve"
        # the hostname.
        for byte in iterbytes(clientRequest):
            self.sock.dataReceived(byte)

        sent = self.sock.transport.value()
        self.sock.transport.clear()

        # Verify that the server responded with the address which will be
        # connected to.
        self.assertEqual(
            sent, struct.pack("!BBH", 0, 90, 1234) + socket.inet_aton("6.7.8.9")
        )
        self.assertFalse(self.sock.transport.stringTCPTransport_closing)
        self.assertIsNotNone(self.sock.driver_listen)

        # connect
        incoming = self.sock.driver_listen.buildProtocol(("127.0.0.1", 5345))
        self.assertIsNotNone(incoming)
        incoming.transport = StringTCPTransport()
        incoming.connectionMade()

        # now we should have the second reply packet
        sent = self.sock.transport.value()
        self.sock.transport.clear()
        self.assertEqual(
            sent, struct.pack("!BBH", 0, 90, 0) + socket.inet_aton("0.0.0.0")
        )
        self.assertIsNot(self.sock.transport.stringTCPTransport_closing, None)

        # Deliver some data from the output connection and verify it is
        # passed along to the incoming side.
        self.sock.dataReceived(b"hi there")
        self.assertEqual(incoming.transport.value(), b"hi there")

        # the other way around
        incoming.dataReceived(b"hi there")
        self.assertEqual(self.sock.transport.value(), b"hi there")

        self.sock.connectionLost("fake reason")

    def test_socks4aFailedResolution(self):
        """
        Failed hostname resolution on a SOCKSv4a packet results in a 91 error
        response and the connection getting closed.
        """
        # send the domain name "failinghost" to be resolved
        clientRequest = (
            struct.pack("!BBH", 4, 2, 34)
            + socket.inet_aton("0.0.0.1")
            + b"fooBAZ\0"
            + b"failinghost\0"
        )

        # Deliver the bytes one by one to exercise the protocol's buffering
        # logic. FakeResolverReactor's resolve method is invoked to "resolve"
        # the hostname.
        for byte in iterbytes(clientRequest):
            self.sock.dataReceived(byte)

        # Verify that the server responds with a 91 error.
        sent = self.sock.transport.value()
        self.assertEqual(
            sent, struct.pack("!BBH", 0, 91, 0) + socket.inet_aton("0.0.0.0")
        )

        # A failed resolution causes the transport to drop the connection.
        self.assertTrue(self.sock.transport.stringTCPTransport_closing)
        self.assertIsNone(self.sock.driver_outgoing)

    def test_accessDenied(self):
        self.sock.authorize = lambda code, server, port, user: 0
        self.sock.dataReceived(
            struct.pack("!BBH", 4, 2, 4242)
            + socket.inet_aton("10.2.3.4")
            + b"fooBAR"
            + b"\0"
        )
        self.assertEqual(
            self.sock.transport.value(),
            struct.pack("!BBH", 0, 91, 0) + socket.inet_aton("0.0.0.0"),
        )
        self.assertTrue(self.sock.transport.stringTCPTransport_closing)
        self.assertIsNone(self.sock.driver_listen)

    def test_eofRemote(self):
        self.sock.dataReceived(
            struct.pack("!BBH", 4, 2, 34)
            + socket.inet_aton("1.2.3.4")
            + b"fooBAR"
            + b"\0"
        )
        sent = self.sock.transport.value()
        self.sock.transport.clear()

        # connect
        incoming = self.sock.driver_listen.buildProtocol(("1.2.3.4", 5345))
        self.assertIsNotNone(incoming)
        incoming.transport = StringTCPTransport()
        incoming.connectionMade()

        # now we should have the second reply packet
        sent = self.sock.transport.value()
        self.sock.transport.clear()
        self.assertEqual(
            sent, struct.pack("!BBH", 0, 90, 0) + socket.inet_aton("0.0.0.0")
        )
        self.assertFalse(self.sock.transport.stringTCPTransport_closing)

        # pass some data through
        self.sock.dataReceived(b"hello, world")
        self.assertEqual(incoming.transport.value(), b"hello, world")

        # now close it from the server side
        incoming.transport.loseConnection()
        incoming.connectionLost("fake reason")

    def test_eofLocal(self):
        self.sock.dataReceived(
            struct.pack("!BBH", 4, 2, 34)
            + socket.inet_aton("1.2.3.4")
            + b"fooBAR"
            + b"\0"
        )
        sent = self.sock.transport.value()
        self.sock.transport.clear()

        # connect
        incoming = self.sock.driver_listen.buildProtocol(("1.2.3.4", 5345))
        self.assertIsNotNone(incoming)
        incoming.transport = StringTCPTransport()
        incoming.connectionMade()

        # now we should have the second reply packet
        sent = self.sock.transport.value()
        self.sock.transport.clear()
        self.assertEqual(
            sent, struct.pack("!BBH", 0, 90, 0) + socket.inet_aton("0.0.0.0")
        )
        self.assertFalse(self.sock.transport.stringTCPTransport_closing)

        # pass some data through
        self.sock.dataReceived(b"hello, world")
        self.assertEqual(incoming.transport.value(), b"hello, world")

        # now close it from the client side
        self.sock.connectionLost("fake reason")

    def test_badSource(self):
        self.sock.dataReceived(
            struct.pack("!BBH", 4, 2, 34)
            + socket.inet_aton("1.2.3.4")
            + b"fooBAR"
            + b"\0"
        )
        sent = self.sock.transport.value()
        self.sock.transport.clear()

        # connect from WRONG address
        incoming = self.sock.driver_listen.buildProtocol(("1.6.6.6", 666))
        self.assertIsNone(incoming)

        # Now we should have the second reply packet and it should
        # be a failure. The connection should be closing.
        sent = self.sock.transport.value()
        self.sock.transport.clear()
        self.assertEqual(
            sent, struct.pack("!BBH", 0, 91, 0) + socket.inet_aton("0.0.0.0")
        )
        self.assertTrue(self.sock.transport.stringTCPTransport_closing)
