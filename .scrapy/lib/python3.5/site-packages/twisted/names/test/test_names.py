# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for twisted.names.
"""

from __future__ import absolute_import, division

import socket
import operator
import copy

from io import BytesIO
from functools import partial, reduce
from struct import pack

from twisted.trial import unittest

from twisted.internet import reactor, defer, error
from twisted.internet.defer import succeed
from twisted.names import client, server, common, authority, dns
from twisted.names.dns import SOA, Message, RRHeader, Record_A, Record_SOA
from twisted.names.error import DomainError
from twisted.names.client import Resolver
from twisted.names.secondary import (
    SecondaryAuthorityService, SecondaryAuthority)

from twisted.test.proto_helpers import StringTransport, MemoryReactorClock

def justPayload(results):
    return [r.payload for r in results[0]]

class NoFileAuthority(authority.FileAuthority):
    def __init__(self, soa, records):
        # Yes, skip FileAuthority
        common.ResolverBase.__init__(self)
        self.soa, self.records = soa, records


soa_record = dns.Record_SOA(
                    mname = b'test-domain.com',
                    rname = u'root.test-domain.com',
                    serial = 100,
                    refresh = 1234,
                    minimum = 7654,
                    expire = 19283784,
                    retry = 15,
                    ttl=1
                )

reverse_soa = dns.Record_SOA(
                     mname = b'93.84.28.in-addr.arpa',
                     rname = b'93.84.28.in-addr.arpa',
                     serial = 120,
                     refresh = 54321,
                     minimum = 382,
                     expire = 11193983,
                     retry = 30,
                     ttl=3
                )

my_soa = dns.Record_SOA(
    mname = u'my-domain.com',
    rname = b'postmaster.test-domain.com',
    serial = 130,
    refresh = 12345,
    minimum = 1,
    expire = 999999,
    retry = 100,
    )

test_domain_com = NoFileAuthority(
    soa = (b'test-domain.com', soa_record),
    records = {
        b'test-domain.com': [
            soa_record,
            dns.Record_A(b'127.0.0.1'),
            dns.Record_NS(b'39.28.189.39'),
            dns.Record_SPF(b'v=spf1 mx/30 mx:example.org/30 -all'),
            dns.Record_SPF(b'v=spf1 +mx a:\0colo',
                           b'.example.com/28 -all not valid'),
            dns.Record_MX(10, u'host.test-domain.com'),
            dns.Record_HINFO(os=b'Linux', cpu=b'A Fast One, Dontcha know'),
            dns.Record_CNAME(b'canonical.name.com'),
            dns.Record_MB(b'mailbox.test-domain.com'),
            dns.Record_MG(b'mail.group.someplace'),
            dns.Record_TXT(b'A First piece of Text', b'a SecoNd piece'),
            dns.Record_A6(0, b'ABCD::4321', b''),
            dns.Record_A6(12, b'0:0069::0', b'some.network.tld'),
            dns.Record_A6(8, b'0:5634:1294:AFCB:56AC:48EF:34C3:01FF',
                          b'tra.la.la.net'),
            dns.Record_TXT(b'Some more text, haha!  Yes.  \0  Still here?'),
            dns.Record_MR(b'mail.redirect.or.whatever'),
            dns.Record_MINFO(rmailbx=b'r mail box', emailbx=b'e mail box'),
            dns.Record_AFSDB(subtype=1, hostname=b'afsdb.test-domain.com'),
            dns.Record_RP(mbox=b'whatever.i.dunno', txt=b'some.more.text'),
            dns.Record_WKS(b'12.54.78.12', socket.IPPROTO_TCP,
                           b'\x12\x01\x16\xfe\xc1\x00\x01'),
            dns.Record_NAPTR(100, 10, b"u", b"sip+E2U",
                             b"!^.*$!sip:information@domain.tld!"),
            dns.Record_AAAA(b'AF43:5634:1294:AFCB:56AC:48EF:34C3:01FF')],
        b'http.tcp.test-domain.com': [
            dns.Record_SRV(257, 16383, 43690, b'some.other.place.fool')
        ],
        b'host.test-domain.com': [
            dns.Record_A(b'123.242.1.5'),
            dns.Record_A(b'0.255.0.255'),
        ],
        b'host-two.test-domain.com': [
#
#  Python bug
#           dns.Record_A('255.255.255.255'),
#
            dns.Record_A(b'255.255.255.254'),
            dns.Record_A(b'0.0.0.0')
        ],
        b'cname.test-domain.com': [
            dns.Record_CNAME(b'test-domain.com')
        ],
        b'anothertest-domain.com': [
            dns.Record_A(b'1.2.3.4')],
    }
)

reverse_domain = NoFileAuthority(
    soa = (b'93.84.28.in-addr.arpa', reverse_soa),
    records = {
        b'123.93.84.28.in-addr.arpa': [
             dns.Record_PTR(b'test.host-reverse.lookup.com'),
             reverse_soa
        ]
    }
)


my_domain_com = NoFileAuthority(
    soa = (b'my-domain.com', my_soa),
    records = {
        b'my-domain.com': [
            my_soa,
            dns.Record_A(b'1.2.3.4', ttl='1S'),
            dns.Record_NS(b'ns1.domain', ttl=b'2M'),
            dns.Record_NS(b'ns2.domain', ttl='3H'),
            dns.Record_SRV(257, 16383, 43690, b'some.other.place.fool',
                           ttl='4D')
            ]
        }
    )


class ServerDNSTests(unittest.TestCase):
    """
    Test cases for DNS server and client.
    """

    def setUp(self):
        self.factory = server.DNSServerFactory([
            test_domain_com, reverse_domain, my_domain_com
        ], verbose=2)

        p = dns.DNSDatagramProtocol(self.factory)

        while 1:
            listenerTCP = reactor.listenTCP(0, self.factory, interface="127.0.0.1")
            # It's simpler to do the stop listening with addCleanup,
            # even though we might not end up using this TCP port in
            # the test (if the listenUDP below fails).  Cleaning up
            # this TCP port sooner than "cleanup time" would mean
            # adding more code to keep track of the Deferred returned
            # by stopListening.
            self.addCleanup(listenerTCP.stopListening)
            port = listenerTCP.getHost().port

            try:
                listenerUDP = reactor.listenUDP(port, p, interface="127.0.0.1")
            except error.CannotListenError:
                pass
            else:
                self.addCleanup(listenerUDP.stopListening)
                break

        self.listenerTCP = listenerTCP
        self.listenerUDP = listenerUDP
        self.resolver = client.Resolver(servers=[('127.0.0.1', port)])


    def tearDown(self):
        """
        Clean up any server connections associated with the
        L{DNSServerFactory} created in L{setUp}
        """
        # It'd be great if DNSServerFactory had a method that
        # encapsulated this task.  At least the necessary data is
        # available, though.
        for conn in self.factory.connections[:]:
            conn.transport.loseConnection()


    def namesTest(self, querying, expectedRecords):
        """
        Assert that the DNS response C{querying} will eventually fire with
        contains exactly a certain collection of records.

        @param querying: A L{Deferred} returned from one of the DNS client
            I{lookup} methods.

        @param expectedRecords: A L{list} of L{IRecord} providers which must be
            in the response or the test will be failed.

        @return: A L{Deferred} that fires when the assertion has been made.  It
            fires with a success result if the assertion succeeds and with a
            L{Failure} if it fails.
        """
        def checkResults(response):
            receivedRecords = justPayload(response)
            self.assertEqual(set(expectedRecords), set(receivedRecords))

        querying.addCallback(checkResults)
        return querying


    def test_addressRecord1(self):
        """Test simple DNS 'A' record queries"""
        return self.namesTest(
            self.resolver.lookupAddress('test-domain.com'),
            [dns.Record_A('127.0.0.1', ttl=19283784)]
        )


    def test_addressRecord2(self):
        """Test DNS 'A' record queries with multiple answers"""
        return self.namesTest(
            self.resolver.lookupAddress('host.test-domain.com'),
            [dns.Record_A('123.242.1.5', ttl=19283784),
             dns.Record_A('0.255.0.255', ttl=19283784)]
        )


    def test_addressRecord3(self):
        """Test DNS 'A' record queries with edge cases"""
        return self.namesTest(
            self.resolver.lookupAddress('host-two.test-domain.com'),
            [dns.Record_A('255.255.255.254', ttl=19283784), dns.Record_A('0.0.0.0', ttl=19283784)]
        )


    def test_authority(self):
        """Test DNS 'SOA' record queries"""
        return self.namesTest(
            self.resolver.lookupAuthority('test-domain.com'),
            [soa_record]
        )


    def test_mailExchangeRecord(self):
        """
        The DNS client can issue an MX query and receive a response including
        an MX record as well as any A record hints.
        """
        return self.namesTest(
            self.resolver.lookupMailExchange(b"test-domain.com"),
            [dns.Record_MX(10, b"host.test-domain.com", ttl=19283784),
             dns.Record_A(b"123.242.1.5", ttl=19283784),
             dns.Record_A(b"0.255.0.255", ttl=19283784)])


    def test_nameserver(self):
        """Test DNS 'NS' record queries"""
        return self.namesTest(
            self.resolver.lookupNameservers('test-domain.com'),
            [dns.Record_NS('39.28.189.39', ttl=19283784)]
        )


    def test_HINFO(self):
        """Test DNS 'HINFO' record queries"""
        return self.namesTest(
            self.resolver.lookupHostInfo('test-domain.com'),
            [dns.Record_HINFO(os=b'Linux', cpu=b'A Fast One, Dontcha know',
                              ttl=19283784)]
        )

    def test_PTR(self):
        """Test DNS 'PTR' record queries"""
        return self.namesTest(
            self.resolver.lookupPointer('123.93.84.28.in-addr.arpa'),
            [dns.Record_PTR('test.host-reverse.lookup.com', ttl=11193983)]
        )


    def test_CNAME(self):
        """Test DNS 'CNAME' record queries"""
        return self.namesTest(
            self.resolver.lookupCanonicalName('test-domain.com'),
            [dns.Record_CNAME('canonical.name.com', ttl=19283784)]
        )

    def test_MB(self):
        """Test DNS 'MB' record queries"""
        return self.namesTest(
            self.resolver.lookupMailBox('test-domain.com'),
            [dns.Record_MB('mailbox.test-domain.com', ttl=19283784)]
        )


    def test_MG(self):
        """Test DNS 'MG' record queries"""
        return self.namesTest(
            self.resolver.lookupMailGroup('test-domain.com'),
            [dns.Record_MG('mail.group.someplace', ttl=19283784)]
        )


    def test_MR(self):
        """Test DNS 'MR' record queries"""
        return self.namesTest(
            self.resolver.lookupMailRename('test-domain.com'),
            [dns.Record_MR('mail.redirect.or.whatever', ttl=19283784)]
        )


    def test_MINFO(self):
        """Test DNS 'MINFO' record queries"""
        return self.namesTest(
            self.resolver.lookupMailboxInfo('test-domain.com'),
            [dns.Record_MINFO(rmailbx='r mail box', emailbx='e mail box', ttl=19283784)]
        )


    def test_SRV(self):
        """Test DNS 'SRV' record queries"""
        return self.namesTest(
            self.resolver.lookupService('http.tcp.test-domain.com'),
            [dns.Record_SRV(257, 16383, 43690, 'some.other.place.fool', ttl=19283784)]
        )

    def test_AFSDB(self):
        """Test DNS 'AFSDB' record queries"""
        return self.namesTest(
            self.resolver.lookupAFSDatabase('test-domain.com'),
            [dns.Record_AFSDB(subtype=1, hostname='afsdb.test-domain.com', ttl=19283784)]
        )


    def test_RP(self):
        """Test DNS 'RP' record queries"""
        return self.namesTest(
            self.resolver.lookupResponsibility('test-domain.com'),
            [dns.Record_RP(mbox='whatever.i.dunno', txt='some.more.text', ttl=19283784)]
        )


    def test_TXT(self):
        """Test DNS 'TXT' record queries"""
        return self.namesTest(
            self.resolver.lookupText('test-domain.com'),
            [dns.Record_TXT(b'A First piece of Text', b'a SecoNd piece',
                            ttl=19283784),
             dns.Record_TXT(b'Some more text, haha!  Yes.  \0  Still here?',
                            ttl=19283784)]
        )


    def test_spf(self):
        """
        L{DNSServerFactory} can serve I{SPF} resource records.
        """
        return self.namesTest(
            self.resolver.lookupSenderPolicy('test-domain.com'),
            [dns.Record_SPF(b'v=spf1 mx/30 mx:example.org/30 -all',
                            ttl=19283784),
            dns.Record_SPF(b'v=spf1 +mx a:\0colo',
                           b'.example.com/28 -all not valid', ttl=19283784)]
        )


    def test_WKS(self):
        """Test DNS 'WKS' record queries"""
        return self.namesTest(
            self.resolver.lookupWellKnownServices('test-domain.com'),
            [dns.Record_WKS('12.54.78.12', socket.IPPROTO_TCP,
                            b'\x12\x01\x16\xfe\xc1\x00\x01', ttl=19283784)]
        )


    def test_someRecordsWithTTLs(self):
        result_soa = copy.copy(my_soa)
        result_soa.ttl = my_soa.expire
        return self.namesTest(
            self.resolver.lookupAllRecords('my-domain.com'),
            [result_soa,
             dns.Record_A('1.2.3.4', ttl='1S'),
             dns.Record_NS('ns1.domain', ttl='2M'),
             dns.Record_NS('ns2.domain', ttl='3H'),
             dns.Record_SRV(257, 16383, 43690, 'some.other.place.fool', ttl='4D')]
            )


    def test_AAAA(self):
        """Test DNS 'AAAA' record queries (IPv6)"""
        return self.namesTest(
            self.resolver.lookupIPV6Address('test-domain.com'),
            [dns.Record_AAAA('AF43:5634:1294:AFCB:56AC:48EF:34C3:01FF', ttl=19283784)]
        )

    def test_A6(self):
        """Test DNS 'A6' record queries (IPv6)"""
        return self.namesTest(
            self.resolver.lookupAddress6('test-domain.com'),
            [dns.Record_A6(0, 'ABCD::4321', '', ttl=19283784),
             dns.Record_A6(12, '0:0069::0', 'some.network.tld', ttl=19283784),
             dns.Record_A6(8, '0:5634:1294:AFCB:56AC:48EF:34C3:01FF', 'tra.la.la.net', ttl=19283784)]
         )


    def test_zoneTransfer(self):
        """
        Test DNS 'AXFR' queries (Zone transfer)
        """
        default_ttl = soa_record.expire
        results = [copy.copy(r) for r in reduce(operator.add, test_domain_com.records.values())]
        for r in results:
            if r.ttl is None:
                r.ttl = default_ttl
        return self.namesTest(
            self.resolver.lookupZone('test-domain.com').addCallback(lambda r: (r[0][:-1],)),
            results
        )


    def test_similarZonesDontInterfere(self):
        """Tests that unrelated zones don't mess with each other."""
        return self.namesTest(
            self.resolver.lookupAddress("anothertest-domain.com"),
            [dns.Record_A('1.2.3.4', ttl=19283784)]
        )


    def test_NAPTR(self):
        """
        Test DNS 'NAPTR' record queries.
        """
        return self.namesTest(
            self.resolver.lookupNamingAuthorityPointer('test-domain.com'),
            [dns.Record_NAPTR(100, 10, b"u", b"sip+E2U",
                              b"!^.*$!sip:information@domain.tld!",
                              ttl=19283784)])



