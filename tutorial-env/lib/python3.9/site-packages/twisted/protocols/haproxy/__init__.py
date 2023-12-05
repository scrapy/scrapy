# -*- test-case-name: twisted.protocols.haproxy.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
HAProxy PROXY protocol implementations.
"""
__all__ = ["proxyEndpoint"]

from ._wrapper import proxyEndpoint
