# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.test.proto_helpers}.
"""

from zope.interface.verify import verifyObject

from twisted.internet.interfaces import (ITransport, IPushProducer, IConsumer,
    IReactorTCP, IReactorSSL, IReactorUNIX, IAddress, IListeningPort,
    IConnector)
from twisted.internet.address import IPv4Address
from twisted.trial.unittest import TestCase
from twisted.test.proto_helpers import (StringTransport, MemoryReactor,
    RaisingMemoryReactor)
from twisted.internet.protocol import ClientFactory, Factory


class StringTransportTests(TestCase):
    """
    Tests for L{twisted.test.proto_helpers.StringTransport}.
    """
    def setUp(self):
        self.transport = StringTransport()


    def test_interfaces(self):
        """
        L{StringTransport} instances provide L{ITransport}, L{IPushProducer},
        and L{IConsumer}.
        """
        self.assertTrue(verifyObject(ITransport, self.transport))
        self.assertTrue(verifyObject(IPushProducer, self.transport))
        self.assertTrue(verifyObject(IConsumer, self.transport))


    def test_registerProducer(self):
        """
        L{StringTransport.registerProducer} records the arguments supplied to
        it as instance attributes.
        """
        producer = object()
        streaming = object()
        self.transport.registerProducer(producer, streaming)
        self.assertIs(self.transport.producer, producer)
        self.assertIs(self.transport.streaming, streaming)


    def test_disallowedRegisterProducer(self):
        """
        L{StringTransport.registerProducer} raises L{RuntimeError} if a
        producer is already registered.
        """
        producer = object()
        self.transport.registerProducer(producer, True)
        self.assertRaises(
            RuntimeError, self.transport.registerProducer, object(), False)
        self.assertIs(self.transport.producer, producer)
        self.assertTrue(self.transport.streaming)


    def test_unregisterProducer(self):
        """
        L{StringTransport.unregisterProducer} causes the transport to forget
        about the registered producer and makes it possible to register a new
        one.
        """
        oldProducer = object()
        newProducer = object()
        self.transport.registerProducer(oldProducer, False)
        self.transport.unregisterProducer()
        self.assertIsNone(self.transport.producer)
        self.transport.registerProducer(newProducer, True)
        self.assertIs(self.transport.producer, newProducer)
        self.assertTrue(self.transport.streaming)


    def test_invalidUnregisterProducer(self):
        """
        L{StringTransport.unregisterProducer} raises L{RuntimeError} if called
        when no producer is registered.
        """
        self.assertRaises(RuntimeError, self.transport.unregisterProducer)


    def test_initialProducerState(self):
        """
        L{StringTransport.producerState} is initially C{'producing'}.
        """
        self.assertEqual(self.transport.producerState, 'producing')


    def test_pauseProducing(self):
        """
        L{StringTransport.pauseProducing} changes the C{producerState} of the
        transport to C{'paused'}.
        """
        self.transport.pauseProducing()
        self.assertEqual(self.transport.producerState, 'paused')


    def test_resumeProducing(self):
        """
        L{StringTransport.resumeProducing} changes the C{producerState} of the
        transport to C{'producing'}.
        """
        self.transport.pauseProducing()
        self.transport.resumeProducing()
        self.assertEqual(self.transport.producerState, 'producing')


    def test_stopProducing(self):
        """
        L{StringTransport.stopProducing} changes the C{'producerState'} of the
        transport to C{'stopped'}.
        """
        self.transport.stopProducing()
        self.assertEqual(self.transport.producerState, 'stopped')


    def test_stoppedTransportCannotPause(self):
        """
        L{StringTransport.pauseProducing} raises L{RuntimeError} if the
        transport has been stopped.
        """
        self.transport.stopProducing()
        self.assertRaises(RuntimeError, self.transport.pauseProducing)


    def test_stoppedTransportCannotResume(self):
        """
        L{StringTransport.resumeProducing} raises L{RuntimeError} if the
        transport has been stopped.
        """
        self.transport.stopProducing()
        self.assertRaises(RuntimeError, self.transport.resumeProducing)


    def test_disconnectingTransportCannotPause(self):
        """
        L{StringTransport.pauseProducing} raises L{RuntimeError} if the
        transport is being disconnected.
        """
        self.transport.loseConnection()
        self.assertRaises(RuntimeError, self.transport.pauseProducing)


    def test_disconnectingTransportCannotResume(self):
        """
        L{StringTransport.resumeProducing} raises L{RuntimeError} if the
        transport is being disconnected.
        """
        self.transport.loseConnection()
        self.assertRaises(RuntimeError, self.transport.resumeProducing)


    def test_loseConnectionSetsDisconnecting(self):
        """
        L{StringTransport.loseConnection} toggles the C{disconnecting} instance
        variable to C{True}.
        """
        self.assertFalse(self.transport.disconnecting)
        self.transport.loseConnection()
        self.assertTrue(self.transport.disconnecting)


    def test_specifiedHostAddress(self):
        """
        If a host address is passed to L{StringTransport.__init__}, that
        value is returned from L{StringTransport.getHost}.
        """
        address = object()
        self.assertIs(StringTransport(address).getHost(), address)


    def test_specifiedPeerAddress(self):
        """
        If a peer address is passed to L{StringTransport.__init__}, that
        value is returned from L{StringTransport.getPeer}.
        """        
        address = object()
        self.assertIs(
            StringTransport(peerAddress=address).getPeer(), address)


    def test_defaultHostAddress(self):
        """
        If no host address is passed to L{StringTransport.__init__}, an
        L{IPv4Address} is returned from L{StringTransport.getHost}.
        """
        address = StringTransport().getHost()
        self.assertIsInstance(address, IPv4Address)


    def test_defaultPeerAddress(self):
        """
        If no peer address is passed to L{StringTransport.__init__}, an
        L{IPv4Address} is returned from L{StringTransport.getPeer}.
        """
        address = StringTransport().getPeer()
        self.assertIsInstance(address, IPv4Address)



class ReactorTests(TestCase):
    """
    Tests for L{MemoryReactor} and L{RaisingMemoryReactor}.
    """

    def test_memoryReactorProvides(self):
        """
        L{MemoryReactor} provides all of the attributes described by the
        interfaces it advertises.
        """
        memoryReactor = MemoryReactor()
        verifyObject(IReactorTCP, memoryReactor)
        verifyObject(IReactorSSL, memoryReactor)
        verifyObject(IReactorUNIX, memoryReactor)


    def test_raisingReactorProvides(self):
        """
        L{RaisingMemoryReactor} provides all of the attributes described by the
        interfaces it advertises.
        """
        raisingReactor = RaisingMemoryReactor()
        verifyObject(IReactorTCP, raisingReactor)
        verifyObject(IReactorSSL, raisingReactor)
        verifyObject(IReactorUNIX, raisingReactor)


    def test_connectDestination(self):
        """
        L{MemoryReactor.connectTCP}, L{MemoryReactor.connectSSL}, and
        L{MemoryReactor.connectUNIX} will return an L{IConnector} whose
        C{getDestination} method returns an L{IAddress} with attributes which
        reflect the values passed.
        """
        memoryReactor = MemoryReactor()
        for connector in [memoryReactor.connectTCP(
                              "test.example.com", 8321, ClientFactory()),
                          memoryReactor.connectSSL(
                              "test.example.com", 8321, ClientFactory(),
                              None)]:
            verifyObject(IConnector, connector)
            address = connector.getDestination()
            verifyObject(IAddress, address)
            self.assertEqual(address.host, "test.example.com")
            self.assertEqual(address.port, 8321)
        connector = memoryReactor.connectUNIX(b"/fake/path", ClientFactory())
        verifyObject(IConnector, connector)
        address = connector.getDestination()
        verifyObject(IAddress, address)
        self.assertEqual(address.name, b"/fake/path")


    def test_listenDefaultHost(self):
        """
        L{MemoryReactor.listenTCP}, L{MemoryReactor.listenSSL} and
        L{MemoryReactor.listenUNIX} will return an L{IListeningPort} whose
        C{getHost} method returns an L{IAddress}; C{listenTCP} and C{listenSSL}
        will have a default host of C{'0.0.0.0'}, and a port that reflects the
        value passed, and C{listenUNIX} will have a name that reflects the path
        passed.
        """
        memoryReactor = MemoryReactor()
        for port in [memoryReactor.listenTCP(8242, Factory()),
                     memoryReactor.listenSSL(8242, Factory(), None)]:
            verifyObject(IListeningPort, port)
            address = port.getHost()
            verifyObject(IAddress, address)
            self.assertEqual(address.host, '0.0.0.0')
            self.assertEqual(address.port, 8242)
        port = memoryReactor.listenUNIX(b"/path/to/socket", Factory())
        verifyObject(IListeningPort, port)
        address = port.getHost()
        verifyObject(IAddress, address)
        self.assertEqual(address.name, b"/path/to/socket")


    def test_readers(self):
        """
        Adding, removing, and listing readers works.
        """
        reader = object()
        reactor = MemoryReactor()

        reactor.addReader(reader)
        reactor.addReader(reader)

        self.assertEqual(reactor.getReaders(), [reader])

        reactor.removeReader(reader)

        self.assertEqual(reactor.getReaders(), [])


    def test_writers(self):
        """
        Adding, removing, and listing writers works.
        """
        writer = object()
        reactor = MemoryReactor()

        reactor.addWriter(writer)
        reactor.addWriter(writer)

        self.assertEqual(reactor.getWriters(), [writer])

        reactor.removeWriter(writer)

        self.assertEqual(reactor.getWriters(), [])
