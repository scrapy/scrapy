# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.web.client.Agent} and related new client APIs.
"""

import zlib

from io import BytesIO

from zope.interface.verify import verifyObject

from twisted.trial.unittest import TestCase
from twisted.web import client, error, http_headers
from twisted.web._newclient import RequestNotSent, RequestTransmissionFailed
from twisted.web._newclient import ResponseNeverReceived, ResponseFailed
from twisted.web._newclient import PotentialDataLoss
from twisted.internet import defer, task
from twisted.python.failure import Failure
from twisted.python.compat import cookielib, intToBytes
from twisted.python.components import proxyForInterface
from twisted.test.proto_helpers import StringTransport, MemoryReactorClock
from twisted.internet.task import Clock
from twisted.internet.error import ConnectionRefusedError, ConnectionDone
from twisted.internet.error import ConnectionLost
from twisted.internet.protocol import Protocol, Factory
from twisted.internet.defer import Deferred, succeed, CancelledError
from twisted.internet.endpoints import TCP4ClientEndpoint, SSL4ClientEndpoint

from twisted.web.client import (FileBodyProducer, Request, HTTPConnectionPool,
                                ResponseDone, _HTTP11ClientFactory, URI)

from twisted.web.iweb import (
    UNKNOWN_LENGTH, IAgent, IBodyProducer, IResponse, IAgentEndpointFactory,
    )
from twisted.web.http_headers import Headers
from twisted.web._newclient import HTTP11ClientProtocol, Response

from twisted.internet.interfaces import IOpenSSLClientConnectionCreator
from zope.interface.declarations import implementer
from twisted.web.iweb import IPolicyForHTTPS
from twisted.python.deprecate import getDeprecationWarningString
from twisted.python.versions import Version
from twisted.web.client import BrowserLikePolicyForHTTPS
from twisted.web.error import SchemeNotSupported

try:
    from twisted.internet import ssl
    from twisted.protocols.tls import TLSMemoryBIOFactory, TLSMemoryBIOProtocol
except ImportError:
    ssl = None
else:
    from twisted.internet._sslverify import ClientTLSOptions, IOpenSSLTrustRoot



class StubHTTPProtocol(Protocol):
    """
    A protocol like L{HTTP11ClientProtocol} but which does not actually know
    HTTP/1.1 and only collects requests in a list.

    @ivar requests: A C{list} of two-tuples.  Each time a request is made, a
        tuple consisting of the request and the L{Deferred} returned from the
        request method is appended to this list.
    """
    def __init__(self):
        self.requests = []
        self.state = 'QUIESCENT'


    def request(self, request):
        """
        Capture the given request for later inspection.

        @return: A L{Deferred} which this code will never fire.
        """
        result = Deferred()
        self.requests.append((request, result))
        return result



class FileConsumer(object):
    def __init__(self, outputFile):
        self.outputFile = outputFile


    def write(self, bytes):
        self.outputFile.write(bytes)



class FileBodyProducerTests(TestCase):
    """
    Tests for the L{FileBodyProducer} which reads bytes from a file and writes
    them to an L{IConsumer}.
    """
    def _termination(self):
        """
        This method can be used as the C{terminationPredicateFactory} for a
        L{Cooperator}.  It returns a predicate which immediately returns
        C{False}, indicating that no more work should be done this iteration.
        This has the result of only allowing one iteration of a cooperative
        task to be run per L{Cooperator} iteration.
        """
        return lambda: True


    def setUp(self):
        """
        Create a L{Cooperator} hooked up to an easily controlled, deterministic
        scheduler to use with L{FileBodyProducer}.
        """
        self._scheduled = []
        self.cooperator = task.Cooperator(
            self._termination, self._scheduled.append)


    def test_interface(self):
        """
        L{FileBodyProducer} instances provide L{IBodyProducer}.
        """
        self.assertTrue(verifyObject(
                IBodyProducer, FileBodyProducer(BytesIO(b""))))


    def test_unknownLength(self):
        """
        If the L{FileBodyProducer} is constructed with a file-like object
        without either a C{seek} or C{tell} method, its C{length} attribute is
        set to C{UNKNOWN_LENGTH}.
        """
        class HasSeek(object):
            def seek(self, offset, whence):
                pass

        class HasTell(object):
            def tell(self):
                pass

        producer = FileBodyProducer(HasSeek())
        self.assertEqual(UNKNOWN_LENGTH, producer.length)
        producer = FileBodyProducer(HasTell())
        self.assertEqual(UNKNOWN_LENGTH, producer.length)


    def test_knownLength(self):
        """
        If the L{FileBodyProducer} is constructed with a file-like object with
        both C{seek} and C{tell} methods, its C{length} attribute is set to the
        size of the file as determined by those methods.
        """
        inputBytes = b"here are some bytes"
        inputFile = BytesIO(inputBytes)
        inputFile.seek(5)
        producer = FileBodyProducer(inputFile)
        self.assertEqual(len(inputBytes) - 5, producer.length)
        self.assertEqual(inputFile.tell(), 5)


    def test_defaultCooperator(self):
        """
        If no L{Cooperator} instance is passed to L{FileBodyProducer}, the
        global cooperator is used.
        """
        producer = FileBodyProducer(BytesIO(b""))
        self.assertEqual(task.cooperate, producer._cooperate)


    def test_startProducing(self):
        """
        L{FileBodyProducer.startProducing} starts writing bytes from the input
        file to the given L{IConsumer} and returns a L{Deferred} which fires
        when they have all been written.
        """
        expectedResult = b"hello, world"
        readSize = 3
        output = BytesIO()
        consumer = FileConsumer(output)
        producer = FileBodyProducer(
            BytesIO(expectedResult), self.cooperator, readSize)
        complete = producer.startProducing(consumer)
        for i in range(len(expectedResult) // readSize + 1):
            self._scheduled.pop(0)()
        self.assertEqual([], self._scheduled)
        self.assertEqual(expectedResult, output.getvalue())
        self.assertEqual(None, self.successResultOf(complete))


    def test_inputClosedAtEOF(self):
        """
        When L{FileBodyProducer} reaches end-of-file on the input file given to
        it, the input file is closed.
        """
        readSize = 4
        inputBytes = b"some friendly bytes"
        inputFile = BytesIO(inputBytes)
        producer = FileBodyProducer(inputFile, self.cooperator, readSize)
        consumer = FileConsumer(BytesIO())
        producer.startProducing(consumer)
        for i in range(len(inputBytes) // readSize + 2):
            self._scheduled.pop(0)()
        self.assertTrue(inputFile.closed)


    def test_failedReadWhileProducing(self):
        """
        If a read from the input file fails while producing bytes to the
        consumer, the L{Deferred} returned by
        L{FileBodyProducer.startProducing} fires with a L{Failure} wrapping
        that exception.
        """
        class BrokenFile(object):
            def read(self, count):
                raise IOError("Simulated bad thing")
        producer = FileBodyProducer(BrokenFile(), self.cooperator)
        complete = producer.startProducing(FileConsumer(BytesIO()))
        self._scheduled.pop(0)()
        self.failureResultOf(complete).trap(IOError)


    def test_stopProducing(self):
        """
        L{FileBodyProducer.stopProducing} stops the underlying L{IPullProducer}
        and the cooperative task responsible for calling C{resumeProducing} and
        closes the input file but does not cause the L{Deferred} returned by
        C{startProducing} to fire.
        """
        expectedResult = b"hello, world"
        readSize = 3
        output = BytesIO()
        consumer = FileConsumer(output)
        inputFile = BytesIO(expectedResult)
        producer = FileBodyProducer(
            inputFile, self.cooperator, readSize)
        complete = producer.startProducing(consumer)
        producer.stopProducing()
        self.assertTrue(inputFile.closed)
        self._scheduled.pop(0)()
        self.assertEqual(b"", output.getvalue())
        self.assertNoResult(complete)


    def test_pauseProducing(self):
        """
        L{FileBodyProducer.pauseProducing} temporarily suspends writing bytes
        from the input file to the given L{IConsumer}.
        """
        expectedResult = b"hello, world"
        readSize = 5
        output = BytesIO()
        consumer = FileConsumer(output)
        producer = FileBodyProducer(
            BytesIO(expectedResult), self.cooperator, readSize)
        complete = producer.startProducing(consumer)
        self._scheduled.pop(0)()
        self.assertEqual(output.getvalue(), expectedResult[:5])
        producer.pauseProducing()

        # Sort of depends on an implementation detail of Cooperator: even
        # though the only task is paused, there's still a scheduled call.  If
        # this were to go away because Cooperator became smart enough to cancel
        # this call in this case, that would be fine.
        self._scheduled.pop(0)()

        # Since the producer is paused, no new data should be here.
        self.assertEqual(output.getvalue(), expectedResult[:5])
        self.assertEqual([], self._scheduled)
        self.assertNoResult(complete)


    def test_resumeProducing(self):
        """
        L{FileBodyProducer.resumeProducing} re-commences writing bytes from the
        input file to the given L{IConsumer} after it was previously paused
        with L{FileBodyProducer.pauseProducing}.
        """
        expectedResult = b"hello, world"
        readSize = 5
        output = BytesIO()
        consumer = FileConsumer(output)
        producer = FileBodyProducer(
            BytesIO(expectedResult), self.cooperator, readSize)
        producer.startProducing(consumer)
        self._scheduled.pop(0)()
        self.assertEqual(expectedResult[:readSize], output.getvalue())
        producer.pauseProducing()
        producer.resumeProducing()
        self._scheduled.pop(0)()
        self.assertEqual(expectedResult[:readSize * 2], output.getvalue())



class FakeReactorAndConnectMixin:
    """
    A test mixin providing a testable C{Reactor} class and a dummy C{connect}
    method which allows instances to pretend to be endpoints.
    """
    Reactor = MemoryReactorClock

    @implementer(IPolicyForHTTPS)
    class StubPolicy(object):
        """
        A stub policy for HTTPS URIs which allows HTTPS tests to run even if
        pyOpenSSL isn't installed.
        """
        def creatorForNetloc(self, hostname, port):
            """
            Don't actually do anything.

            @param hostname: ignored

            @param port: ignored
            """

    class StubEndpoint(object):
        """
        Endpoint that wraps existing endpoint, substitutes StubHTTPProtocol, and
        resulting protocol instances are attached to the given test case.
        """

        def __init__(self, endpoint, testCase):
            self.endpoint = endpoint
            self.testCase = testCase
            self.factory = _HTTP11ClientFactory(lambda p: None)
            self.protocol = StubHTTPProtocol()
            self.factory.buildProtocol = lambda addr: self.protocol

        def connect(self, ignoredFactory):
            self.testCase.protocol = self.protocol
            self.endpoint.connect(self.factory)
            return succeed(self.protocol)


    def buildAgentForWrapperTest(self, reactor):
        """
        Return an Agent suitable for use in tests that wrap the Agent and want
        both a fake reactor and StubHTTPProtocol.
        """
        agent = client.Agent(reactor, self.StubPolicy())
        _oldGetEndpoint = agent._getEndpoint
        agent._getEndpoint = lambda *args: (
            self.StubEndpoint(_oldGetEndpoint(*args), self))
        return agent


    def connect(self, factory):
        """
        Fake implementation of an endpoint which synchronously
        succeeds with an instance of L{StubHTTPProtocol} for ease of
        testing.
        """
        protocol = StubHTTPProtocol()
        protocol.makeConnection(None)
        self.protocol = protocol
        return succeed(protocol)



class DummyEndpoint(object):
    """
    An endpoint that uses a fake transport.
    """

    def connect(self, factory):
        protocol = factory.buildProtocol(None)
        protocol.makeConnection(StringTransport())
        return succeed(protocol)



class BadEndpoint(object):
    """
    An endpoint that shouldn't be called.
    """

    def connect(self, factory):
        raise RuntimeError("This endpoint should not have been used.")


class DummyFactory(Factory):
    """
    Create C{StubHTTPProtocol} instances.
    """
    def __init__(self, quiescentCallback):
        pass

    protocol = StubHTTPProtocol



class HTTPConnectionPoolTests(TestCase, FakeReactorAndConnectMixin):
    """
    Tests for the L{HTTPConnectionPool} class.
    """
    def setUp(self):
        self.fakeReactor = self.Reactor()
        self.pool = HTTPConnectionPool(self.fakeReactor)
        self.pool._factory = DummyFactory
        # The retry code path is tested in HTTPConnectionPoolRetryTests:
        self.pool.retryAutomatically = False


    def test_getReturnsNewIfCacheEmpty(self):
        """
        If there are no cached connections,
        L{HTTPConnectionPool.getConnection} returns a new connection.
        """
        self.assertEqual(self.pool._connections, {})

        def gotConnection(conn):
            self.assertIsInstance(conn, StubHTTPProtocol)
            # The new connection is not stored in the pool:
            self.assertNotIn(conn, self.pool._connections.values())

        unknownKey = 12245
        d = self.pool.getConnection(unknownKey, DummyEndpoint())
        return d.addCallback(gotConnection)


    def test_putStartsTimeout(self):
        """
        If a connection is put back to the pool, a 240-sec timeout is started.

        When the timeout hits, the connection is closed and removed from the
        pool.
        """
        # We start out with one cached connection:
        protocol = StubHTTPProtocol()
        protocol.makeConnection(StringTransport())
        self.pool._putConnection(("http", b"example.com", 80), protocol)

        # Connection is in pool, still not closed:
        self.assertEqual(protocol.transport.disconnecting, False)
        self.assertIn(protocol,
                      self.pool._connections[("http", b"example.com", 80)])

        # Advance 239 seconds, still not closed:
        self.fakeReactor.advance(239)
        self.assertEqual(protocol.transport.disconnecting, False)
        self.assertIn(protocol,
                      self.pool._connections[("http", b"example.com", 80)])
        self.assertIn(protocol, self.pool._timeouts)

        # Advance past 240 seconds, connection will be closed:
        self.fakeReactor.advance(1.1)
        self.assertEqual(protocol.transport.disconnecting, True)
        self.assertNotIn(protocol,
                         self.pool._connections[("http", b"example.com", 80)])
        self.assertNotIn(protocol, self.pool._timeouts)


    def test_putExceedsMaxPersistent(self):
        """
        If an idle connection is put back in the cache and the max number of
        persistent connections has been exceeded, one of the connections is
        closed and removed from the cache.
        """
        pool = self.pool

        # We start out with two cached connection, the max:
        origCached = [StubHTTPProtocol(), StubHTTPProtocol()]
        for p in origCached:
            p.makeConnection(StringTransport())
            pool._putConnection(("http", b"example.com", 80), p)
        self.assertEqual(pool._connections[("http", b"example.com", 80)],
                         origCached)
        timeouts = pool._timeouts.copy()

        # Now we add another one:
        newProtocol = StubHTTPProtocol()
        newProtocol.makeConnection(StringTransport())
        pool._putConnection(("http", b"example.com", 80), newProtocol)

        # The oldest cached connections will be removed and disconnected:
        newCached = pool._connections[("http", b"example.com", 80)]
        self.assertEqual(len(newCached), 2)
        self.assertEqual(newCached, [origCached[1], newProtocol])
        self.assertEqual([p.transport.disconnecting for p in newCached],
                         [False, False])
        self.assertEqual(origCached[0].transport.disconnecting, True)
        self.assertTrue(timeouts[origCached[0]].cancelled)
        self.assertNotIn(origCached[0], pool._timeouts)


    def test_maxPersistentPerHost(self):
        """
        C{maxPersistentPerHost} is enforced per C{(scheme, host, port)}:
        different keys have different max connections.
        """
        def addProtocol(scheme, host, port):
            p = StubHTTPProtocol()
            p.makeConnection(StringTransport())
            self.pool._putConnection((scheme, host, port), p)
            return p
        persistent = []
        persistent.append(addProtocol("http", b"example.com", 80))
        persistent.append(addProtocol("http", b"example.com", 80))
        addProtocol("https", b"example.com", 443)
        addProtocol("http", b"www2.example.com", 80)

        self.assertEqual(
            self.pool._connections[("http", b"example.com", 80)], persistent)
        self.assertEqual(
            len(self.pool._connections[("https", b"example.com", 443)]), 1)
        self.assertEqual(
            len(self.pool._connections[("http", b"www2.example.com", 80)]), 1)


    def test_getCachedConnection(self):
        """
        Getting an address which has a cached connection returns the cached
        connection, removes it from the cache and cancels its timeout.
        """
        # We start out with one cached connection:
        protocol = StubHTTPProtocol()
        protocol.makeConnection(StringTransport())
        self.pool._putConnection(("http", b"example.com", 80), protocol)

        def gotConnection(conn):
            # We got the cached connection:
            self.assertIdentical(protocol, conn)
            self.assertNotIn(
                conn, self.pool._connections[("http", b"example.com", 80)])
            # And the timeout was cancelled:
            self.fakeReactor.advance(241)
            self.assertEqual(conn.transport.disconnecting, False)
            self.assertNotIn(conn, self.pool._timeouts)

        return self.pool.getConnection(("http", b"example.com", 80),
                                       BadEndpoint(),
                                       ).addCallback(gotConnection)


    def test_newConnection(self):
        """
        The pool's C{_newConnection} method constructs a new connection.
        """
        # We start out with one cached connection:
        protocol = StubHTTPProtocol()
        protocol.makeConnection(StringTransport())
        key = 12245
        self.pool._putConnection(key, protocol)

        def gotConnection(newConnection):
            # We got a new connection:
            self.assertNotIdentical(protocol, newConnection)
            # And the old connection is still there:
            self.assertIn(protocol, self.pool._connections[key])
            # While the new connection is not:
            self.assertNotIn(newConnection, self.pool._connections.values())

        d = self.pool._newConnection(key, DummyEndpoint())
        return d.addCallback(gotConnection)


    def test_getSkipsDisconnected(self):
        """
        When getting connections out of the cache, disconnected connections
        are removed and not returned.
        """
        pool = self.pool
        key = ("http", b"example.com", 80)

        # We start out with two cached connection, the max:
        origCached = [StubHTTPProtocol(), StubHTTPProtocol()]
        for p in origCached:
            p.makeConnection(StringTransport())
            pool._putConnection(key, p)
        self.assertEqual(pool._connections[key], origCached)

        # We close the first one:
        origCached[0].state = "DISCONNECTED"

        # Now, when we retrive connections we should get the *second* one:
        result = []
        self.pool.getConnection(key,
                                BadEndpoint()).addCallback(result.append)
        self.assertIdentical(result[0], origCached[1])

        # And both the disconnected and removed connections should be out of
        # the cache:
        self.assertEqual(pool._connections[key], [])
        self.assertEqual(pool._timeouts, {})


    def test_putNotQuiescent(self):
        """
        If a non-quiescent connection is put back in the cache, an error is
        logged.
        """
        protocol = StubHTTPProtocol()
        # By default state is QUIESCENT
        self.assertEqual(protocol.state, "QUIESCENT")

        protocol.state = "NOTQUIESCENT"
        self.pool._putConnection(("http", b"example.com", 80), protocol)
        exc, = self.flushLoggedErrors(RuntimeError)
        self.assertEqual(
            exc.value.args[0],
            "BUG: Non-quiescent protocol added to connection pool.")
        self.assertIdentical(None, self.pool._connections.get(
                ("http", b"example.com", 80)))


    def test_getUsesQuiescentCallback(self):
        """
        When L{HTTPConnectionPool.getConnection} connects, it returns a
        C{Deferred} that fires with an instance of L{HTTP11ClientProtocol}
        that has the correct quiescent callback attached. When this callback
        is called the protocol is returned to the cache correctly, using the
        right key.
        """
        class StringEndpoint(object):
            def connect(self, factory):
                p = factory.buildProtocol(None)
                p.makeConnection(StringTransport())
                return succeed(p)

        pool = HTTPConnectionPool(self.fakeReactor, True)
        pool.retryAutomatically = False
        result = []
        key = "a key"
        pool.getConnection(
            key, StringEndpoint()).addCallback(
            result.append)
        protocol = result[0]
        self.assertIsInstance(protocol, HTTP11ClientProtocol)

        # Now that we have protocol instance, lets try to put it back in the
        # pool:
        protocol._state = "QUIESCENT"
        protocol._quiescentCallback(protocol)

        # If we try to retrive a connection to same destination again, we
        # should get the same protocol, because it should've been added back
        # to the pool:
        result2 = []
        pool.getConnection(
            key, StringEndpoint()).addCallback(
            result2.append)
        self.assertIdentical(result2[0], protocol)


    def test_closeCachedConnections(self):
        """
        L{HTTPConnectionPool.closeCachedConnections} closes all cached
        connections and removes them from the cache. It returns a Deferred
        that fires when they have all lost their connections.
        """
        persistent = []
        def addProtocol(scheme, host, port):
            p = HTTP11ClientProtocol()
            p.makeConnection(StringTransport())
            self.pool._putConnection((scheme, host, port), p)
            persistent.append(p)
        addProtocol("http", b"example.com", 80)
        addProtocol("http", b"www2.example.com", 80)
        doneDeferred = self.pool.closeCachedConnections()

        # Connections have begun disconnecting:
        for p in persistent:
            self.assertEqual(p.transport.disconnecting, True)
        self.assertEqual(self.pool._connections, {})
        # All timeouts were cancelled and removed:
        for dc in self.fakeReactor.getDelayedCalls():
            self.assertEqual(dc.cancelled, True)
        self.assertEqual(self.pool._timeouts, {})

        # Returned Deferred fires when all connections have been closed:
        result = []
        doneDeferred.addCallback(result.append)
        self.assertEqual(result, [])
        persistent[0].connectionLost(Failure(ConnectionDone()))
        self.assertEqual(result, [])
        persistent[1].connectionLost(Failure(ConnectionDone()))
        self.assertEqual(result, [None])


    def test_cancelGetConnectionCancelsEndpointConnect(self):
        """
        Cancelling the C{Deferred} returned from
        L{HTTPConnectionPool.getConnection} cancels the C{Deferred} returned
        by opening a new connection with the given endpoint.
        """
        self.assertEqual(self.pool._connections, {})
        connectionResult = Deferred()

        class Endpoint:
            def connect(self, factory):
                return connectionResult

        d = self.pool.getConnection(12345, Endpoint())
        d.cancel()
        self.assertEqual(self.failureResultOf(connectionResult).type,
                         CancelledError)



class AgentTestsMixin(object):
    """
    Tests for any L{IAgent} implementation.
    """
    def test_interface(self):
        """
        The agent object provides L{IAgent}.
        """
        self.assertTrue(verifyObject(IAgent, self.makeAgent()))



@implementer(IAgentEndpointFactory)
class StubEndpointFactory(object):
    """
    A stub L{IAgentEndpointFactory} for use in testing.
    """
    def endpointForURI(self, uri):
        """
        Testing implementation.

        @param uri: A L{URI}.

        @return: C{(scheme, host, port)} of passed in URI; violation of
            interface but useful for testing.
        @rtype: L{tuple}
        """
        return (uri.scheme, uri.host, uri.port)



class AgentTests(TestCase, FakeReactorAndConnectMixin, AgentTestsMixin):
    """
    Tests for the new HTTP client API provided by L{Agent}.
    """
    def makeAgent(self):
        """
        @return: a new L{twisted.web.client.Agent} instance
        """
        return client.Agent(self.reactor)


    def setUp(self):
        """
        Create an L{Agent} wrapped around a fake reactor.
        """
        self.reactor = self.Reactor()
        self.agent = self.makeAgent()


    def test_defaultPool(self):
        """
        If no pool is passed in, the L{Agent} creates a non-persistent pool.
        """
        agent = client.Agent(self.reactor)
        self.assertIsInstance(agent._pool, HTTPConnectionPool)
        self.assertEqual(agent._pool.persistent, False)
        self.assertIdentical(agent._reactor, agent._pool._reactor)


    def test_persistent(self):
        """
        If C{persistent} is set to C{True} on the L{HTTPConnectionPool} (the
        default), C{Request}s are created with their C{persistent} flag set to
        C{True}.
        """
        pool = HTTPConnectionPool(self.reactor)
        agent = client.Agent(self.reactor, pool=pool)
        agent._getEndpoint = lambda *args: self
        agent.request(b"GET", b"http://127.0.0.1")
        self.assertEqual(self.protocol.requests[0][0].persistent, True)


    def test_nonPersistent(self):
        """
        If C{persistent} is set to C{False} when creating the
        L{HTTPConnectionPool}, C{Request}s are created with their
        C{persistent} flag set to C{False}.

        Elsewhere in the tests for the underlying HTTP code we ensure that
        this will result in the disconnection of the HTTP protocol once the
        request is done, so that the connection will not be returned to the
        pool.
        """
        pool = HTTPConnectionPool(self.reactor, persistent=False)
        agent = client.Agent(self.reactor, pool=pool)
        agent._getEndpoint = lambda *args: self
        agent.request(b"GET", b"http://127.0.0.1")
        self.assertEqual(self.protocol.requests[0][0].persistent, False)


    def test_connectUsesConnectionPool(self):
        """
        When a connection is made by the Agent, it uses its pool's
        C{getConnection} method to do so, with the endpoint returned by
        C{self._getEndpoint}. The key used is C{(scheme, host, port)}.
        """
        endpoint = DummyEndpoint()
        class MyAgent(client.Agent):
            def _getEndpoint(this, uri):
                self.assertEqual((uri.scheme, uri.host, uri.port),
                                 (b"http", b"foo", 80))
                return endpoint

        class DummyPool(object):
            connected = False
            persistent = False
            def getConnection(this, key, ep):
                this.connected = True
                self.assertEqual(ep, endpoint)
                # This is the key the default Agent uses, others will have
                # different keys:
                self.assertEqual(key, (b"http", b"foo", 80))
                return defer.succeed(StubHTTPProtocol())

        pool = DummyPool()
        agent = MyAgent(self.reactor, pool=pool)
        self.assertIdentical(pool, agent._pool)

        headers = http_headers.Headers()
        headers.addRawHeader(b"host", b"foo")
        bodyProducer = object()
        agent.request(b'GET', b'http://foo/',
                      bodyProducer=bodyProducer, headers=headers)
        self.assertEqual(agent._pool.connected, True)


    def test_unsupportedScheme(self):
        """
        L{Agent.request} returns a L{Deferred} which fails with
        L{SchemeNotSupported} if the scheme of the URI passed to it is not
        C{'http'}.
        """
        return self.assertFailure(
            self.agent.request(b'GET', b'mailto:alice@example.com'),
            SchemeNotSupported)


    def test_connectionFailed(self):
        """
        The L{Deferred} returned by L{Agent.request} fires with a L{Failure} if
        the TCP connection attempt fails.
        """
        result = self.agent.request(b'GET', b'http://foo/')
        # Cause the connection to be refused
        host, port, factory = self.reactor.tcpClients.pop()[:3]
        factory.clientConnectionFailed(None, Failure(ConnectionRefusedError()))
        return self.assertFailure(result, ConnectionRefusedError)


    def test_connectHTTP(self):
        """
        L{Agent._getEndpoint} return a C{TCP4ClientEndpoint} when passed a
        scheme of C{'http'}.
        """
        expectedHost = b'example.com'
        expectedPort = 1234
        endpoint = self.agent._getEndpoint(URI.fromBytes(
            b'http://' + expectedHost + b":" + intToBytes(expectedPort)))
        self.assertEqual(endpoint._host, "example.com")
        self.assertEqual(endpoint._port, expectedPort)
        self.assertIsInstance(endpoint, TCP4ClientEndpoint)


    def test_nonDecodableURI(self):
        """
        L{Agent._getEndpoint} when given a non-ASCII decodable URI will raise a
        L{ValueError} saying such.
        """
        uri = URI.fromBytes(b"http://example.com:80")
        uri.host = u'\u2603.com'.encode('utf8')

        with self.assertRaises(ValueError) as e:
            self.agent._getEndpoint(uri)

        self.assertEqual(e.exception.args[0],
                         ("The host of the provided URI ({reprout}) contains "
                          "non-ASCII octets, it should be ASCII "
                          "decodable.").format(reprout=repr(uri.host)))


    def test_connectHTTPSCustomContextFactory(self):
        """
        If a context factory is passed to L{Agent.__init__} it will be used to
        determine the SSL parameters for HTTPS requests.  When an HTTPS request
        is made, the hostname and port number of the request URL will be passed
        to the context factory's C{getContext} method.  The resulting context
        object will be used to establish the SSL connection.
        """
        expectedHost = b'example.org'
        expectedPort = 20443
        expectedContext = object()

        contextArgs = []
        class StubWebContextFactory(object):
            def getContext(self, hostname, port):
                contextArgs.append((hostname, port))
                return expectedContext

        agent = client.Agent(self.reactor, StubWebContextFactory())
        endpoint = agent._getEndpoint(URI.fromBytes(
            b'https://' + expectedHost + b":" + intToBytes(expectedPort)))
        contextFactory = endpoint._sslContextFactory
        context = contextFactory.getContext()
        self.assertEqual(context, expectedContext)
        self.assertEqual(contextArgs, [(expectedHost, expectedPort)])


    def test_hostProvided(self):
        """
        If L{None} is passed to L{Agent.request} for the C{headers} parameter,
        a L{Headers} instance is created for the request and a I{Host} header
        added to it.
        """
        self.agent._getEndpoint = lambda *args: self
        self.agent.request(
            b'GET', b'http://example.com/foo?bar')

        req, res = self.protocol.requests.pop()
        self.assertEqual(req.headers.getRawHeaders(b'host'), [b'example.com'])


    def test_hostIPv6Bracketed(self):
        """
        If an IPv6 address is used in the C{uri} passed to L{Agent.request},
        the computed I{Host} header needs to be bracketed.
        """
        self.agent._getEndpoint = lambda *args: self
        self.agent.request(b'GET', b'http://[::1]/')

        req, res = self.protocol.requests.pop()
        self.assertEqual(req.headers.getRawHeaders(b'host'), [b'[::1]'])


    def test_hostOverride(self):
        """
        If the headers passed to L{Agent.request} includes a value for the
        I{Host} header, that value takes precedence over the one which would
        otherwise be automatically provided.
        """
        headers = http_headers.Headers({b'foo': [b'bar'], b'host': [b'quux']})
        self.agent._getEndpoint = lambda *args: self
        self.agent.request(
            b'GET', b'http://example.com/foo?bar', headers)

        req, res = self.protocol.requests.pop()
        self.assertEqual(req.headers.getRawHeaders(b'host'), [b'quux'])


    def test_headersUnmodified(self):
        """
        If a I{Host} header must be added to the request, the L{Headers}
        instance passed to L{Agent.request} is not modified.
        """
        headers = http_headers.Headers()
        self.agent._getEndpoint = lambda *args: self
        self.agent.request(
            b'GET', b'http://example.com/foo', headers)

        protocol = self.protocol

        # The request should have been issued.
        self.assertEqual(len(protocol.requests), 1)
        # And the headers object passed in should not have changed.
        self.assertEqual(headers, http_headers.Headers())


    def test_hostValueStandardHTTP(self):
        """
        When passed a scheme of C{'http'} and a port of C{80},
        L{Agent._computeHostValue} returns a string giving just
        the host name passed to it.
        """
        self.assertEqual(
            self.agent._computeHostValue(b'http', b'example.com', 80),
            b'example.com')


    def test_hostValueNonStandardHTTP(self):
        """
        When passed a scheme of C{'http'} and a port other than C{80},
        L{Agent._computeHostValue} returns a string giving the
        host passed to it joined together with the port number by C{":"}.
        """
        self.assertEqual(
            self.agent._computeHostValue(b'http', b'example.com', 54321),
            b'example.com:54321')


    def test_hostValueStandardHTTPS(self):
        """
        When passed a scheme of C{'https'} and a port of C{443},
        L{Agent._computeHostValue} returns a string giving just
        the host name passed to it.
        """
        self.assertEqual(
            self.agent._computeHostValue(b'https', b'example.com', 443),
            b'example.com')


    def test_hostValueNonStandardHTTPS(self):
        """
        When passed a scheme of C{'https'} and a port other than C{443},
        L{Agent._computeHostValue} returns a string giving the
        host passed to it joined together with the port number by C{":"}.
        """
        self.assertEqual(
            self.agent._computeHostValue(b'https', b'example.com', 54321),
            b'example.com:54321')


    def test_request(self):
        """
        L{Agent.request} establishes a new connection to the host indicated by
        the host part of the URI passed to it and issues a request using the
        method, the path portion of the URI, the headers, and the body producer
        passed to it.  It returns a L{Deferred} which fires with an
        L{IResponse} from the server.
        """
        self.agent._getEndpoint = lambda *args: self

        headers = http_headers.Headers({b'foo': [b'bar']})
        # Just going to check the body for identity, so it doesn't need to be
        # real.
        body = object()
        self.agent.request(
            b'GET', b'http://example.com:1234/foo?bar', headers, body)

        protocol = self.protocol

        # The request should be issued.
        self.assertEqual(len(protocol.requests), 1)
        req, res = protocol.requests.pop()
        self.assertIsInstance(req, Request)
        self.assertEqual(req.method, b'GET')
        self.assertEqual(req.uri, b'/foo?bar')
        self.assertEqual(
            req.headers,
            http_headers.Headers({b'foo': [b'bar'],
                                  b'host': [b'example.com:1234']}))
        self.assertIdentical(req.bodyProducer, body)


    def test_connectTimeout(self):
        """
        L{Agent} takes a C{connectTimeout} argument which is forwarded to the
        following C{connectTCP} agent.
        """
        agent = client.Agent(self.reactor, connectTimeout=5)
        agent.request(b'GET', b'http://foo/')
        timeout = self.reactor.tcpClients.pop()[3]
        self.assertEqual(5, timeout)


    def test_connectSSLTimeout(self):
        """
        L{Agent} takes a C{connectTimeout} argument which is forwarded to the
        following C{connectSSL} call.
        """
        agent = client.Agent(self.reactor, self.StubPolicy(), connectTimeout=5)
        agent.request(b'GET', b'https://foo/')
        timeout = self.reactor.sslClients.pop()[4]
        self.assertEqual(5, timeout)


    def test_bindAddress(self):
        """
        L{Agent} takes a C{bindAddress} argument which is forwarded to the
        following C{connectTCP} call.
        """
        agent = client.Agent(self.reactor, bindAddress='192.168.0.1')
        agent.request(b'GET', b'http://foo/')
        address = self.reactor.tcpClients.pop()[4]
        self.assertEqual('192.168.0.1', address)


    def test_bindAddressSSL(self):
        """
        L{Agent} takes a C{bindAddress} argument which is forwarded to the
        following C{connectSSL} call.
        """
        agent = client.Agent(self.reactor, self.StubPolicy(),
                             bindAddress='192.168.0.1')
        agent.request(b'GET', b'https://foo/')
        address = self.reactor.sslClients.pop()[5]
        self.assertEqual('192.168.0.1', address)


    def test_responseIncludesRequest(self):
        """
        L{Response}s returned by L{Agent.request} have a reference to the
        L{Request} that was originally issued.
        """
        uri = b'http://example.com/'
        agent = self.buildAgentForWrapperTest(self.reactor)
        d = agent.request(b'GET', uri)

        # The request should be issued.
        self.assertEqual(len(self.protocol.requests), 1)
        req, res = self.protocol.requests.pop()
        self.assertIsInstance(req, Request)

        resp = client.Response._construct(
            (b'HTTP', 1, 1),
            200,
            b'OK',
            client.Headers({}),
            None,
            req)
        res.callback(resp)

        response = self.successResultOf(d)
        self.assertEqual(
            (response.request.method, response.request.absoluteURI,
             response.request.headers),
            (req.method, req.absoluteURI, req.headers))


    def test_requestAbsoluteURI(self):
        """
        L{Request.absoluteURI} is the absolute URI of the request.
        """
        uri = b'http://example.com/foo;1234?bar#frag'
        agent = self.buildAgentForWrapperTest(self.reactor)
        agent.request(b'GET', uri)

        # The request should be issued.
        self.assertEqual(len(self.protocol.requests), 1)
        req, res = self.protocol.requests.pop()
        self.assertIsInstance(req, Request)
        self.assertEqual(req.absoluteURI, uri)


    def test_requestMissingAbsoluteURI(self):
        """
        L{Request.absoluteURI} is L{None} if L{Request._parsedURI} is L{None}.
        """
        request = client.Request(b'FOO', b'/', client.Headers(), None)
        self.assertIdentical(request.absoluteURI, None)


    def test_endpointFactory(self):
        """
        L{Agent.usingEndpointFactory} creates an L{Agent} that uses the given
        factory to create endpoints.
        """
        factory = StubEndpointFactory()
        agent = client.Agent.usingEndpointFactory(
            None, endpointFactory=factory)
        uri = URI.fromBytes(b'http://example.com/')
        returnedEndpoint = agent._getEndpoint(uri)
        self.assertEqual(returnedEndpoint, (b"http", b"example.com", 80))


    def test_endpointFactoryDefaultPool(self):
        """
        If no pool is passed in to L{Agent.usingEndpointFactory}, a default
        pool is constructed with no persistent connections.
        """
        agent = client.Agent.usingEndpointFactory(
            self.reactor, StubEndpointFactory())
        pool = agent._pool
        self.assertEqual((pool.__class__, pool.persistent, pool._reactor),
                          (HTTPConnectionPool, False, agent._reactor))


    def test_endpointFactoryPool(self):
        """
        If a pool is passed in to L{Agent.usingEndpointFactory} it is used as
        the L{Agent} pool.
        """
        pool = object()
        agent = client.Agent.usingEndpointFactory(
            self.reactor, StubEndpointFactory(), pool)
        self.assertIs(pool, agent._pool)



class AgentHTTPSTests(TestCase, FakeReactorAndConnectMixin):
    """
    Tests for the new HTTP client API that depends on SSL.
    """
    if ssl is None:
        skip = "SSL not present, cannot run SSL tests"


    def makeEndpoint(self, host=b'example.com', port=443):
        """
        Create an L{Agent} with an https scheme and return its endpoint
        created according to the arguments.

        @param host: The host for the endpoint.
        @type host: L{bytes}

        @param port: The port for the endpoint.
        @type port: L{int}

        @return: An endpoint of an L{Agent} constructed according to args.
        @rtype: L{SSL4ClientEndpoint}
        """
        return client.Agent(self.Reactor())._getEndpoint(
            URI.fromBytes(b'https://' + host + b":" + intToBytes(port) + b"/"))


    def test_endpointType(self):
        """
        L{Agent._getEndpoint} return a L{SSL4ClientEndpoint} when passed a
        scheme of C{'https'}.
        """
        self.assertIsInstance(self.makeEndpoint(), SSL4ClientEndpoint)


    def test_hostArgumentIsRespected(self):
        """
        If a host is passed, the endpoint respects it.
        """
        endpoint = self.makeEndpoint(host=b"example.com")
        self.assertEqual(endpoint._host, "example.com")


    def test_portArgumentIsRespected(self):
        """
        If a port is passed, the endpoint respects it.
        """
        expectedPort = 4321
        endpoint = self.makeEndpoint(port=expectedPort)
        self.assertEqual(endpoint._port, expectedPort)


    def test_contextFactoryType(self):
        """
        L{Agent} wraps its connection creator creator and uses modern TLS APIs.
        """
        endpoint = self.makeEndpoint()
        contextFactory = endpoint._sslContextFactory
        self.assertIsInstance(contextFactory, ClientTLSOptions)
        self.assertEqual(contextFactory._hostname, u"example.com")


    def test_connectHTTPSCustomConnectionCreator(self):
        """
        If a custom L{WebClientConnectionCreator}-like object is passed to
        L{Agent.__init__} it will be used to determine the SSL parameters for
        HTTPS requests.  When an HTTPS request is made, the hostname and port
        number of the request URL will be passed to the connection creator's
        C{creatorForNetloc} method.  The resulting context object will be used
        to establish the SSL connection.
        """
        expectedHost = b'example.org'
        expectedPort = 20443
        class JustEnoughConnection(object):
            handshakeStarted = False
            connectState = False
            def do_handshake(self):
                """
                The handshake started.  Record that fact.
                """
                self.handshakeStarted = True
            def set_connect_state(self):
                """
                The connection started.  Record that fact.
                """
                self.connectState = True

        contextArgs = []

        @implementer(IOpenSSLClientConnectionCreator)
        class JustEnoughCreator(object):
            def __init__(self, hostname, port):
                self.hostname = hostname
                self.port = port

            def clientConnectionForTLS(self, tlsProtocol):
                """
                Implement L{IOpenSSLClientConnectionCreator}.

                @param tlsProtocol: The TLS protocol.
                @type tlsProtocol: L{TLSMemoryBIOProtocol}

                @return: C{expectedConnection}
                """
                contextArgs.append((tlsProtocol, self.hostname, self.port))
                return expectedConnection

        expectedConnection = JustEnoughConnection()
        @implementer(IPolicyForHTTPS)
        class StubBrowserLikePolicyForHTTPS(object):
            def creatorForNetloc(self, hostname, port):
                """
                Emulate L{BrowserLikePolicyForHTTPS}.

                @param hostname: The hostname to verify.
                @type hostname: L{bytes}

                @param port: The port number.
                @type port: L{int}

                @return: a stub L{IOpenSSLClientConnectionCreator}
                @rtype: L{JustEnoughCreator}
                """
                return JustEnoughCreator(hostname, port)

        expectedCreatorCreator = StubBrowserLikePolicyForHTTPS()
        reactor = self.Reactor()
        agent = client.Agent(reactor, expectedCreatorCreator)
        endpoint = agent._getEndpoint(URI.fromBytes(
            b'https://' + expectedHost + b":" + intToBytes(expectedPort)))
        endpoint.connect(Factory.forProtocol(Protocol))
        passedFactory = reactor.sslClients[-1][2]
        passedContextFactory = reactor.sslClients[-1][3]
        tlsFactory = TLSMemoryBIOFactory(
            passedContextFactory, True, passedFactory
        )
        tlsProtocol = tlsFactory.buildProtocol(None)
        tlsProtocol.makeConnection(StringTransport())
        tls = contextArgs[0][0]
        self.assertIsInstance(tls, TLSMemoryBIOProtocol)
        self.assertEqual(contextArgs[0][1:], (expectedHost, expectedPort))
        self.assertTrue(expectedConnection.handshakeStarted)
        self.assertTrue(expectedConnection.connectState)


    def test_deprecatedDuckPolicy(self):
        """
        Passing something that duck-types I{like} a L{web client context
        factory <twisted.web.client.WebClientContextFactory>} - something that
        does not provide L{IPolicyForHTTPS} - to L{Agent} emits a
        L{DeprecationWarning} even if you don't actually C{import
        WebClientContextFactory} to do it.
        """
        def warnMe():
            client.Agent(MemoryReactorClock(),
                         "does-not-provide-IPolicyForHTTPS")
        warnMe()
        warnings = self.flushWarnings([warnMe])
        self.assertEqual(len(warnings), 1)
        [warning] = warnings
        self.assertEqual(warning['category'], DeprecationWarning)
        self.assertEqual(
            warning['message'],
            "'does-not-provide-IPolicyForHTTPS' was passed as the HTTPS "
            "policy for an Agent, but it does not provide IPolicyForHTTPS.  "
            "Since Twisted 14.0, you must pass a provider of IPolicyForHTTPS."
        )


    def test_alternateTrustRoot(self):
        """
        L{BrowserLikePolicyForHTTPS.creatorForNetloc} returns an
        L{IOpenSSLClientConnectionCreator} provider which will add certificates
        from the given trust root.
        """
        @implementer(IOpenSSLTrustRoot)
        class CustomOpenSSLTrustRoot(object):
            called = False
            context = None
            def _addCACertsToContext(self, context):
                self.called = True
                self.context = context
        trustRoot = CustomOpenSSLTrustRoot()
        policy = BrowserLikePolicyForHTTPS(trustRoot=trustRoot)
        creator = policy.creatorForNetloc(b"thingy", 4321)
        self.assertTrue(trustRoot.called)
        connection = creator.clientConnectionForTLS(None)
        self.assertIs(trustRoot.context, connection.get_context())



class WebClientContextFactoryTests(TestCase):
    """
    Tests for the context factory wrapper for web clients
    L{twisted.web.client.WebClientContextFactory}.
    """

    def setUp(self):
        """
        Get WebClientContextFactory while quashing its deprecation warning.
        """
        from twisted.web.client import WebClientContextFactory
        self.warned = self.flushWarnings([WebClientContextFactoryTests.setUp])
        self.webClientContextFactory = WebClientContextFactory


    def test_deprecated(self):
        """
        L{twisted.web.client.WebClientContextFactory} is deprecated.  Importing
        it displays a warning.
        """
        self.assertEqual(len(self.warned), 1)
        [warning] = self.warned
        self.assertEqual(warning['category'], DeprecationWarning)
        self.assertEqual(
            warning['message'],
            getDeprecationWarningString(
                self.webClientContextFactory, Version("Twisted", 14, 0, 0),
                replacement=BrowserLikePolicyForHTTPS,
            )

            # See https://twistedmatrix.com/trac/ticket/7242
            .replace(";", ":")
        )


    def test_missingSSL(self):
        """
        If C{getContext} is called and SSL is not available, raise
        L{NotImplementedError}.
        """
        self.assertRaises(
            NotImplementedError,
            self.webClientContextFactory().getContext,
            b'example.com', 443,
        )


    def test_returnsContext(self):
        """
        If SSL is present, C{getContext} returns a L{OpenSSL.SSL.Context}.
        """
        ctx = self.webClientContextFactory().getContext('example.com', 443)
        self.assertIsInstance(ctx, ssl.SSL.Context)


    def test_setsTrustRootOnContextToDefaultTrustRoot(self):
        """
        The L{CertificateOptions} has C{trustRoot} set to the default trust
        roots.
        """
        ctx = self.webClientContextFactory()
        certificateOptions = ctx._getCertificateOptions('example.com', 443)
        self.assertIsInstance(
            certificateOptions.trustRoot, ssl.OpenSSLDefaultPaths)


    if ssl is None:
        test_returnsContext.skip = "SSL not present, cannot run SSL tests."
        test_setsTrustRootOnContextToDefaultTrustRoot.skip = (
            "SSL not present, cannot run SSL tests.")
    else:
        test_missingSSL.skip = "SSL present."



class HTTPConnectionPoolRetryTests(TestCase, FakeReactorAndConnectMixin):
    """
    L{client.HTTPConnectionPool}, by using
    L{client._RetryingHTTP11ClientProtocol}, supports retrying requests done
    against previously cached connections.
    """

    def test_onlyRetryIdempotentMethods(self):
        """
        Only GET, HEAD, OPTIONS, TRACE, DELETE methods cause a retry.
        """
        pool = client.HTTPConnectionPool(None)
        connection = client._RetryingHTTP11ClientProtocol(None, pool)
        self.assertTrue(connection._shouldRetry(
            b"GET", RequestNotSent(), None))
        self.assertTrue(connection._shouldRetry(
            b"HEAD", RequestNotSent(), None))
        self.assertTrue(connection._shouldRetry(
            b"OPTIONS", RequestNotSent(), None))
        self.assertTrue(connection._shouldRetry(
            b"TRACE", RequestNotSent(), None))
        self.assertTrue(connection._shouldRetry(
            b"DELETE", RequestNotSent(), None))
        self.assertFalse(connection._shouldRetry(
            b"POST", RequestNotSent(), None))
        self.assertFalse(connection._shouldRetry(
            b"MYMETHOD", RequestNotSent(), None))
        # This will be covered by a different ticket, since we need support
        #for resettable body producers:
        # self.assertTrue(connection._doRetry("PUT", RequestNotSent(), None))


    def test_onlyRetryIfNoResponseReceived(self):
        """
        Only L{RequestNotSent}, L{RequestTransmissionFailed} and
        L{ResponseNeverReceived} exceptions cause a retry.
        """
        pool = client.HTTPConnectionPool(None)
        connection = client._RetryingHTTP11ClientProtocol(None, pool)
        self.assertTrue(connection._shouldRetry(
            b"GET", RequestNotSent(), None))
        self.assertTrue(connection._shouldRetry(
            b"GET", RequestTransmissionFailed([]), None))
        self.assertTrue(connection._shouldRetry(
            b"GET", ResponseNeverReceived([]),None))
        self.assertFalse(connection._shouldRetry(
            b"GET", ResponseFailed([]), None))
        self.assertFalse(connection._shouldRetry(
            b"GET", ConnectionRefusedError(), None))


    def test_dontRetryIfFailedDueToCancel(self):
        """
        If a request failed due to the operation being cancelled,
        C{_shouldRetry} returns C{False} to indicate the request should not be
        retried.
        """
        pool = client.HTTPConnectionPool(None)
        connection = client._RetryingHTTP11ClientProtocol(None, pool)
        exception = ResponseNeverReceived([Failure(defer.CancelledError())])
        self.assertFalse(connection._shouldRetry(b"GET", exception, None))


    def test_retryIfFailedDueToNonCancelException(self):
        """
        If a request failed with L{ResponseNeverReceived} due to some
        arbitrary exception, C{_shouldRetry} returns C{True} to indicate the
        request should be retried.
        """
        pool = client.HTTPConnectionPool(None)
        connection = client._RetryingHTTP11ClientProtocol(None, pool)
        self.assertTrue(connection._shouldRetry(
            b"GET", ResponseNeverReceived([Failure(Exception())]), None))


    def test_wrappedOnPersistentReturned(self):
        """
        If L{client.HTTPConnectionPool.getConnection} returns a previously
        cached connection, it will get wrapped in a
        L{client._RetryingHTTP11ClientProtocol}.
        """
        pool = client.HTTPConnectionPool(Clock())

        # Add a connection to the cache:
        protocol = StubHTTPProtocol()
        protocol.makeConnection(StringTransport())
        pool._putConnection(123, protocol)

        # Retrieve it, it should come back wrapped in a
        # _RetryingHTTP11ClientProtocol:
        d = pool.getConnection(123, DummyEndpoint())

        def gotConnection(connection):
            self.assertIsInstance(connection,
                                  client._RetryingHTTP11ClientProtocol)
            self.assertIdentical(connection._clientProtocol, protocol)
        return d.addCallback(gotConnection)


    def test_notWrappedOnNewReturned(self):
        """
        If L{client.HTTPConnectionPool.getConnection} returns a new
        connection, it will be returned as is.
        """
        pool = client.HTTPConnectionPool(None)
        d = pool.getConnection(123, DummyEndpoint())

        def gotConnection(connection):
            # Don't want to use isinstance since potentially the wrapper might
            # subclass it at some point:
            self.assertIdentical(connection.__class__, HTTP11ClientProtocol)
        return d.addCallback(gotConnection)


    def retryAttempt(self, willWeRetry):
        """
        Fail a first request, possibly retrying depending on argument.
        """
        protocols = []
        def newProtocol():
            protocol = StubHTTPProtocol()
            protocols.append(protocol)
            return defer.succeed(protocol)

        bodyProducer = object()
        request = client.Request(b"FOO", b"/", client.Headers(), bodyProducer,
                                 persistent=True)
        newProtocol()
        protocol = protocols[0]
        retrier = client._RetryingHTTP11ClientProtocol(protocol, newProtocol)

        def _shouldRetry(m, e, bp):
            self.assertEqual(m, b"FOO")
            self.assertIdentical(bp, bodyProducer)
            self.assertIsInstance(e, (RequestNotSent, ResponseNeverReceived))
            return willWeRetry
        retrier._shouldRetry = _shouldRetry

        d = retrier.request(request)

        # So far, one request made:
        self.assertEqual(len(protocols), 1)
        self.assertEqual(len(protocols[0].requests), 1)

        # Fail the first request:
        protocol.requests[0][1].errback(RequestNotSent())
        return d, protocols


    def test_retryIfShouldRetryReturnsTrue(self):
        """
        L{client._RetryingHTTP11ClientProtocol} retries when
        L{client._RetryingHTTP11ClientProtocol._shouldRetry} returns C{True}.
        """
        d, protocols = self.retryAttempt(True)
        # We retried!
        self.assertEqual(len(protocols), 2)
        response = object()
        protocols[1].requests[0][1].callback(response)
        return d.addCallback(self.assertIdentical, response)


    def test_dontRetryIfShouldRetryReturnsFalse(self):
        """
        L{client._RetryingHTTP11ClientProtocol} does not retry when
        L{client._RetryingHTTP11ClientProtocol._shouldRetry} returns C{False}.
        """
        d, protocols = self.retryAttempt(False)
        # We did not retry:
        self.assertEqual(len(protocols), 1)
        return self.assertFailure(d, RequestNotSent)


    def test_onlyRetryWithoutBody(self):
        """
        L{_RetryingHTTP11ClientProtocol} only retries queries that don't have
        a body.

        This is an implementation restriction; if the restriction is fixed,
        this test should be removed and PUT added to list of methods that
        support retries.
        """
        pool = client.HTTPConnectionPool(None)
        connection = client._RetryingHTTP11ClientProtocol(None, pool)
        self.assertTrue(connection._shouldRetry(b"GET", RequestNotSent(), None))
        self.assertFalse(connection._shouldRetry(b"GET", RequestNotSent(), object()))


    def test_onlyRetryOnce(self):
        """
        If a L{client._RetryingHTTP11ClientProtocol} fails more than once on
        an idempotent query before a response is received, it will not retry.
        """
        d, protocols = self.retryAttempt(True)
        self.assertEqual(len(protocols), 2)
        # Fail the second request too:
        protocols[1].requests[0][1].errback(ResponseNeverReceived([]))
        # We didn't retry again:
        self.assertEqual(len(protocols), 2)
        return self.assertFailure(d, ResponseNeverReceived)


    def test_dontRetryIfRetryAutomaticallyFalse(self):
        """
        If L{HTTPConnectionPool.retryAutomatically} is set to C{False}, don't
        wrap connections with retrying logic.
        """
        pool = client.HTTPConnectionPool(Clock())
        pool.retryAutomatically = False

        # Add a connection to the cache:
        protocol = StubHTTPProtocol()
        protocol.makeConnection(StringTransport())
        pool._putConnection(123, protocol)

        # Retrieve it, it should come back unwrapped:
        d = pool.getConnection(123, DummyEndpoint())

        def gotConnection(connection):
            self.assertIdentical(connection, protocol)
        return d.addCallback(gotConnection)


    def test_retryWithNewConnection(self):
        """
        L{client.HTTPConnectionPool} creates
        {client._RetryingHTTP11ClientProtocol} with a new connection factory
        method that creates a new connection using the same key and endpoint
        as the wrapped connection.
        """
        pool = client.HTTPConnectionPool(Clock())
        key = 123
        endpoint = DummyEndpoint()
        newConnections = []

        # Override the pool's _newConnection:
        def newConnection(k, e):
            newConnections.append((k, e))
        pool._newConnection = newConnection

        # Add a connection to the cache:
        protocol = StubHTTPProtocol()
        protocol.makeConnection(StringTransport())
        pool._putConnection(key, protocol)

        # Retrieve it, it should come back wrapped in a
        # _RetryingHTTP11ClientProtocol:
        d = pool.getConnection(key, endpoint)

        def gotConnection(connection):
            self.assertIsInstance(connection,
                                  client._RetryingHTTP11ClientProtocol)
            self.assertIdentical(connection._clientProtocol, protocol)
            # Verify that the _newConnection method on retrying connection
            # calls _newConnection on the pool:
            self.assertEqual(newConnections, [])
            connection._newConnection()
            self.assertEqual(len(newConnections), 1)
            self.assertEqual(newConnections[0][0], key)
            self.assertIdentical(newConnections[0][1], endpoint)
        return d.addCallback(gotConnection)



class CookieTestsMixin(object):
    """
    Mixin for unit tests dealing with cookies.
    """
    def addCookies(self, cookieJar, uri, cookies):
        """
        Add a cookie to a cookie jar.
        """
        response = client._FakeUrllib2Response(
            client.Response(
                (b'HTTP', 1, 1),
                200,
                b'OK',
                client.Headers({b'Set-Cookie': cookies}),
                None))
        request = client._FakeUrllib2Request(uri)
        cookieJar.extract_cookies(response, request)
        return request, response



class CookieJarTests(TestCase, CookieTestsMixin):
    """
    Tests for L{twisted.web.client._FakeUrllib2Response} and
    L{twisted.web.client._FakeUrllib2Request}'s interactions with
    C{cookielib.CookieJar} instances.
    """
    def makeCookieJar(self):
        """
        @return: a C{cookielib.CookieJar} with some sample cookies
        """
        cookieJar = cookielib.CookieJar()
        reqres = self.addCookies(
            cookieJar,
            b'http://example.com:1234/foo?bar',
            [b'foo=1; cow=moo; Path=/foo; Comment=hello',
             b'bar=2; Comment=goodbye'])
        return cookieJar, reqres


    def test_extractCookies(self):
        """
        L{cookielib.CookieJar.extract_cookies} extracts cookie information from
        fake urllib2 response instances.
        """
        jar = self.makeCookieJar()[0]
        cookies = dict([(c.name, c) for c in jar])

        cookie = cookies['foo']
        self.assertEqual(cookie.version, 0)
        self.assertEqual(cookie.name, 'foo')
        self.assertEqual(cookie.value, '1')
        self.assertEqual(cookie.path, '/foo')
        self.assertEqual(cookie.comment, 'hello')
        self.assertEqual(cookie.get_nonstandard_attr('cow'), 'moo')

        cookie = cookies['bar']
        self.assertEqual(cookie.version, 0)
        self.assertEqual(cookie.name, 'bar')
        self.assertEqual(cookie.value, '2')
        self.assertEqual(cookie.path, '/')
        self.assertEqual(cookie.comment, 'goodbye')
        self.assertIdentical(cookie.get_nonstandard_attr('cow'), None)


    def test_sendCookie(self):
        """
        L{cookielib.CookieJar.add_cookie_header} adds a cookie header to a fake
        urllib2 request instance.
        """
        jar, (request, response) = self.makeCookieJar()

        self.assertIdentical(
            request.get_header('Cookie', None),
            None)

        jar.add_cookie_header(request)
        self.assertEqual(
            request.get_header('Cookie', None),
            'foo=1; bar=2')



class CookieAgentTests(TestCase, CookieTestsMixin, FakeReactorAndConnectMixin,
                       AgentTestsMixin):
    """
    Tests for L{twisted.web.client.CookieAgent}.
    """
    def makeAgent(self):
        """
        @return: a new L{twisted.web.client.CookieAgent}
        """
        return client.CookieAgent(
            self.buildAgentForWrapperTest(self.reactor),
            cookielib.CookieJar())


    def setUp(self):
        self.reactor = self.Reactor()


    def test_emptyCookieJarRequest(self):
        """
        L{CookieAgent.request} does not insert any C{'Cookie'} header into the
        L{Request} object if there is no cookie in the cookie jar for the URI
        being requested. Cookies are extracted from the response and stored in
        the cookie jar.
        """
        cookieJar = cookielib.CookieJar()
        self.assertEqual(list(cookieJar), [])

        agent = self.buildAgentForWrapperTest(self.reactor)
        cookieAgent = client.CookieAgent(agent, cookieJar)
        d = cookieAgent.request(
            b'GET', b'http://example.com:1234/foo?bar')

        def _checkCookie(ignored):
            cookies = list(cookieJar)
            self.assertEqual(len(cookies), 1)
            self.assertEqual(cookies[0].name, 'foo')
            self.assertEqual(cookies[0].value, '1')

        d.addCallback(_checkCookie)

        req, res = self.protocol.requests.pop()
        self.assertIdentical(req.headers.getRawHeaders(b'cookie'), None)

        resp = client.Response(
            (b'HTTP', 1, 1),
            200,
            b'OK',
            client.Headers({b'Set-Cookie': [b'foo=1',]}),
            None)
        res.callback(resp)

        return d


    def test_requestWithCookie(self):
        """
        L{CookieAgent.request} inserts a C{'Cookie'} header into the L{Request}
        object when there is a cookie matching the request URI in the cookie
        jar.
        """
        uri = b'http://example.com:1234/foo?bar'
        cookie = b'foo=1'

        cookieJar = cookielib.CookieJar()
        self.addCookies(cookieJar, uri, [cookie])
        self.assertEqual(len(list(cookieJar)), 1)

        agent = self.buildAgentForWrapperTest(self.reactor)
        cookieAgent = client.CookieAgent(agent, cookieJar)
        cookieAgent.request(b'GET', uri)

        req, res = self.protocol.requests.pop()
        self.assertEqual(req.headers.getRawHeaders(b'cookie'), [cookie])


    def test_secureCookie(self):
        """
        L{CookieAgent} is able to handle secure cookies, ie cookies which
        should only be handled over https.
        """
        uri = b'https://example.com:1234/foo?bar'
        cookie = b'foo=1;secure'

        cookieJar = cookielib.CookieJar()
        self.addCookies(cookieJar, uri, [cookie])
        self.assertEqual(len(list(cookieJar)), 1)

        agent = self.buildAgentForWrapperTest(self.reactor)
        cookieAgent = client.CookieAgent(agent, cookieJar)
        cookieAgent.request(b'GET', uri)

        req, res = self.protocol.requests.pop()
        self.assertEqual(req.headers.getRawHeaders(b'cookie'), [b'foo=1'])


    def test_secureCookieOnInsecureConnection(self):
        """
        If a cookie is setup as secure, it won't be sent with the request if
        it's not over HTTPS.
        """
        uri = b'http://example.com/foo?bar'
        cookie = b'foo=1;secure'

        cookieJar = cookielib.CookieJar()
        self.addCookies(cookieJar, uri, [cookie])
        self.assertEqual(len(list(cookieJar)), 1)

        agent = self.buildAgentForWrapperTest(self.reactor)
        cookieAgent = client.CookieAgent(agent, cookieJar)
        cookieAgent.request(b'GET', uri)

        req, res = self.protocol.requests.pop()
        self.assertIdentical(None, req.headers.getRawHeaders(b'cookie'))


    def test_portCookie(self):
        """
        L{CookieAgent} supports cookies which enforces the port number they
        need to be transferred upon.
        """
        uri = b'https://example.com:1234/foo?bar'
        cookie = b'foo=1;port=1234'

        cookieJar = cookielib.CookieJar()
        self.addCookies(cookieJar, uri, [cookie])
        self.assertEqual(len(list(cookieJar)), 1)

        agent = self.buildAgentForWrapperTest(self.reactor)
        cookieAgent = client.CookieAgent(agent, cookieJar)
        cookieAgent.request(b'GET', uri)

        req, res = self.protocol.requests.pop()
        self.assertEqual(req.headers.getRawHeaders(b'cookie'), [b'foo=1'])


    def test_portCookieOnWrongPort(self):
        """
        When creating a cookie with a port directive, it won't be added to the
        L{cookie.CookieJar} if the URI is on a different port.
        """
        uri = b'https://example.com:4567/foo?bar'
        cookie = b'foo=1;port=1234'

        cookieJar = cookielib.CookieJar()
        self.addCookies(cookieJar, uri, [cookie])
        self.assertEqual(len(list(cookieJar)), 0)



class Decoder1(proxyForInterface(IResponse)):
    """
    A test decoder to be used by L{client.ContentDecoderAgent} tests.
    """



class Decoder2(Decoder1):
    """
    A test decoder to be used by L{client.ContentDecoderAgent} tests.
    """



class ContentDecoderAgentTests(TestCase, FakeReactorAndConnectMixin,
                               AgentTestsMixin):
    """
    Tests for L{client.ContentDecoderAgent}.
    """
    def makeAgent(self):
        """
        @return: a new L{twisted.web.client.ContentDecoderAgent}
        """
        return client.ContentDecoderAgent(self.agent, [])


    def setUp(self):
        """
        Create an L{Agent} wrapped around a fake reactor.
        """
        self.reactor = self.Reactor()
        self.agent = self.buildAgentForWrapperTest(self.reactor)


    def test_acceptHeaders(self):
        """
        L{client.ContentDecoderAgent} sets the I{Accept-Encoding} header to the
        names of the available decoder objects.
        """
        agent = client.ContentDecoderAgent(
            self.agent, [(b'decoder1', Decoder1), (b'decoder2', Decoder2)])

        agent.request(b'GET', b'http://example.com/foo')

        protocol = self.protocol

        self.assertEqual(len(protocol.requests), 1)
        req, res = protocol.requests.pop()
        self.assertEqual(req.headers.getRawHeaders(b'accept-encoding'),
                         [b'decoder1,decoder2'])


    def test_existingHeaders(self):
        """
        If there are existing I{Accept-Encoding} fields,
        L{client.ContentDecoderAgent} creates a new field for the decoders it
        knows about.
        """
        headers = http_headers.Headers({b'foo': [b'bar'],
                                        b'accept-encoding': [b'fizz']})
        agent = client.ContentDecoderAgent(
            self.agent, [(b'decoder1', Decoder1), (b'decoder2', Decoder2)])
        agent.request(b'GET', b'http://example.com/foo', headers=headers)

        protocol = self.protocol

        self.assertEqual(len(protocol.requests), 1)
        req, res = protocol.requests.pop()
        self.assertEqual(
            list(sorted(req.headers.getAllRawHeaders())),
            [(b'Accept-Encoding', [b'fizz', b'decoder1,decoder2']),
             (b'Foo', [b'bar']),
             (b'Host', [b'example.com'])])


    def test_plainEncodingResponse(self):
        """
        If the response is not encoded despited the request I{Accept-Encoding}
        headers, L{client.ContentDecoderAgent} simply forwards the response.
        """
        agent = client.ContentDecoderAgent(
            self.agent, [(b'decoder1', Decoder1), (b'decoder2', Decoder2)])
        deferred = agent.request(b'GET', b'http://example.com/foo')

        req, res = self.protocol.requests.pop()

        response = Response((b'HTTP', 1, 1), 200, b'OK', http_headers.Headers(),
                            None)
        res.callback(response)

        return deferred.addCallback(self.assertIdentical, response)


    def test_unsupportedEncoding(self):
        """
        If an encoding unknown to the L{client.ContentDecoderAgent} is found,
        the response is unchanged.
        """
        agent = client.ContentDecoderAgent(
            self.agent, [(b'decoder1', Decoder1), (b'decoder2', Decoder2)])
        deferred = agent.request(b'GET', b'http://example.com/foo')

        req, res = self.protocol.requests.pop()

        headers = http_headers.Headers({b'foo': [b'bar'],
                                        b'content-encoding': [b'fizz']})
        response = Response((b'HTTP', 1, 1), 200, b'OK', headers, None)
        res.callback(response)

        return deferred.addCallback(self.assertIdentical, response)


    def test_unknownEncoding(self):
        """
        When L{client.ContentDecoderAgent} encounters a decoder it doesn't know
        about, it stops decoding even if another encoding is known afterwards.
        """
        agent = client.ContentDecoderAgent(
            self.agent, [(b'decoder1', Decoder1), (b'decoder2', Decoder2)])
        deferred = agent.request(b'GET', b'http://example.com/foo')

        req, res = self.protocol.requests.pop()

        headers = http_headers.Headers({b'foo': [b'bar'],
                                        b'content-encoding':
                                        [b'decoder1,fizz,decoder2']})
        response = Response((b'HTTP', 1, 1), 200, b'OK', headers, None)
        res.callback(response)

        def check(result):
            self.assertNotIdentical(response, result)
            self.assertIsInstance(result, Decoder2)
            self.assertEqual([b'decoder1,fizz'],
                             result.headers.getRawHeaders(b'content-encoding'))

        return deferred.addCallback(check)



class SimpleAgentProtocol(Protocol):
    """
    A L{Protocol} to be used with an L{client.Agent} to receive data.

    @ivar finished: L{Deferred} firing when C{connectionLost} is called.

    @ivar made: L{Deferred} firing when C{connectionMade} is called.

    @ivar received: C{list} of received data.
    """

    def __init__(self):
        self.made = Deferred()
        self.finished = Deferred()
        self.received = []


    def connectionMade(self):
        self.made.callback(None)


    def connectionLost(self, reason):
        self.finished.callback(None)


    def dataReceived(self, data):
        self.received.append(data)



class ContentDecoderAgentWithGzipTests(TestCase,
                                       FakeReactorAndConnectMixin):

    def setUp(self):
        """
        Create an L{Agent} wrapped around a fake reactor.
        """
        self.reactor = self.Reactor()
        agent = self.buildAgentForWrapperTest(self.reactor)
        self.agent = client.ContentDecoderAgent(
            agent, [(b"gzip", client.GzipDecoder)])


    def test_gzipEncodingResponse(self):
        """
        If the response has a C{gzip} I{Content-Encoding} header,
        L{GzipDecoder} wraps the response to return uncompressed data to the
        user.
        """
        deferred = self.agent.request(b'GET', b'http://example.com/foo')

        req, res = self.protocol.requests.pop()

        headers = http_headers.Headers({b'foo': [b'bar'],
                                        b'content-encoding': [b'gzip']})
        transport = StringTransport()
        response = Response((b'HTTP', 1, 1), 200, b'OK', headers, transport)
        response.length = 12
        res.callback(response)

        compressor = zlib.compressobj(2, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
        data = (compressor.compress(b'x' * 6) + compressor.compress(b'y' * 4) +
                compressor.flush())

        def checkResponse(result):
            self.assertNotIdentical(result, response)
            self.assertEqual(result.version, (b'HTTP', 1, 1))
            self.assertEqual(result.code, 200)
            self.assertEqual(result.phrase, b'OK')
            self.assertEqual(list(result.headers.getAllRawHeaders()),
                              [(b'Foo', [b'bar'])])
            self.assertEqual(result.length, UNKNOWN_LENGTH)
            self.assertRaises(AttributeError, getattr, result, 'unknown')

            response._bodyDataReceived(data[:5])
            response._bodyDataReceived(data[5:])
            response._bodyDataFinished()

            protocol = SimpleAgentProtocol()
            result.deliverBody(protocol)

            self.assertEqual(protocol.received, [b'x' * 6 + b'y' * 4])
            return defer.gatherResults([protocol.made, protocol.finished])

        deferred.addCallback(checkResponse)

        return deferred


    def test_brokenContent(self):
        """
        If the data received by the L{GzipDecoder} isn't valid gzip-compressed
        data, the call to C{deliverBody} fails with a C{zlib.error}.
        """
        deferred = self.agent.request(b'GET', b'http://example.com/foo')

        req, res = self.protocol.requests.pop()

        headers = http_headers.Headers({b'foo': [b'bar'],
                                        b'content-encoding': [b'gzip']})
        transport = StringTransport()
        response = Response((b'HTTP', 1, 1), 200, b'OK', headers, transport)
        response.length = 12
        res.callback(response)

        data = b"not gzipped content"

        def checkResponse(result):
            response._bodyDataReceived(data)

            result.deliverBody(Protocol())

        deferred.addCallback(checkResponse)
        self.assertFailure(deferred, client.ResponseFailed)

        def checkFailure(error):
            error.reasons[0].trap(zlib.error)
            self.assertIsInstance(error.response, Response)

        return deferred.addCallback(checkFailure)


    def test_flushData(self):
        """
        When the connection with the server is lost, the gzip protocol calls
        C{flush} on the zlib decompressor object to get uncompressed data which
        may have been buffered.
        """
        class decompressobj(object):

            def __init__(self, wbits):
                pass

            def decompress(self, data):
                return b'x'

            def flush(self):
                return b'y'


        oldDecompressObj = zlib.decompressobj
        zlib.decompressobj = decompressobj
        self.addCleanup(setattr, zlib, 'decompressobj', oldDecompressObj)

        deferred = self.agent.request(b'GET', b'http://example.com/foo')

        req, res = self.protocol.requests.pop()

        headers = http_headers.Headers({b'content-encoding': [b'gzip']})
        transport = StringTransport()
        response = Response((b'HTTP', 1, 1), 200, b'OK', headers, transport)
        res.callback(response)

        def checkResponse(result):
            response._bodyDataReceived(b'data')
            response._bodyDataFinished()

            protocol = SimpleAgentProtocol()
            result.deliverBody(protocol)

            self.assertEqual(protocol.received, [b'x', b'y'])
            return defer.gatherResults([protocol.made, protocol.finished])

        deferred.addCallback(checkResponse)

        return deferred


    def test_flushError(self):
        """
        If the C{flush} call in C{connectionLost} fails, the C{zlib.error}
        exception is caught and turned into a L{ResponseFailed}.
        """
        class decompressobj(object):

            def __init__(self, wbits):
                pass

            def decompress(self, data):
                return b'x'

            def flush(self):
                raise zlib.error()


        oldDecompressObj = zlib.decompressobj
        zlib.decompressobj = decompressobj
        self.addCleanup(setattr, zlib, 'decompressobj', oldDecompressObj)

        deferred = self.agent.request(b'GET', b'http://example.com/foo')

        req, res = self.protocol.requests.pop()

        headers = http_headers.Headers({b'content-encoding': [b'gzip']})
        transport = StringTransport()
        response = Response((b'HTTP', 1, 1), 200, b'OK', headers, transport)
        res.callback(response)

        def checkResponse(result):
            response._bodyDataReceived(b'data')
            response._bodyDataFinished()

            protocol = SimpleAgentProtocol()
            result.deliverBody(protocol)

            self.assertEqual(protocol.received, [b'x', b'y'])
            return defer.gatherResults([protocol.made, protocol.finished])

        deferred.addCallback(checkResponse)

        self.assertFailure(deferred, client.ResponseFailed)

        def checkFailure(error):
            error.reasons[1].trap(zlib.error)
            self.assertIsInstance(error.response, Response)

        return deferred.addCallback(checkFailure)



class ProxyAgentTests(TestCase, FakeReactorAndConnectMixin, AgentTestsMixin):
    """
    Tests for L{client.ProxyAgent}.
    """
    def makeAgent(self):
        """
        @return: a new L{twisted.web.client.ProxyAgent}
        """
        return client.ProxyAgent(
            TCP4ClientEndpoint(self.reactor, "127.0.0.1", 1234),
            self.reactor)


    def setUp(self):
        self.reactor = self.Reactor()
        self.agent = client.ProxyAgent(
            TCP4ClientEndpoint(self.reactor, "bar", 5678), self.reactor)
        oldEndpoint = self.agent._proxyEndpoint
        self.agent._proxyEndpoint = self.StubEndpoint(oldEndpoint, self)


    def test_proxyRequest(self):
        """
        L{client.ProxyAgent} issues an HTTP request against the proxy, with the
        full URI as path, when C{request} is called.
        """
        headers = http_headers.Headers({b'foo': [b'bar']})
        # Just going to check the body for identity, so it doesn't need to be
        # real.
        body = object()
        self.agent.request(
            b'GET', b'http://example.com:1234/foo?bar', headers, body)

        host, port, factory = self.reactor.tcpClients.pop()[:3]
        self.assertEqual(host, "bar")
        self.assertEqual(port, 5678)

        self.assertIsInstance(factory._wrappedFactory,
                              client._HTTP11ClientFactory)

        protocol = self.protocol

        # The request should be issued.
        self.assertEqual(len(protocol.requests), 1)
        req, res = protocol.requests.pop()
        self.assertIsInstance(req, Request)
        self.assertEqual(req.method, b'GET')
        self.assertEqual(req.uri, b'http://example.com:1234/foo?bar')
        self.assertEqual(
            req.headers,
            http_headers.Headers({b'foo': [b'bar'],
                                  b'host': [b'example.com:1234']}))
        self.assertIdentical(req.bodyProducer, body)


    def test_nonPersistent(self):
        """
        C{ProxyAgent} connections are not persistent by default.
        """
        self.assertEqual(self.agent._pool.persistent, False)


    def test_connectUsesConnectionPool(self):
        """
        When a connection is made by the C{ProxyAgent}, it uses its pool's
        C{getConnection} method to do so, with the endpoint it was constructed
        with and a key of C{("http-proxy", endpoint)}.
        """
        endpoint = DummyEndpoint()
        class DummyPool(object):
            connected = False
            persistent = False
            def getConnection(this, key, ep):
                this.connected = True
                self.assertIdentical(ep, endpoint)
                # The key is *not* tied to the final destination, but only to
                # the address of the proxy, since that's where *we* are
                # connecting:
                self.assertEqual(key, ("http-proxy", endpoint))
                return defer.succeed(StubHTTPProtocol())

        pool = DummyPool()
        agent = client.ProxyAgent(endpoint, self.reactor, pool=pool)
        self.assertIdentical(pool, agent._pool)

        agent.request(b'GET', b'http://foo/')
        self.assertEqual(agent._pool.connected, True)



class _RedirectAgentTestsMixin(object):
    """
    Test cases mixin for L{RedirectAgentTests} and
    L{BrowserLikeRedirectAgentTests}.
    """
    def test_noRedirect(self):
        """
        L{client.RedirectAgent} behaves like L{client.Agent} if the response
        doesn't contain a redirect.
        """
        deferred = self.agent.request(b'GET', b'http://example.com/foo')

        req, res = self.protocol.requests.pop()

        headers = http_headers.Headers()
        response = Response((b'HTTP', 1, 1), 200, b'OK', headers, None)
        res.callback(response)

        self.assertEqual(0, len(self.protocol.requests))
        result = self.successResultOf(deferred)
        self.assertIdentical(response, result)
        self.assertIdentical(result.previousResponse, None)


    def _testRedirectDefault(self, code):
        """
        When getting a redirect, L{client.RedirectAgent} follows the URL
        specified in the L{Location} header field and make a new request.

        @param code: HTTP status code.
        """
        self.agent.request(b'GET', b'http://example.com/foo')

        host, port = self.reactor.tcpClients.pop()[:2]
        self.assertEqual("example.com", host)
        self.assertEqual(80, port)

        req, res = self.protocol.requests.pop()

        headers = http_headers.Headers(
            {b'location': [b'https://example.com/bar']})
        response = Response((b'HTTP', 1, 1), code, b'OK', headers, None)
        res.callback(response)

        req2, res2 = self.protocol.requests.pop()
        self.assertEqual(b'GET', req2.method)
        self.assertEqual(b'/bar', req2.uri)

        host, port = self.reactor.sslClients.pop()[:2]
        self.assertEqual("example.com", host)
        self.assertEqual(443, port)


    def test_redirect301(self):
        """
        L{client.RedirectAgent} follows redirects on status code 301.
        """
        self._testRedirectDefault(301)


    def test_redirect302(self):
        """
        L{client.RedirectAgent} follows redirects on status code 302.
        """
        self._testRedirectDefault(302)


    def test_redirect307(self):
        """
        L{client.RedirectAgent} follows redirects on status code 307.
        """
        self._testRedirectDefault(307)


    def _testRedirectToGet(self, code, method):
        """
        L{client.RedirectAgent} changes the method to I{GET} when getting
        a redirect on a non-I{GET} request.

        @param code: HTTP status code.

        @param method: HTTP request method.
        """
        self.agent.request(method, b'http://example.com/foo')

        req, res = self.protocol.requests.pop()

        headers = http_headers.Headers(
            {b'location': [b'http://example.com/bar']})
        response = Response((b'HTTP', 1, 1), code, b'OK', headers, None)
        res.callback(response)

        req2, res2 = self.protocol.requests.pop()
        self.assertEqual(b'GET', req2.method)
        self.assertEqual(b'/bar', req2.uri)


    def test_redirect303(self):
        """
        L{client.RedirectAgent} changes the method to I{GET} when getting a 303
        redirect on a I{POST} request.
        """
        self._testRedirectToGet(303, b'POST')


    def test_noLocationField(self):
        """
        If no L{Location} header field is found when getting a redirect,
        L{client.RedirectAgent} fails with a L{ResponseFailed} error wrapping a
        L{error.RedirectWithNoLocation} exception.
        """
        deferred = self.agent.request(b'GET', b'http://example.com/foo')

        req, res = self.protocol.requests.pop()

        headers = http_headers.Headers()
        response = Response((b'HTTP', 1, 1), 301, b'OK', headers, None)
        res.callback(response)

        fail = self.failureResultOf(deferred, client.ResponseFailed)
        fail.value.reasons[0].trap(error.RedirectWithNoLocation)
        self.assertEqual(b'http://example.com/foo',
                         fail.value.reasons[0].value.uri)
        self.assertEqual(301, fail.value.response.code)


    def _testPageRedirectFailure(self, code, method):
        """
        When getting a redirect on an unsupported request method,
        L{client.RedirectAgent} fails with a L{ResponseFailed} error wrapping
        a L{error.PageRedirect} exception.

        @param code: HTTP status code.

        @param method: HTTP request method.
        """
        deferred = self.agent.request(method, b'http://example.com/foo')

        req, res = self.protocol.requests.pop()

        headers = http_headers.Headers()
        response = Response((b'HTTP', 1, 1), code, b'OK', headers, None)
        res.callback(response)

        fail = self.failureResultOf(deferred, client.ResponseFailed)
        fail.value.reasons[0].trap(error.PageRedirect)
        self.assertEqual(b'http://example.com/foo',
                         fail.value.reasons[0].value.location)
        self.assertEqual(code, fail.value.response.code)


    def test_307OnPost(self):
        """
        When getting a 307 redirect on a I{POST} request,
        L{client.RedirectAgent} fails with a L{ResponseFailed} error wrapping
        a L{error.PageRedirect} exception.
        """
        self._testPageRedirectFailure(307, b'POST')


    def test_redirectLimit(self):
        """
        If the limit of redirects specified to L{client.RedirectAgent} is
        reached, the deferred fires with L{ResponseFailed} error wrapping
        a L{InfiniteRedirection} exception.
        """
        agent = self.buildAgentForWrapperTest(self.reactor)
        redirectAgent = client.RedirectAgent(agent, 1)

        deferred = redirectAgent.request(b'GET', b'http://example.com/foo')

        req, res = self.protocol.requests.pop()

        headers = http_headers.Headers(
            {b'location': [b'http://example.com/bar']})
        response = Response((b'HTTP', 1, 1), 302, b'OK', headers, None)
        res.callback(response)

        req2, res2 = self.protocol.requests.pop()

        response2 = Response((b'HTTP', 1, 1), 302, b'OK', headers, None)
        res2.callback(response2)

        fail = self.failureResultOf(deferred, client.ResponseFailed)

        fail.value.reasons[0].trap(error.InfiniteRedirection)
        self.assertEqual(b'http://example.com/foo',
                         fail.value.reasons[0].value.location)
        self.assertEqual(302, fail.value.response.code)


    def _testRedirectURI(self, uri, location, finalURI):
        """
        When L{client.RedirectAgent} encounters a relative redirect I{URI}, it
        is resolved against the request I{URI} before following the redirect.

        @param uri: Request URI.

        @param location: I{Location} header redirect URI.

        @param finalURI: Expected final URI.
        """
        self.agent.request(b'GET', uri)

        req, res = self.protocol.requests.pop()

        headers = http_headers.Headers(
            {b'location': [location]})
        response = Response((b'HTTP', 1, 1), 302, b'OK', headers, None)
        res.callback(response)

        req2, res2 = self.protocol.requests.pop()
        self.assertEqual(b'GET', req2.method)
        self.assertEqual(finalURI, req2.absoluteURI)


    def test_relativeURI(self):
        """
        L{client.RedirectAgent} resolves and follows relative I{URI}s in
        redirects, preserving query strings.
        """
        self._testRedirectURI(
            b'http://example.com/foo/bar', b'baz',
            b'http://example.com/foo/baz')
        self._testRedirectURI(
            b'http://example.com/foo/bar', b'/baz',
            b'http://example.com/baz')
        self._testRedirectURI(
            b'http://example.com/foo/bar', b'/baz?a',
            b'http://example.com/baz?a')


    def test_relativeURIPreserveFragments(self):
        """
        L{client.RedirectAgent} resolves and follows relative I{URI}s in
        redirects, preserving fragments in way that complies with the HTTP 1.1
        bis draft.

        @see: U{https://tools.ietf.org/html/draft-ietf-httpbis-p2-semantics-22#section-7.1.2}
        """
        self._testRedirectURI(
            b'http://example.com/foo/bar#frag', b'/baz?a',
            b'http://example.com/baz?a#frag')
        self._testRedirectURI(
            b'http://example.com/foo/bar', b'/baz?a#frag2',
            b'http://example.com/baz?a#frag2')


    def test_relativeURISchemeRelative(self):
        """
        L{client.RedirectAgent} resolves and follows scheme relative I{URI}s in
        redirects, replacing the hostname and port when required.
        """
        self._testRedirectURI(
            b'http://example.com/foo/bar', b'//foo.com/baz',
            b'http://foo.com/baz')
        self._testRedirectURI(
            b'http://example.com/foo/bar', b'//foo.com:81/baz',
            b'http://foo.com:81/baz')


    def test_responseHistory(self):
        """
        L{Response.response} references the previous L{Response} from
        a redirect, or L{None} if there was no previous response.
        """
        agent = self.buildAgentForWrapperTest(self.reactor)
        redirectAgent = client.RedirectAgent(agent)

        deferred = redirectAgent.request(b'GET', b'http://example.com/foo')

        redirectReq, redirectRes = self.protocol.requests.pop()

        headers = http_headers.Headers(
            {b'location': [b'http://example.com/bar']})
        redirectResponse = Response((b'HTTP', 1, 1), 302, b'OK', headers, None)
        redirectRes.callback(redirectResponse)

        req, res = self.protocol.requests.pop()

        response = Response((b'HTTP', 1, 1), 200, b'OK', headers, None)
        res.callback(response)

        finalResponse = self.successResultOf(deferred)
        self.assertIdentical(finalResponse.previousResponse, redirectResponse)
        self.assertIdentical(redirectResponse.previousResponse, None)



class RedirectAgentTests(TestCase, FakeReactorAndConnectMixin,
                         _RedirectAgentTestsMixin, AgentTestsMixin):
    """
    Tests for L{client.RedirectAgent}.
    """
    def makeAgent(self):
        """
        @return: a new L{twisted.web.client.RedirectAgent}
        """
        return client.RedirectAgent(
            self.buildAgentForWrapperTest(self.reactor))


    def setUp(self):
        self.reactor = self.Reactor()
        self.agent = self.makeAgent()


    def test_301OnPost(self):
        """
        When getting a 301 redirect on a I{POST} request,
        L{client.RedirectAgent} fails with a L{ResponseFailed} error wrapping
        a L{error.PageRedirect} exception.
        """
        self._testPageRedirectFailure(301, b'POST')


    def test_302OnPost(self):
        """
        When getting a 302 redirect on a I{POST} request,
        L{client.RedirectAgent} fails with a L{ResponseFailed} error wrapping
        a L{error.PageRedirect} exception.
        """
        self._testPageRedirectFailure(302, b'POST')



class BrowserLikeRedirectAgentTests(TestCase,
                                    FakeReactorAndConnectMixin,
                                    _RedirectAgentTestsMixin,
                                    AgentTestsMixin):
    """
    Tests for L{client.BrowserLikeRedirectAgent}.
    """
    def makeAgent(self):
        """
        @return: a new L{twisted.web.client.BrowserLikeRedirectAgent}
        """
        return client.BrowserLikeRedirectAgent(
            self.buildAgentForWrapperTest(self.reactor))


    def setUp(self):
        self.reactor = self.Reactor()
        self.agent = self.makeAgent()


    def test_redirectToGet301(self):
        """
        L{client.BrowserLikeRedirectAgent} changes the method to I{GET} when
        getting a 302 redirect on a I{POST} request.
        """
        self._testRedirectToGet(301, b'POST')


    def test_redirectToGet302(self):
        """
        L{client.BrowserLikeRedirectAgent} changes the method to I{GET} when
        getting a 302 redirect on a I{POST} request.
        """
        self._testRedirectToGet(302, b'POST')



class AbortableStringTransport(StringTransport):
    """
    A version of L{StringTransport} that supports C{abortConnection}.
    """
    # This should be replaced by a common version in #6530.
    aborting = False


    def abortConnection(self):
        """
        A testable version of the C{ITCPTransport.abortConnection} method.

        Since this is a special case of closing the connection,
        C{loseConnection} is also called.
        """
        self.aborting = True
        self.loseConnection()



class DummyResponse(object):
    """
    Fake L{IResponse} for testing readBody that captures the protocol passed to
    deliverBody and uses it to make a connection with a transport.

    @ivar protocol: After C{deliverBody} is called, the protocol it was called
        with.

    @ivar transport: An instance created by calling C{transportFactory} which
        is used by L{DummyResponse.protocol} to make a connection.
    """

    code = 200
    phrase = b"OK"

    def __init__(self, headers=None, transportFactory=AbortableStringTransport):
        """
        @param headers: The headers for this response.  If L{None}, an empty
            L{Headers} instance will be used.
        @type headers: L{Headers}

        @param transportFactory: A callable used to construct the transport.
        """
        if headers is None:
            headers = Headers()
        self.headers = headers
        self.transport = transportFactory()


    def deliverBody(self, protocol):
        """
        Record the given protocol and use it to make a connection with
        L{DummyResponse.transport}.
        """
        self.protocol = protocol
        self.protocol.makeConnection(self.transport)



class AlreadyCompletedDummyResponse(DummyResponse):
    """
    A dummy response that has already had its transport closed.
    """
    def deliverBody(self, protocol):
        """
        Make the connection, then remove the transport.
        """
        self.protocol = protocol
        self.protocol.makeConnection(self.transport)
        self.protocol.transport = None



class ReadBodyTests(TestCase):
    """
    Tests for L{client.readBody}
    """
    def test_success(self):
        """
        L{client.readBody} returns a L{Deferred} which fires with the complete
        body of the L{IResponse} provider passed to it.
        """
        response = DummyResponse()
        d = client.readBody(response)
        response.protocol.dataReceived(b"first")
        response.protocol.dataReceived(b"second")
        response.protocol.connectionLost(Failure(ResponseDone()))
        self.assertEqual(self.successResultOf(d), b"firstsecond")


    def test_cancel(self):
        """
        When cancelling the L{Deferred} returned by L{client.readBody}, the
        connection to the server will be aborted.
        """
        response = DummyResponse()
        deferred = client.readBody(response)
        deferred.cancel()
        self.failureResultOf(deferred, defer.CancelledError)
        self.assertTrue(response.transport.aborting)


    def test_withPotentialDataLoss(self):
        """
        If the full body of the L{IResponse} passed to L{client.readBody} is
        not definitely received, the L{Deferred} returned by L{client.readBody}
        fires with a L{Failure} wrapping L{client.PartialDownloadError} with
        the content that was received.
        """
        response = DummyResponse()
        d = client.readBody(response)
        response.protocol.dataReceived(b"first")
        response.protocol.dataReceived(b"second")
        response.protocol.connectionLost(Failure(PotentialDataLoss()))
        failure = self.failureResultOf(d)
        failure.trap(client.PartialDownloadError)
        self.assertEqual({
            "status": failure.value.status,
            "message": failure.value.message,
            "body": failure.value.response,
        }, {
            "status": b"200",
            "message": b"OK",
            "body": b"firstsecond",
        })


    def test_otherErrors(self):
        """
        If there is an exception other than L{client.PotentialDataLoss} while
        L{client.readBody} is collecting the response body, the L{Deferred}
        returned by {client.readBody} fires with that exception.
        """
        response = DummyResponse()
        d = client.readBody(response)
        response.protocol.dataReceived(b"first")
        response.protocol.connectionLost(
            Failure(ConnectionLost("mystery problem")))
        reason = self.failureResultOf(d)
        reason.trap(ConnectionLost)
        self.assertEqual(reason.value.args, ("mystery problem",))


    def test_deprecatedTransport(self):
        """
        Calling L{client.readBody} with a transport that does not implement
        L{twisted.internet.interfaces.ITCPTransport} produces a deprecation
        warning, but no exception when cancelling.
        """
        response = DummyResponse(transportFactory=StringTransport)
        response.transport.abortConnection = None
        d = self.assertWarns(
            DeprecationWarning,
            'Using readBody with a transport that does not have an '
            'abortConnection method',
            __file__,
            lambda: client.readBody(response))
        d.cancel()
        self.failureResultOf(d, defer.CancelledError)


    def test_deprecatedTransportNoWarning(self):
        """
        Calling L{client.readBody} with a response that has already had its
        transport closed (eg. for a very small request) will not trigger a
        deprecation warning.
        """
        response = AlreadyCompletedDummyResponse()
        client.readBody(response)

        warnings = self.flushWarnings()
        self.assertEqual(len(warnings), 0)
