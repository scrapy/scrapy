# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for implementations of L{IHostnameResolver} and their interactions with
reactor implementations.
"""


from collections import defaultdict
from socket import (
    AF_INET,
    AF_INET6,
    AF_UNSPEC,
    EAI_NONAME,
    IPPROTO_TCP,
    SOCK_DGRAM,
    SOCK_STREAM,
    gaierror,
    getaddrinfo,
)
from threading import Lock, local

from zope.interface import implementer
from zope.interface.verify import verifyObject

from twisted._threads import LockWorker, Team, createMemoryWorker
from twisted.internet._resolver import (
    ComplexResolverSimplifier,
    GAIResolver,
    SimpleResolverComplexifier,
)
from twisted.internet.address import IPv4Address, IPv6Address
from twisted.internet.base import PluggableResolverMixin, ReactorBase
from twisted.internet.defer import Deferred
from twisted.internet.error import DNSLookupError
from twisted.internet.interfaces import (
    IHostnameResolver,
    IReactorPluggableNameResolver,
    IResolutionReceiver,
    IResolverSimple,
)
from twisted.python.threadpool import ThreadPool
from twisted.trial.unittest import SynchronousTestCase as UnitTest


class DeterministicThreadPool(ThreadPool):
    """
    Create a deterministic L{ThreadPool} object.
    """

    def __init__(self, team):
        """
        Create a L{DeterministicThreadPool} from a L{Team}.
        """
        self.min = 1
        self.max = 1
        self.name = None
        self.threads = []
        self._team = team


def deterministicPool():
    """
    Create a deterministic threadpool.

    @return: 2-tuple of L{ThreadPool}, 0-argument C{work} callable; when
        C{work} is called, do the work.
    """
    worker, doer = createMemoryWorker()
    return (
        DeterministicThreadPool(
            Team(LockWorker(Lock(), local()), (lambda: worker), lambda: None)
        ),
        doer,
    )


def deterministicReactorThreads():
    """
    Create a deterministic L{IReactorThreads}

    @return: a 2-tuple consisting of an L{IReactorThreads}-like object and a
        0-argument callable that will perform one unit of work invoked via that
        object's C{callFromThread} method.
    """
    worker, doer = createMemoryWorker()

    class CFT:
        def callFromThread(self, f, *a, **k):
            worker.do(lambda: f(*a, **k))

    return CFT(), doer


class FakeAddrInfoGetter:
    """
    Test object implementing getaddrinfo.
    """

    def __init__(self):
        """
        Create a L{FakeAddrInfoGetter}.
        """
        self.calls = []
        self.results = defaultdict(list)

    def getaddrinfo(self, host, port, family=0, socktype=0, proto=0, flags=0):
        """
        Mock for L{socket.getaddrinfo}.

        @param host: see L{socket.getaddrinfo}

        @param port: see L{socket.getaddrinfo}

        @param family: see L{socket.getaddrinfo}

        @param socktype: see L{socket.getaddrinfo}

        @param proto: see L{socket.getaddrinfo}

        @param flags: see L{socket.getaddrinfo}

        @return: L{socket.getaddrinfo}
        """
        self.calls.append((host, port, family, socktype, proto, flags))
        results = self.results[host]
        if results:
            return results
        else:
            raise gaierror(EAI_NONAME, "nodename nor servname provided, or not known")

    def addResultForHost(
        self,
        host,
        sockaddr,
        family=AF_INET,
        socktype=SOCK_STREAM,
        proto=IPPROTO_TCP,
        canonname=b"",
    ):
        """
        Add a result for a given hostname.  When this hostname is resolved, the
        result will be a L{list} of all results C{addResultForHost} has been
        called with using that hostname so far.

        @param host: The hostname to give this result for.  This will be the
            next result from L{FakeAddrInfoGetter.getaddrinfo} when passed this
            host.

        @type canonname: native L{str}

        @param sockaddr: The resulting socket address; should be a 2-tuple for
            IPv4 or a 4-tuple for IPv6.

        @param family: An C{AF_*} constant that will be returned from
            C{getaddrinfo}.

        @param socktype: A C{SOCK_*} constant that will be returned from
            C{getaddrinfo}.

        @param proto: An C{IPPROTO_*} constant that will be returned from
            C{getaddrinfo}.

        @param canonname: A canonical name that will be returned from
            C{getaddrinfo}.
        @type canonname: native L{str}
        """
        self.results[host].append((family, socktype, proto, canonname, sockaddr))


@implementer(IResolutionReceiver)
class ResultHolder:
    """
    A resolution receiver which holds onto the results it received.
    """

    _started = False
    _ended = False

    def __init__(self, testCase):
        """
        Create a L{ResultHolder} with a L{UnitTest}.
        """
        self._testCase = testCase

    def resolutionBegan(self, hostResolution):
        """
        Hostname resolution began.

        @param hostResolution: see L{IResolutionReceiver}
        """
        self._started = True
        self._resolution = hostResolution
        self._addresses = []

    def addressResolved(self, address):
        """
        An address was resolved.

        @param address: see L{IResolutionReceiver}
        """
        self._addresses.append(address)

    def resolutionComplete(self):
        """
        Hostname resolution is complete.
        """
        self._ended = True


class HelperTests(UnitTest):
    """
    Tests for error cases of helpers used in this module.
    """

    def test_logErrorsInThreads(self):
        """
        L{DeterministicThreadPool} will log any exceptions that its "thread"
        workers encounter.
        """
        self.pool, self.doThreadWork = deterministicPool()

        def divideByZero():
            return 1 / 0

        self.pool.callInThread(divideByZero)
        self.doThreadWork()
        self.assertEqual(len(self.flushLoggedErrors(ZeroDivisionError)), 1)


class HostnameResolutionTests(UnitTest):
    """
    Tests for hostname resolution.
    """

    def setUp(self):
        """
        Set up a L{GAIResolver}.
        """
        self.pool, self.doThreadWork = deterministicPool()
        self.reactor, self.doReactorWork = deterministicReactorThreads()
        self.getter = FakeAddrInfoGetter()
        self.resolver = GAIResolver(
            self.reactor, lambda: self.pool, self.getter.getaddrinfo
        )

    def test_resolveOneHost(self):
        """
        Resolving an individual hostname that results in one address from
        getaddrinfo results in a single call each to C{resolutionBegan},
        C{addressResolved}, and C{resolutionComplete}.
        """
        receiver = ResultHolder(self)
        self.getter.addResultForHost("sample.example.com", ("4.3.2.1", 0))
        resolution = self.resolver.resolveHostName(receiver, "sample.example.com")
        self.assertIs(receiver._resolution, resolution)
        self.assertEqual(receiver._started, True)
        self.assertEqual(receiver._ended, False)
        self.doThreadWork()
        self.doReactorWork()
        self.assertEqual(receiver._ended, True)
        self.assertEqual(receiver._addresses, [IPv4Address("TCP", "4.3.2.1", 0)])

    def test_resolveOneIPv6Host(self):
        """
        Resolving an individual hostname that results in one address from
        getaddrinfo results in a single call each to C{resolutionBegan},
        C{addressResolved}, and C{resolutionComplete}; C{addressResolved} will
        receive an L{IPv6Address}.
        """
        receiver = ResultHolder(self)
        flowInfo = 1
        scopeID = 2
        self.getter.addResultForHost(
            "sample.example.com", ("::1", 0, flowInfo, scopeID), family=AF_INET6
        )
        resolution = self.resolver.resolveHostName(receiver, "sample.example.com")
        self.assertIs(receiver._resolution, resolution)
        self.assertEqual(receiver._started, True)
        self.assertEqual(receiver._ended, False)
        self.doThreadWork()
        self.doReactorWork()
        self.assertEqual(receiver._ended, True)
        self.assertEqual(
            receiver._addresses, [IPv6Address("TCP", "::1", 0, flowInfo, scopeID)]
        )

    def test_gaierror(self):
        """
        Resolving a hostname that results in C{getaddrinfo} raising a
        L{gaierror} will result in the L{IResolutionReceiver} receiving a call
        to C{resolutionComplete} with no C{addressResolved} calls in between;
        no failure is logged.
        """
        receiver = ResultHolder(self)
        resolution = self.resolver.resolveHostName(receiver, "sample.example.com")
        self.assertIs(receiver._resolution, resolution)
        self.doThreadWork()
        self.doReactorWork()
        self.assertEqual(receiver._started, True)
        self.assertEqual(receiver._ended, True)
        self.assertEqual(receiver._addresses, [])

    def _resolveOnlyTest(self, addrTypes, expectedAF):
        """
        Verify that the given set of address types results in the given C{AF_}
        constant being passed to C{getaddrinfo}.

        @param addrTypes: iterable of L{IAddress} implementers

        @param expectedAF: an C{AF_*} constant
        """
        receiver = ResultHolder(self)
        resolution = self.resolver.resolveHostName(
            receiver, "sample.example.com", addressTypes=addrTypes
        )
        self.assertIs(receiver._resolution, resolution)
        self.doThreadWork()
        self.doReactorWork()
        host, port, family, socktype, proto, flags = self.getter.calls[0]
        self.assertEqual(family, expectedAF)

    def test_resolveOnlyIPv4(self):
        """
        When passed an C{addressTypes} parameter containing only
        L{IPv4Address}, L{GAIResolver} will pass C{AF_INET} to C{getaddrinfo}.
        """
        self._resolveOnlyTest([IPv4Address], AF_INET)

    def test_resolveOnlyIPv6(self):
        """
        When passed an C{addressTypes} parameter containing only
        L{IPv6Address}, L{GAIResolver} will pass C{AF_INET6} to C{getaddrinfo}.
        """
        self._resolveOnlyTest([IPv6Address], AF_INET6)

    def test_resolveBoth(self):
        """
        When passed an C{addressTypes} parameter containing both L{IPv4Address}
        and L{IPv6Address} (or the default of C{None}, which carries the same
        meaning), L{GAIResolver} will pass C{AF_UNSPEC} to C{getaddrinfo}.
        """
        self._resolveOnlyTest([IPv4Address, IPv6Address], AF_UNSPEC)
        self._resolveOnlyTest(None, AF_UNSPEC)

    def test_transportSemanticsToSocketType(self):
        """
        When passed a C{transportSemantics} paramter, C{'TCP'} (the value
        present in L{IPv4Address.type} to indicate a stream transport) maps to
        C{SOCK_STREAM} and C{'UDP'} maps to C{SOCK_DGRAM}.
        """
        receiver = ResultHolder(self)
        self.resolver.resolveHostName(receiver, "example.com", transportSemantics="TCP")
        receiver2 = ResultHolder(self)
        self.resolver.resolveHostName(
            receiver2, "example.com", transportSemantics="UDP"
        )
        self.doThreadWork()
        self.doReactorWork()
        self.doThreadWork()
        self.doReactorWork()
        host, port, family, socktypeT, proto, flags = self.getter.calls[0]
        host, port, family, socktypeU, proto, flags = self.getter.calls[1]
        self.assertEqual(socktypeT, SOCK_STREAM)
        self.assertEqual(socktypeU, SOCK_DGRAM)

    def test_socketTypeToAddressType(self):
        """
        When L{GAIResolver} receives a C{SOCK_DGRAM} result from
        C{getaddrinfo}, it returns a C{'TCP'} L{IPv4Address} or L{IPv6Address};
        if it receives C{SOCK_STREAM} then it returns a C{'UDP'} type of same.
        """
        receiver = ResultHolder(self)
        flowInfo = 1
        scopeID = 2
        for socktype in SOCK_STREAM, SOCK_DGRAM:
            self.getter.addResultForHost(
                "example.com",
                ("::1", 0, flowInfo, scopeID),
                family=AF_INET6,
                socktype=socktype,
            )
            self.getter.addResultForHost(
                "example.com", ("127.0.0.3", 0), family=AF_INET, socktype=socktype
            )
        self.resolver.resolveHostName(receiver, "example.com")
        self.doThreadWork()
        self.doReactorWork()
        stream4, stream6, dgram4, dgram6 = receiver._addresses
        self.assertEqual(stream4.type, "TCP")
        self.assertEqual(stream6.type, "TCP")
        self.assertEqual(dgram4.type, "UDP")
        self.assertEqual(dgram6.type, "UDP")


@implementer(IResolverSimple)
class SillyResolverSimple:
    """
    Trivial implementation of L{IResolverSimple}
    """

    def __init__(self):
        """
        Create a L{SillyResolverSimple} with a queue of requests it is working
        on.
        """
        self._requests = []

    def getHostByName(self, name, timeout=()):
        """
        Implement L{IResolverSimple.getHostByName}.

        @param name: see L{IResolverSimple.getHostByName}.

        @param timeout: see L{IResolverSimple.getHostByName}.

        @return: see L{IResolverSimple.getHostByName}.
        """
        self._requests.append(Deferred())
        return self._requests[-1]


class LegacyCompatibilityTests(UnitTest):
    """
    Older applications may supply an object to the reactor via
    C{installResolver} that only provides L{IResolverSimple}.
    L{SimpleResolverComplexifier} is a wrapper for an L{IResolverSimple}.
    """

    def test_success(self):
        """
        L{SimpleResolverComplexifier} translates C{resolveHostName} into
        L{IResolutionReceiver.addressResolved}.
        """
        simple = SillyResolverSimple()
        complex = SimpleResolverComplexifier(simple)
        receiver = ResultHolder(self)
        self.assertEqual(receiver._started, False)
        complex.resolveHostName(receiver, "example.com")
        self.assertEqual(receiver._started, True)
        self.assertEqual(receiver._ended, False)
        self.assertEqual(receiver._addresses, [])
        simple._requests[0].callback("192.168.1.1")
        self.assertEqual(receiver._addresses, [IPv4Address("TCP", "192.168.1.1", 0)])
        self.assertEqual(receiver._ended, True)

    def test_failure(self):
        """
        L{SimpleResolverComplexifier} translates a known error result from
        L{IResolverSimple.resolveHostName} into an empty result.
        """
        simple = SillyResolverSimple()
        complex = SimpleResolverComplexifier(simple)
        receiver = ResultHolder(self)
        self.assertEqual(receiver._started, False)
        complex.resolveHostName(receiver, "example.com")
        self.assertEqual(receiver._started, True)
        self.assertEqual(receiver._ended, False)
        self.assertEqual(receiver._addresses, [])
        simple._requests[0].errback(DNSLookupError("nope"))
        self.assertEqual(receiver._ended, True)
        self.assertEqual(receiver._addresses, [])

    def test_error(self):
        """
        L{SimpleResolverComplexifier} translates an unknown error result from
        L{IResolverSimple.resolveHostName} into an empty result and a logged
        error.
        """
        simple = SillyResolverSimple()
        complex = SimpleResolverComplexifier(simple)
        receiver = ResultHolder(self)
        self.assertEqual(receiver._started, False)
        complex.resolveHostName(receiver, "example.com")
        self.assertEqual(receiver._started, True)
        self.assertEqual(receiver._ended, False)
        self.assertEqual(receiver._addresses, [])
        simple._requests[0].errback(ZeroDivisionError("zow"))
        self.assertEqual(len(self.flushLoggedErrors(ZeroDivisionError)), 1)
        self.assertEqual(receiver._ended, True)
        self.assertEqual(receiver._addresses, [])

    def test_simplifier(self):
        """
        L{ComplexResolverSimplifier} translates an L{IHostnameResolver} into an
        L{IResolverSimple} for applications that still expect the old
        interfaces to be in place.
        """
        self.pool, self.doThreadWork = deterministicPool()
        self.reactor, self.doReactorWork = deterministicReactorThreads()
        self.getter = FakeAddrInfoGetter()
        self.resolver = GAIResolver(
            self.reactor, lambda: self.pool, self.getter.getaddrinfo
        )
        simpleResolver = ComplexResolverSimplifier(self.resolver)
        self.getter.addResultForHost("example.com", ("192.168.3.4", 4321))
        success = simpleResolver.getHostByName("example.com")
        failure = simpleResolver.getHostByName("nx.example.com")
        self.doThreadWork()
        self.doReactorWork()
        self.doThreadWork()
        self.doReactorWork()
        self.assertEqual(self.failureResultOf(failure).type, DNSLookupError)
        self.assertEqual(self.successResultOf(success), "192.168.3.4")

    def test_portNumber(self):
        """
        L{SimpleResolverComplexifier} preserves the C{port} argument passed to
        C{resolveHostName} in its returned addresses.
        """
        simple = SillyResolverSimple()
        complex = SimpleResolverComplexifier(simple)
        receiver = ResultHolder(self)
        complex.resolveHostName(receiver, "example.com", 4321)
        self.assertEqual(receiver._started, True)
        self.assertEqual(receiver._ended, False)
        self.assertEqual(receiver._addresses, [])
        simple._requests[0].callback("192.168.1.1")
        self.assertEqual(receiver._addresses, [IPv4Address("TCP", "192.168.1.1", 4321)])
        self.assertEqual(receiver._ended, True)


class JustEnoughReactor(ReactorBase):
    """
    Just enough subclass implementation to be a valid L{ReactorBase} subclass.
    """

    def installWaker(self):
        """
        Do nothing.
        """


class ReactorInstallationTests(UnitTest):
    """
    Tests for installing old and new resolvers onto a
    L{PluggableResolverMixin} and L{ReactorBase} (from which all of Twisted's
    reactor implementations derive).
    """

    def test_interfaceCompliance(self):
        """
        L{PluggableResolverMixin} (and its subclasses) implement both
        L{IReactorPluggableNameResolver} and L{IReactorPluggableResolver}.
        """
        reactor = PluggableResolverMixin()
        verifyObject(IReactorPluggableNameResolver, reactor)
        verifyObject(IResolverSimple, reactor.resolver)
        verifyObject(IHostnameResolver, reactor.nameResolver)

    def test_installingOldStyleResolver(self):
        """
        L{PluggableResolverMixin} will wrap an L{IResolverSimple} in a
        complexifier.
        """
        reactor = PluggableResolverMixin()
        it = SillyResolverSimple()
        verifyObject(IResolverSimple, reactor.installResolver(it))
        self.assertIsInstance(reactor.nameResolver, SimpleResolverComplexifier)
        self.assertIs(reactor.nameResolver._simpleResolver, it)

    def test_defaultToGAIResolver(self):
        """
        L{ReactorBase} defaults to using a L{GAIResolver}.
        """
        reactor = JustEnoughReactor()
        self.assertIsInstance(reactor.nameResolver, GAIResolver)
        self.assertIs(reactor.nameResolver._getaddrinfo, getaddrinfo)
        self.assertIsInstance(reactor.resolver, ComplexResolverSimplifier)
        self.assertIs(reactor.nameResolver._reactor, reactor)
        self.assertIs(reactor.resolver._nameResolver, reactor.nameResolver)
