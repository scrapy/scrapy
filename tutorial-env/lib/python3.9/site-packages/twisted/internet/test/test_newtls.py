# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet._newtls}.
"""


from twisted.internet import interfaces
from twisted.internet.test.connectionmixins import (
    ConnectableProtocol,
    runProtocolsWithReactor,
)
from twisted.internet.test.reactormixins import ReactorBuilder
from twisted.internet.test.test_tcp import TCPCreator
from twisted.internet.test.test_tls import (
    ContextGeneratingMixin,
    SSLCreator,
    StartTLSClientCreator,
    TLSMixin,
)
from twisted.trial import unittest

try:
    from twisted.internet import _newtls as __newtls
    from twisted.protocols import tls
except ImportError:
    _newtls = None
else:
    _newtls = __newtls
from zope.interface import implementer


class BypassTLSTests(unittest.TestCase):
    """
    Tests for the L{_newtls._BypassTLS} class.
    """

    if not _newtls:
        skip = "Couldn't import _newtls, perhaps pyOpenSSL is old or missing"

    def test_loseConnectionPassThrough(self):
        """
        C{_BypassTLS.loseConnection} calls C{loseConnection} on the base
        class, while preserving any default argument in the base class'
        C{loseConnection} implementation.
        """
        default = object()
        result = []

        class FakeTransport:
            def loseConnection(self, _connDone=default):
                result.append(_connDone)

        bypass = _newtls._BypassTLS(FakeTransport, FakeTransport())

        # The default from FakeTransport is used:
        bypass.loseConnection()
        self.assertEqual(result, [default])

        # And we can pass our own:
        notDefault = object()
        bypass.loseConnection(notDefault)
        self.assertEqual(result, [default, notDefault])


class FakeProducer:
    """
    A producer that does nothing.
    """

    def pauseProducing(self):
        pass

    def resumeProducing(self):
        pass

    def stopProducing(self):
        pass


@implementer(interfaces.IHandshakeListener)
class ProducerProtocol(ConnectableProtocol):
    """
    Register a producer, unregister it, and verify the producer hooks up to
    innards of C{TLSMemoryBIOProtocol}.
    """

    def __init__(self, producer, result):
        self.producer = producer
        self.result = result

    def handshakeCompleted(self):
        if not isinstance(self.transport.protocol, tls.TLSMemoryBIOProtocol):
            # Either the test or the code have a bug...
            raise RuntimeError("TLSMemoryBIOProtocol not hooked up.")

        self.transport.registerProducer(self.producer, True)
        # The producer was registered with the TLSMemoryBIOProtocol:
        self.result.append(self.transport.protocol._producer._producer)

        self.transport.unregisterProducer()
        # The producer was unregistered from the TLSMemoryBIOProtocol:
        self.result.append(self.transport.protocol._producer)
        self.transport.loseConnection()


class ProducerTestsMixin(ReactorBuilder, TLSMixin, ContextGeneratingMixin):
    """
    Test the new TLS code integrates C{TLSMemoryBIOProtocol} correctly.
    """

    if not _newtls:
        skip = "Could not import twisted.internet._newtls"

    def test_producerSSLFromStart(self):
        """
        C{registerProducer} and C{unregisterProducer} on TLS transports
        created as SSL from the get go are passed to the
        C{TLSMemoryBIOProtocol}, not the underlying transport directly.
        """
        result = []
        producer = FakeProducer()

        runProtocolsWithReactor(
            self,
            ConnectableProtocol(),
            ProducerProtocol(producer, result),
            SSLCreator(),
        )
        self.assertEqual(result, [producer, None])

    def test_producerAfterStartTLS(self):
        """
        C{registerProducer} and C{unregisterProducer} on TLS transports
        created by C{startTLS} are passed to the C{TLSMemoryBIOProtocol}, not
        the underlying transport directly.
        """
        result = []
        producer = FakeProducer()

        runProtocolsWithReactor(
            self,
            ConnectableProtocol(),
            ProducerProtocol(producer, result),
            StartTLSClientCreator(),
        )
        self.assertEqual(result, [producer, None])

    def startTLSAfterRegisterProducer(self, streaming):
        """
        When a producer is registered, and then startTLS is called,
        the producer is re-registered with the C{TLSMemoryBIOProtocol}.
        """
        clientContext = self.getClientContext()
        serverContext = self.getServerContext()
        result = []
        producer = FakeProducer()

        class RegisterTLSProtocol(ConnectableProtocol):
            def connectionMade(self):
                self.transport.registerProducer(producer, streaming)
                self.transport.startTLS(serverContext)
                # Store TLSMemoryBIOProtocol and underlying transport producer
                # status:
                if streaming:
                    # _ProducerMembrane -> producer:
                    result.append(self.transport.protocol._producer._producer)
                    result.append(self.transport.producer._producer)
                else:
                    # _ProducerMembrane -> _PullToPush -> producer:
                    result.append(self.transport.protocol._producer._producer._producer)
                    result.append(self.transport.producer._producer._producer)
                self.transport.unregisterProducer()
                self.transport.loseConnection()

        class StartTLSProtocol(ConnectableProtocol):
            def connectionMade(self):
                self.transport.startTLS(clientContext)

        runProtocolsWithReactor(
            self, RegisterTLSProtocol(), StartTLSProtocol(), TCPCreator()
        )
        self.assertEqual(result, [producer, producer])

    def test_startTLSAfterRegisterProducerStreaming(self):
        """
        When a streaming producer is registered, and then startTLS is called,
        the producer is re-registered with the C{TLSMemoryBIOProtocol}.
        """
        self.startTLSAfterRegisterProducer(True)

    def test_startTLSAfterRegisterProducerNonStreaming(self):
        """
        When a non-streaming producer is registered, and then startTLS is
        called, the producer is re-registered with the
        C{TLSMemoryBIOProtocol}.
        """
        self.startTLSAfterRegisterProducer(False)


globals().update(ProducerTestsMixin.makeTestCaseClasses())
