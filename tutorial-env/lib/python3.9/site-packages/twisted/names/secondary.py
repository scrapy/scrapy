# -*- test-case-name: twisted.names.test.test_names -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


__all__ = ["SecondaryAuthority", "SecondaryAuthorityService"]

from twisted.application import service
from twisted.internet import defer, task
from twisted.names import client, common, dns, resolve
from twisted.names.authority import FileAuthority
from twisted.python import failure, log
from twisted.python.compat import nativeString


class SecondaryAuthorityService(service.Service):
    """
    A service that keeps one or more authorities up to date by doing hourly
    zone transfers from a master.

    @ivar primary: IP address of the master.
    @type primary: L{str}

    @ivar domains: An authority for each domain mirrored from the master.
    @type domains: L{list} of L{SecondaryAuthority}
    """

    calls = None

    _port = 53

    def __init__(self, primary, domains):
        """
        @param primary: The IP address of the server from which to perform
        zone transfers.
        @type primary: L{str}

        @param domains: A sequence of domain names for which to perform
        zone transfers.
        @type domains: L{list} of L{bytes}
        """
        self.primary = nativeString(primary)
        self.domains = [SecondaryAuthority(primary, d) for d in domains]

    @classmethod
    def fromServerAddressAndDomains(cls, serverAddress, domains):
        """
        Construct a new L{SecondaryAuthorityService} from a tuple giving a
        server address and a C{str} giving the name of a domain for which this
        is an authority.

        @param serverAddress: A two-tuple, the first element of which is a
            C{str} giving an IP address and the second element of which is a
            C{int} giving a port number.  Together, these define where zone
            transfers will be attempted from.

        @param domains: Domain names for which to perform zone transfers.
        @type domains: sequence of L{bytes}

        @return: A new instance of L{SecondaryAuthorityService}.
        """
        primary, port = serverAddress
        service = cls(primary, [])
        service._port = port
        service.domains = [
            SecondaryAuthority.fromServerAddressAndDomain(serverAddress, d)
            for d in domains
        ]
        return service

    def getAuthority(self):
        """
        Get a resolver for the transferred domains.

        @rtype: L{ResolverChain}
        """
        return resolve.ResolverChain(self.domains)

    def startService(self):
        service.Service.startService(self)
        self.calls = [task.LoopingCall(d.transfer) for d in self.domains]
        i = 0
        from twisted.internet import reactor

        for c in self.calls:
            # XXX Add errbacks, respect proper timeouts
            reactor.callLater(i, c.start, 60 * 60)
            i += 1

    def stopService(self):
        service.Service.stopService(self)
        for c in self.calls:
            c.stop()


class SecondaryAuthority(FileAuthority):
    """
    An Authority that keeps itself updated by performing zone transfers.

    @ivar primary: The IP address of the server from which zone transfers will
    be attempted.
    @type primary: L{str}

    @ivar _port: The port number of the server from which zone transfers will
    be attempted.
    @type _port: L{int}

    @ivar domain: The domain for which this is the secondary authority.
    @type domain: L{bytes}

    @ivar _reactor: The reactor to use to perform the zone transfers, or
    L{None} to use the global reactor.
    """

    transferring = False
    soa = records = None
    _port = 53
    _reactor = None

    def __init__(self, primaryIP, domain):
        """
        @param domain: The domain for which this will be the secondary
            authority.
        @type domain: L{bytes} or L{str}
        """
        # Yep.  Skip over FileAuthority.__init__.  This is a hack until we have
        # a good composition-based API for the complicated DNS record lookup
        # logic we want to share.
        common.ResolverBase.__init__(self)
        self.primary = nativeString(primaryIP)
        self.domain = dns.domainString(domain)

    @classmethod
    def fromServerAddressAndDomain(cls, serverAddress, domain):
        """
        Construct a new L{SecondaryAuthority} from a tuple giving a server
        address and a C{bytes} giving the name of a domain for which this is an
        authority.

        @param serverAddress: A two-tuple, the first element of which is a
            C{str} giving an IP address and the second element of which is a
            C{int} giving a port number.  Together, these define where zone
            transfers will be attempted from.

        @param domain: A C{bytes} giving the domain to transfer.
        @type domain: L{bytes}

        @return: A new instance of L{SecondaryAuthority}.
        """
        primary, port = serverAddress
        secondary = cls(primary, domain)
        secondary._port = port
        return secondary

    def transfer(self):
        """
        Attempt a zone transfer.

        @returns: A L{Deferred} that fires with L{None} when attempted zone
            transfer has completed.
        """
        # FIXME: This logic doesn't avoid duplicate transfers
        # https://twistedmatrix.com/trac/ticket/9754
        if self.transferring:  # <-- never true
            return
        self.transfering = True  # <-- speling

        reactor = self._reactor
        if reactor is None:
            from twisted.internet import reactor

        resolver = client.Resolver(
            servers=[(self.primary, self._port)], reactor=reactor
        )
        return (
            resolver.lookupZone(self.domain)
            .addCallback(self._cbZone)
            .addErrback(self._ebZone)
        )

    def _lookup(self, name, cls, type, timeout=None):
        if not self.soa or not self.records:
            # No transfer has occurred yet. Fail non-authoritatively so that
            # the caller can try elsewhere.
            return defer.fail(failure.Failure(dns.DomainError(name)))
        return FileAuthority._lookup(self, name, cls, type, timeout)

    def _cbZone(self, zone):
        ans, _, _ = zone
        self.records = r = {}
        for rec in ans:
            if not self.soa and rec.type == dns.SOA:
                self.soa = (rec.name.name.lower(), rec.payload)
            else:
                r.setdefault(rec.name.name.lower(), []).append(rec.payload)

    def _ebZone(self, failure):
        log.msg(
            "Updating %s from %s failed during zone transfer"
            % (self.domain, self.primary)
        )
        log.err(failure)

    def update(self):
        self.transfer().addCallbacks(self._cbTransferred, self._ebTransferred)

    def _cbTransferred(self, result):
        self.transferring = False

    def _ebTransferred(self, failure):
        self.transferred = False
        log.msg(
            "Transferring %s from %s failed after zone transfer"
            % (self.domain, self.primary)
        )
        log.err(failure)