class HelperTests(unittest.TestCase):
    def test_serialGenerator(self):
        f = self.mktemp()
        a = authority.getSerial(f)
        for i in range(20):
            b = authority.getSerial(f)
            self.assertTrue(a < b)
            a = b


class AXFRTests(unittest.TestCase):
    def setUp(self):
        self.results = None
        self.d = defer.Deferred()
        self.d.addCallback(self._gotResults)
        self.controller = client.AXFRController('fooby.com', self.d)

        self.soa = dns.RRHeader(name='fooby.com', type=dns.SOA, cls=dns.IN, ttl=86400, auth=False,
                                payload=dns.Record_SOA(mname='fooby.com',
                                                       rname='hooj.fooby.com',
                                                       serial=100,
                                                       refresh=200,
                                                       retry=300,
                                                       expire=400,
                                                       minimum=500,
                                                       ttl=600))

        self.records = [
            self.soa,
            dns.RRHeader(name='fooby.com', type=dns.NS, cls=dns.IN, ttl=700, auth=False,
                         payload=dns.Record_NS(name='ns.twistedmatrix.com', ttl=700)),

            dns.RRHeader(name='fooby.com', type=dns.MX, cls=dns.IN, ttl=700, auth=False,
                         payload=dns.Record_MX(preference=10, exchange='mail.mv3d.com', ttl=700)),

            dns.RRHeader(name='fooby.com', type=dns.A, cls=dns.IN, ttl=700, auth=False,
                         payload=dns.Record_A(address='64.123.27.105', ttl=700)),
            self.soa
            ]

    def _makeMessage(self):
        # hooray they all have the same message format
        return dns.Message(id=999, answer=1, opCode=0, recDes=0, recAv=1, auth=1, rCode=0, trunc=0, maxSize=0)

    def test_bindAndTNamesStyle(self):
        # Bind style = One big single message
        m = self._makeMessage()
        m.queries = [dns.Query('fooby.com', dns.AXFR, dns.IN)]
        m.answers = self.records
        self.controller.messageReceived(m, None)
        self.assertEqual(self.results, self.records)

    def _gotResults(self, result):
        self.results = result

    def test_DJBStyle(self):
        # DJB style = message per record
        records = self.records[:]
        while records:
            m = self._makeMessage()
            m.queries = [] # DJB *doesn't* specify any queries.. hmm..
            m.answers = [records.pop(0)]
            self.controller.messageReceived(m, None)
        self.assertEqual(self.results, self.records)



