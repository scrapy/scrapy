# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet.protocol}.
"""

from __future__ import division, absolute_import

from zope.interface.verify import verifyObject
from zope.interface import implementer

from twisted.python.failure import Failure
from twisted.internet.interfaces import (
    IProtocol, ILoggingContext, IProtocolFactory, IConsumer)
from twisted.internet.defer import CancelledError
from twisted.internet.protocol import (
    Protocol, ClientCreator, Factory, ProtocolToConsumerAdapter,
    ConsumerToProtocolAdapter)
from twisted.trial.unittest import TestCase
from twisted.test.proto_helpers import MemoryReactorClock, StringTransport
from twisted.logger import LogLevel, globalLogPublisher



class ClientCreatorTests(TestCase):
    """
    Tests for L{twisted.internet.protocol.ClientCreator}.
    """
    def _basicConnectTest(self, check):
        """
        Helper for implementing a test to verify that one of the I{connect}
        methods of L{ClientCreator} passes the right arguments to the right
        reactor method.

        @param check: A function which will be invoked with a reactor and a
            L{ClientCreator} instance and which should call one of the
            L{ClientCreator}'s I{connect} methods and assert that all of its
            arguments except for the factory are passed on as expected to the
            reactor.  The factory should be returned.
        """
        class SomeProtocol(Protocol):
            pass

        reactor = MemoryReactorClock()
        cc = ClientCreator(reactor, SomeProtocol)
        factory = check(reactor, cc)
        protocol = factory.buildProtocol(None)
        self.assertIsInstance(protocol, SomeProtocol)


    def test_connectTCP(self):
        """
        L{ClientCreator.connectTCP} calls C{reactor.connectTCP} with the host
        and port information passed to it, and with a factory which will
        construct the protocol passed to L{ClientCreator.__init__}.
        """
        def check(reactor, cc):
            cc.connectTCP('example.com', 1234, 4321, ('1.2.3.4', 9876))
            host, port, factory, timeout, bindAddress = reactor.tcpClients.pop()
            self.assertEqual(host, 'example.com')
            self.assertEqual(port, 1234)
            self.assertEqual(timeout, 4321)
            self.assertEqual(bindAddress, ('1.2.3.4', 9876))
            return factory
        self._basicConnectTest(check)


    def test_connectUNIX(self):
        """
        L{ClientCreator.connectUNIX} calls C{reactor.connectUNIX} with the
        filename passed to it, and with a factory which will construct the
        protocol passed to L{ClientCreator.__init__}.
        """
        def check(reactor, cc):
            cc.connectUNIX('/foo/bar', 123, True)
            address, factory, timeout, checkPID = reactor.unixClients.pop()
            self.assertEqual(address, '/foo/bar')
            self.assertEqual(timeout, 123)
            self.assertTrue(checkPID)
            return factory
        self._basicConnectTest(check)


    def test_connectSSL(self):
        """
        L{ClientCreator.connectSSL} calls C{reactor.connectSSL} with the host,
        port, and context factory passed to it, and with a factory which will
        construct the protocol passed to L{ClientCreator.__init__}.
        """
        def check(reactor, cc):
            expectedContextFactory = object()
            cc.connectSSL('example.com', 1234, expectedContextFactory, 4321, ('4.3.2.1', 5678))
            host, port, factory, contextFactory, timeout, bindAddress = reactor.sslClients.pop()
            self.assertEqual(host, 'example.com')
            self.assertEqual(port, 1234)
            self.assertIs(contextFactory, expectedContextFactory)
            self.assertEqual(timeout, 4321)
            self.assertEqual(bindAddress, ('4.3.2.1', 5678))
            return factory
        self._basicConnectTest(check)


    def _cancelConnectTest(self, connect):
        """
        Helper for implementing a test to verify that cancellation of the
        L{Deferred} returned by one of L{ClientCreator}'s I{connect} methods is
        implemented to cancel the underlying connector.

        @param connect: A function which will be invoked with a L{ClientCreator}
            instance as an argument and which should call one its I{connect}
            methods and return the result.

        @return: A L{Deferred} which fires when the test is complete or fails if
            there is a problem.
        """
        reactor = MemoryReactorClock()
        cc = ClientCreator(reactor, Protocol)
        d = connect(cc)
        connector = reactor.connectors.pop()
        self.assertFalse(connector._disconnected)
        d.cancel()
        self.assertTrue(connector._disconnected)
        return self.assertFailure(d, CancelledError)


    def test_cancelConnectTCP(self):
        """
        The L{Deferred} returned by L{ClientCreator.connectTCP} can be cancelled
        to abort the connection attempt before it completes.
        """
        def connect(cc):
            return cc.connectTCP('example.com', 1234)
        return self._cancelConnectTest(connect)


    def test_cancelConnectUNIX(self):
        """
        The L{Deferred} returned by L{ClientCreator.connectTCP} can be cancelled
        to abort the connection attempt before it completes.
        """
        def connect(cc):
            return cc.connectUNIX('/foo/bar')
        return self._cancelConnectTest(connect)


    def test_cancelConnectSSL(self):
        """
        The L{Deferred} returned by L{ClientCreator.connectTCP} can be cancelled
        to abort the connection attempt before it completes.
        """
        def connect(cc):
            return cc.connectSSL('example.com', 1234, object())
        return self._cancelConnectTest(connect)


    def _cancelConnectTimeoutTest(self, connect):
        """
        Like L{_cancelConnectTest}, but for the case where the L{Deferred} is
        cancelled after the connection is set up but before it is fired with the
        resulting protocol instance.
        """
        reactor = MemoryReactorClock()
        cc = ClientCreator(reactor, Protocol)
        d = connect(reactor, cc)
        connector = reactor.connectors.pop()
        # Sanity check - there is an outstanding delayed call to fire the
        # Deferred.
        self.assertEqual(len(reactor.getDelayedCalls()), 1)

        # Cancel the Deferred, disconnecting the transport just set up and
        # cancelling the delayed call.
        d.cancel()

        self.assertEqual(reactor.getDelayedCalls(), [])

        # A real connector implementation is responsible for disconnecting the
        # transport as well.  For our purposes, just check that someone told the
        # connector to disconnect.
        self.assertTrue(connector._disconnected)

        return self.assertFailure(d, CancelledError)


    def test_cancelConnectTCPTimeout(self):
        """
        L{ClientCreator.connectTCP} inserts a very short delayed call between
        the time the connection is established and the time the L{Deferred}
        returned from one of its connect methods actually fires.  If the
        L{Deferred} is cancelled in this interval, the established connection is
        closed, the timeout is cancelled, and the L{Deferred} fails with
        L{CancelledError}.
        """
        def connect(reactor, cc):
            d = cc.connectTCP('example.com', 1234)
            host, port, factory, timeout, bindAddress = reactor.tcpClients.pop()
            protocol = factory.buildProtocol(None)
            transport = StringTransport()
            protocol.makeConnection(transport)
            return d
        return self._cancelConnectTimeoutTest(connect)


    def test_cancelConnectUNIXTimeout(self):
        """
        L{ClientCreator.connectUNIX} inserts a very short delayed call between
        the time the connection is established and the time the L{Deferred}
        returned from one of its connect methods actually fires.  If the
        L{Deferred} is cancelled in this interval, the established connection is
        closed, the timeout is cancelled, and the L{Deferred} fails with
        L{CancelledError}.
        """
        def connect(reactor, cc):
            d = cc.connectUNIX('/foo/bar')
            address, factory, timeout, bindAddress = reactor.unixClients.pop()
            protocol = factory.buildProtocol(None)
            transport = StringTransport()
            protocol.makeConnection(transport)
            return d
        return self._cancelConnectTimeoutTest(connect)


    def test_cancelConnectSSLTimeout(self):
        """
        L{ClientCreator.connectSSL} inserts a very short delayed call between
        the time the connection is established and the time the L{Deferred}
        returned from one of its connect methods actually fires.  If the
        L{Deferred} is cancelled in this interval, the established connection is
        closed, the timeout is cancelled, and the L{Deferred} fails with
        L{CancelledError}.
        """
        def connect(reactor, cc):
            d = cc.connectSSL('example.com', 1234, object())
            host, port, factory, contextFactory, timeout, bindADdress = reactor.sslClients.pop()
            protocol = factory.buildProtocol(None)
            transport = StringTransport()
            protocol.makeConnection(transport)
            return d
        return self._cancelConnectTimeoutTest(connect)


    def _cancelConnectFailedTimeoutTest(self, connect):
        """
        Like L{_cancelConnectTest}, but for the case where the L{Deferred} is
        cancelled after the connection attempt has failed but before it is fired
        with the resulting failure.
        """
        reactor = MemoryReactorClock()
        cc = ClientCreator(reactor, Protocol)
        d, factory = connect(reactor, cc)
        connector = reactor.connectors.pop()
        factory.clientConnectionFailed(
            connector, Failure(Exception("Simulated failure")))

        # Sanity check - there is an outstanding delayed call to fire the
        # Deferred.
        self.assertEqual(len(reactor.getDelayedCalls()), 1)

        # Cancel the Deferred, cancelling the delayed call.
        d.cancel()

        self.assertEqual(reactor.getDelayedCalls(), [])

        return self.assertFailure(d, CancelledError)


    def test_cancelConnectTCPFailedTimeout(self):
        """
        Similar to L{test_cancelConnectTCPTimeout}, but for the case where the
        connection attempt fails.
        """
        def connect(reactor, cc):
            d = cc.connectTCP('example.com', 1234)
            host, port, factory, timeout, bindAddress = reactor.tcpClients.pop()
            return d, factory
        return self._cancelConnectFailedTimeoutTest(connect)


    def test_cancelConnectUNIXFailedTimeout(self):
        """
        Similar to L{test_cancelConnectUNIXTimeout}, but for the case where the
        connection attempt fails.
        """
        def connect(reactor, cc):
            d = cc.connectUNIX('/foo/bar')
            address, factory, timeout, bindAddress = reactor.unixClients.pop()
            return d, factory
        return self._cancelConnectFailedTimeoutTest(connect)


    def test_cancelConnectSSLFailedTimeout(self):
        """
        Similar to L{test_cancelConnectSSLTimeout}, but for the case where the
        connection attempt fails.
        """
        def connect(reactor, cc):
            d = cc.connectSSL('example.com', 1234, object())
            host, port, factory, contextFactory, timeout, bindADdress = reactor.sslClients.pop()
            return d, factory
        return self._cancelConnectFailedTimeoutTest(connect)



class ProtocolTests(TestCase):
    """
    Tests for L{twisted.internet.protocol.Protocol}.
    """
    def test_interfaces(self):
        """
        L{Protocol} instances provide L{IProtocol} and L{ILoggingContext}.
        """
        proto = Protocol()
        self.assertTrue(verifyObject(IProtocol, proto))
        self.assertTrue(verifyObject(ILoggingContext, proto))


    def test_logPrefix(self):
        """
        L{Protocol.logPrefix} returns the protocol class's name.
        """
        class SomeThing(Protocol):
            pass
        self.assertEqual("SomeThing", SomeThing().logPrefix())


    def test_makeConnection(self):
        """
        L{Protocol.makeConnection} sets the given transport on itself, and
        then calls C{connectionMade}.
        """
        result = []
        class SomeProtocol(Protocol):
            def connectionMade(self):
                result.append(self.transport)

        transport = object()
        protocol = SomeProtocol()
        protocol.makeConnection(transport)
        self.assertEqual(result, [transport])



class FactoryTests(TestCase):
    """
    Tests for L{protocol.Factory}.
    """

    def test_interfaces(self):
        """
        L{Factory} instances provide both L{IProtocolFactory} and
        L{ILoggingContext}.
        """
        factory = Factory()
        self.assertTrue(verifyObject(IProtocolFactory, factory))
        self.assertTrue(verifyObject(ILoggingContext, factory))


    def test_logPrefix(self):
        """
        L{Factory.logPrefix} returns the name of the factory class.
        """
        class SomeKindOfFactory(Factory):
            pass

        self.assertEqual("SomeKindOfFactory", SomeKindOfFactory().logPrefix())


    def test_defaultBuildProtocol(self):
        """
        L{Factory.buildProtocol} by default constructs a protocol by calling
        its C{protocol} attribute, and attaches the factory to the result.
        """
        class SomeProtocol(Protocol):
            pass
        f = Factory()
        f.protocol = SomeProtocol
        protocol = f.buildProtocol(None)
        self.assertIsInstance(protocol, SomeProtocol)
        self.assertIs(protocol.factory, f)


    def test_forProtocol(self):
        """
        L{Factory.forProtocol} constructs a Factory, passing along any
        additional arguments, and sets its C{protocol} attribute to the given
        Protocol subclass.
        """
        class ArgTakingFactory(Factory):
            def __init__(self, *args, **kwargs):
                self.args, self.kwargs = args, kwargs
        factory = ArgTakingFactory.forProtocol(Protocol, 1, 2, foo=12)
        self.assertEqual(factory.protocol, Protocol)
        self.assertEqual(factory.args, (1, 2))
        self.assertEqual(factory.kwargs, {"foo": 12})


    def test_doStartLoggingStatement(self):
        """
        L{Factory.doStart} logs that it is starting a factory, followed by
        the L{repr} of the L{Factory} instance that is being started.
        """
        events = []
        globalLogPublisher.addObserver(events.append)
        self.addCleanup(
            lambda: globalLogPublisher.removeObserver(events.append))

        f = Factory()
        f.doStart()

        self.assertIs(events[0]['factory'], f)
        self.assertEqual(events[0]['log_level'], LogLevel.info)
        self.assertEqual(events[0]['log_format'],
                         'Starting factory {factory!r}')


    def test_doStopLoggingStatement(self):
        """
        L{Factory.doStop} logs that it is stopping a factory, followed by
        the L{repr} of the L{Factory} instance that is being stopped.
        """
        events = []
        globalLogPublisher.addObserver(events.append)
        self.addCleanup(
            lambda: globalLogPublisher.removeObserver(events.append))

        class MyFactory(Factory):
            numPorts = 1

        f = MyFactory()
        f.doStop()

        self.assertIs(events[0]['factory'], f)
        self.assertEqual(events[0]['log_level'], LogLevel.info)
        self.assertEqual(events[0]['log_format'],
                         'Stopping factory {factory!r}')



class AdapterTests(TestCase):
    """
    Tests for L{ProtocolToConsumerAdapter} and L{ConsumerToProtocolAdapter}.
    """
    def test_protocolToConsumer(self):
        """
        L{IProtocol} providers can be adapted to L{IConsumer} providers using
        L{ProtocolToConsumerAdapter}.
        """
        result = []
        p = Protocol()
        p.dataReceived = result.append
        consumer = IConsumer(p)
        consumer.write(b"hello")
        self.assertEqual(result, [b"hello"])
        self.assertIsInstance(consumer, ProtocolToConsumerAdapter)


    def test_consumerToProtocol(self):
        """
        L{IConsumer} providers can be adapted to L{IProtocol} providers using
        L{ProtocolToConsumerAdapter}.
        """
        result = []
        @implementer(IConsumer)
        class Consumer(object):
            def write(self, d):
                result.append(d)

        c = Consumer()
        protocol = IProtocol(c)
        protocol.dataReceived(b"hello")
        self.assertEqual(result, [b"hello"])
        self.assertIsInstance(protocol, ConsumerToProtocolAdapter)
