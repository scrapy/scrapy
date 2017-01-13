"""
Common verification code.
"""

from __future__ import absolute_import, division, print_function

import re

import attr

from ._compat import maketrans, text_type
from .exceptions import (
    CertificateError,
    DNSMismatch,
    SRVMismatch,
    URIMismatch,
    VerificationError,
)

try:
    import idna
except ImportError:  # pragma: nocover
    idna = None


@attr.s
class ServiceMatch(object):
    """
    A match of a service id and a certificate pattern.
    """
    service_id = attr.ib()
    cert_pattern = attr.ib()


def verify_service_identity(cert_patterns, obligatory_ids, optional_ids):
    """
    Verify whether *cert_patterns* are valid for *obligatory_ids* and
    *optional_ids*.

    *obligatory_ids* must be both present and match.  *optional_ids* must match
    if a pattern of the respective type is present.
    """
    errors = []
    matches = (_find_matches(cert_patterns, obligatory_ids) +
               _find_matches(cert_patterns, optional_ids))

    matched_ids = [match.service_id for match in matches]
    for i in obligatory_ids:
        if i not in matched_ids:
            errors.append(i.error_on_mismatch(mismatched_id=i))

    for i in optional_ids:
        # If an optional ID is not matched by a certificate pattern *but* there
        # is a pattern of the same type , it is an error and the verification
        # fails.  Example: the user passes a SRV-ID for "_mail.domain.com" but
        # the certificate contains an SRV-Pattern for "_xmpp.domain.com".
        if (
            i not in matched_ids and
            _contains_instance_of(cert_patterns, i.pattern_class)
        ):
            errors.append(i.error_on_mismatch(mismatched_id=i))

    if errors:
        raise VerificationError(errors=errors)

    return matches


def _find_matches(cert_patterns, service_ids):
    """
    Search for matching certificate patterns and service_ids.

    :param cert_ids: List certificate IDs like DNSPattern.
    :type cert_ids: `list`

    :param service_ids: List of service IDs like DNS_ID.
    :type service_ids: `list`

    :rtype: `list` of `ServiceMatch`
    """
    matches = []
    for sid in service_ids:
        for cid in cert_patterns:
            if sid.verify(cid):
                matches.append(
                    ServiceMatch(cert_pattern=cid, service_id=sid)
                )
    return matches


def _contains_instance_of(seq, cl):
    """
    :type seq: iterable
    :type cl: type

    :rtype: bool
    """
    for e in seq:
        if isinstance(e, cl):
            return True
    return False


_RE_IPv4 = re.compile(br"^([0-9*]{1,3}\.){3}[0-9*]{1,3}$")
_RE_IPv6 = re.compile(br"^([a-f0-9*]{0,4}:)+[a-f0-9*]{1,4}$")
_RE_NUMBER = re.compile(br"^[0-9]+$")


def _is_ip_address(pattern):
    """
    Check whether *pattern* could be/match an IP address.

    Does *not* guarantee that pattern is in fact a valid IP address; especially
    the checks for IPv6 are rather coarse.  This function is for security
    checks, not for validating IP addresses.

    :param pattern: A pattern for a host name.
    :type pattern: `bytes` or `unicode`

    :return: `True` if *pattern* could be an IP address, else `False`.
    :rtype: `bool`
    """
    if isinstance(pattern, text_type):
        try:
            pattern = pattern.encode('ascii')
        except UnicodeError:
            return False

    return (
        _RE_IPv4.match(pattern) is not None or
        _RE_IPv6.match(pattern) is not None or
        _RE_NUMBER.match(pattern) is not None
    )


