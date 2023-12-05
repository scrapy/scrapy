# -*- test-case-name: twisted.names.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Base functionality useful to various parts of Twisted Names.
"""


import socket

from zope.interface import implementer

from twisted.internet import defer, error, interfaces
from twisted.logger import Logger
from twisted.names import dns
from twisted.names.error import (
    DNSFormatError,
    DNSNameError,
    DNSNotImplementedError,
    DNSQueryRefusedError,
    DNSServerError,
    DNSUnknownError,
)

# Helpers for indexing the three-tuples that get thrown around by this code a
# lot.
_ANS, _AUTH, _ADD = range(3)

EMPTY_RESULT = (), (), ()


@implementer(interfaces.IResolver)
class ResolverBase:
    """
    L{ResolverBase} is a base class for implementations of
    L{interfaces.IResolver} which deals with a lot
    of the boilerplate of implementing all of the lookup methods.

    @cvar _errormap: A C{dict} mapping DNS protocol failure response codes
        to exception classes which will be used to represent those failures.
    """

    _log = Logger()
    _errormap = {
        dns.EFORMAT: DNSFormatError,
        dns.ESERVER: DNSServerError,
        dns.ENAME: DNSNameError,
        dns.ENOTIMP: DNSNotImplementedError,
        dns.EREFUSED: DNSQueryRefusedError,
    }

    typeToMethod = None

    def __init__(self):
        self.typeToMethod = {}
        for (k, v) in typeToMethod.items():
            self.typeToMethod[k] = getattr(self, v)

    def exceptionForCode(self, responseCode):
        """
        Convert a response code (one of the possible values of
        L{dns.Message.rCode} to an exception instance representing it.

        @since: 10.0
        """
        return self._errormap.get(responseCode, DNSUnknownError)

    def query(self, query, timeout=None):
        try:
            method = self.typeToMethod[query.type]
        except KeyError:
            self._log.debug(
                "Query of unknown type {query.type} for {query.name.name!r}",
                query=query,
            )
            return defer.maybeDeferred(
                self._lookup, query.name.name, dns.IN, query.type, timeout
            )
        else:
            return defer.maybeDeferred(method, query.name.name, timeout)

    def _lookup(self, name, cls, type, timeout):
        return defer.fail(NotImplementedError("ResolverBase._lookup"))

    def lookupAddress(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.A, timeout)

    def lookupIPV6Address(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.AAAA, timeout)

    def lookupAddress6(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.A6, timeout)

    def lookupMailExchange(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.MX, timeout)

    def lookupNameservers(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.NS, timeout)

    def lookupCanonicalName(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.CNAME, timeout)

    def lookupMailBox(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.MB, timeout)

    def lookupMailGroup(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.MG, timeout)

    def lookupMailRename(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.MR, timeout)

    def lookupPointer(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.PTR, timeout)

    def lookupAuthority(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.SOA, timeout)

    def lookupNull(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.NULL, timeout)

    def lookupWellKnownServices(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.WKS, timeout)

    def lookupService(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.SRV, timeout)

    def lookupHostInfo(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.HINFO, timeout)

    def lookupMailboxInfo(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.MINFO, timeout)

    def lookupText(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.TXT, timeout)

    def lookupSenderPolicy(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.SPF, timeout)

    def lookupResponsibility(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.RP, timeout)

    def lookupAFSDatabase(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.AFSDB, timeout)

    def lookupZone(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.AXFR, timeout)

    def lookupNamingAuthorityPointer(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.NAPTR, timeout)

    def lookupAllRecords(self, name, timeout=None):
        return self._lookup(dns.domainString(name), dns.IN, dns.ALL_RECORDS, timeout)

    # IResolverSimple
    def getHostByName(self, name, timeout=None, effort=10):
        name = dns.domainString(name)
        # XXX - respect timeout
        # XXX - this should do A and AAAA lookups, not ANY (see RFC 8482).
        # https://twistedmatrix.com/trac/ticket/9691
        d = self.lookupAllRecords(name, timeout)
        d.addCallback(self._cbRecords, name, effort)
        return d

    def _cbRecords(self, records, name, effort):
        (ans, auth, add) = records
        result = extractRecord(self, dns.Name(name), ans + auth + add, effort)
        if not result:
            raise error.DNSLookupError(name)
        return result


def extractRecord(resolver, name, answers, level=10):
    """
    Resolve a name to an IP address, following I{CNAME} records and I{NS}
    referrals recursively.

    This is an implementation detail of L{ResolverBase.getHostByName}.

    @param resolver: The resolver to use for the next query (unless handling
    an I{NS} referral).
    @type resolver: L{IResolver}

    @param name: The name being looked up.
    @type name: L{dns.Name}

    @param answers: All of the records returned by the previous query (answers,
    authority, and additional concatenated).
    @type answers: L{list} of L{dns.RRHeader}

    @param level: Remaining recursion budget. This is decremented at each
    recursion. The query returns L{None} when it reaches 0.
    @type level: L{int}

    @returns: The first IPv4 or IPv6 address (as a dotted quad or colon
    quibbles), or L{None} when no result is found.
    @rtype: native L{str} or L{None}
    """
    if not level:
        return None
    # FIXME: twisted.python.compat monkeypatches this if missing, so this
    # condition is always true. https://twistedmatrix.com/trac/ticket/9753
    if hasattr(socket, "inet_ntop"):
        for r in answers:
            if r.name == name and r.type == dns.A6:
                return socket.inet_ntop(socket.AF_INET6, r.payload.address)
        for r in answers:
            if r.name == name and r.type == dns.AAAA:
                return socket.inet_ntop(socket.AF_INET6, r.payload.address)
    for r in answers:
        if r.name == name and r.type == dns.A:
            return socket.inet_ntop(socket.AF_INET, r.payload.address)
    for r in answers:
        if r.name == name and r.type == dns.CNAME:
            result = extractRecord(resolver, r.payload.name, answers, level - 1)
            if not result:
                return resolver.getHostByName(r.payload.name.name, effort=level - 1)
            return result
    # No answers, but maybe there's a hint at who we should be asking about
    # this
    for r in answers:
        if r.type != dns.NS:
            continue
        from twisted.names import client

        nsResolver = client.Resolver(
            servers=[
                (r.payload.name.name.decode("ascii"), dns.PORT),
            ]
        )

        def queryAgain(records):
            (ans, auth, add) = records
            return extractRecord(nsResolver, name, ans + auth + add, level - 1)

        return nsResolver.lookupAddress(name.name).addCallback(queryAgain)


typeToMethod = {
    dns.A: "lookupAddress",
    dns.AAAA: "lookupIPV6Address",
    dns.A6: "lookupAddress6",
    dns.NS: "lookupNameservers",
    dns.CNAME: "lookupCanonicalName",
    dns.SOA: "lookupAuthority",
    dns.MB: "lookupMailBox",
    dns.MG: "lookupMailGroup",
    dns.MR: "lookupMailRename",
    dns.NULL: "lookupNull",
    dns.WKS: "lookupWellKnownServices",
    dns.PTR: "lookupPointer",
    dns.HINFO: "lookupHostInfo",
    dns.MINFO: "lookupMailboxInfo",
    dns.MX: "lookupMailExchange",
    dns.TXT: "lookupText",
    dns.SPF: "lookupSenderPolicy",
    dns.RP: "lookupResponsibility",
    dns.AFSDB: "lookupAFSDatabase",
    dns.SRV: "lookupService",
    dns.NAPTR: "lookupNamingAuthorityPointer",
    dns.AXFR: "lookupZone",
    dns.ALL_RECORDS: "lookupAllRecords",
}
