# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for twisted.protocols package.
"""

from twisted.internet import address, defer, protocol, reactor
from twisted.protocols import portforward, wire
from twisted.python.compat import iterbytes
from twisted.test import proto_helpers
from twisted.trial import unittest


class WireTests(unittest.TestCase):
    """
    Test wire protocols.
    """

    def test_echo(self):
        """
        Test wire.Echo protocol: send some data and check it send it back.
        """
        t = proto_helpers.StringTransport()
        a = wire.Echo()
        a.makeConnection(t)
        a.dataReceived(b"hello")
        a.dataReceived(b"world")
        a.dataReceived(b"how")
        a.dataReceived(b"are")
        a.dataReceived(b"you")
        self.assertEqual(t.value(), b"helloworldhowareyou")

    def test_who(self):
        """
        Test wire.Who protocol.
        """
        t = proto_helpers.StringTransport()
        a = wire.Who()
        a.makeConnection(t)
        self.assertEqual(t.value(), b"root\r\n")

    def test_QOTD(self):
        """
        Test wire.QOTD protocol.
        """
        t = proto_helpers.StringTransport()
        a = wire.QOTD()
        a.makeConnection(t)
        self.assertEqual(t.value(), b"An apple a day keeps the doctor away.\r\n")

    def test_discard(self):
        """
        Test wire.Discard protocol.
        """
        t = proto_helpers.StringTransport()
        a = wire.Discard()
        a.makeConnection(t)
        a.dataReceived(b"hello")
        a.dataReceived(b"world")
        a.dataReceived(b"how")
        a.dataReceived(b"are")
        a.dataReceived(b"you")
        self.assertEqual(t.value(), b"")


class TestableProxyClientFactory(portforward.ProxyClientFactory):
    """
    Test proxy client factory that keeps the last created protocol instance.

    @ivar protoInstance: the last instance of the protocol.
    @type protoInstance: L{portforward.ProxyClient}
    """

    def buildProtocol(self, addr):
        """
        Create the protocol instance and keeps track of it.
        """
        proto = portforward.ProxyClientFactory.buildProtocol(self, addr)
        self.protoInstance = proto
        return proto


class TestableProxyFactory(portforward.ProxyFactory):
    """
    Test proxy factory that keeps the last created protocol instance.

    @ivar protoInstance: the last instance of the protocol.
    @type protoInstance: L{portforward.ProxyServer}

    @ivar clientFactoryInstance: client factory used by C{protoInstance} to
        create forward connections.
    @type clientFactoryInstance: L{TestableProxyClientFactory}
    """

    def buildProtocol(self, addr):
        """
        Create the protocol instance, keeps track of it, and makes it use
        C{clientFactoryInstance} as client factory.
        """
        proto = portforward.ProxyFactory.buildProtocol(self, addr)
        self.clientFactoryInstance = TestableProxyClientFactory()
        # Force the use of this specific instance
        proto.clientProtocolFactory = lambda: self.clientFactoryInstance
        self.protoInstance = proto
        return proto


class PortforwardingTests(unittest.TestCase):
    """
    Test port forwarding.
    """

    def setUp(self):
        self.serverProtocol = wire.Echo()
        self.clientProtocol = protocol.Protocol()
        self.openPorts = []

    def tearDown(self):
        try:
            self.proxyServerFactory.protoInstance.transport.loseConnection()
        except AttributeError:
            pass
        try:
            pi = self.proxyServerFactory.clientFactoryInstance.protoInstance
            pi.transport.loseConnection()
        except AttributeError:
            pass
        try:
            self.clientProtocol.transport.loseConnection()
        except AttributeError:
            pass
        try:
            self.serverProtocol.transport.loseConnection()
        except AttributeError:
            pass
        return defer.gatherResults(
            [defer.maybeDeferred(p.stopListening) for p in self.openPorts]
        )

    def test_portforward(self):
        """
        Test port forwarding through Echo protocol.
        """
        realServerFactory = protocol.ServerFactory()
        realServerFactory.protocol = lambda: self.serverProtocol
        realServerPort = reactor.listenTCP(0, realServerFactory, interface="127.0.0.1")
        self.openPorts.append(realServerPort)
        self.proxyServerFactory = TestableProxyFactory(
            "127.0.0.1", realServerPort.getHost().port
        )
        proxyServerPort = reactor.listenTCP(
            0, self.proxyServerFactory, interface="127.0.0.1"
        )
        self.openPorts.append(proxyServerPort)

        nBytes = 1000
        received = []
        d = defer.Deferred()

        def testDataReceived(data):
            received.extend(iterbytes(data))
            if len(received) >= nBytes:
                self.assertEqual(b"".join(received), b"x" * nBytes)
                d.callback(None)

        self.clientProtocol.dataReceived = testDataReceived

        def testConnectionMade():
            self.clientProtocol.transport.write(b"x" * nBytes)

        self.clientProtocol.connectionMade = testConnectionMade

        clientFactory = protocol.ClientFactory()
        clientFactory.protocol = lambda: self.clientProtocol

        reactor.connectTCP("127.0.0.1", proxyServerPort.getHost().port, clientFactory)

        return d

    def test_registerProducers(self):
        """
        The proxy client registers itself as a producer of the proxy server and
        vice versa.
        """
        # create a ProxyServer instance
        addr = address.IPv4Address("TCP", "127.0.0.1", 0)
        server = portforward.ProxyFactory("127.0.0.1", 0).buildProtocol(addr)

        # set the reactor for this test
        reactor = proto_helpers.MemoryReactor()
        server.reactor = reactor

        # make the connection
        serverTransport = proto_helpers.StringTransport()
        server.makeConnection(serverTransport)

        # check that the ProxyClientFactory is connecting to the backend
        self.assertEqual(len(reactor.tcpClients), 1)
        # get the factory instance and check it's the one we expect
        host, port, clientFactory, timeout, _ = reactor.tcpClients[0]
        self.assertIsInstance(clientFactory, portforward.ProxyClientFactory)

        # Connect it
        client = clientFactory.buildProtocol(addr)
        clientTransport = proto_helpers.StringTransport()
        client.makeConnection(clientTransport)

        # check that the producers are registered
        self.assertIs(clientTransport.producer, serverTransport)
        self.assertIs(serverTransport.producer, clientTransport)
        # check the streaming attribute in both transports
        self.assertTrue(clientTransport.streaming)
        self.assertTrue(serverTransport.streaming)


class StringTransportTests(unittest.TestCase):
    """
    Test L{proto_helpers.StringTransport} helper behaviour.
    """

    def test_noUnicode(self):
        """
        Test that L{proto_helpers.StringTransport} doesn't accept unicode data.
        """
        s = proto_helpers.StringTransport()
        self.assertRaises(TypeError, s.write, "foo")