@attr.s(init=False)
class DNSPattern(object):
    """
    A DNS pattern as extracted from certificates.
    """
    pattern = attr.ib()

    _RE_LEGAL_CHARS = re.compile(br"^[a-z0-9\-_.]+$")

    def __init__(self, pattern):
        """
        :type pattern: `bytes`
        """
        if not isinstance(pattern, bytes):
            raise TypeError("The DNS pattern must be a bytes string.")

        pattern = pattern.strip()

        if pattern == b"" or _is_ip_address(pattern) or b"\0" in pattern:
            raise CertificateError(
                "Invalid DNS pattern {0!r}.".format(pattern)
            )

        self.pattern = pattern.translate(_TRANS_TO_LOWER)
        if b'*' in self.pattern:
            _validate_pattern(self.pattern)


@attr.s(init=False)
class URIPattern(object):
    """
    An URI pattern as extracted from certificates.
    """
    protocol_pattern = attr.ib()
    dns_pattern = attr.ib()

    def __init__(self, pattern):
        """
        :type pattern: `bytes`
        """
        if not isinstance(pattern, bytes):
            raise TypeError("The URI pattern must be a bytes string.")

        pattern = pattern.strip().translate(_TRANS_TO_LOWER)

        if (
            b":" not in pattern or
            b"*" in pattern or
            _is_ip_address(pattern)
        ):
            raise CertificateError(
                "Invalid URI pattern {0!r}.".format(pattern)
            )
        self.protocol_pattern, hostname = pattern.split(b":")
        self.dns_pattern = DNSPattern(hostname)


@attr.s(init=False)
class SRVPattern(object):
    """
    An SRV pattern as extracted from certificates.
    """
    name_pattern = attr.ib()
    dns_pattern = attr.ib()

    def __init__(self, pattern):
        """
        :type pattern: `bytes`
        """
        if not isinstance(pattern, bytes):
            raise TypeError("The SRV pattern must be a bytes string.")

        pattern = pattern.strip().translate(_TRANS_TO_LOWER)

        if (
            pattern[0] != b"_"[0] or
            b"." not in pattern or
            b"*" in pattern or
            _is_ip_address(pattern)
        ):
            raise CertificateError(
                "Invalid SRV pattern {0!r}.".format(pattern)
            )
        name, hostname = pattern.split(b".", 1)
        self.name_pattern = name[1:]
        self.dns_pattern = DNSPattern(hostname)


@attr.s(init=False)
class DNS_ID(object):
    """
    A DNS service ID, aka hostname.
    """
    hostname = attr.ib()

    # characters that are legal in a normalized hostname
    _RE_LEGAL_CHARS = re.compile(br"^[a-z0-9\-_.]+$")
    pattern_class = DNSPattern
    error_on_mismatch = DNSMismatch

    def __init__(self, hostname):
        """
        :type hostname: `unicode`
        """
        if not isinstance(hostname, text_type):
            raise TypeError("DNS-ID must be a unicode string.")

        hostname = hostname.strip()
        if hostname == u"" or _is_ip_address(hostname):
            raise ValueError("Invalid DNS-ID.")

        if any(ord(c) > 127 for c in hostname):
            if idna:
                ascii_id = idna.encode(hostname)
            else:
                raise ImportError(
                    "idna library is required for non-ASCII IDs."
                )
        else:
            ascii_id = hostname.encode("ascii")

        self.hostname = ascii_id.translate(_TRANS_TO_LOWER)
        if self._RE_LEGAL_CHARS.match(self.hostname) is None:
            raise ValueError("Invalid DNS-ID.")

    def verify(self, pattern):
        """
        http://tools.ietf.org/search/rfc6125#section-6.4
        """
        if isinstance(pattern, self.pattern_class):
            return _hostname_matches(pattern.pattern, self.hostname)
        else:
            return False


