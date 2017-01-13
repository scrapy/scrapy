# -*- test-case-name: twisted.names.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Exception class definitions for Twisted Names.
"""

from __future__ import division, absolute_import

from twisted.internet.defer import TimeoutError


class DomainError(ValueError):
    """
    Indicates a lookup failed because there were no records matching the given
    C{name, class, type} triple.
    """



class AuthoritativeDomainError(ValueError):
    """
    Indicates a lookup failed for a name for which this server is authoritative
    because there were no records matching the given C{name, class, type}
    triple.
    """



class DNSQueryTimeoutError(TimeoutError):
    """
    Indicates a lookup failed due to a timeout.

    @ivar id: The id of the message which timed out.
    """
    def __init__(self, id):
        TimeoutError.__init__(self)
        self.id = id



class DNSFormatError(DomainError):
    """
    Indicates a query failed with a result of C{twisted.names.dns.EFORMAT}.
    """



class DNSServerError(DomainError):
    """
    Indicates a query failed with a result of C{twisted.names.dns.ESERVER}.
    """



class DNSNameError(DomainError):
    """
    Indicates a query failed with a result of C{twisted.names.dns.ENAME}.
    """



class DNSNotImplementedError(DomainError):
    """
    Indicates a query failed with a result of C{twisted.names.dns.ENOTIMP}.
    """



class DNSQueryRefusedError(DomainError):
    """
    Indicates a query failed with a result of C{twisted.names.dns.EREFUSED}.
    """



class DNSUnknownError(DomainError):
    """
    Indicates a query failed with an unknown result.
    """



class ResolverError(Exception):
    """
    Indicates a query failed because of a decision made by the local
    resolver object.
    """


__all__ = [
    'DomainError', 'AuthoritativeDomainError', 'DNSQueryTimeoutError',

    'DNSFormatError', 'DNSServerError', 'DNSNameError',
    'DNSNotImplementedError', 'DNSQueryRefusedError',
    'DNSUnknownError', 'ResolverError']
