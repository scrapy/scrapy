# -*- test-case-name: twisted.protocols.haproxy.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
HAProxy PROXY protocol implementations.
"""

from ._wrapper import proxyEndpoint

__all__ = [
    'proxyEndpoint',
]