class ResolvConfHandlingTests(unittest.TestCase):
    def test_missing(self):
        resolvConf = self.mktemp()
        r = client.Resolver(resolv=resolvConf)
        self.assertEqual(r.dynServers, [('127.0.0.1', 53)])
        r._parseCall.cancel()

    def test_empty(self):
        resolvConf = self.mktemp()
        open(resolvConf, 'w').close()
        r = client.Resolver(resolv=resolvConf)
        self.assertEqual(r.dynServers, [('127.0.0.1', 53)])
        r._parseCall.cancel()



class AuthorityTests(unittest.TestCase):
    """
    Tests for the basic response record selection code in L{FileAuthority}
    (independent of its fileness).
    """

    def test_domainErrorForNameWithCommonSuffix(self):
        """
        L{FileAuthority} lookup methods errback with L{DomainError} if
        the requested C{name} shares a common suffix with its zone but
        is not actually a descendant of its zone, in terms of its
        sequence of DNS name labels. eg www.the-example.com has
        nothing to do with the zone example.com.
        """
        testDomain = test_domain_com
        testDomainName = b'nonexistent.prefix-' + testDomain.soa[0]
        f = self.failureResultOf(testDomain.lookupAddress(testDomainName))
        self.assertIsInstance(f.value, DomainError)


    def test_recordMissing(self):
        """
        If a L{FileAuthority} has a zone which includes an I{NS} record for a
        particular name and that authority is asked for another record for the
        same name which does not exist, the I{NS} record is not included in the
        authority section of the response.
        """
        authority = NoFileAuthority(
            soa=(str(soa_record.mname), soa_record),
            records={
                str(soa_record.mname): [
                    soa_record,
                    dns.Record_NS('1.2.3.4'),
                    ]})
        d = authority.lookupAddress(str(soa_record.mname))
        result = []
        d.addCallback(result.append)
        answer, authority, additional = result[0]
        self.assertEqual(answer, [])
        self.assertEqual(
            authority, [
                dns.RRHeader(
                    str(soa_record.mname), soa_record.TYPE,
                    ttl=soa_record.expire, payload=soa_record,
                    auth=True)])
        self.assertEqual(additional, [])


    def _referralTest(self, method):
        """
        Create an authority and make a request against it.  Then verify that the
        result is a referral, including no records in the answers or additional
        sections, but with an I{NS} record in the authority section.
        """
        subdomain = 'example.' + str(soa_record.mname)
        nameserver = dns.Record_NS('1.2.3.4')
        authority = NoFileAuthority(
            soa=(str(soa_record.mname), soa_record),
            records={
                subdomain: [
                    nameserver,
                    ]})
        d = getattr(authority, method)(subdomain)
        answer, authority, additional = self.successResultOf(d)
        self.assertEqual(answer, [])
        self.assertEqual(
            authority, [dns.RRHeader(
                    subdomain, dns.NS, ttl=soa_record.expire,
                    payload=nameserver, auth=False)])
        self.assertEqual(additional, [])


    def test_referral(self):
        """
        When an I{NS} record is found for a child zone, it is included in the
        authority section of the response. It is marked as non-authoritative if
        the authority is not also authoritative for the child zone (RFC 2181,
        section 6.1).
        """
        self._referralTest('lookupAddress')


    def test_allRecordsReferral(self):
        """
        A referral is also generated for a request of type C{ALL_RECORDS}.
        """
        self._referralTest('lookupAllRecords')



