# -*- test-case-name: twisted.names.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Base functionality useful to various parts of Twisted Names.
"""

from __future__ import division, absolute_import

import socket

from zope.interface import implementer

from twisted.names import dns
from twisted.names.error import DNSFormatError, DNSServerError, DNSNameError
from twisted.names.error import DNSNotImplementedError, DNSQueryRefusedError
from twisted.names.error import DNSUnknownError

from twisted.internet import defer, error, interfaces
from twisted.python import failure

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
    _errormap = {
        dns.EFORMAT: DNSFormatError,
        dns.ESERVER: DNSServerError,
        dns.ENAME: DNSNameError,
        dns.ENOTIMP: DNSNotImplementedError,
        dns.EREFUSED: DNSQueryRefusedError}

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
            return defer.fail(failure.Failure(NotImplementedError(
                        str(self.__class__) + " " + str(query.type))))
        else:
            return defer.maybeDeferred(method, query.name.name, timeout)


    def _lookup(self, name, cls, type, timeout):
        return defer.fail(NotImplementedError("ResolverBase._lookup"))


    def lookupAddress(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.A, timeout)


    def lookupIPV6Address(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.AAAA, timeout)


    def lookupAddress6(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.A6, timeout)


    def lookupMailExchange(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.MX, timeout)


    def lookupNameservers(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.NS, timeout)


    def lookupCanonicalName(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.CNAME, timeout)


    def lookupMailBox(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.MB, timeout)


    def lookupMailGroup(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.MG, timeout)


    def lookupMailRename(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.MR, timeout)


    def lookupPointer(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.PTR, timeout)


    def lookupAuthority(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.SOA, timeout)


    def lookupNull(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.NULL, timeout)


    def lookupWellKnownServices(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.WKS, timeout)


    def lookupService(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.SRV, timeout)


    def lookupHostInfo(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.HINFO, timeout)


    def lookupMailboxInfo(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.MINFO, timeout)


    def lookupText(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.TXT, timeout)


    def lookupSenderPolicy(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.SPF, timeout)


    def lookupResponsibility(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.RP, timeout)


    def lookupAFSDatabase(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.AFSDB, timeout)


    def lookupZone(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.AXFR, timeout)


    def lookupNamingAuthorityPointer(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.NAPTR, timeout)


    def lookupAllRecords(self, name, timeout=None):
        return self._lookup(name, dns.IN, dns.ALL_RECORDS, timeout)


    # IResolverSimple
    def getHostByName(self, name, timeout=None, effort=10):
        # XXX - respect timeout
        return self.lookupAllRecords(name, timeout
            ).addCallback(self._cbRecords, name, effort
            )


    def _cbRecords(self, records, name, effort):
        (ans, auth, add) = records
        result = extractRecord(self, dns.Name(name), ans + auth + add, effort)
        if not result:
            raise error.DNSLookupError(name)
        return result



def extractRecord(resolver, name, answers, level=10):
    if not level:
        return None
    if hasattr(socket, 'inet_ntop'):
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
            result = extractRecord(
                resolver, r.payload.name, answers, level - 1)
            if not result:
                return resolver.getHostByName(
                    str(r.payload.name), effort=level - 1)
            return result
    # No answers, but maybe there's a hint at who we should be asking about
    # this
    for r in answers:
        if r.type == dns.NS:
            from twisted.names import client
            r = client.Resolver(servers=[(str(r.payload.name), dns.PORT)])
            return r.lookupAddress(str(name)
                ).addCallback(
                    lambda records: extractRecord(
                        r, name,
                        records[_ANS] + records[_AUTH] + records[_ADD],
                        level - 1))



typeToMethod = {
    dns.A:     'lookupAddress',
    dns.AAAA:  'lookupIPV6Address',
    dns.A6:    'lookupAddress6',
    dns.NS:    'lookupNameservers',
    dns.CNAME: 'lookupCanonicalName',
    dns.SOA:   'lookupAuthority',
    dns.MB:    'lookupMailBox',
    dns.MG:    'lookupMailGroup',
    dns.MR:    'lookupMailRename',
    dns.NULL:  'lookupNull',
    dns.WKS:   'lookupWellKnownServices',
    dns.PTR:   'lookupPointer',
    dns.HINFO: 'lookupHostInfo',
    dns.MINFO: 'lookupMailboxInfo',
    dns.MX:    'lookupMailExchange',
    dns.TXT:   'lookupText',
    dns.SPF:   'lookupSenderPolicy',

    dns.RP:    'lookupResponsibility',
    dns.AFSDB: 'lookupAFSDatabase',
    dns.SRV:   'lookupService',
    dns.NAPTR: 'lookupNamingAuthorityPointer',
    dns.AXFR:         'lookupZone',
    dns.ALL_RECORDS:  'lookupAllRecords',
}
