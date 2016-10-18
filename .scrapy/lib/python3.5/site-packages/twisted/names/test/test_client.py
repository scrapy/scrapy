# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.names.client}.
"""

from __future__ import division, absolute_import

from zope.interface.verify import verifyClass, verifyObject

from twisted.python import failure
from twisted.python.filepath import FilePath
from twisted.python.runtime import platform

from twisted.internet import defer
from twisted.internet.error import CannotListenError, ConnectionRefusedError
from twisted.internet.interfaces import IResolver
from twisted.internet.test.modulehelpers import AlternateReactor
from twisted.internet.task import Clock

from twisted.names import error, client, dns, hosts, cache
from twisted.names.error import DNSQueryTimeoutError
from twisted.names.common import ResolverBase

from twisted.names.test.test_hosts import GoodTempPathMixin
from twisted.names.test.test_util import MemoryReactor

from twisted.test import proto_helpers

from twisted.trial import unittest

if platform.isWindows():
    windowsSkip = "These tests need more work before they'll work on Windows."
else:
    windowsSkip = None



class FakeResolver(ResolverBase):

    def _lookup(self, name, cls, qtype, timeout):
        """
        The getHostByNameTest does a different type of query that requires it
        return an A record from an ALL_RECORDS lookup, so we accommodate that
        here.
        """
        if name == b'getHostByNameTest':
            rr = dns.RRHeader(name=name, type=dns.A, cls=cls, ttl=60,
                    payload=dns.Record_A(address='127.0.0.1', ttl=60))
        else:
            rr = dns.RRHeader(name=name, type=qtype, cls=cls, ttl=60)

        results = [rr]
        authority = []
        addtional = []
        return defer.succeed((results, authority, addtional))



class StubPort(object):
    """
    A partial implementation of L{IListeningPort} which only keeps track of
    whether it has been stopped.

    @ivar disconnected: A C{bool} which is C{False} until C{stopListening} is
        called, C{True} afterwards.
    """
    disconnected = False

    def stopListening(self):
        self.disconnected = True



class StubDNSDatagramProtocol(object):
    """
    L{dns.DNSDatagramProtocol}-alike.

    @ivar queries: A C{list} of tuples giving the arguments passed to
        C{query} along with the L{defer.Deferred} which was returned from
        the call.
    """
    def __init__(self):
        self.queries = []
        self.transport = StubPort()


    def query(self, address, queries, timeout=10, id=None):
        """
        Record the given arguments and return a Deferred which will not be
        called back by this code.
        """
        result = defer.Deferred()
        self.queries.append((address, queries, timeout, id, result))
        return result



class GetResolverTests(unittest.TestCase):
    """
    Tests for L{client.getResolver}.
    """
    if windowsSkip:
        skip = windowsSkip

    def test_interface(self):
        """
        L{client.getResolver} returns an object providing L{IResolver}.
        """
        with AlternateReactor(Clock()):
            resolver = client.getResolver()
        self.assertTrue(verifyObject(IResolver, resolver))


    def test_idempotent(self):
        """
        Multiple calls to L{client.getResolver} return the same L{IResolver}
        implementation.
        """
        with AlternateReactor(Clock()):
            a = client.getResolver()
            b = client.getResolver()
        self.assertIs(a, b)



class CreateResolverTests(unittest.TestCase, GoodTempPathMixin):
    """
    Tests for L{client.createResolver}.
    """
    if windowsSkip:
        skip = windowsSkip

    def _hostsTest(self, resolver, filename):
        res = [r for r in resolver.resolvers if isinstance(r, hosts.Resolver)]
        self.assertEqual(1, len(res))
        self.assertEqual(res[0].file, filename)


    def test_defaultHosts(self):
        """
        L{client.createResolver} returns a L{resolve.ResolverChain} including a
        L{hosts.Resolver} using I{/etc/hosts} if no alternate hosts file is
        specified.
        """
        with AlternateReactor(Clock()):
            resolver = client.createResolver()
        self._hostsTest(resolver, b"/etc/hosts")


    def test_overrideHosts(self):
        """
        The I{hosts} parameter to L{client.createResolver} overrides the hosts
        file used by the L{hosts.Resolver} in the L{resolve.ResolverChain} it
        returns.
        """
        with AlternateReactor(Clock()):
            resolver = client.createResolver(hosts=b"/foo/bar")
        self._hostsTest(resolver, b"/foo/bar")


    def _resolvConfTest(self, resolver, filename):
        """
        Verify that C{resolver} has a L{client.Resolver} with a configuration
        filename set to C{filename}.
        """
        res = [r for r in resolver.resolvers if isinstance(r, client.Resolver)]
        self.assertEqual(1, len(res))
        self.assertEqual(res[0].resolv, filename)


    def test_reactor(self):
        """
        The L{client.Resolver} included in the L{resolve.ResolverChain} returned
        by L{client.createResolver} uses the global reactor.
        """
        reactor = Clock()
        with AlternateReactor(reactor):
            resolver = client.createResolver()
        res = [r for r in resolver.resolvers if isinstance(r, client.Resolver)]
        self.assertEqual(1, len(res))
        self.assertIs(reactor, res[0]._reactor)


    def test_defaultResolvConf(self):
        """
        L{client.createResolver} returns a L{resolve.ResolverChain} including a
        L{client.Resolver} using I{/etc/resolv.conf} if no alternate resolver
        configuration file is specified.
        """
        with AlternateReactor(Clock()):
            resolver = client.createResolver()
        self._resolvConfTest(resolver, b"/etc/resolv.conf")


    def test_overrideResolvConf(self):
        """
        The I{resolvconf} parameter to L{client.createResolver} overrides the
        resolver configuration file used by the L{client.Resolver} in the
        L{resolve.ResolverChain} it returns.
        """
        with AlternateReactor(Clock()):
            resolver = client.createResolver(resolvconf=b"/foo/bar")
        self._resolvConfTest(resolver, b"/foo/bar")


    def test_defaultServers(self):
        """
        If no servers are given, addresses are taken from the file given by the
        I{resolvconf} parameter to L{client.createResolver}.
        """
        resolvconf = self.path()
        resolvconf.setContent(b"nameserver 127.1.2.3\n")
        with AlternateReactor(Clock()):
            resolver = client.createResolver(resolvconf=resolvconf.path)
        res = [r for r in resolver.resolvers if isinstance(r, client.Resolver)]
        self.assertEqual(1, len(res))
        self.assertEqual([], res[0].servers)
        self.assertEqual([("127.1.2.3", 53)], res[0].dynServers)


    def test_overrideServers(self):
        """
        Servers passed to L{client.createResolver} are used in addition to any
        found in the file given by the I{resolvconf} parameter.
        """
        resolvconf = self.path()
        resolvconf.setContent(b"nameserver 127.1.2.3\n")
        with AlternateReactor(Clock()):
            resolver = client.createResolver(
                servers=[("127.3.2.1", 53)], resolvconf=resolvconf.path)
        res = [r for r in resolver.resolvers if isinstance(r, client.Resolver)]
        self.assertEqual(1, len(res))
        self.assertEqual([("127.3.2.1", 53)], res[0].servers)
        self.assertEqual([("127.1.2.3", 53)], res[0].dynServers)


    def test_cache(self):
        """
        L{client.createResolver} returns a L{resolve.ResolverChain} including a
        L{cache.CacheResolver}.
        """
        with AlternateReactor(Clock()):
            resolver = client.createResolver()
        res = [r for r in resolver.resolvers if isinstance(r, cache.CacheResolver)]
        self.assertEqual(1, len(res))




class ResolverTests(unittest.TestCase):
    """
    Tests for L{client.Resolver}.
    """

    def test_clientProvidesIResolver(self):
        """
        L{client} provides L{IResolver} through a series of free
        functions.
        """
        verifyObject(IResolver, client)


    def test_clientResolverProvidesIResolver(self):
        """
        L{client.Resolver} provides L{IResolver}.
        """
        verifyClass(IResolver, client.Resolver)


    def test_noServers(self):
        """
        L{client.Resolver} raises L{ValueError} if constructed with neither
        servers nor a nameserver configuration file.
        """
        self.assertRaises(ValueError, client.Resolver)


    def test_missingConfiguration(self):
        """
        A missing nameserver configuration file results in no server information
        being loaded from it (ie, not an exception) and a default server being
        provided.
        """
        resolver = client.Resolver(resolv=self.mktemp(), reactor=Clock())
        self.assertEqual([("127.0.0.1", 53)], resolver.dynServers)


    def test_closesResolvConf(self):
        """
        As part of its constructor, C{StubResolver} opens C{/etc/resolv.conf};
        then, explicitly closes it and does not count on the GC to do so for
        it.
        """
        handle = FilePath(self.mktemp())
        resolvConf = handle.open(mode='w+')
        class StubResolver(client.Resolver):
            def _openFile(self, name):
                return resolvConf
        StubResolver(servers=["example.com", 53], resolv='/etc/resolv.conf',
                     reactor=Clock())
        self.assertTrue(resolvConf.closed)


    def test_domainEmptyArgument(self):
        """
        L{client.Resolver.parseConfig} treats a I{domain} line without an
        argument as indicating a domain of C{b""}.
        """
        resolver = client.Resolver(servers=[("127.0.0.1", 53)])
        resolver.parseConfig([b"domain\n"])
        self.assertEqual(b"", resolver.domain)


    def test_searchEmptyArgument(self):
        """
        L{client.Resolver.parseConfig} treats a I{search} line without an
        argument as indicating an empty search suffix.
        """
        resolver = client.Resolver(servers=[("127.0.0.1", 53)])
        resolver.parseConfig([b"search\n"])
        self.assertEqual([], resolver.search)


    def test_datagramQueryServerOrder(self):
        """
        L{client.Resolver.queryUDP} should issue queries to its
        L{dns.DNSDatagramProtocol} with server addresses taken from its own
        C{servers} and C{dynServers} lists, proceeding through them in order
        as L{DNSQueryTimeoutError}s occur.
        """
        protocol = StubDNSDatagramProtocol()

        servers = [object(), object()]
        dynServers = [object(), object()]
        resolver = client.Resolver(servers=servers)
        resolver.dynServers = dynServers
        resolver._connectedProtocol = lambda: protocol

        expectedResult = object()
        queryResult = resolver.queryUDP(None)
        queryResult.addCallback(self.assertEqual, expectedResult)

        self.assertEqual(len(protocol.queries), 1)
        self.assertIs(protocol.queries[0][0], servers[0])
        protocol.queries[0][-1].errback(DNSQueryTimeoutError(0))
        self.assertEqual(len(protocol.queries), 2)
        self.assertIs(protocol.queries[1][0], servers[1])
        protocol.queries[1][-1].errback(DNSQueryTimeoutError(1))
        self.assertEqual(len(protocol.queries), 3)
        self.assertIs(protocol.queries[2][0], dynServers[0])
        protocol.queries[2][-1].errback(DNSQueryTimeoutError(2))
        self.assertEqual(len(protocol.queries), 4)
        self.assertIs(protocol.queries[3][0], dynServers[1])
        protocol.queries[3][-1].callback(expectedResult)

        return queryResult


    def test_singleConcurrentRequest(self):
        """
        L{client.Resolver.query} only issues one request at a time per query.
        Subsequent requests made before responses to prior ones are received
        are queued and given the same response as is given to the first one.
        """
        protocol = StubDNSDatagramProtocol()
        resolver = client.Resolver(servers=[('example.com', 53)])
        resolver._connectedProtocol = lambda: protocol
        queries = protocol.queries

        query = dns.Query(b'foo.example.com', dns.A, dns.IN)
        # The first query should be passed to the underlying protocol.
        firstResult = resolver.query(query)
        self.assertEqual(len(queries), 1)

        # The same query again should not be passed to the underlying protocol.
        secondResult = resolver.query(query)
        self.assertEqual(len(queries), 1)

        # The response to the first query should be sent in response to both
        # queries.
        answer = object()
        response = dns.Message()
        response.answers.append(answer)
        queries.pop()[-1].callback(response)

        d = defer.gatherResults([firstResult, secondResult])
        def cbFinished(responses):
            firstResponse, secondResponse = responses
            self.assertEqual(firstResponse, ([answer], [], []))
            self.assertEqual(secondResponse, ([answer], [], []))
        d.addCallback(cbFinished)
        return d


    def test_multipleConcurrentRequests(self):
        """
        L{client.Resolver.query} issues a request for each different concurrent
        query.
        """
        protocol = StubDNSDatagramProtocol()
        resolver = client.Resolver(servers=[('example.com', 53)])
        resolver._connectedProtocol = lambda: protocol
        queries = protocol.queries

        # The first query should be passed to the underlying protocol.
        firstQuery = dns.Query(b'foo.example.com', dns.A)
        resolver.query(firstQuery)
        self.assertEqual(len(queries), 1)

        # A query for a different name is also passed to the underlying
        # protocol.
        secondQuery = dns.Query(b'bar.example.com', dns.A)
        resolver.query(secondQuery)
        self.assertEqual(len(queries), 2)

        # A query for a different type is also passed to the underlying
        # protocol.
        thirdQuery = dns.Query(b'foo.example.com', dns.A6)
        resolver.query(thirdQuery)
        self.assertEqual(len(queries), 3)


    def test_multipleSequentialRequests(self):
        """
        After a response is received to a query issued with
        L{client.Resolver.query}, another query with the same parameters
        results in a new network request.
        """
        protocol = StubDNSDatagramProtocol()
        resolver = client.Resolver(servers=[('example.com', 53)])
        resolver._connectedProtocol = lambda: protocol
        queries = protocol.queries

        query = dns.Query(b'foo.example.com', dns.A)

        # The first query should be passed to the underlying protocol.
        resolver.query(query)
        self.assertEqual(len(queries), 1)

        # Deliver the response.
        queries.pop()[-1].callback(dns.Message())

        # Repeating the first query should touch the protocol again.
        resolver.query(query)
        self.assertEqual(len(queries), 1)


    def test_multipleConcurrentFailure(self):
        """
        If the result of a request is an error response, the Deferreds for all
        concurrently issued requests associated with that result fire with the
        L{Failure}.
        """
        protocol = StubDNSDatagramProtocol()
        resolver = client.Resolver(servers=[('example.com', 53)])
        resolver._connectedProtocol = lambda: protocol
        queries = protocol.queries

        query = dns.Query(b'foo.example.com', dns.A)
        firstResult = resolver.query(query)
        secondResult = resolver.query(query)

        class ExpectedException(Exception):
            pass

        queries.pop()[-1].errback(failure.Failure(ExpectedException()))

        return defer.gatherResults([
                self.assertFailure(firstResult, ExpectedException),
                self.assertFailure(secondResult, ExpectedException)])


    def test_connectedProtocol(self):
        """
        L{client.Resolver._connectedProtocol} returns a new
        L{DNSDatagramProtocol} connected to a new address with a
        cryptographically secure random port number.
        """
        resolver = client.Resolver(servers=[('example.com', 53)])
        firstProto = resolver._connectedProtocol()
        secondProto = resolver._connectedProtocol()

        self.assertIsNotNone(firstProto.transport)
        self.assertIsNotNone(secondProto.transport)
        self.assertNotEqual(
            firstProto.transport.getHost().port,
            secondProto.transport.getHost().port)

        return defer.gatherResults([
                defer.maybeDeferred(firstProto.transport.stopListening),
                defer.maybeDeferred(secondProto.transport.stopListening)])


    def test_resolverUsesOnlyParameterizedReactor(self):
        """
        If a reactor instance is supplied to L{client.Resolver}
        L{client.Resolver._connectedProtocol} should pass that reactor
        to L{twisted.names.dns.DNSDatagramProtocol}.
        """
        reactor = MemoryReactor()
        resolver = client.Resolver(resolv=self.mktemp(), reactor=reactor)
        proto = resolver._connectedProtocol()
        self.assertIs(proto._reactor, reactor)


    def test_differentProtocol(self):
        """
        L{client.Resolver._connectedProtocol} is called once each time a UDP
        request needs to be issued and the resulting protocol instance is used
        for that request.
        """
        resolver = client.Resolver(servers=[('example.com', 53)])
        protocols = []

        class FakeProtocol(object):
            def __init__(self):
                self.transport = StubPort()

            def query(self, address, query, timeout=10, id=None):
                protocols.append(self)
                return defer.succeed(dns.Message())

        resolver._connectedProtocol = FakeProtocol
        resolver.query(dns.Query(b'foo.example.com'))
        resolver.query(dns.Query(b'bar.example.com'))
        self.assertEqual(len(set(protocols)), 2)


    def test_disallowedPort(self):
        """
        If a port number is initially selected which cannot be bound, the
        L{CannotListenError} is handled and another port number is attempted.
        """
        ports = []

        class FakeReactor(object):
            def listenUDP(self, port, *args):
                ports.append(port)
                if len(ports) == 1:
                    raise CannotListenError(None, port, None)

        resolver = client.Resolver(servers=[('example.com', 53)])
        resolver._reactor = FakeReactor()

        resolver._connectedProtocol()
        self.assertEqual(len(set(ports)), 2)


    def test_differentProtocolAfterTimeout(self):
        """
        When a query issued by L{client.Resolver.query} times out, the retry
        uses a new protocol instance.
        """
        resolver = client.Resolver(servers=[('example.com', 53)])
        protocols = []
        results = [defer.fail(failure.Failure(DNSQueryTimeoutError(None))),
                   defer.succeed(dns.Message())]

        class FakeProtocol(object):
            def __init__(self):
                self.transport = StubPort()

            def query(self, address, query, timeout=10, id=None):
                protocols.append(self)
                return results.pop(0)

        resolver._connectedProtocol = FakeProtocol
        resolver.query(dns.Query(b'foo.example.com'))
        self.assertEqual(len(set(protocols)), 2)


    def test_protocolShutDown(self):
        """
        After the L{Deferred} returned by L{DNSDatagramProtocol.query} is
        called back, the L{DNSDatagramProtocol} is disconnected from its
        transport.
        """
        resolver = client.Resolver(servers=[('example.com', 53)])
        protocols = []
        result = defer.Deferred()

        class FakeProtocol(object):
            def __init__(self):
                self.transport = StubPort()

            def query(self, address, query, timeout=10, id=None):
                protocols.append(self)
                return result

        resolver._connectedProtocol = FakeProtocol
        resolver.query(dns.Query(b'foo.example.com'))

        self.assertFalse(protocols[0].transport.disconnected)
        result.callback(dns.Message())
        self.assertTrue(protocols[0].transport.disconnected)


    def test_protocolShutDownAfterTimeout(self):
        """
        The L{DNSDatagramProtocol} created when an interim timeout occurs is
        also disconnected from its transport after the Deferred returned by its
        query method completes.
        """
        resolver = client.Resolver(servers=[('example.com', 53)])
        protocols = []
        result = defer.Deferred()
        results = [defer.fail(failure.Failure(DNSQueryTimeoutError(None))),
                   result]

        class FakeProtocol(object):
            def __init__(self):
                self.transport = StubPort()

            def query(self, address, query, timeout=10, id=None):
                protocols.append(self)
                return results.pop(0)

        resolver._connectedProtocol = FakeProtocol
        resolver.query(dns.Query(b'foo.example.com'))

        self.assertFalse(protocols[1].transport.disconnected)
        result.callback(dns.Message())
        self.assertTrue(protocols[1].transport.disconnected)


    def test_protocolShutDownAfterFailure(self):
        """
        If the L{Deferred} returned by L{DNSDatagramProtocol.query} fires with
        a failure, the L{DNSDatagramProtocol} is still disconnected from its
        transport.
        """
        class ExpectedException(Exception):
            pass

        resolver = client.Resolver(servers=[('example.com', 53)])
        protocols = []
        result = defer.Deferred()

        class FakeProtocol(object):
            def __init__(self):
                self.transport = StubPort()

            def query(self, address, query, timeout=10, id=None):
                protocols.append(self)
                return result

        resolver._connectedProtocol = FakeProtocol
        queryResult = resolver.query(dns.Query(b'foo.example.com'))

        self.assertFalse(protocols[0].transport.disconnected)
        result.errback(failure.Failure(ExpectedException()))
        self.assertTrue(protocols[0].transport.disconnected)

        return self.assertFailure(queryResult, ExpectedException)


    def test_tcpDisconnectRemovesFromConnections(self):
        """
        When a TCP DNS protocol associated with a Resolver disconnects, it is
        removed from the Resolver's connection list.
        """
        resolver = client.Resolver(servers=[('example.com', 53)])
        protocol = resolver.factory.buildProtocol(None)
        protocol.makeConnection(None)
        self.assertIn(protocol, resolver.connections)

        # Disconnecting should remove the protocol from the connection list:
        protocol.connectionLost(None)
        self.assertNotIn(protocol, resolver.connections)


    def test_singleTCPQueryErrbackOnConnectionFailure(self):
        """
        The deferred returned by L{client.Resolver.queryTCP} will
        errback when the TCP connection attempt fails. The reason for
        the connection failure is passed as the argument to errback.
        """
        reactor = proto_helpers.MemoryReactor()
        resolver = client.Resolver(
            servers=[('192.0.2.100', 53)],
            reactor=reactor)

        d = resolver.queryTCP(dns.Query('example.com'))
        host, port, factory, timeout, bindAddress = reactor.tcpClients[0]

        class SentinelException(Exception):
            pass

        factory.clientConnectionFailed(
            reactor.connectors[0], failure.Failure(SentinelException()))

        self.failureResultOf(d, SentinelException)


    def test_multipleTCPQueryErrbackOnConnectionFailure(self):
        """
        All pending L{resolver.queryTCP} C{deferred}s will C{errback}
        with the same C{Failure} if the connection attempt fails.
        """
        reactor = proto_helpers.MemoryReactor()
        resolver = client.Resolver(
            servers=[('192.0.2.100', 53)],
            reactor=reactor)

        d1 = resolver.queryTCP(dns.Query('example.com'))
        d2 = resolver.queryTCP(dns.Query('example.net'))
        host, port, factory, timeout, bindAddress = reactor.tcpClients[0]

        class SentinelException(Exception):
            pass

        factory.clientConnectionFailed(
            reactor.connectors[0], failure.Failure(SentinelException()))

        f1 = self.failureResultOf(d1, SentinelException)
        f2 = self.failureResultOf(d2, SentinelException)
        self.assertIs(f1, f2)


    def test_reentrantTCPQueryErrbackOnConnectionFailure(self):
        """
        An errback on the deferred returned by
        L{client.Resolver.queryTCP} may trigger another TCP query.
        """
        reactor = proto_helpers.MemoryReactor()
        resolver = client.Resolver(
            servers=[('127.0.0.1', 10053)],
            reactor=reactor)

        q = dns.Query('example.com')

        # First query sent
        d = resolver.queryTCP(q)

        # Repeat the query when the first query fails
        def reissue(e):
            e.trap(ConnectionRefusedError)
            return resolver.queryTCP(q)
        d.addErrback(reissue)

        self.assertEqual(len(reactor.tcpClients), 1)
        self.assertEqual(len(reactor.connectors), 1)

        host, port, factory, timeout, bindAddress = reactor.tcpClients[0]

        # First query fails
        f1 = failure.Failure(ConnectionRefusedError())
        factory.clientConnectionFailed(
            reactor.connectors[0],
            f1)

        # A second TCP connection is immediately attempted
        self.assertEqual(len(reactor.tcpClients), 2)
        self.assertEqual(len(reactor.connectors), 2)
        # No result expected until the second chained query returns
        self.assertNoResult(d)

        # Second query fails
        f2 = failure.Failure(ConnectionRefusedError())
        factory.clientConnectionFailed(
            reactor.connectors[1],
            f2)

        # Original deferred now fires with the second failure
        f = self.failureResultOf(d, ConnectionRefusedError)
        self.assertIs(f, f2)


    def test_pendingEmptiedInPlaceOnError(self):
        """
        When the TCP connection attempt fails, the
        L{client.Resolver.pending} list is emptied in place. It is not
        replaced with a new empty list.
        """
        reactor = proto_helpers.MemoryReactor()
        resolver = client.Resolver(
            servers=[('192.0.2.100', 53)],
            reactor=reactor)

        d = resolver.queryTCP(dns.Query('example.com'))

        host, port, factory, timeout, bindAddress = reactor.tcpClients[0]

        prePending = resolver.pending
        self.assertEqual(len(prePending), 1)

        class SentinelException(Exception):
            pass

        factory.clientConnectionFailed(
            reactor.connectors[0], failure.Failure(SentinelException()))

        self.failureResultOf(d, SentinelException)
        self.assertIs(resolver.pending, prePending)
        self.assertEqual(len(prePending), 0)



class ClientTests(unittest.TestCase):

    def setUp(self):
        """
        Replace the resolver with a FakeResolver
        """
        client.theResolver = FakeResolver()
        self.hostname = b'example.com'
        self.hostnameForGetHostByName = b'getHostByNameTest'

    def tearDown(self):
        """
        By setting the resolver to None, it will be recreated next time a name
        lookup is done.
        """
        client.theResolver = None

    def checkResult(self, results, qtype):
        """
        Verify that the result is the same query type as what is expected.
        """
        answers, authority, additional = results
        result = answers[0]
        self.assertEqual(result.name.name, self.hostname)
        self.assertEqual(result.type, qtype)

    def checkGetHostByName(self, result):
        """
        Test that the getHostByName query returns the 127.0.0.1 address.
        """
        self.assertEqual(result, '127.0.0.1')

    def test_getHostByName(self):
        """
        do a getHostByName of a value that should return 127.0.0.1.
        """
        d = client.getHostByName(self.hostnameForGetHostByName)
        d.addCallback(self.checkGetHostByName)
        return d

    def test_lookupAddress(self):
        """
        Do a lookup and test that the resolver will issue the correct type of
        query type. We do this by checking that FakeResolver returns a result
        record with the same query type as what we issued.
        """
        d = client.lookupAddress(self.hostname)
        d.addCallback(self.checkResult, dns.A)
        return d

    def test_lookupIPV6Address(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupIPV6Address(self.hostname)
        d.addCallback(self.checkResult, dns.AAAA)
        return d

    def test_lookupAddress6(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupAddress6(self.hostname)
        d.addCallback(self.checkResult, dns.A6)
        return d

    def test_lookupNameservers(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupNameservers(self.hostname)
        d.addCallback(self.checkResult, dns.NS)
        return d

    def test_lookupCanonicalName(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupCanonicalName(self.hostname)
        d.addCallback(self.checkResult, dns.CNAME)
        return d

    def test_lookupAuthority(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupAuthority(self.hostname)
        d.addCallback(self.checkResult, dns.SOA)
        return d

    def test_lookupMailBox(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupMailBox(self.hostname)
        d.addCallback(self.checkResult, dns.MB)
        return d

    def test_lookupMailGroup(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupMailGroup(self.hostname)
        d.addCallback(self.checkResult, dns.MG)
        return d

    def test_lookupMailRename(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupMailRename(self.hostname)
        d.addCallback(self.checkResult, dns.MR)
        return d

    def test_lookupNull(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupNull(self.hostname)
        d.addCallback(self.checkResult, dns.NULL)
        return d

    def test_lookupWellKnownServices(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupWellKnownServices(self.hostname)
        d.addCallback(self.checkResult, dns.WKS)
        return d

    def test_lookupPointer(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupPointer(self.hostname)
        d.addCallback(self.checkResult, dns.PTR)
        return d

    def test_lookupHostInfo(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupHostInfo(self.hostname)
        d.addCallback(self.checkResult, dns.HINFO)
        return d

    def test_lookupMailboxInfo(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupMailboxInfo(self.hostname)
        d.addCallback(self.checkResult, dns.MINFO)
        return d

    def test_lookupMailExchange(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupMailExchange(self.hostname)
        d.addCallback(self.checkResult, dns.MX)
        return d

    def test_lookupText(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupText(self.hostname)
        d.addCallback(self.checkResult, dns.TXT)
        return d

    def test_lookupSenderPolicy(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupSenderPolicy(self.hostname)
        d.addCallback(self.checkResult, dns.SPF)
        return d

    def test_lookupResponsibility(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupResponsibility(self.hostname)
        d.addCallback(self.checkResult, dns.RP)
        return d

    def test_lookupAFSDatabase(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupAFSDatabase(self.hostname)
        d.addCallback(self.checkResult, dns.AFSDB)
        return d

    def test_lookupService(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupService(self.hostname)
        d.addCallback(self.checkResult, dns.SRV)
        return d


    def test_lookupZone(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupZone(self.hostname)
        d.addCallback(self.checkResult, dns.AXFR)
        return d


    def test_lookupAllRecords(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupAllRecords(self.hostname)
        d.addCallback(self.checkResult, dns.ALL_RECORDS)
        return d


    def test_lookupNamingAuthorityPointer(self):
        """
        See L{test_lookupAddress}
        """
        d = client.lookupNamingAuthorityPointer(self.hostname)
        d.addCallback(self.checkResult, dns.NAPTR)
        return d


    def test_query(self):
        """
        L{client.query} accepts a L{dns.Query} instance and dispatches
        it to L{client.theResolver}.C{query}, which in turn dispatches
        to an appropriate C{lookup*} method of L{client.theResolver},
        based on the L{dns.Query} type.
        """
        q = dns.Query(self.hostname, dns.A)
        d = client.query(q)
        d.addCallback(self.checkResult, dns.A)
        return d



class FilterAnswersTests(unittest.TestCase):
    """
    Test L{twisted.names.client.Resolver.filterAnswers}'s handling of various
    error conditions it might encounter.
    """
    def setUp(self):
        # Create a resolver pointed at an invalid server - we won't be hitting
        # the network in any of these tests.
        self.resolver = client.Resolver(servers=[('0.0.0.0', 0)])


    def test_truncatedMessage(self):
        """
        Test that a truncated message results in an equivalent request made via
        TCP.
        """
        m = dns.Message(trunc=True)
        m.addQuery(b'example.com')

        def queryTCP(queries):
            self.assertEqual(queries, m.queries)
            response = dns.Message()
            response.answers = ['answer']
            response.authority = ['authority']
            response.additional = ['additional']
            return defer.succeed(response)
        self.resolver.queryTCP = queryTCP
        d = self.resolver.filterAnswers(m)
        d.addCallback(
            self.assertEqual, (['answer'], ['authority'], ['additional']))
        return d


    def _rcodeTest(self, rcode, exc):
        m = dns.Message(rCode=rcode)
        err = self.resolver.filterAnswers(m)
        err.trap(exc)


    def test_formatError(self):
        """
        Test that a message with a result code of C{EFORMAT} results in a
        failure wrapped around L{DNSFormatError}.
        """
        return self._rcodeTest(dns.EFORMAT, error.DNSFormatError)


    def test_serverError(self):
        """
        Like L{test_formatError} but for C{ESERVER}/L{DNSServerError}.
        """
        return self._rcodeTest(dns.ESERVER, error.DNSServerError)


    def test_nameError(self):
        """
        Like L{test_formatError} but for C{ENAME}/L{DNSNameError}.
        """
        return self._rcodeTest(dns.ENAME, error.DNSNameError)


    def test_notImplementedError(self):
        """
        Like L{test_formatError} but for C{ENOTIMP}/L{DNSNotImplementedError}.
        """
        return self._rcodeTest(dns.ENOTIMP, error.DNSNotImplementedError)


    def test_refusedError(self):
        """
        Like L{test_formatError} but for C{EREFUSED}/L{DNSQueryRefusedError}.
        """
        return self._rcodeTest(dns.EREFUSED, error.DNSQueryRefusedError)


    def test_refusedErrorUnknown(self):
        """
        Like L{test_formatError} but for an unrecognized error code and
        L{DNSUnknownError}.
        """
        return self._rcodeTest(dns.EREFUSED + 1, error.DNSUnknownError)



class FakeDNSDatagramProtocol(object):
    def __init__(self):
        self.queries = []
        self.transport = StubPort()

    def query(self, address, queries, timeout=10, id=None):
        self.queries.append((address, queries, timeout, id))
        return defer.fail(error.DNSQueryTimeoutError(queries))

    def removeResend(self, id):
        # Ignore this for the time being.
        pass



class RetryLogicTests(unittest.TestCase):
    """
    Tests for query retrying implemented by L{client.Resolver}.
    """
    testServers = [
        '1.2.3.4',
        '4.3.2.1',
        'a.b.c.d',
        'z.y.x.w']

    def test_roundRobinBackoff(self):
        """
        When timeouts occur waiting for responses to queries, the next
        configured server is issued the query.  When the query has been issued
        to all configured servers, the timeout is increased and the process
        begins again at the beginning.
        """
        addrs = [(x, 53) for x in self.testServers]
        r = client.Resolver(resolv=None, servers=addrs)
        proto = FakeDNSDatagramProtocol()
        r._connectedProtocol = lambda: proto
        return r.lookupAddress(b"foo.example.com"
            ).addCallback(self._cbRoundRobinBackoff
            ).addErrback(self._ebRoundRobinBackoff, proto
            )


    def _cbRoundRobinBackoff(self, result):
        self.fail("Lookup address succeeded, should have timed out")


    def _ebRoundRobinBackoff(self, failure, fakeProto):
        failure.trap(defer.TimeoutError)

        # Assert that each server is tried with a particular timeout
        # before the timeout is increased and the attempts are repeated.

        for t in (1, 3, 11, 45):
            tries = fakeProto.queries[:len(self.testServers)]
            del fakeProto.queries[:len(self.testServers)]

            tries.sort()
            expected = list(self.testServers)
            expected.sort()

            for ((addr, query, timeout, id), expectedAddr) in zip(tries, expected):
                self.assertEqual(addr, (expectedAddr, 53))
                self.assertEqual(timeout, t)

        self.assertFalse(fakeProto.queries)



class ThreadedResolverTests(unittest.TestCase):
    """
    Tests for L{client.ThreadedResolver}.
    """
    def test_deprecated(self):
        """
        L{client.ThreadedResolver} is deprecated.  Instantiating it emits a
        deprecation warning pointing at the code that does the instantiation.
        """
        client.ThreadedResolver()
        warnings = self.flushWarnings(offendingFunctions=[self.test_deprecated])
        self.assertEqual(
            warnings[0]['message'],
            "twisted.names.client.ThreadedResolver is deprecated since "
            "Twisted 9.0, use twisted.internet.base.ThreadedResolver "
            "instead.")
        self.assertEqual(warnings[0]['category'], DeprecationWarning)
        self.assertEqual(len(warnings), 1)
