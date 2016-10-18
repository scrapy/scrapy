# -*- test-case-name: twisted.protocols.haproxy.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
HAProxy specific exceptions.
"""

import contextlib
import sys

from twisted.python import compat


class InvalidProxyHeader(Exception):
    """
    The provided PROXY protocol header is invalid.
    """



class InvalidNetworkProtocol(InvalidProxyHeader):
    """
    The network protocol was not one of TCP4 TCP6 or UNKNOWN.
    """



class MissingAddressData(InvalidProxyHeader):
    """
    The address data is missing or incomplete.
    """



@contextlib.contextmanager
def convertError(sourceType, targetType):
    """
    Convert an error into a different error type.

    @param sourceType: The type of exception that should be caught and
        converted.
    @type sourceType: L{Exception}

    @param targetType: The type of exception to which the original should be
        converted.
    @type targetType: L{Exception}
    """
    try:
        yield None
    except sourceType:
        compat.reraise(targetType(), sys.exc_info()[-1])
