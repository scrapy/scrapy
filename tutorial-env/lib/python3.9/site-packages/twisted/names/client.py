# -*- test-case-name: twisted.names.test.test_names -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Asynchronous client DNS

The functions exposed in this module can be used for asynchronous name
resolution and dns queries.

If you need to create a resolver with specific requirements, such as needing to
do queries against a particular host, the L{createResolver} function will
return an C{IResolver}.

Future plans: Proper nameserver acquisition on Windows/MacOS,
better caching, respect timeouts
"""

import errno
import os
import warnings

from zope.interface import moduleProvides

from twisted.internet import defer, error, interfaces, protocol
from twisted.internet.abstract import isIPv6Address
from twisted.names import cache, common, dns, hosts as hostsModule, resolve, root
from twisted.python import failure, log

# Twisted imports
from twisted.python.compat import nativeString
from twisted.python.filepath import FilePath
from twisted.python.runtime import platform

moduleProvides(interfaces.IResolver)


class Resolver(common.ResolverBase):
    """
    @ivar _waiting: A C{dict} mapping tuple keys of query name/type/class to
        Deferreds which will be called back with the result of those queries.
        This is used to avoid issuing the same query more than once in
        parallel.  This is more efficient on the network and helps avoid a
        "birthday paradox" attack by keeping the number of outstanding requests
        for a particular query fixed at one instead of allowing the attacker to
        raise it to an arbitrary number.

    @ivar _reactor: A provider of L{IReactorTCP}, L{IReactorUDP}, and
        L{IReactorTime} which will be used to set up network resources and
        track timeouts.
    """

    index = 0
    timeout = None

    factory = None
    servers = None
    dynServers = ()
    pending = None
    connections = None

    resolv = None
    _lastResolvTime = None
    _resolvReadInterval = 60

    def __init__(self, resolv=None, servers=None, timeout=(1, 3, 11, 45), reactor=None):
        """
        Construct a resolver which will query domain name servers listed in
        the C{resolv.conf(5)}-format file given by C{resolv} as well as
        those in the given C{servers} list.  Servers are queried in a
        round-robin fashion.  If given, C{resolv} is periodically checked
        for modification and re-parsed if it is noticed to have changed.

        @type servers: C{list} of C{(str, int)} or L{None}
        @param servers: If not None, interpreted as a list of (host, port)
            pairs specifying addresses of domain name servers to attempt to use
            for this lookup.  Host addresses should be in IPv4 dotted-quad
            form.  If specified, overrides C{resolv}.

        @type resolv: C{str}
        @param resolv: Filename to read and parse as a resolver(5)
            configuration file.

        @type timeout: Sequence of C{int}
        @param timeout: Default number of seconds after which to reissue the
            query.  When the last timeout expires, the query is considered
            failed.

        @param reactor: A provider of L{IReactorTime}, L{IReactorUDP}, and
            L{IReactorTCP} which will be used to establish connections, listen
            for DNS datagrams, and enforce timeouts.  If not provided, the
            global reactor will be used.

        @raise ValueError: Raised if no nameserver addresses can be found.
        """
        common.ResolverBase.__init__(self)

        if reactor is None:
            from twisted.internet import reactor
        self._reactor = reactor

        self.timeout = timeout

        if servers is None:
            self.servers = []
        else:
            self.servers = servers

        self.resolv = resolv

        if not len(self.servers) and not resolv:
            raise ValueError("No nameservers specified")

        self.factory = DNSClientFactory(self, timeout)
        self.factory.noisy = 0  # Be quiet by default

        self.connections = []
        self.pending = []

        self._waiting = {}

        self.maybeParseConfig()

    def __getstate__(self):
        d = self.__dict__.copy()
        d["connections"] = []
        d["_parseCall"] = None
        return d

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.maybeParseConfig()

    def _openFile(self, path):
        """
        Wrapper used for opening files in the class, exists primarily for unit
        testing purposes.
        """
        return FilePath(path).open()

    def maybeParseConfig(self):
        if self.resolv is None:
            # Don't try to parse it, don't set up a call loop
            return

        try:
            resolvConf = self._openFile(self.resolv)
        except OSError as e:
            if e.errno == errno.ENOENT:
                # Missing resolv.conf is treated the same as an empty resolv.conf
                self.parseConfig(())
            else:
                raise
        else:
            with resolvConf:
                mtime = os.fstat(resolvConf.fileno()).st_mtime
                if mtime != self._lastResolvTime:
                    log.msg(f"{self.resolv} changed, reparsing")
                    self._lastResolvTime = mtime
                    self.parseConfig(resolvConf)

        # Check again in a little while
        self._parseCall = self._reactor.callLater(
            self._resolvReadInterval, self.maybeParseConfig
        )

    def parseConfig(self, resolvConf):
        servers = []
        for L in resolvConf:
            L = L.strip()
            if L.startswith(b"nameserver"):
                resolver = (nativeString(L.split()[1]), dns.PORT)
                servers.append(resolver)
                log.msg(f"Resolver added {resolver!r} to server list")
            elif L.startswith(b"domain"):
                try:
                    self.domain = L.split()[1]
                except IndexError:
                    self.domain = b""
                self.search = None
            elif L.startswith(b"search"):
                self.search = L.split()[1:]
                self.domain = None
        if not servers:
            servers.append(("127.0.0.1", dns.PORT))
        self.dynServers = servers

    def pickServer(self):
        """
        Return the address of a nameserver.

        TODO: Weight servers for response time so faster ones can be
        preferred.
        """
        if not self.servers and not self.dynServers:
            return None
        serverL = len(self.servers)
        dynL = len(self.dynServers)

        self.index += 1
        self.index %= serverL + dynL
        if self.index < serverL:
            return self.servers[self.index]
        else:
            return self.dynServers[self.index - serverL]

    def _connectedProtocol(self, interface=""):
        """
        Return a new L{DNSDatagramProtocol} bound to a randomly selected port
        number.
        """
        failures = 0
        proto = dns.DNSDatagramProtocol(self, reactor=self._reactor)

        while True:
            try:
                self._reactor.listenUDP(dns.randomSource(), proto, interface=interface)
            except error.CannotListenError as e:
                failures += 1

                if (
                    hasattr(e.socketError, "errno")
                    and e.socketError.errno == errno.EMFILE
                ):
                    # We've run out of file descriptors. Stop trying.
                    raise

                if failures >= 1000:
                    # We've tried a thousand times and haven't found a port.
                    # This is almost impossible, and likely means something
                    # else weird is going on. Raise, as to not infinite loop.
                    raise
            else:
                return proto

    def connectionMade(self, protocol):
        """
        Called by associated L{dns.DNSProtocol} instances when they connect.
        """
        self.connections.append(protocol)
        for (d, q, t) in self.pending:
            self.queryTCP(q, t).chainDeferred(d)
        del self.pending[:]

    def connectionLost(self, protocol):
        """
        Called by associated L{dns.DNSProtocol} instances when they disconnect.
        """
        if protocol in self.connections:
            self.connections.remove(protocol)

    def messageReceived(self, message, protocol, address=None):
        log.msg("Unexpected message (%d) received from %r" % (message.id, address))

    def _query(self, *args):
        """
        Get a new L{DNSDatagramProtocol} instance from L{_connectedProtocol},
        issue a query to it using C{*args}, and arrange for it to be
        disconnected from its transport after the query completes.

        @param args: Positional arguments to be passed to
            L{DNSDatagramProtocol.query}.

        @return: A L{Deferred} which will be called back with the result of the
            query.
        """
        if isIPv6Address(args[0][0]):
            protocol = self._connectedProtocol(interface="::")
        else:
            protocol = self._connectedProtocol()
        d = protocol.query(*args)

        def cbQueried(result):
            protocol.transport.stopListening()
            return result

        d.addBoth(cbQueried)
        return d

    def queryUDP(self, queries, timeout=None):
        """
        Make a number of DNS queries via UDP.

        @type queries: A C{list} of C{dns.Query} instances
        @param queries: The queries to make.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
        When the last timeout expires, the query is considered failed.

        @rtype: C{Deferred}
        @raise C{twisted.internet.defer.TimeoutError}: When the query times
        out.
        """
        if timeout is None:
            timeout = self.timeout

        addresses = self.servers + list(self.dynServers)
        if not addresses:
            return defer.fail(IOError("No domain name servers available"))

        # Make sure we go through servers in the list in the order they were
        # specified.
        addresses.reverse()

        used = addresses.pop()
        d = self._query(used, queries, timeout[0])
        d.addErrback(self._reissue, addresses, [used], queries, timeout)
        return d

    def _reissue(self, reason, addressesLeft, addressesUsed, query, timeout):
        reason.trap(dns.DNSQueryTimeoutError)

        # If there are no servers left to be tried, adjust the timeout
        # to the next longest timeout period and move all the
        # "used" addresses back to the list of addresses to try.
        if not addressesLeft:
            addressesLeft = addressesUsed
            addressesLeft.reverse()
            addressesUsed = []
            timeout = timeout[1:]

        # If all timeout values have been used this query has failed.  Tell the
        # protocol we're giving up on it and return a terminal timeout failure
        # to our caller.
        if not timeout:
            return failure.Failure(defer.TimeoutError(query))

        # Get an address to try.  Take it out of the list of addresses
        # to try and put it ino the list of already tried addresses.
        address = addressesLeft.pop()
        addressesUsed.append(address)

        # Issue a query to a server.  Use the current timeout.  Add this
        # function as a timeout errback in case another retry is required.
        d = self._query(address, query, timeout[0], reason.value.id)
        d.addErrback(self._reissue, addressesLeft, addressesUsed, query, timeout)
        return d

    def queryTCP(self, queries, timeout=10):
        """
        Make a number of DNS queries via TCP.

        @type queries: Any non-zero number of C{dns.Query} instances
        @param queries: The queries to make.

        @type timeout: C{int}
        @param timeout: The number of seconds after which to fail.

        @rtype: C{Deferred}
        """
        if not len(self.connections):
            address = self.pickServer()
            if address is None:
                return defer.fail(IOError("No domain name servers available"))
            host, port = address
            self._reactor.connectTCP(host, port, self.factory)
            self.pending.append((defer.Deferred(), queries, timeout))
            return self.pending[-1][0]
        else:
            return self.connections[0].query(queries, timeout)

    def filterAnswers(self, message):
        """
        Extract results from the given message.

        If the message was truncated, re-attempt the query over TCP and return
        a Deferred which will fire with the results of that query.

        If the message's result code is not C{twisted.names.dns.OK}, return a
        Failure indicating the type of error which occurred.

        Otherwise, return a three-tuple of lists containing the results from
        the answers section, the authority section, and the additional section.
        """
        if message.trunc:
            return self.queryTCP(message.queries).addCallback(self.filterAnswers)
        if message.rCode != dns.OK:
            return failure.Failure(self.exceptionForCode(message.rCode)(message))
        return (message.answers, message.authority, message.additional)

    def _lookup(self, name, cls, type, timeout):
        """
        Build a L{dns.Query} for the given parameters and dispatch it via UDP.

        If this query is already outstanding, it will not be re-issued.
        Instead, when the outstanding query receives a response, that response
        will be re-used for this query as well.

        @type name: C{str}
        @type type: C{int}
        @type cls: C{int}

        @return: A L{Deferred} which fires with a three-tuple giving the
            answer, authority, and additional sections of the response or with
            a L{Failure} if the response code is anything other than C{dns.OK}.
        """
        key = (name, type, cls)
        waiting = self._waiting.get(key)
        if waiting is None:
            self._waiting[key] = []
            d = self.queryUDP([dns.Query(name, type, cls)], timeout)

            def cbResult(result):
                for d in self._waiting.pop(key):
                    d.callback(result)
                return result

            d.addCallback(self.filterAnswers)
            d.addBoth(cbResult)
        else:
            d = defer.Deferred()
            waiting.append(d)
        return d

    # This one doesn't ever belong on UDP
    def lookupZone(self, name, timeout=10):
        address = self.pickServer()
        if address is None:
            return defer.fail(IOError("No domain name servers available"))
        host, port = address
        d = defer.Deferred()
        controller = AXFRController(name, d)
        factory = DNSClientFactory(controller, timeout)
        factory.noisy = False  # stfu

        connector = self._reactor.connectTCP(host, port, factory)
        controller.timeoutCall = self._reactor.callLater(
            timeout or 10, self._timeoutZone, d, controller, connector, timeout or 10
        )

        def eliminateTimeout(failure):
            controller.timeoutCall.cancel()
            controller.timeoutCall = None
            return failure

        return d.addCallbacks(
            self._cbLookupZone, eliminateTimeout, callbackArgs=(connector,)
        )

    def _timeoutZone(self, d, controller, connector, seconds):
        connector.disconnect()
        controller.timeoutCall = None
        controller.deferred = None
        d.errback(
            error.TimeoutError("Zone lookup timed out after %d seconds" % (seconds,))
        )

    def _cbLookupZone(self, result, connector):
        connector.disconnect()
        return (result, [], [])


class AXFRController:
    timeoutCall = None

    def __init__(self, name, deferred):
        self.name = name
        self.deferred = deferred
        self.soa = None
        self.records = []
        self.pending = [(deferred,)]

    def connectionMade(self, protocol):
        # dig saids recursion-desired to 0, so I will too
        message = dns.Message(protocol.pickID(), recDes=0)
        message.queries = [dns.Query(self.name, dns.AXFR, dns.IN)]
        protocol.writeMessage(message)

    def connectionLost(self, protocol):
        # XXX Do something here - see #3428
        pass

    def messageReceived(self, message, protocol):
        # Caveat: We have to handle two cases: All records are in 1
        # message, or all records are in N messages.

        # According to http://cr.yp.to/djbdns/axfr-notes.html,
        # 'authority' and 'additional' are always empty, and only
        # 'answers' is present.
        self.records.extend(message.answers)
        if not self.records:
            return
        if not self.soa:
            if self.records[0].type == dns.SOA:
                # print "first SOA!"
                self.soa = self.records[0]
        if len(self.records) > 1 and self.records[-1].type == dns.SOA:
            # print "It's the second SOA! We're done."
            if self.timeoutCall is not None:
                self.timeoutCall.cancel()
                self.timeoutCall = None
            if self.deferred is not None:
                self.deferred.callback(self.records)
                self.deferred = None


from twisted.internet.base import ThreadedResolver as _ThreadedResolverImpl


class ThreadedResolver(_ThreadedResolverImpl):
    def __init__(self, reactor=None):
        if reactor is None:
            from twisted.internet import reactor
        _ThreadedResolverImpl.__init__(self, reactor)
        warnings.warn(
            "twisted.names.client.ThreadedResolver is deprecated since "
            "Twisted 9.0, use twisted.internet.base.ThreadedResolver "
            "instead.",
            category=DeprecationWarning,
            stacklevel=2,
        )


class DNSClientFactory(protocol.ClientFactory):
    def __init__(self, controller, timeout=10):
        self.controller = controller
        self.timeout = timeout

    def clientConnectionLost(self, connector, reason):
        pass

    def clientConnectionFailed(self, connector, reason):
        """
        Fail all pending TCP DNS queries if the TCP connection attempt
        fails.

        @see: L{twisted.internet.protocol.ClientFactory}

        @param connector: Not used.
        @type connector: L{twisted.internet.interfaces.IConnector}

        @param reason: A C{Failure} containing information about the
            cause of the connection failure. This will be passed as the
            argument to C{errback} on every pending TCP query
            C{deferred}.
        @type reason: L{twisted.python.failure.Failure}
        """
        # Copy the current pending deferreds then reset the master
        # pending list. This prevents triggering new deferreds which
        # may be added by callback or errback functions on the current
        # deferreds.
        pending = self.controller.pending[:]
        del self.controller.pending[:]
        for pendingState in pending:
            d = pendingState[0]
            d.errback(reason)

    def buildProtocol(self, addr):
        p = dns.DNSProtocol(self.controller)
        p.factory = self
        return p


def createResolver(servers=None, resolvconf=None, hosts=None):
    r"""
    Create and return a Resolver.

    @type servers: C{list} of C{(str, int)} or L{None}

    @param servers: If not L{None}, interpreted as a list of domain name servers
    to attempt to use. Each server is a tuple of address in C{str} dotted-quad
    form and C{int} port number.

    @type resolvconf: C{str} or L{None}
    @param resolvconf: If not L{None}, on posix systems will be interpreted as
    an alternate resolv.conf to use. Will do nothing on windows systems. If
    L{None}, /etc/resolv.conf will be used.

    @type hosts: C{str} or L{None}
    @param hosts: If not L{None}, an alternate hosts file to use. If L{None}
    on posix systems, /etc/hosts will be used. On windows, C:\windows\hosts
    will be used.

    @rtype: C{IResolver}
    """
    if platform.getType() == "posix":
        if resolvconf is None:
            resolvconf = b"/etc/resolv.conf"
        if hosts is None:
            hosts = b"/etc/hosts"
        theResolver = Resolver(resolvconf, servers)
        hostResolver = hostsModule.Resolver(hosts)
    else:
        if hosts is None:
            hosts = r"c:\windows\hosts"
        from twisted.internet import reactor

        bootstrap = _ThreadedResolverImpl(reactor)
        hostResolver = hostsModule.Resolver(hosts)
        theResolver = root.bootstrap(bootstrap, resolverFactory=Resolver)

    L = [hostResolver, cache.CacheResolver(), theResolver]
    return resolve.ResolverChain(L)


theResolver = None


def getResolver():
    """
    Get a Resolver instance.

    Create twisted.names.client.theResolver if it is L{None}, and then return
    that value.

    @rtype: C{IResolver}
    """
    global theResolver
    if theResolver is None:
        try:
            theResolver = createResolver()
        except ValueError:
            theResolver = createResolver(servers=[("127.0.0.1", 53)])
    return theResolver


def getHostByName(name, timeout=None, effort=10):
    """
    Resolve a name to a valid ipv4 or ipv6 address.

    Will errback with C{DNSQueryTimeoutError} on a timeout, C{DomainError} or
    C{AuthoritativeDomainError} (or subclasses) on other errors.

    @type name: C{str}
    @param name: DNS name to resolve.

    @type timeout: Sequence of C{int}
    @param timeout: Number of seconds after which to reissue the query.
    When the last timeout expires, the query is considered failed.

    @type effort: C{int}
    @param effort: How many times CNAME and NS records to follow while
    resolving this name.

    @rtype: C{Deferred}
    """
    return getResolver().getHostByName(name, timeout, effort)


def query(query, timeout=None):
    return getResolver().query(query, timeout)


def lookupAddress(name, timeout=None):
    return getResolver().lookupAddress(name, timeout)


def lookupIPV6Address(name, timeout=None):
    return getResolver().lookupIPV6Address(name, timeout)


def lookupAddress6(name, timeout=None):
    return getResolver().lookupAddress6(name, timeout)


def lookupMailExchange(name, timeout=None):
    return getResolver().lookupMailExchange(name, timeout)


def lookupNameservers(name, timeout=None):
    return getResolver().lookupNameservers(name, timeout)


def lookupCanonicalName(name, timeout=None):
    return getResolver().lookupCanonicalName(name, timeout)


def lookupMailBox(name, timeout=None):
    return getResolver().lookupMailBox(name, timeout)


def lookupMailGroup(name, timeout=None):
    return getResolver().lookupMailGroup(name, timeout)


def lookupMailRename(name, timeout=None):
    return getResolver().lookupMailRename(name, timeout)


def lookupPointer(name, timeout=None):
    return getResolver().lookupPointer(name, timeout)


def lookupAuthority(name, timeout=None):
    return getResolver().lookupAuthority(name, timeout)


def lookupNull(name, timeout=None):
    return getResolver().lookupNull(name, timeout)


def lookupWellKnownServices(name, timeout=None):
    return getResolver().lookupWellKnownServices(name, timeout)


def lookupService(name, timeout=None):
    return getResolver().lookupService(name, timeout)


def lookupHostInfo(name, timeout=None):
    return getResolver().lookupHostInfo(name, timeout)


def lookupMailboxInfo(name, timeout=None):
    return getResolver().lookupMailboxInfo(name, timeout)


def lookupText(name, timeout=None):
    return getResolver().lookupText(name, timeout)


def lookupSenderPolicy(name, timeout=None):
    return getResolver().lookupSenderPolicy(name, timeout)


def lookupResponsibility(name, timeout=None):
    return getResolver().lookupResponsibility(name, timeout)


def lookupAFSDatabase(name, timeout=None):
    return getResolver().lookupAFSDatabase(name, timeout)


def lookupZone(name, timeout=None):
    return getResolver().lookupZone(name, timeout)


def lookupAllRecords(name, timeout=None):
    return getResolver().lookupAllRecords(name, timeout)


def lookupNamingAuthorityPointer(name, timeout=None):
    return getResolver().lookupNamingAuthorityPointer(name, timeout)
