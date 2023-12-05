# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for the I{hosts(5)}-based resolver, L{twisted.names.hosts}.
"""


from twisted.internet.defer import gatherResults
from twisted.names.dns import (
    AAAA,
    IN,
    A,
    DomainError,
    Query,
    Record_A,
    Record_AAAA,
    RRHeader,
)
from twisted.names.hosts import Resolver, searchFileFor, searchFileForAll
from twisted.python.filepath import FilePath
from twisted.trial.unittest import SynchronousTestCase


class GoodTempPathMixin:
    def path(self):
        return FilePath(self.mktemp().encode("utf-8"))


class SearchHostsFileTests(SynchronousTestCase, GoodTempPathMixin):
    """
    Tests for L{searchFileFor}, a helper which finds the first address for a
    particular hostname in a I{hosts(5)}-style file.
    """

    def test_findAddress(self):
        """
        If there is an IPv4 address for the hostname passed to L{searchFileFor},
        it is returned.
        """
        hosts = self.path()
        hosts.setContent(b"10.2.3.4 foo.example.com\n")
        self.assertEqual("10.2.3.4", searchFileFor(hosts.path, b"foo.example.com"))

    def test_notFoundAddress(self):
        """
        If there is no address information for the hostname passed to
        L{searchFileFor}, L{None} is returned.
        """
        hosts = self.path()
        hosts.setContent(b"10.2.3.4 foo.example.com\n")
        self.assertIsNone(searchFileFor(hosts.path, b"bar.example.com"))

    def test_firstAddress(self):
        """
        The first address associated with the given hostname is returned.
        """
        hosts = self.path()
        hosts.setContent(
            b"::1 foo.example.com\n"
            b"10.1.2.3 foo.example.com\n"
            b"fe80::21b:fcff:feee:5a1d foo.example.com\n"
        )
        self.assertEqual("::1", searchFileFor(hosts.path, b"foo.example.com"))

    def test_searchFileForAliases(self):
        """
        For a host with a canonical name and one or more aliases,
        L{searchFileFor} can find an address given any of the names.
        """
        hosts = self.path()
        hosts.setContent(
            b"127.0.1.1\thelmut.example.org\thelmut\n"
            b"# a comment\n"
            b"::1 localhost ip6-localhost ip6-loopback\n"
        )
        self.assertEqual(searchFileFor(hosts.path, b"helmut"), "127.0.1.1")
        self.assertEqual(searchFileFor(hosts.path, b"helmut.example.org"), "127.0.1.1")
        self.assertEqual(searchFileFor(hosts.path, b"ip6-localhost"), "::1")
        self.assertEqual(searchFileFor(hosts.path, b"ip6-loopback"), "::1")
        self.assertEqual(searchFileFor(hosts.path, b"localhost"), "::1")


class SearchHostsFileForAllTests(SynchronousTestCase, GoodTempPathMixin):
    """
    Tests for L{searchFileForAll}, a helper which finds all addresses for a
    particular hostname in a I{hosts(5)}-style file.
    """

    def test_allAddresses(self):
        """
        L{searchFileForAll} returns a list of all addresses associated with the
        name passed to it.
        """
        hosts = self.path()
        hosts.setContent(
            b"127.0.0.1     foobar.example.com\n"
            b"127.0.0.2     foobar.example.com\n"
            b"::1           foobar.example.com\n"
        )
        self.assertEqual(
            ["127.0.0.1", "127.0.0.2", "::1"],
            searchFileForAll(hosts, b"foobar.example.com"),
        )

    def test_caseInsensitively(self):
        """
        L{searchFileForAll} searches for names case-insensitively.
        """
        hosts = self.path()
        hosts.setContent(b"127.0.0.1     foobar.EXAMPLE.com\n")
        self.assertEqual(["127.0.0.1"], searchFileForAll(hosts, b"FOOBAR.example.com"))

    def test_readError(self):
        """
        If there is an error reading the contents of the hosts file,
        L{searchFileForAll} returns an empty list.
        """
        self.assertEqual([], searchFileForAll(self.path(), b"example.com"))

    def test_malformedIP(self):
        """
        L{searchFileForAll} ignores any malformed IP addresses associated with
        the name passed to it.
        """
        hosts = self.path()
        hosts.setContent(
            b"127.0.0.1\tmiser.example.org\tmiser\n"
            b"not-an-ip\tmiser\n"
            b"\xffnot-ascii\t miser\n"
            b"# miser\n"
            b"miser\n"
            b"::1 miser"
        )
        self.assertEqual(
            ["127.0.0.1", "::1"],
            searchFileForAll(hosts, b"miser"),
        )


class HostsTests(SynchronousTestCase, GoodTempPathMixin):
    """
    Tests for the I{hosts(5)}-based L{twisted.names.hosts.Resolver}.
    """

    def setUp(self):
        f = self.path()
        f.setContent(
            b"""