class AdditionalProcessingTests(unittest.TestCase):
    """
    Tests for L{FileAuthority}'s additional processing for those record types
    which require it (MX, CNAME, etc).
    """
    _A = dns.Record_A(b"10.0.0.1")
    _AAAA = dns.Record_AAAA(b"f080::1")

    def _lookupSomeRecords(self, method, soa, makeRecord, target, addresses):
        """
        Perform a DNS lookup against a L{FileAuthority} configured with records
        as defined by C{makeRecord} and C{addresses}.

        @param method: The name of the lookup method to use; for example,
            C{"lookupNameservers"}.
        @type method: L{str}

        @param soa: A L{Record_SOA} for the zone for which the L{FileAuthority}
            is authoritative.

        @param makeRecord: A one-argument callable which accepts a name and
            returns an L{IRecord} provider.  L{FileAuthority} is constructed
            with this record.  The L{FileAuthority} is queried for a record of
            the resulting type with the given name.

        @param target: The extra name which the record returned by
            C{makeRecord} will be pointed at; this is the name which might
            require extra processing by the server so that all the available,
            useful information is returned.  For example, this is the target of
            a CNAME record or the mail exchange host pointed to by an MX record.
        @type target: L{bytes}

        @param addresses: A L{list} of records giving addresses of C{target}.

        @return: A L{Deferred} that fires with the result of the resolver
            method give by C{method}.
        """
        authority = NoFileAuthority(
            soa=(soa.mname.name, soa),
            records={
                soa.mname.name: [makeRecord(target)],
                target: addresses,
                },
            )
        return getattr(authority, method)(soa_record.mname.name)


    def assertRecordsMatch(self, expected, computed):
        """
        Assert that the L{RRHeader} instances given by C{expected} and
        C{computed} carry all the same information but without requiring the
        records appear in the same order.

        @param expected: A L{list} of L{RRHeader} instances giving the expected
            records.

        @param computed: A L{list} of L{RRHeader} instances giving the records
            computed by the scenario under test.

        @raise self.failureException: If the two collections of records
            disagree.
        """
        # RRHeader instances aren't inherently ordered.  Impose an ordering
        # that's good enough for the purposes of these tests - in which we
        # never have more than one record of a particular type.
        key = lambda rr: rr.type
        self.assertEqual(sorted(expected, key=key), sorted(computed, key=key))


    def _additionalTest(self, method, makeRecord, addresses):
        """
        Verify that certain address records are included in the I{additional}
        section of a response generated by L{FileAuthority}.

        @param method: See L{_lookupSomeRecords}

        @param makeRecord: See L{_lookupSomeRecords}

        @param addresses: A L{list} of L{IRecord} providers which the
            I{additional} section of the response is required to match
            (ignoring order).

        @raise self.failureException: If the I{additional} section of the
            response consists of different records than those given by
            C{addresses}.
        """
        target = b"mail." + soa_record.mname.name
        d = self._lookupSomeRecords(
            method, soa_record, makeRecord, target, addresses)
        answer, authority, additional = self.successResultOf(d)

        self.assertRecordsMatch(
            [dns.RRHeader(
                    target, address.TYPE, ttl=soa_record.expire, payload=address,
                    auth=True)
             for address in addresses],
            additional)


    def _additionalMXTest(self, addresses):
        """
        Verify that a response to an MX query has certain records in the
        I{additional} section.

        @param addresses: See C{_additionalTest}
        """
        self._additionalTest(
            "lookupMailExchange", partial(dns.Record_MX, 10), addresses)


    def test_mailExchangeAdditionalA(self):
        """
        If the name of the MX response has A records, they are included in the
        additional section of the response.
        """
        self._additionalMXTest([self._A])


    def test_mailExchangeAdditionalAAAA(self):
        """
        If the name of the MX response has AAAA records, they are included in
        the additional section of the response.
        """
        self._additionalMXTest([self._AAAA])


    def test_mailExchangeAdditionalBoth(self):
        """
        If the name of the MX response has both A and AAAA records, they are
        all included in the additional section of the response.
        """
        self._additionalMXTest([self._A, self._AAAA])


    def _additionalNSTest(self, addresses):
        """
        Verify that a response to an NS query has certain records in the
        I{additional} section.

        @param addresses: See C{_additionalTest}
        """
        self._additionalTest(
            "lookupNameservers", dns.Record_NS, addresses)


    def test_nameserverAdditionalA(self):
        """
        If the name of the NS response has A records, they are included in the
        additional section of the response.
        """
        self._additionalNSTest([self._A])


    def test_nameserverAdditionalAAAA(self):
        """
        If the name of the NS response has AAAA records, they are included in
        the additional section of the response.
        """
        self._additionalNSTest([self._AAAA])


    def test_nameserverAdditionalBoth(self):
        """
        If the name of the NS response has both A and AAAA records, they are
        all included in the additional section of the response.
        """
        self._additionalNSTest([self._A, self._AAAA])


    def _answerCNAMETest(self, addresses):
        """
        Verify that a response to a CNAME query has certain records in the
        I{answer} section.

        @param addresses: See C{_additionalTest}
        """
        target = b"www." + soa_record.mname.name
        d = self._lookupSomeRecords(
            "lookupCanonicalName", soa_record, dns.Record_CNAME, target,
            addresses)
        answer, authority, additional = self.successResultOf(d)

        alias = dns.RRHeader(
            soa_record.mname.name, dns.CNAME, ttl=soa_record.expire,
            payload=dns.Record_CNAME(target), auth=True)
        self.assertRecordsMatch(
            [dns.RRHeader(
                    target, address.TYPE, ttl=soa_record.expire, payload=address,
                    auth=True)
             for address in addresses] + [alias],
            answer)


    def test_canonicalNameAnswerA(self):
        """
        If the name of the CNAME response has A records, they are included in
        the answer section of the response.
        """
        self._answerCNAMETest([self._A])


    def test_canonicalNameAnswerAAAA(self):
        """
        If the name of the CNAME response has AAAA records, they are included
        in the answer section of the response.
        """
        self._answerCNAMETest([self._AAAA])


    def test_canonicalNameAnswerBoth(self):
        """
        If the name of the CNAME response has both A and AAAA records, they are
        all included in the answer section of the response.
        """
        self._answerCNAMETest([self._A, self._AAAA])



