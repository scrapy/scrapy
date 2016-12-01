# -*- test-case-name: twisted.internet.test.test_endpoints -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Implementations of L{IStreamServerEndpoint} and L{IStreamClientEndpoint} that
wrap the L{IReactorTCP}, L{IReactorSSL}, and L{IReactorUNIX} interfaces.

This also implements an extensible mini-language for describing endpoints,
parsed by the L{clientFromString} and L{serverFromString} functions.

@since: 10.1
"""

from __future__ import division, absolute_import

from twisted.internet.endpoints import (
    clientFromString, serverFromString, quoteStringArgument,
    TCP4ServerEndpoint, TCP6ServerEndpoint,
    TCP4ClientEndpoint, TCP6ClientEndpoint,
    UNIXServerEndpoint, UNIXClientEndpoint,
    SSL4ServerEndpoint, SSL4ClientEndpoint,
    AdoptedStreamServerEndpoint, connectProtocol,
)

__all__ = ["TCP4ClientEndpoint", "SSL4ServerEndpoint"]
