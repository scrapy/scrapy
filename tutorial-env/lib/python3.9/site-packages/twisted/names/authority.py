# -*- test-case-name: twisted.names.test.test_names -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Authoritative resolvers.
"""


import os
import time

from twisted.internet import defer
from twisted.names import common, dns, error
from twisted.python import failure
from twisted.python.compat import execfile, nativeString
from twisted.python.filepath import FilePath


def getSerial(filename="/tmp/twisted-names.serial"):
    """
    Return a monotonically increasing (across program runs) integer.

    State is stored in the given file.  If it does not exist, it is
    created with rw-/---/--- permissions.

    This manipulates process-global state by calling C{os.umask()}, so it isn't
    thread-safe.

    @param filename: Path to a file that is used to store the state across
        program runs.
    @type filename: L{str}

    @return: a monotonically increasing number
    @rtype: L{str}
    """
    serial = time.strftime("%Y%m%d")

    o = os.umask(0o177)
    try:
        if not os.path.exists(filename):
            with open(filename, "w") as f:
                f.write(serial + " 0")
    finally:
        os.umask(o)

    with open(filename) as serialFile:
        lastSerial, zoneID = serialFile.readline().split()

    zoneID = (lastSerial == serial) and (int(zoneID) + 1) or 0

    with open(filename, "w") as serialFile:
        serialFile.write("%s %d" % (serial, zoneID))

    serial = serial + ("%02d" % (zoneID,))
    return serial


class FileAuthority(common.ResolverBase):
    """
    An Authority that is loaded from a file.

    This is an abstract class that implements record search logic. To create
    a functional resolver, subclass it and override the L{loadFile} method.

    @ivar _ADDITIONAL_PROCESSING_TYPES: Record types for which additional
        processing will be done.

    @ivar _ADDRESS_TYPES: Record types which are useful for inclusion in the
        additional section generated during additional processing.

    @ivar soa: A 2-tuple containing the SOA domain name as a L{bytes} and a
        L{dns.Record_SOA}.

    @ivar records: A mapping of domains (as lowercased L{bytes}) to records.
    @type records: L{dict} with L{bytes} keys
    """

    # See https://twistedmatrix.com/trac/ticket/6650
    _ADDITIONAL_PROCESSING_TYPES = (dns.CNAME, dns.MX, dns.NS)
    _ADDRESS_TYPES = (dns.A, dns.AAAA)

    soa = None
    records = None

    def __init__(self, filename):
        common.ResolverBase.__init__(self)
        self.loadFile(filename)
        self._cache = {}

    def __setstate__(self, state):
        self.__dict__ = state

    def loadFile(self, filename):
        """
        Load DNS records from a file.

        This method populates the I{soa} and I{records} attributes. It must be
        overridden in a subclass. It is called once from the initializer.

        @param filename: The I{filename} parameter that was passed to the
        initilizer.

        @returns: L{None} -- the return value is ignored
        """

    def _additionalRecords(self, answer, authority, ttl):
        """
        Find locally known information that could be useful to the consumer of
        the response and construct appropriate records to include in the
        I{additional} section of that response.

        Essentially, implement RFC 1034 section 4.3.2 step 6.

        @param answer: A L{list} of the records which will be included in the
            I{answer} section of the response.

        @param authority: A L{list} of the records which will be included in
            the I{authority} section of the response.

        @param ttl: The default TTL for records for which this is not otherwise
            specified.

        @return: A generator of L{dns.RRHeader} instances for inclusion in the
            I{additional} section.  These instances represent extra information
            about the records in C{answer} and C{authority}.
        """
        for record in answer + authority:
            if record.type in self._ADDITIONAL_PROCESSING_TYPES:
                name = record.payload.name.name
                for rec in self.records.get(name.lower(), ()):
                    if rec.TYPE in self._ADDRESS_TYPES:
                        yield dns.RRHeader(
                            name, rec.TYPE, dns.IN, rec.ttl or ttl, rec, auth=True
                        )

    def _lookup(self, name, cls, type, timeout=None):
        """
        Determine a response to a particular DNS query.

        @param name: The name which is being queried and for which to lookup a
            response.
        @type name: L{bytes}

        @param cls: The class which is being queried.  Only I{IN} is
            implemented here and this value is presently disregarded.
        @type cls: L{int}

        @param type: The type of records being queried.  See the types defined
            in L{twisted.names.dns}.
        @type type: L{int}

        @param timeout: All processing is done locally and a result is
            available immediately, so the timeout value is ignored.

        @return: A L{Deferred} that fires with a L{tuple} of three sets of
            response records (to comprise the I{answer}, I{authority}, and
            I{additional} sections of a DNS response) or with a L{Failure} if
            there is a problem processing the query.
        """
        cnames = []
        results = []
        authority = []
        additional = []
        default_ttl = max(self.soa[1].minimum, self.soa[1].expire)

        domain_records = self.records.get(name.lower())

        if domain_records:
            for record in domain_records:
                if record.ttl is not None:
                    ttl = record.ttl
                else:
                    ttl = default_ttl

                if record.TYPE == dns.NS and name.lower() != self.soa[0].lower():
                    # NS record belong to a child zone: this is a referral.  As
                    # NS records are authoritative in the child zone, ours here
                    # are not.  RFC 2181, section 6.1.
                    authority.append(
                        dns.RRHeader(name, record.TYPE, dns.IN, ttl, record, auth=False)
                    )
                elif record.TYPE == type or type == dns.ALL_RECORDS:
                    results.append(
                        dns.RRHeader(name, record.TYPE, dns.IN, ttl, record, auth=True)
                    )
                if record.TYPE == dns.CNAME:
                    cnames.append(
                        dns.RRHeader(name, record.TYPE, dns.IN, ttl, record, auth=True)
                    )
            if not results:
                results = cnames

            # Sort of https://tools.ietf.org/html/rfc1034#section-4.3.2 .
            # See https://twistedmatrix.com/trac/ticket/6732
            additionalInformation = self._additionalRecords(
                results, authority, default_ttl
            )
            if cnames:
                results.extend(additionalInformation)
            else:
                additional.extend(additionalInformation)

            if not results and not authority:
                # Empty response. Include SOA record to allow clients to cache
                # this response. RFC 1034, sections 3.7 and 4.3.4, and RFC 2181
                # section 7.1.
                authority.append(
                    dns.RRHeader(
                        self.soa[0], dns.SOA, dns.IN, ttl, self.soa[1], auth=True
                    )
                )
            return defer.succeed((results, authority, additional))
        else:
            if dns._isSubdomainOf(name, self.soa[0]):
                # We may be the authority and we didn't find it.
                # XXX: The QNAME may also be in a delegated child zone. See
                # #6581 and #6580
                return defer.fail(failure.Failure(dns.AuthoritativeDomainError(name)))
            else:
                # The QNAME is not a descendant of this zone. Fail with
                # DomainError so that the next chained authority or
                # resolver will be queried.
                return defer.fail(failure.Failure(error.DomainError(name)))

    def lookupZone(self, name, timeout=10):
        name = dns.domainString(name)
        if self.soa[0].lower() == name.lower():
            # Wee hee hee hooo yea
            default_ttl = max(self.soa[1].minimum, self.soa[1].expire)
            if self.soa[1].ttl is not None:
                soa_ttl = self.soa[1].ttl
            else:
                soa_ttl = default_ttl
            results = [
                dns.RRHeader(
                    self.soa[0], dns.SOA, dns.IN, soa_ttl, self.soa[1], auth=True
                )
            ]
            for (k, r) in self.records.items():
                for rec in r:
                    if rec.ttl is not None:
                        ttl = rec.ttl
                    else:
                        ttl = default_ttl
                    if rec.TYPE != dns.SOA:
                        results.append(
                            dns.RRHeader(k, rec.TYPE, dns.IN, ttl, rec, auth=True)
                        )
            results.append(results[0])
            return defer.succeed((results, (), ()))
        return defer.fail(failure.Failure(dns.DomainError(name)))

    def _cbAllRecords(self, results):
        ans, auth, add = [], [], []
        for res in results:
            if res[0]:
                ans.extend(res[1][0])
                auth.extend(res[1][1])
                add.extend(res[1][2])
        return ans, auth, add


class PySourceAuthority(FileAuthority):
    """
    A FileAuthority that is built up from Python source code.
    """

    def loadFile(self, filename):
        g, l = self.setupConfigNamespace(), {}
        execfile(filename, g, l)
        if "zone" not in l:
            raise ValueError("No zone defined in " + filename)

        self.records = {}
        for rr in l["zone"]:
            if isinstance(rr[1], dns.Record_SOA):
                self.soa = rr
            self.records.setdefault(rr[0].lower(), []).append(rr[1])

    def wrapRecord(self, type):
        def wrapRecordFunc(name, *arg, **kw):
            return (dns.domainString(name), type(*arg, **kw))

        return wrapRecordFunc

    def setupConfigNamespace(self):
        r = {}
        items = dns.__dict__.keys()
        for record in [x for x in items if x.startswith("Record_")]:
            type = getattr(dns, record)
            f = self.wrapRecord(type)
            r[record[len("Record_") :]] = f
        return r


class BindAuthority(FileAuthority):
    """
    An Authority that loads U{BIND zone files
    <https://en.wikipedia.org/wiki/Zone_file>}.

    Supports only C{$ORIGIN} and C{$TTL} directives.
    """

    def loadFile(self, filename):
        """
        Load records from C{filename}.

        @param filename: file to read from
        @type filename: L{bytes}
        """
        fp = FilePath(filename)
        # Not the best way to set an origin. It can be set using $ORIGIN
        # though.
        self.origin = nativeString(fp.basename() + b".")

        lines = fp.getContent().splitlines(True)
        lines = self.stripComments(lines)
        lines = self.collapseContinuations(lines)
        self.parseLines(lines)

    def stripComments(self, lines):
        """
        Strip comments from C{lines}.

        @param lines: lines to work on
        @type lines: iterable of L{bytes}

        @return: C{lines} sans comments.
        """
        return (
            a.find(b";") == -1 and a or a[: a.find(b";")]
            for a in [b.strip() for b in lines]
        )

    def collapseContinuations(self, lines):
        """
        Transform multiline statements into single lines.

        @param lines: lines to work on
        @type lines: iterable of L{bytes}

        @return: iterable of continuous lines
        """
        l = []
        state = 0
        for line in lines:
            if state == 0:
                if line.find(b"(") == -1:
                    l.append(line)
                else:
                    l.append(line[: line.find(b"(")])
                    state = 1
            else:
                if line.find(b")") != -1:
                    l[-1] += b" " + line[: line.find(b")")]
                    state = 0
                else:
                    l[-1] += b" " + line
        return filter(None, (line.split() for line in l))

    def parseLines(self, lines):
        """
        Parse C{lines}.

        @param lines: lines to work on
        @type lines: iterable of L{bytes}
        """
        ttl = 60 * 60 * 3
        origin = self.origin

        self.records = {}

        for line in lines:
            if line[0] == b"$TTL":
                ttl = dns.str2time(line[1])
            elif line[0] == b"$ORIGIN":
                origin = line[1]
            elif line[0] == b"$INCLUDE":
                raise NotImplementedError("$INCLUDE directive not implemented")
            elif line[0] == b"$GENERATE":
                raise NotImplementedError("$GENERATE directive not implemented")
            else:
                self.parseRecordLine(origin, ttl, line)

        # If the origin changed, reflect that within the instance.
        self.origin = origin

    def addRecord(self, owner, ttl, type, domain, cls, rdata):
        """
        Add a record to our authority.  Expand domain with origin if necessary.

        @param owner: origin?
        @type owner: L{bytes}

        @param ttl: time to live for the record
        @type ttl: L{int}

        @param domain: the domain for which the record is to be added
        @type domain: L{bytes}

        @param type: record type
        @type type: L{str}

        @param cls: record class
        @type cls: L{str}

        @param rdata: record data
        @type rdata: L{list} of L{bytes}
        """
        if not domain.endswith(b"."):
            domain = domain + b"." + owner[:-1]
        else:
            domain = domain[:-1]
        f = getattr(self, f"class_{cls}", None)
        if f:
            f(ttl, type, domain, rdata)
        else:
            raise NotImplementedError(f"Record class {cls!r} not supported")

    def class_IN(self, ttl, type, domain, rdata):
        """
        Simulate a class IN and recurse into the actual class.

        @param ttl: time to live for the record
        @type ttl: L{int}

        @param type: record type
        @type type: str

        @param domain: the domain
        @type domain: bytes

        @param rdata:
        @type rdata: bytes
        """
        record = getattr(dns, f"Record_{nativeString(type)}", None)
        if record:
            r = record(*rdata)
            r.ttl = ttl
            self.records.setdefault(domain.lower(), []).append(r)

            if type == "SOA":
                self.soa = (domain, r)
        else:
            raise NotImplementedError(
                f"Record type {nativeString(type)!r} not supported"
            )

    def parseRecordLine(self, origin, ttl, line):
        """
        Parse a C{line} from a zone file respecting C{origin} and C{ttl}.

        Add resulting records to authority.

        @param origin: starting point for the zone
        @type origin: L{bytes}

        @param ttl: time to live for the record
        @type ttl: L{int}

        @param line: zone file line to parse; split by word
        @type line: L{list} of L{bytes}
        """
        queryClasses = {qc.encode("ascii") for qc in dns.QUERY_CLASSES.values()}
        queryTypes = {qt.encode("ascii") for qt in dns.QUERY_TYPES.values()}

        markers = queryClasses | queryTypes

        cls = b"IN"
        owner = origin

        if line[0] == b"@":
            line = line[1:]
            owner = origin
        elif not line[0].isdigit() and line[0] not in markers:
            owner = line[0]
            line = line[1:]

        if line[0].isdigit() or line[0] in markers:
            domain = owner
            owner = origin
        else:
            domain = line[0]
            line = line[1:]

        if line[0] in queryClasses:
            cls = line[0]
            line = line[1:]
            if line[0].isdigit():
                ttl = int(line[0])
                line = line[1:]
        elif line[0].isdigit():
            ttl = int(line[0])
            line = line[1:]
            if line[0] in queryClasses:
                cls = line[0]
                line = line[1:]

        type = line[0]
        rdata = line[1:]

        self.addRecord(owner, ttl, nativeString(type), domain, nativeString(cls), rdata)