class NoInitialResponseTests(unittest.TestCase):

    def test_noAnswer(self):
        """
        If a request returns a L{dns.NS} response, but we can't connect to the
        given server, the request fails with the error returned at connection.
        """

        def query(self, *args):
            # Pop from the message list, so that it blows up if more queries
            # are run than expected.
            return succeed(messages.pop(0))

        def queryProtocol(self, *args, **kwargs):
            return defer.fail(socket.gaierror("Couldn't connect"))

        resolver = Resolver(servers=[('0.0.0.0', 0)])
        resolver._query = query
        messages = []
        # Let's patch dns.DNSDatagramProtocol.query, as there is no easy way to
        # customize it.
        self.patch(dns.DNSDatagramProtocol, "query", queryProtocol)

        records = [
            dns.RRHeader(name='fooba.com', type=dns.NS, cls=dns.IN, ttl=700,
                         auth=False,
                         payload=dns.Record_NS(name='ns.twistedmatrix.com',
                         ttl=700))]
        m = dns.Message(id=999, answer=1, opCode=0, recDes=0, recAv=1, auth=1,
                        rCode=0, trunc=0, maxSize=0)
        m.answers = records
        messages.append(m)
        return self.assertFailure(
            resolver.getHostByName("fooby.com"), socket.gaierror)