1.1.1.1    EXAMPLE EXAMPLE.EXAMPLETHING
::2        mixed
1.1.1.2    MIXED
::1        ip6thingy
1.1.1.3    multiple
1.1.1.4    multiple
::3        ip6-multiple
::4        ip6-multiple
not-an-ip  malformed
malformed
# malformed
1.1.1.5    malformed
::5        malformed
"""
        )
        self.ttl = 4200
        self.resolver = Resolver(f.path, self.ttl)

    def test_defaultPath(self):
        """
        The default hosts file used by L{Resolver} is I{/etc/hosts} if no value
        is given for the C{file} initializer parameter.
        """
        resolver = Resolver()
        self.assertEqual(b"/etc/hosts", resolver.file)

    def test_getHostByName(self):
        """
        L{hosts.Resolver.getHostByName} returns a L{Deferred} which fires with a
        string giving the address of the queried name as found in the resolver's
        hosts file.
        """
        data = [
            (b"EXAMPLE", "1.1.1.1"),
            (b"EXAMPLE.EXAMPLETHING", "1.1.1.1"),
            (b"MIXED", "1.1.1.2"),
        ]
        ds = [
            self.resolver.getHostByName(n).addCallback(self.assertEqual, ip)
            for n, ip in data
        ]
        self.successResultOf(gatherResults(ds))

    def test_lookupAddress(self):
        """
        L{hosts.Resolver.lookupAddress} returns a L{Deferred} which fires with A
        records from the hosts file.
        """
        d = self.resolver.lookupAddress(b"multiple")
        answers, authority, additional = self.successResultOf(d)
        self.assertEqual(
            (
                RRHeader(b"multiple", A, IN, self.ttl, Record_A("1.1.1.3", self.ttl)),
                RRHeader(b"multiple", A, IN, self.ttl, Record_A("1.1.1.4", self.ttl)),
            ),
            answers,
        )

    def test_lookupIPV6Address(self):
        """
        L{hosts.Resolver.lookupIPV6Address} returns a L{Deferred} which fires
        with AAAA records from the hosts file.
        """
        d = self.resolver.lookupIPV6Address(b"ip6-multiple")
        answers, authority, additional = self.successResultOf(d)
        self.assertEqual(
            (
                RRHeader(
                    b"ip6-multiple", AAAA, IN, self.ttl, Record_AAAA("::3", self.ttl)
                ),
                RRHeader(
                    b"ip6-multiple", AAAA, IN, self.ttl, Record_AAAA("::4", self.ttl)
                ),
            ),
            answers,
        )

    def test_lookupAllRecords(self):
        """
        L{hosts.Resolver.lookupAllRecords} returns a L{Deferred} which fires
        with A records from the hosts file.
        """
        d = self.resolver.lookupAllRecords(b"mixed")
        answers, authority, additional = self.successResultOf(d)
        self.assertEqual(
            (RRHeader(b"mixed", A, IN, self.ttl, Record_A("1.1.1.2", self.ttl)),),
            answers,
        )

    def test_notImplemented(self):
        """
        L{hosts.Resolver} fails with L{NotImplementedError} for L{IResolver}
        methods it doesn't implement.
        """
        self.failureResultOf(
            self.resolver.lookupMailExchange(b"EXAMPLE"), NotImplementedError
        )

    def test_query(self):
        d = self.resolver.query(Query(b"EXAMPLE"))
        [answer], authority, additional = self.successResultOf(d)
        self.assertEqual(answer.payload.dottedQuad(), "1.1.1.1")

    def test_lookupAddressNotFound(self):
        """
        L{hosts.Resolver.lookupAddress} returns a L{Deferred} which fires with
        L{dns.DomainError} if the name passed in has no addresses in the hosts
        file.
        """
        self.failureResultOf(self.resolver.lookupAddress(b"foueoa"), DomainError)

    def test_lookupIPV6AddressNotFound(self):
        """
        Like L{test_lookupAddressNotFound}, but for
        L{hosts.Resolver.lookupIPV6Address}.
        """
        self.failureResultOf(self.resolver.lookupIPV6Address(b"foueoa"), DomainError)

    def test_lookupAllRecordsNotFound(self):
        """
        Like L{test_lookupAddressNotFound}, but for
        L{hosts.Resolver.lookupAllRecords}.
        """
        self.failureResultOf(self.resolver.lookupAllRecords(b"foueoa"), DomainError)

    def test_lookupMalformed(self):
        """
        L{hosts.Resolver.lookupAddress} returns a L{Deferred} which fires with
        the valid addresses from the hosts file, ignoring any entries that
        aren't valid IP addresses.
        """
        d = self.resolver.lookupAddress(b"malformed")
        [answer], authority, additional = self.successResultOf(d)
        self.assertEqual(
            RRHeader(b"malformed", A, IN, self.ttl, Record_A("1.1.1.5", self.ttl)),
            answer,
        )

    def test_lookupIPV6Malformed(self):
        """
        Like L{test_lookupAddressMalformed}, but for
        L{hosts.Resolver.lookupIPV6Address}.
        """
        d = self.resolver.lookupIPV6Address(b"malformed")
        [answer], authority, additional = self.successResultOf(d)
        self.assertEqual(
            RRHeader(b"malformed", AAAA, IN, self.ttl, Record_AAAA("::5", self.ttl)),
            answer,
        )