@attr.s(init=False)
class URI_ID(object):
    """
    An URI service ID.
    """
    protocol = attr.ib()
    dns_id = attr.ib()

    pattern_class = URIPattern
    error_on_mismatch = URIMismatch

    def __init__(self, uri):
        """
        :type uri: `unicode`
        """
        if not isinstance(uri, text_type):
            raise TypeError("URI-ID must be a unicode string.")

        uri = uri.strip()
        if u":" not in uri or _is_ip_address(uri):
            raise ValueError("Invalid URI-ID.")

        prot, hostname = uri.split(u":")

        self.protocol = prot.encode("ascii").translate(_TRANS_TO_LOWER)
        self.dns_id = DNS_ID(hostname.strip(u"/"))

    def verify(self, pattern):
        """
        http://tools.ietf.org/search/rfc6125#section-6.5.2
        """
        if isinstance(pattern, self.pattern_class):
            return (
                pattern.protocol_pattern == self.protocol and
                self.dns_id.verify(pattern.dns_pattern)
            )
        else:
            return False


@attr.s(init=False)
class SRV_ID(object):
    """
    An SRV service ID.
    """
    name = attr.ib()
    dns_id = attr.ib()

    pattern_class = SRVPattern
    error_on_mismatch = SRVMismatch

    def __init__(self, srv):
        """
        :type srv: `unicode`
        """
        if not isinstance(srv, text_type):
            raise TypeError("SRV-ID must be a unicode string.")

        srv = srv.strip()
        if u"." not in srv or _is_ip_address(srv) or srv[0] != u"_":
            raise ValueError("Invalid SRV-ID.")

        name, hostname = srv.split(u".", 1)

        self.name = name[1:].encode("ascii").translate(_TRANS_TO_LOWER)
        self.dns_id = DNS_ID(hostname)

    def verify(self, pattern):
        """
        http://tools.ietf.org/search/rfc6125#section-6.5.1
        """
        if isinstance(pattern, self.pattern_class):
            return (
                self.name == pattern.name_pattern and
                self.dns_id.verify(pattern.dns_pattern)
            )
        else:
            return False


def _hostname_matches(cert_pattern, actual_hostname):
    """
    :type cert_pattern: `bytes`
    :type actual_hostname: `bytes`

    :return: `True` if *cert_pattern* matches *actual_hostname*, else `False`.
    :rtype: `bool`
    """
    if b'*' in cert_pattern:
        cert_head, cert_tail = cert_pattern.split(b".", 1)
        actual_head, actual_tail = actual_hostname.split(b".", 1)
        if cert_tail != actual_tail:
            return False
        # No patterns for IDNA
        if actual_head.startswith(b"xn--"):
            return False

        if cert_head == b"*":
            return True

        start, end = cert_head.split(b"*")
        if start == b"":
            # *oo
            return actual_head.endswith(end)
        elif end == b"":
            # f*
            return actual_head.startswith(start)
        else:
            # f*o
            return actual_head.startswith(start) and actual_head.endswith(end)

    else:
        return cert_pattern == actual_hostname


def _validate_pattern(cert_pattern):
    """
    Check whether the usage of wildcards within *cert_pattern* conforms with
    our expectations.

    :type hostname: `bytes`

    :return: None
    """
    cnt = cert_pattern.count(b"*")
    if cnt > 1:
        raise CertificateError(
            "Certificate's DNS-ID {0!r} contains too many wildcards."
            .format(cert_pattern)
        )
    parts = cert_pattern.split(b".")
    if len(parts) < 3:
        raise CertificateError(
            "Certificate's DNS-ID {0!r} hast too few host components for "
            "wildcard usage."
            .format(cert_pattern)
        )
    # We assume there will always be only one wildcard allowed.
    if b"*" not in parts[0]:
        raise CertificateError(
            "Certificate's DNS-ID {0!r} has a wildcard outside the left-most "
            "part.".format(cert_pattern)
        )
    if any(not len(p) for p in parts):
        raise CertificateError(
            "Certificate's DNS-ID {0!r} contains empty parts."
            .format(cert_pattern)
        )


# Ensure no locale magic interferes.
_TRANS_TO_LOWER = maketrans(b"ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                            b"abcdefghijklmnopqrstuvwxyz")
