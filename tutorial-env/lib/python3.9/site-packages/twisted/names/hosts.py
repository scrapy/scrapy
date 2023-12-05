# -*- test-case-name: twisted.names.test.test_hosts -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
hosts(5) support.
"""


from twisted.internet import defer
from twisted.internet.abstract import isIPAddress, isIPv6Address
from twisted.names import common, dns
from twisted.python import failure
from twisted.python.compat import nativeString
from twisted.python.filepath import FilePath


def searchFileForAll(hostsFile, name):
    """
    Search the given file, which is in hosts(5) standard format, for addresses
    associated with a given name.

    @param hostsFile: The name of the hosts(5)-format file to search.
    @type hostsFile: L{FilePath}

    @param name: The name to search for.
    @type name: C{bytes}

    @return: L{None} if the name is not found in the file, otherwise a
        C{str} giving the address in the file associated with the name.
    """
    results = []
    try:
        lines = hostsFile.getContent().splitlines()
    except BaseException:
        return results

    name = name.lower()
    for line in lines:
        idx = line.find(b"#")
        if idx != -1:
            line = line[:idx]
        if not line:
            continue
        parts = line.split()

        if name.lower() in [s.lower() for s in parts[1:]]:
            try:
                maybeIP = nativeString(parts[0])
            except ValueError:  # Not ASCII.
                continue
            if isIPAddress(maybeIP) or isIPv6Address(maybeIP):
                results.append(maybeIP)
    return results


def searchFileFor(file, name):
    """
    Grep given file, which is in hosts(5) standard format, for an address
    entry with a given name.

    @param file: The name of the hosts(5)-format file to search.
    @type file: C{str} or C{bytes}

    @param name: The name to search for.
    @type name: C{bytes}

    @return: L{None} if the name is not found in the file, otherwise a
        C{str} giving the first address in the file associated with
        the name.
    """
    addresses = searchFileForAll(FilePath(file), name)
    if addresses:
        return addresses[0]
    return None


class Resolver(common.ResolverBase):
    """
    A resolver that services hosts(5) format files.
    """

    def __init__(self, file=b"/etc/hosts", ttl=60 * 60):
        common.ResolverBase.__init__(self)
        self.file = file
        self.ttl = ttl

    def _aRecords(self, name):
        """
        Return a tuple of L{dns.RRHeader} instances for all of the IPv4
        addresses in the hosts file.
        """
        return tuple(
            dns.RRHeader(name, dns.A, dns.IN, self.ttl, dns.Record_A(addr, self.ttl))
            for addr in searchFileForAll(FilePath(self.file), name)
            if isIPAddress(addr)
        )

    def _aaaaRecords(self, name):
        """
        Return a tuple of L{dns.RRHeader} instances for all of the IPv6
        addresses in the hosts file.
        """
        return tuple(
            dns.RRHeader(
                name, dns.AAAA, dns.IN, self.ttl, dns.Record_AAAA(addr, self.ttl)
            )
            for addr in searchFileForAll(FilePath(self.file), name)
            if isIPv6Address(addr)
        )

    def _respond(self, name, records):
        """
        Generate a response for the given name containing the given result
        records, or a failure if there are no result records.

        @param name: The DNS name the response is for.
        @type name: C{str}

        @param records: A tuple of L{dns.RRHeader} instances giving the results
            that will go into the response.

        @return: A L{Deferred} which will fire with a three-tuple of result
            records, authority records, and additional records, or which will
            fail with L{dns.DomainError} if there are no result records.
        """
        if records:
            return defer.succeed((records, (), ()))
        return defer.fail(failure.Failure(dns.DomainError(name)))

    def lookupAddress(self, name, timeout=None):
        """
        Read any IPv4 addresses from C{self.file} and return them as
        L{Record_A} instances.
        """
        name = dns.domainString(name)
        return self._respond(name, self._aRecords(name))

    def lookupIPV6Address(self, name, timeout=None):
        """
        Read any IPv6 addresses from C{self.file} and return them as
        L{Record_AAAA} instances.
        """
        name = dns.domainString(name)
        return self._respond(name, self._aaaaRecords(name))

    # Someday this should include IPv6 addresses too, but that will cause
    # problems if users of the API (mainly via getHostByName) aren't updated to
    # know about IPv6 first.
    # FIXME - getHostByName knows about IPv6 now.
    lookupAllRecords = lookupAddress