class SecondaryAuthorityServiceTests(unittest.TestCase):
    """
    Tests for L{SecondaryAuthorityService}, a service which keeps one or more
    authorities up to date by doing zone transfers from a master.
    """

    def test_constructAuthorityFromHost(self):
        """
        L{SecondaryAuthorityService} can be constructed with a C{str} giving a
        master server address and several domains, causing the creation of a
        secondary authority for each domain and that master server address and
        the default DNS port.
        """
        primary = '192.168.1.2'
        service = SecondaryAuthorityService(
            primary, ['example.com', 'example.org'])
        self.assertEqual(service.primary, primary)
        self.assertEqual(service._port, 53)

        self.assertEqual(service.domains[0].primary, primary)
        self.assertEqual(service.domains[0]._port, 53)
        self.assertEqual(service.domains[0].domain, 'example.com')

        self.assertEqual(service.domains[1].primary, primary)
        self.assertEqual(service.domains[1]._port, 53)
        self.assertEqual(service.domains[1].domain, 'example.org')


    def test_constructAuthorityFromHostAndPort(self):
        """
        L{SecondaryAuthorityService.fromServerAddressAndDomains} constructs a
        new L{SecondaryAuthorityService} from a C{str} giving a master server
        address and DNS port and several domains, causing the creation of a secondary
        authority for each domain and that master server address and the given
        DNS port.
        """
        primary = '192.168.1.3'
        port = 5335
        service = SecondaryAuthorityService.fromServerAddressAndDomains(
            (primary, port), ['example.net', 'example.edu'])
        self.assertEqual(service.primary, primary)
        self.assertEqual(service._port, 5335)

        self.assertEqual(service.domains[0].primary, primary)
        self.assertEqual(service.domains[0]._port, port)
        self.assertEqual(service.domains[0].domain, 'example.net')

        self.assertEqual(service.domains[1].primary, primary)
        self.assertEqual(service.domains[1]._port, port)
        self.assertEqual(service.domains[1].domain, 'example.edu')



