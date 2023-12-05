# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet.testing}.
"""

from zope.interface.verify import verifyObject

from twisted.internet.address import IPv4Address
from twisted.internet.interfaces import (
    IAddress,
    IConnector,
    IConsumer,
    IListeningPort,
    IPushProducer,
    IReactorSSL,
    IReactorTCP,
    IReactorUNIX,
    ITransport,
)
from twisted.internet.protocol import ClientFactory, Factory
from twisted.internet.testing import (
    MemoryReactor,
    NonStreamingProducer,
    RaisingMemoryReactor,
    StringTransport,
)
from twisted.python.reflect import namedAny
from twisted.trial.unittest import TestCase


class StringTransportTests(TestCase):
    """
    Tests for L{twisted.internet.testing.StringTransport}.
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
            RuntimeError, self.transport.registerProducer, object(), False
        )
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
        self.assertEqual(self.transport.producerState, "producing")

    def test_pauseProducing(self):
        """
        L{StringTransport.pauseProducing} changes the C{producerState} of the
        transport to C{'paused'}.
        """
        self.transport.pauseProducing()
        self.assertEqual(self.transport.producerState, "paused")

    def test_resumeProducing(self):
        """
        L{StringTransport.resumeProducing} changes the C{producerState} of the
        transport to C{'producing'}.
        """
        self.transport.pauseProducing()
        self.transport.resumeProducing()
        self.assertEqual(self.transport.producerState, "producing")

    def test_stopProducing(self):
        """
        L{StringTransport.stopProducing} changes the C{'producerState'} of the
        transport to C{'stopped'}.
        """
        self.transport.stopProducing()
        self.assertEqual(self.transport.producerState, "stopped")

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
        self.assertIs(StringTransport(peerAddress=address).getPeer(), address)

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
        for connector in [
            memoryReactor.connectTCP("test.example.com", 8321, ClientFactory()),
            memoryReactor.connectSSL("test.example.com", 8321, ClientFactory(), None),
        ]:
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
        for port in [
            memoryReactor.listenTCP(8242, Factory()),
            memoryReactor.listenSSL(8242, Factory(), None),
        ]:
            verifyObject(IListeningPort, port)
            address = port.getHost()
            verifyObject(IAddress, address)
            self.assertEqual(address.host, "0.0.0.0")
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


class TestConsumer:
    """
    A very basic test consumer for use with the NonStreamingProducerTests.
    """

    def __init__(self):
        self.writes = []
        self.producer = None
        self.producerStreaming = None

    def registerProducer(self, producer, streaming):
        """
        Registers a single producer with this consumer. Just keeps track of it.

        @param producer: The producer to register.
        @param streaming: Whether the producer is a streaming one or not.
        """
        self.producer = producer
        self.producerStreaming = streaming

    def unregisterProducer(self):
        """
        Forget the producer we had previously registered.
        """
        self.producer = None
        self.producerStreaming = None

    def write(self, data):
        """
        Some data was written to the consumer: stores it for later use.

        @param data: The data to write.
        """
        self.writes.append(data)


class NonStreamingProducerTests(TestCase):
    """
    Tests for the L{NonStreamingProducer} to validate behaviour.
    """

    def test_producesOnly10Times(self):
        """
        When the L{NonStreamingProducer} has resumeProducing called 10 times,
        it writes the counter each time and then fails.
        """
        consumer = TestConsumer()
        producer = NonStreamingProducer(consumer)
        consumer.registerProducer(producer, False)

        self.assertIs(consumer.producer, producer)
        self.assertIs(producer.consumer, consumer)
        self.assertFalse(consumer.producerStreaming)

        for _ in range(10):
            producer.resumeProducing()

        # We should have unregistered the producer and printed the 10 results.
        expectedWrites = [b"0", b"1", b"2", b"3", b"4", b"5", b"6", b"7", b"8", b"9"]
        self.assertIsNone(consumer.producer)
        self.assertIsNone(consumer.producerStreaming)
        self.assertIsNone(producer.consumer)
        self.assertEqual(consumer.writes, expectedWrites)

        # Another attempt to produce fails.
        self.assertRaises(RuntimeError, producer.resumeProducing)

    def test_cannotPauseProduction(self):
        """
        When the L{NonStreamingProducer} is paused, it raises a
        L{RuntimeError}.
        """
        consumer = TestConsumer()
        producer = NonStreamingProducer(consumer)
        consumer.registerProducer(producer, False)

        # Produce once, just to be safe.
        producer.resumeProducing()

        self.assertRaises(RuntimeError, producer.pauseProducing)


class DeprecationTests(TestCase):
    """
    Deprecations in L{twisted.test.proto_helpers}.
    """

    def helper(self, test, obj):
        new_path = f"twisted.internet.testing.{obj.__name__}"
        warnings = self.flushWarnings([test])
        self.assertEqual(DeprecationWarning, warnings[0]["category"])
        self.assertEqual(1, len(warnings))
        self.assertIn(new_path, warnings[0]["message"])
        self.assertIs(obj, namedAny(new_path))

    def test_accumulatingProtocol(self):
        from twisted.test.proto_helpers import AccumulatingProtocol

        self.helper(self.test_accumulatingProtocol, AccumulatingProtocol)

    def test_lineSendingProtocol(self):
        from twisted.test.proto_helpers import LineSendingProtocol

        self.helper(self.test_lineSendingProtocol, LineSendingProtocol)

    def test_fakeDatagramTransport(self):
        from twisted.test.proto_helpers import FakeDatagramTransport

        self.helper(self.test_fakeDatagramTransport, FakeDatagramTransport)

    def test_stringTransport(self):
        from twisted.test.proto_helpers import StringTransport

        self.helper(self.test_stringTransport, StringTransport)

    def test_stringTransportWithDisconnection(self):
        from twisted.test.proto_helpers import StringTransportWithDisconnection

        self.helper(
            self.test_stringTransportWithDisconnection, StringTransportWithDisconnection
        )

    def test_stringIOWithoutClosing(self):
        from twisted.test.proto_helpers import StringIOWithoutClosing

        self.helper(self.test_stringIOWithoutClosing, StringIOWithoutClosing)

    def test__fakeConnector(self):
        from twisted.test.proto_helpers import _FakeConnector

        self.helper(self.test__fakeConnector, _FakeConnector)

    def test__fakePort(self):
        from twisted.test.proto_helpers import _FakePort

        self.helper(self.test__fakePort, _FakePort)

    def test_memoryReactor(self):
        from twisted.test.proto_helpers import MemoryReactor

        self.helper(self.test_memoryReactor, MemoryReactor)

    def test_memoryReactorClock(self):
        from twisted.test.proto_helpers import MemoryReactorClock

        self.helper(self.test_memoryReactorClock, MemoryReactorClock)

    def test_raisingMemoryReactor(self):
        from twisted.test.proto_helpers import RaisingMemoryReactor

        self.helper(self.test_raisingMemoryReactor, RaisingMemoryReactor)

    def test_nonStreamingProducer(self):
        from twisted.test.proto_helpers import NonStreamingProducer

        self.helper(self.test_nonStreamingProducer, NonStreamingProducer)

    def test_waitUntilAllDisconnected(self):
        from twisted.test.proto_helpers import waitUntilAllDisconnected

        self.helper(self.test_waitUntilAllDisconnected, waitUntilAllDisconnected)

    def test_eventLoggingObserver(self):
        from twisted.test.proto_helpers import EventLoggingObserver

        self.helper(self.test_eventLoggingObserver, EventLoggingObserver)
