# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.names.srvconnect}.
"""


import random

from zope.interface.verify import verifyObject

from twisted.internet import defer, protocol
from twisted.internet.error import DNSLookupError, ServiceNameUnknownError
from twisted.internet.interfaces import IConnector
from twisted.names import client, dns, srvconnect
from twisted.names.common import ResolverBase
from twisted.names.error import DNSNameError
from twisted.test.proto_helpers import MemoryReactor
from twisted.trial import unittest


class FakeResolver(ResolverBase):
    """
    Resolver that only gives out one given result.

    Either L{results} or L{failure} must be set and will be used for
    the return value of L{_lookup}

    @ivar results: List of L{dns.RRHeader} for the desired result.
    @type results: C{list}
    @ivar failure: Failure with an exception from L{twisted.names.error}.
    @type failure: L{Failure<twisted.python.failure.Failure>}
    """

    def __init__(self, results=None, failure=None):
        self.results = results
        self.failure = failure
        self.lookups = []

    def _lookup(self, name, cls, qtype, timeout):
        """
        Return the result or failure on lookup.
        """
        self.lookups.append((name, cls, qtype, timeout))
        if self.results is not None:
            return defer.succeed((self.results, [], []))
        else:
            return defer.fail(self.failure)


class DummyFactory(protocol.ClientFactory):
    """
    Dummy client factory that stores the reason of connection failure.
    """

    def __init__(self):
        self.reason = None

    def clientConnectionFailed(self, connector, reason):
        self.reason = reason


class SRVConnectorTests(unittest.TestCase):
    """
    Tests for L{srvconnect.SRVConnector}.
    """

    def setUp(self):
        self.patch(client, "theResolver", FakeResolver())
        self.reactor = MemoryReactor()
        self.factory = DummyFactory()
        self.connector = srvconnect.SRVConnector(
            self.reactor, "xmpp-server", "example.org", self.factory
        )
        self.randIntArgs = []
        self.randIntResults = []

    def _randint(self, min, max):
        """
        Fake randint.

        Returns the first element of L{randIntResults} and records the
        arguments passed to it in L{randIntArgs}.

        @param min: Lower bound of the random number.
        @type min: L{int}

        @param max: Higher bound of the random number.
        @type max: L{int}

        @return: Fake random number from L{randIntResults}.
        @rtype: L{int}
        """
        self.randIntArgs.append((min, max))
        return self.randIntResults.pop(0)

    def test_interface(self):
        """
        L{srvconnect.SRVConnector} implements L{IConnector}.
        """
        verifyObject(IConnector, self.connector)

    def test_SRVPresent(self):
        """
        Test connectTCP gets called with the address from the SRV record.
        """
        payload = dns.Record_SRV(port=6269, target="host.example.org", ttl=60)
        client.theResolver.results = [
            dns.RRHeader(
                name="example.org", type=dns.SRV, cls=dns.IN, ttl=60, payload=payload
            )
        ]
        self.connector.connect()

        self.assertIsNone(self.factory.reason)
        self.assertEqual(self.reactor.tcpClients.pop()[:2], ("host.example.org", 6269))

    def test_SRVNotPresent(self):
        """
        Test connectTCP gets called with fallback parameters on NXDOMAIN.
        """
        client.theResolver.failure = DNSNameError(b"example.org")
        self.connector.connect()

        self.assertIsNone(self.factory.reason)
        self.assertEqual(
            self.reactor.tcpClients.pop()[:2], ("example.org", "xmpp-server")
        )

    def test_SRVNoResult(self):
        """
        Test connectTCP gets called with fallback parameters on empty result.
        """
        client.theResolver.results = []
        self.connector.connect()

        self.assertIsNone(self.factory.reason)
        self.assertEqual(
            self.reactor.tcpClients.pop()[:2], ("example.org", "xmpp-server")
        )

    def test_SRVNoResultUnknownServiceDefaultPort(self):
        """
        connectTCP gets called with default port if the service is not defined.
        """
        self.connector = srvconnect.SRVConnector(
            self.reactor,
            "thisbetternotexist",
            "example.org",
            self.factory,
            defaultPort=5222,
        )

        client.theResolver.failure = ServiceNameUnknownError()
        self.connector.connect()

        self.assertIsNone(self.factory.reason)
        self.assertEqual(self.reactor.tcpClients.pop()[:2], ("example.org", 5222))

    def test_SRVNoResultUnknownServiceNoDefaultPort(self):
        """
        Connect fails on no result, unknown service and no default port.
        """
        self.connector = srvconnect.SRVConnector(
            self.reactor, "thisbetternotexist", "example.org", self.factory
        )

        client.theResolver.failure = ServiceNameUnknownError()
        self.connector.connect()

        self.assertTrue(self.factory.reason.check(ServiceNameUnknownError))

    def test_SRVBadResult(self):
        """
        Test connectTCP gets called with fallback parameters on bad result.
        """
        client.theResolver.results = [
            dns.RRHeader(
                name="example.org", type=dns.CNAME, cls=dns.IN, ttl=60, payload=None
            )
        ]
        self.connector.connect()

        self.assertIsNone(self.factory.reason)
        self.assertEqual(
            self.reactor.tcpClients.pop()[:2], ("example.org", "xmpp-server")
        )

    def test_SRVNoService(self):
        """
        Test that connecting fails when no service is present.
        """
        payload = dns.Record_SRV(port=5269, target=b".", ttl=60)
        client.theResolver.results = [
            dns.RRHeader(
                name="example.org", type=dns.SRV, cls=dns.IN, ttl=60, payload=payload
            )
        ]
        self.connector.connect()

        self.assertIsNotNone(self.factory.reason)
        self.factory.reason.trap(DNSLookupError)
        self.assertEqual(self.reactor.tcpClients, [])

    def test_SRVLookupName(self):
        """
        The lookup name is a native string from service, protocol and domain.
        """
        client.theResolver.results = []
        self.connector.connect()

        name = client.theResolver.lookups[-1][0]
        self.assertEqual(b"_xmpp-server._tcp.example.org", name)

    def test_unicodeDomain(self):
        """
        L{srvconnect.SRVConnector} automatically encodes unicode domain using
        C{idna} encoding.
        """
        self.connector = srvconnect.SRVConnector(
            self.reactor, "xmpp-client", "\u00e9chec.example.org", self.factory
        )
        self.assertEqual(b"xn--chec-9oa.example.org", self.connector.domain)

    def test_pickServerWeights(self):
        """
        pickServer calculates running sum of weights and calls randint.

        This exercises the server selection algorithm specified in RFC 2782 by
        preparing fake L{random.randint} results and checking the values it was
        called with.
        """
        record1 = dns.Record_SRV(10, 10, 5222, "host1.example.org")
        record2 = dns.Record_SRV(10, 20, 5222, "host2.example.org")

        self.connector.orderedServers = [record1, record2]
        self.connector.servers = []
        self.patch(random, "randint", self._randint)

        # 1st round
        self.randIntResults = [11, 0]

        self.connector.pickServer()
        self.assertEqual(self.randIntArgs[0], (0, 30))

        self.connector.pickServer()
        self.assertEqual(self.randIntArgs[1], (0, 10))

        # 2nd round
        self.randIntResults = [10, 0]

        self.connector.pickServer()
        self.assertEqual(self.randIntArgs[2], (0, 30))

        self.connector.pickServer()
        self.assertEqual(self.randIntArgs[3], (0, 20))

    def test_pickServerSamePriorities(self):
        """
        Two records with equal priorities compare on weight (ascending).
        """
        record1 = dns.Record_SRV(10, 10, 5222, "host1.example.org")
        record2 = dns.Record_SRV(10, 20, 5222, "host2.example.org")

        self.connector.orderedServers = [record2, record1]
        self.connector.servers = []
        self.patch(random, "randint", self._randint)
        self.randIntResults = [0, 0]

        self.assertEqual(("host1.example.org", 5222), self.connector.pickServer())

        self.assertEqual(("host2.example.org", 5222), self.connector.pickServer())

    def test_srvDifferentPriorities(self):
        """
        Two records with differing priorities compare on priority (ascending).
        """
        record1 = dns.Record_SRV(10, 0, 5222, "host1.example.org")
        record2 = dns.Record_SRV(20, 0, 5222, "host2.example.org")

        self.connector.orderedServers = [record2, record1]
        self.connector.servers = []
        self.patch(random, "randint", self._randint)
        self.randIntResults = [0, 0]

        self.assertEqual(("host1.example.org", 5222), self.connector.pickServer())

        self.assertEqual(("host2.example.org", 5222), self.connector.pickServer())