class SecondaryAuthorityTests(unittest.TestCase):
    """
    L{twisted.names.secondary.SecondaryAuthority} correctly constructs objects
    with a specified IP address and optionally specified DNS port.
    """

    def test_defaultPort(self):
        """
        When constructed using L{SecondaryAuthority.__init__}, the default port
        of 53 is used.
        """
        secondary = SecondaryAuthority('192.168.1.1', 'inside.com')
        self.assertEqual(secondary.primary, '192.168.1.1')
        self.assertEqual(secondary._port, 53)
        self.assertEqual(secondary.domain, 'inside.com')


    def test_explicitPort(self):
        """
        When constructed using L{SecondaryAuthority.fromServerAddressAndDomain},
        the specified port is used.
        """
        secondary = SecondaryAuthority.fromServerAddressAndDomain(
            ('192.168.1.1', 5353), 'inside.com')
        self.assertEqual(secondary.primary, '192.168.1.1')
        self.assertEqual(secondary._port, 5353)
        self.assertEqual(secondary.domain, 'inside.com')


    def test_transfer(self):
        """
        An attempt is made to transfer the zone for the domain the
        L{SecondaryAuthority} was constructed with from the server address it
        was constructed with when L{SecondaryAuthority.transfer} is called.
        """
        secondary = SecondaryAuthority.fromServerAddressAndDomain(
            ('192.168.1.2', 1234), 'example.com')
        secondary._reactor = reactor = MemoryReactorClock()

        secondary.transfer()

        # Verify a connection attempt to the server address above
        host, port, factory, timeout, bindAddress = reactor.tcpClients.pop(0)
        self.assertEqual(host, '192.168.1.2')
        self.assertEqual(port, 1234)

        # See if a zone transfer query is issued.
        proto = factory.buildProtocol((host, port))
        transport = StringTransport()
        proto.makeConnection(transport)

        msg = Message()
        # DNSProtocol.writeMessage length encodes the message by prepending a
        # 2 byte message length to the buffered value.
        msg.decode(BytesIO(transport.value()[2:]))

        self.assertEqual(
            [dns.Query('example.com', dns.AXFR, dns.IN)], msg.queries)


    def test_lookupAddress(self):
        """
        L{SecondaryAuthority.lookupAddress} returns a L{Deferred} that fires
        with the I{A} records the authority has cached from the primary.
        """
        secondary = SecondaryAuthority.fromServerAddressAndDomain(
            ('192.168.1.2', 1234), b'example.com')
        secondary._reactor = reactor = MemoryReactorClock()

        secondary.transfer()

        host, port, factory, timeout, bindAddress = reactor.tcpClients.pop(0)

        proto = factory.buildProtocol((host, port))
        transport = StringTransport()
        proto.makeConnection(transport)

        query = Message(answer=1, auth=1)
        query.decode(BytesIO(transport.value()[2:]))

        # Generate a response with some data we can check.
        soa = Record_SOA(
            mname=b'ns1.example.com',
            rname='admin.example.com',
            serial=123456,
            refresh=3600,
            minimum=4800,
            expire=7200,
            retry=9600,
            ttl=12000,
            )
        a = Record_A(b'192.168.1.2', ttl=0)
        answer = Message(id=query.id, answer=1, auth=1)
        answer.answers.extend([
                RRHeader(b'example.com', type=SOA, payload=soa),
                RRHeader(b'example.com', payload=a),
                RRHeader(b'example.com', type=SOA, payload=soa),
                ])

        data = answer.toStr()
        proto.dataReceived(pack('!H', len(data)) + data)

        result = self.successResultOf(secondary.lookupAddress('example.com'))
        self.assertEqual((
                [RRHeader(b'example.com', payload=a, auth=True)], [], []), result)
