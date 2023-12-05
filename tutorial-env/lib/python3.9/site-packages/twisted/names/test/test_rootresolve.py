# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for Twisted.names' root resolver.
"""

from zope.interface import implementer
from zope.interface.verify import verifyClass

from twisted.internet.defer import Deferred, TimeoutError, gatherResults, succeed
from twisted.internet.interfaces import IResolverSimple
from twisted.names import client, root
from twisted.names.dns import (
    CNAME,
    ENAME,
    HS,
    IN,
    NS,
    OK,
    A,
    Message,
    Name,
    Query,
    Record_A,
    Record_CNAME,
    Record_NS,
    RRHeader,
)
from twisted.names.error import DNSNameError, ResolverError
from twisted.names.root import Resolver
from twisted.names.test.test_util import MemoryReactor
from twisted.python.log import msg
from twisted.trial import util
from twisted.trial.unittest import SynchronousTestCase, TestCase


def getOnePayload(results):
    """
    From the result of a L{Deferred} returned by L{IResolver.lookupAddress},
    return the payload of the first record in the answer section.
    """
    ans, auth, add = results
    return ans[0].payload


def getOneAddress(results):
    """
    From the result of a L{Deferred} returned by L{IResolver.lookupAddress},
    return the first IPv4 address from the answer section.
    """
    return getOnePayload(results).dottedQuad()


class RootResolverTests(TestCase):
    """
    Tests for L{twisted.names.root.Resolver}.
    """

    def _queryTest(self, filter):
        """
        Invoke L{Resolver._query} and verify that it sends the correct DNS
        query.  Deliver a canned response to the query and return whatever the
        L{Deferred} returned by L{Resolver._query} fires with.

        @param filter: The value to pass for the C{filter} parameter to
            L{Resolver._query}.
        """
        reactor = MemoryReactor()
        resolver = Resolver([], reactor=reactor)
        d = resolver._query(
            Query(b"foo.example.com", A, IN), [("1.1.2.3", 1053)], (30,), filter
        )

        # A UDP port should have been started.
        portNumber, transport = reactor.udpPorts.popitem()

        # And a DNS packet sent.
        [(packet, address)] = transport._sentPackets

        message = Message()
        message.fromStr(packet)

        # It should be a query with the parameters used above.
        self.assertEqual(message.queries, [Query(b"foo.example.com", A, IN)])
        self.assertEqual(message.answers, [])
        self.assertEqual(message.authority, [])
        self.assertEqual(message.additional, [])

        response = []
        d.addCallback(response.append)
        self.assertEqual(response, [])

        # Once a reply is received, the Deferred should fire.
        del message.queries[:]
        message.answer = 1
        message.answers.append(
            RRHeader(b"foo.example.com", payload=Record_A("5.8.13.21"))
        )
        transport._protocol.datagramReceived(message.toStr(), ("1.1.2.3", 1053))
        return response[0]

    def test_filteredQuery(self):
        """
        L{Resolver._query} accepts a L{Query} instance and an address, issues
        the query, and returns a L{Deferred} which fires with the response to
        the query.  If a true value is passed for the C{filter} parameter, the
        result is a three-tuple of lists of records.
        """
        answer, authority, additional = self._queryTest(True)
        self.assertEqual(
            answer, [RRHeader(b"foo.example.com", payload=Record_A("5.8.13.21", ttl=0))]
        )
        self.assertEqual(authority, [])
        self.assertEqual(additional, [])

    def test_unfilteredQuery(self):
        """
        Similar to L{test_filteredQuery}, but for the case where a false value
        is passed for the C{filter} parameter.  In this case, the result is a
        L{Message} instance.
        """
        message = self._queryTest(False)
        self.assertIsInstance(message, Message)
        self.assertEqual(message.queries, [])
        self.assertEqual(
            message.answers,
            [RRHeader(b"foo.example.com", payload=Record_A("5.8.13.21", ttl=0))],
        )
        self.assertEqual(message.authority, [])
        self.assertEqual(message.additional, [])

    def _respond(self, answers=[], authority=[], additional=[], rCode=OK):
        """
        Create a L{Message} suitable for use as a response to a query.

        @param answers: A C{list} of two-tuples giving data for the answers
            section of the message.  The first element of each tuple is a name
            for the L{RRHeader}.  The second element is the payload.
        @param authority: A C{list} like C{answers}, but for the authority
            section of the response.
        @param additional: A C{list} like C{answers}, but for the
            additional section of the response.
        @param rCode: The response code the message will be created with.

        @return: A new L{Message} initialized with the given values.
        """
        response = Message(rCode=rCode)
        for (section, data) in [
            (response.answers, answers),
            (response.authority, authority),
            (response.additional, additional),
        ]:
            section.extend(
                [
                    RRHeader(
                        name, record.TYPE, getattr(record, "CLASS", IN), payload=record
                    )
                    for (name, record) in data
                ]
            )
        return response

    def _getResolver(self, serverResponses, maximumQueries=10):
        """
        Create and return a new L{root.Resolver} modified to resolve queries
        against the record data represented by C{servers}.

        @param serverResponses: A mapping from dns server addresses to
            mappings.  The inner mappings are from query two-tuples (name,
            type) to dictionaries suitable for use as **arguments to
            L{_respond}.  See that method for details.
        """
        roots = ["1.1.2.3"]
        resolver = Resolver(roots, maximumQueries)

        def query(query, serverAddresses, timeout, filter):
            msg(f"Query for QNAME {query.name} at {serverAddresses!r}")
            for addr in serverAddresses:
                try:
                    server = serverResponses[addr]
                except KeyError:
                    continue
                records = server[query.name.name, query.type]
                return succeed(self._respond(**records))

        resolver._query = query
        return resolver

    def test_lookupAddress(self):
        """
        L{root.Resolver.lookupAddress} looks up the I{A} records for the
        specified hostname by first querying one of the root servers the
        resolver was created with and then following the authority delegations
        until a result is received.
        """
        servers = {
            ("1.1.2.3", 53): {
                (b"foo.example.com", A): {
                    "authority": [(b"foo.example.com", Record_NS(b"ns1.example.com"))],
                    "additional": [(b"ns1.example.com", Record_A("34.55.89.144"))],
                },
            },
            ("34.55.89.144", 53): {
                (b"foo.example.com", A): {
                    "answers": [(b"foo.example.com", Record_A("10.0.0.1"))],
                }
            },
        }
        resolver = self._getResolver(servers)
        d = resolver.lookupAddress(b"foo.example.com")
        d.addCallback(getOneAddress)
        d.addCallback(self.assertEqual, "10.0.0.1")
        return d

    def test_lookupChecksClass(self):
        """
        If a response includes a record with a class different from the one
        in the query, it is ignored and lookup continues until a record with
        the right class is found.
        """
        badClass = Record_A("10.0.0.1")
        badClass.CLASS = HS
        servers = {
            ("1.1.2.3", 53): {
                (b"foo.example.com", A): {
                    "answers": [(b"foo.example.com", badClass)],
                    "authority": [(b"foo.example.com", Record_NS(b"ns1.example.com"))],
                    "additional": [(b"ns1.example.com", Record_A("10.0.0.2"))],
                },
            },
            ("10.0.0.2", 53): {
                (b"foo.example.com", A): {
                    "answers": [(b"foo.example.com", Record_A("10.0.0.3"))],
                },
            },
        }
        resolver = self._getResolver(servers)
        d = resolver.lookupAddress(b"foo.example.com")
        d.addCallback(getOnePayload)
        d.addCallback(self.assertEqual, Record_A("10.0.0.3"))
        return d

    def test_missingGlue(self):
        """
        If an intermediate response includes no glue records for the
        authorities, separate queries are made to find those addresses.
        """
        servers = {
            ("1.1.2.3", 53): {
                (b"foo.example.com", A): {
                    "authority": [(b"foo.example.com", Record_NS(b"ns1.example.org"))],
                    # Conspicuous lack of an additional section naming ns1.example.com
                },
                (b"ns1.example.org", A): {
                    "answers": [(b"ns1.example.org", Record_A("10.0.0.1"))],
                },
            },
            ("10.0.0.1", 53): {
                (b"foo.example.com", A): {
                    "answers": [(b"foo.example.com", Record_A("10.0.0.2"))],
                },
            },
        }
        resolver = self._getResolver(servers)
        d = resolver.lookupAddress(b"foo.example.com")
        d.addCallback(getOneAddress)
        d.addCallback(self.assertEqual, "10.0.0.2")
        return d

    def test_missingName(self):
        """
        If a name is missing, L{Resolver.lookupAddress} returns a L{Deferred}
        which fails with L{DNSNameError}.
        """
        servers = {
            ("1.1.2.3", 53): {
                (b"foo.example.com", A): {
                    "rCode": ENAME,
                },
            },
        }
        resolver = self._getResolver(servers)
        d = resolver.lookupAddress(b"foo.example.com")
        return self.assertFailure(d, DNSNameError)

    def test_answerless(self):
        """
        If a query is responded to with no answers or nameserver records, the
        L{Deferred} returned by L{Resolver.lookupAddress} fires with
        L{ResolverError}.
        """
        servers = {
            ("1.1.2.3", 53): {
                (b"example.com", A): {},
            },
        }
        resolver = self._getResolver(servers)
        d = resolver.lookupAddress(b"example.com")
        return self.assertFailure(d, ResolverError)

    def test_delegationLookupError(self):
        """
        If there is an error resolving the nameserver in a delegation response,
        the L{Deferred} returned by L{Resolver.lookupAddress} fires with that
        error.
        """
        servers = {
            ("1.1.2.3", 53): {
                (b"example.com", A): {
                    "authority": [(b"example.com", Record_NS(b"ns1.example.com"))],
                },
                (b"ns1.example.com", A): {
                    "rCode": ENAME,
                },
            },
        }
        resolver = self._getResolver(servers)
        d = resolver.lookupAddress(b"example.com")
        return self.assertFailure(d, DNSNameError)

    def test_delegationLookupEmpty(self):
        """
        If there are no records in the response to a lookup of a delegation
        nameserver, the L{Deferred} returned by L{Resolver.lookupAddress} fires
        with L{ResolverError}.
        """
        servers = {
            ("1.1.2.3", 53): {
                (b"example.com", A): {
                    "authority": [(b"example.com", Record_NS(b"ns1.example.com"))],
                },
                (b"ns1.example.com", A): {},
            },
        }
        resolver = self._getResolver(servers)
        d = resolver.lookupAddress(b"example.com")
        return self.assertFailure(d, ResolverError)

    def test_lookupNameservers(self):
        """
        L{Resolver.lookupNameservers} is like L{Resolver.lookupAddress}, except
        it queries for I{NS} records instead of I{A} records.
        """
        servers = {
            ("1.1.2.3", 53): {
                (b"example.com", A): {
                    "rCode": ENAME,
                },
                (b"example.com", NS): {
                    "answers": [(b"example.com", Record_NS(b"ns1.example.com"))],
                },
            },
        }
        resolver = self._getResolver(servers)
        d = resolver.lookupNameservers(b"example.com")

        def getOneName(results):
            ans, auth, add = results
            return ans[0].payload.name

        d.addCallback(getOneName)
        d.addCallback(self.assertEqual, Name(b"ns1.example.com"))
        return d

    def test_returnCanonicalName(self):
        """
        If a I{CNAME} record is encountered as the answer to a query for
        another record type, that record is returned as the answer.
        """
        servers = {
            ("1.1.2.3", 53): {
                (b"example.com", A): {
                    "answers": [
                        (b"example.com", Record_CNAME(b"example.net")),
                        (b"example.net", Record_A("10.0.0.7")),
                    ],
                },
            },
        }
        resolver = self._getResolver(servers)
        d = resolver.lookupAddress(b"example.com")
        d.addCallback(lambda results: results[0])  # Get the answer section
        d.addCallback(
            self.assertEqual,
            [
                RRHeader(b"example.com", CNAME, payload=Record_CNAME(b"example.net")),
                RRHeader(b"example.net", A, payload=Record_A("10.0.0.7")),
            ],
        )
        return d

    def test_followCanonicalName(self):
        """
        If no record of the requested type is included in a response, but a
        I{CNAME} record for the query name is included, queries are made to
        resolve the value of the I{CNAME}.
        """
        servers = {
            ("1.1.2.3", 53): {
                (b"example.com", A): {
                    "answers": [(b"example.com", Record_CNAME(b"example.net"))],
                },
                (b"example.net", A): {
                    "answers": [(b"example.net", Record_A("10.0.0.5"))],
                },
            },
        }
        resolver = self._getResolver(servers)
        d = resolver.lookupAddress(b"example.com")
        d.addCallback(lambda results: results[0])  # Get the answer section
        d.addCallback(
            self.assertEqual,
            [
                RRHeader(b"example.com", CNAME, payload=Record_CNAME(b"example.net")),
                RRHeader(b"example.net", A, payload=Record_A("10.0.0.5")),
            ],
        )
        return d

    def test_detectCanonicalNameLoop(self):
        """
        If there is a cycle between I{CNAME} records in a response, this is
        detected and the L{Deferred} returned by the lookup method fails
        with L{ResolverError}.
        """
        servers = {
            ("1.1.2.3", 53): {
                (b"example.com", A): {
                    "answers": [
                        (b"example.com", Record_CNAME(b"example.net")),
                        (b"example.net", Record_CNAME(b"example.com")),
                    ],
                },
            },
        }
        resolver = self._getResolver(servers)
        d = resolver.lookupAddress(b"example.com")
        return self.assertFailure(d, ResolverError)

    def test_boundedQueries(self):
        """
        L{Resolver.lookupAddress} won't issue more queries following
        delegations than the limit passed to its initializer.
        """
        servers = {
            ("1.1.2.3", 53): {
                # First query - force it to start over with a name lookup of
                # ns1.example.com
                (b"example.com", A): {
                    "authority": [(b"example.com", Record_NS(b"ns1.example.com"))],
                },
                # Second query - let it resume the original lookup with the
                # address of the nameserver handling the delegation.
                (b"ns1.example.com", A): {
                    "answers": [(b"ns1.example.com", Record_A("10.0.0.2"))],
                },
            },
            ("10.0.0.2", 53): {
                # Third query - let it jump straight to asking the
                # delegation server by including its address here (different
                # case from the first query).
                (b"example.com", A): {
                    "authority": [(b"example.com", Record_NS(b"ns2.example.com"))],
                    "additional": [(b"ns2.example.com", Record_A("10.0.0.3"))],
                },
            },
            ("10.0.0.3", 53): {
                # Fourth query - give it the answer, we're done.
                (b"example.com", A): {
                    "answers": [(b"example.com", Record_A("10.0.0.4"))],
                },
            },
        }

        # Make two resolvers.  One which is allowed to make 3 queries
        # maximum, and so will fail, and on which may make 4, and so should
        # succeed.
        failer = self._getResolver(servers, 3)
        failD = self.assertFailure(failer.lookupAddress(b"example.com"), ResolverError)

        succeeder = self._getResolver(servers, 4)
        succeedD = succeeder.lookupAddress(b"example.com")
        succeedD.addCallback(getOnePayload)
        succeedD.addCallback(self.assertEqual, Record_A("10.0.0.4"))

        return gatherResults([failD, succeedD])


class ResolverFactoryArguments(Exception):
    """
    Raised by L{raisingResolverFactory} with the *args and **kwargs passed to
    that function.
    """

    def __init__(self, args, kwargs):
        """
        Store the supplied args and kwargs as attributes.

        @param args: Positional arguments.
        @param kwargs: Keyword arguments.
        """
        self.args = args
        self.kwargs = kwargs


def raisingResolverFactory(*args, **kwargs):
    """
    Raise a L{ResolverFactoryArguments} exception containing the
    positional and keyword arguments passed to resolverFactory.

    @param args: A L{list} of all the positional arguments supplied by
        the caller.

    @param kwargs: A L{list} of all the keyword arguments supplied by
        the caller.
    """
    raise ResolverFactoryArguments(args, kwargs)


class RootResolverResolverFactoryTests(TestCase):
    """
    Tests for L{root.Resolver._resolverFactory}.
    """

    def test_resolverFactoryArgumentPresent(self):
        """
        L{root.Resolver.__init__} accepts a C{resolverFactory}
        argument and assigns it to C{self._resolverFactory}.
        """
        r = Resolver(hints=[None], resolverFactory=raisingResolverFactory)
        self.assertIs(r._resolverFactory, raisingResolverFactory)

    def test_resolverFactoryArgumentAbsent(self):
        """
        L{root.Resolver.__init__} sets L{client.Resolver} as the
        C{_resolverFactory} if a C{resolverFactory} argument is not
        supplied.
        """
        r = Resolver(hints=[None])
        self.assertIs(r._resolverFactory, client.Resolver)

    def test_resolverFactoryOnlyExpectedArguments(self):
        """
        L{root.Resolver._resolverFactory} is supplied with C{reactor} and
        C{servers} keyword arguments.
        """
        dummyReactor = object()
        r = Resolver(
            hints=["192.0.2.101"],
            resolverFactory=raisingResolverFactory,
            reactor=dummyReactor,
        )

        e = self.assertRaises(ResolverFactoryArguments, r.lookupAddress, "example.com")

        self.assertEqual(
            ((), {"reactor": dummyReactor, "servers": [("192.0.2.101", 53)]}),
            (e.args, e.kwargs),
        )


ROOT_SERVERS = [
    "a.root-servers.net",
    "b.root-servers.net",
    "c.root-servers.net",
    "d.root-servers.net",
    "e.root-servers.net",
    "f.root-servers.net",
    "g.root-servers.net",
    "h.root-servers.net",
    "i.root-servers.net",
    "j.root-servers.net",
    "k.root-servers.net",
    "l.root-servers.net",
    "m.root-servers.net",
]


@implementer(IResolverSimple)
class StubResolver:
    """
    An L{IResolverSimple} implementer which traces all getHostByName
    calls and their deferred results. The deferred results can be
    accessed and fired synchronously.
    """

    def __init__(self):
        """
        @type calls: L{list} of L{tuple} containing C{args} and
            C{kwargs} supplied to C{getHostByName} calls.
        @type pendingResults: L{list} of L{Deferred} returned by
            C{getHostByName}.
        """
        self.calls = []
        self.pendingResults = []

    def getHostByName(self, *args, **kwargs):
        """
        A fake implementation of L{IResolverSimple.getHostByName}

        @param args: A L{list} of all the positional arguments supplied by
           the caller.

        @param kwargs: A L{list} of all the keyword arguments supplied by
           the caller.

        @return: A L{Deferred} which may be fired later from the test
            fixture.
        """
        self.calls.append((args, kwargs))
        d = Deferred()
        self.pendingResults.append(d)
        return d


verifyClass(IResolverSimple, StubResolver)


class BootstrapTests(SynchronousTestCase):
    """
    Tests for L{root.bootstrap}
    """

    def test_returnsDeferredResolver(self):
        """
        L{root.bootstrap} returns an object which is initially a
        L{root.DeferredResolver}.
        """
        deferredResolver = root.bootstrap(StubResolver())
        self.assertIsInstance(deferredResolver, root.DeferredResolver)

    def test_resolves13RootServers(self):
        """
        The L{IResolverSimple} supplied to L{root.bootstrap} is used to lookup
        the IP addresses of the 13 root name servers.
        """
        stubResolver = StubResolver()
        root.bootstrap(stubResolver)
        self.assertEqual(stubResolver.calls, [((s,), {}) for s in ROOT_SERVERS])

    def test_becomesResolver(self):
        """
        The L{root.DeferredResolver} initially returned by L{root.bootstrap}
        becomes a L{root.Resolver} when the supplied resolver has successfully
        looked up all root hints.
        """
        stubResolver = StubResolver()
        deferredResolver = root.bootstrap(stubResolver)
        for d in stubResolver.pendingResults:
            d.callback("192.0.2.101")
        self.assertIsInstance(deferredResolver, Resolver)

    def test_resolverReceivesRootHints(self):
        """
        The L{root.Resolver} which eventually replaces L{root.DeferredResolver}
        is supplied with the IP addresses of the 13 root servers.
        """
        stubResolver = StubResolver()
        deferredResolver = root.bootstrap(stubResolver)
        for d in stubResolver.pendingResults:
            d.callback("192.0.2.101")
        self.assertEqual(deferredResolver.hints, ["192.0.2.101"] * 13)

    def test_continuesWhenSomeRootHintsFail(self):
        """
        The L{root.Resolver} is eventually created, even if some of the root
        hint lookups fail. Only the working root hint IP addresses are supplied
        to the L{root.Resolver}.
        """
        stubResolver = StubResolver()
        deferredResolver = root.bootstrap(stubResolver)
        results = iter(stubResolver.pendingResults)
        d1 = next(results)
        for d in results:
            d.callback("192.0.2.101")
        d1.errback(TimeoutError())

        def checkHints(res):
            self.assertEqual(deferredResolver.hints, ["192.0.2.101"] * 12)

        d1.addBoth(checkHints)

    def test_continuesWhenAllRootHintsFail(self):
        """
        The L{root.Resolver} is eventually created, even if all of the root hint
        lookups fail. Pending and new lookups will then fail with
        AttributeError.
        """
        stubResolver = StubResolver()
        deferredResolver = root.bootstrap(stubResolver)
        results = iter(stubResolver.pendingResults)
        d1 = next(results)
        for d in results:
            d.errback(TimeoutError())
        d1.errback(TimeoutError())

        def checkHints(res):
            self.assertEqual(deferredResolver.hints, [])

        d1.addBoth(checkHints)

        self.addCleanup(self.flushLoggedErrors, TimeoutError)

    def test_passesResolverFactory(self):
        """
        L{root.bootstrap} accepts a C{resolverFactory} argument which is passed
        as an argument to L{root.Resolver} when it has successfully looked up
        root hints.
        """
        stubResolver = StubResolver()
        deferredResolver = root.bootstrap(
            stubResolver, resolverFactory=raisingResolverFactory
        )

        for d in stubResolver.pendingResults:
            d.callback("192.0.2.101")

        self.assertIs(deferredResolver._resolverFactory, raisingResolverFactory)


class StubDNSDatagramProtocol:
    """
    A do-nothing stand-in for L{DNSDatagramProtocol} which can be used to avoid
    network traffic in tests where that kind of thing doesn't matter.
    """

    def query(self, *a, **kw):
        return Deferred()


_retrySuppression = util.suppress(
    category=DeprecationWarning,
    message=(
        "twisted.names.root.retry is deprecated since Twisted 10.0.  Use a "
        "Resolver object for retry logic."
    ),
)
