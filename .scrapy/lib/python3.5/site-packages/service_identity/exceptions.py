"""
All exceptions and warnings thrown by ``service_identity``.

Separated into an own package for nicer tracebacks, you should still import
them from __init__.py.
"""

from __future__ import absolute_import, division, print_function

import attr


class SubjectAltNameWarning(Warning):
    """
    Server Certificate does not contain a ``SubjectAltName``.

    Hostname matching is performed on the ``CommonName`` which is deprecated.
    """


@attr.s
class VerificationError(Exception):
    """
    Service identity verification failed.
    """
    errors = attr.ib()

    def __str__(self):
        return self.__repr__()


@attr.s
class DNSMismatch(object):
    """
    Not matching DNSPattern could be found.
    """
    mismatched_id = attr.ib()


@attr.s
class SRVMismatch(object):
    """
    Not matching SRVPattern could be found.
    """
    mismatched_id = attr.ib()


@attr.s
class URIMismatch(object):
    """
    Not matching URIPattern could be found.
    """
    mismatched_id = attr.ib()


class CertificateError(Exception):
    """
    Certificate contains invalid or unexpected data.
    """
