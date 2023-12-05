# -*- test-case-name: twisted.conch.test.test_address -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Address object for SSH network connections.

Maintainer: Paul Swartz

@since: 12.1
"""


from zope.interface import implementer

from twisted.internet.interfaces import IAddress
from twisted.python import util


@implementer(IAddress)
class SSHTransportAddress(util.FancyEqMixin):
    """
    Object representing an SSH Transport endpoint.

    This is used to ensure that any code inspecting this address and
    attempting to construct a similar connection based upon it is not
    mislead into creating a transport which is not similar to the one it is
    indicating.

    @ivar address: An instance of an object which implements I{IAddress} to
        which this transport address is connected.
    """

    compareAttributes = ("address",)

    def __init__(self, address):
        self.address = address

    def __repr__(self) -> str:
        return f"SSHTransportAddress({self.address!r})"

    def __hash__(self):
        return hash(("SSH", self.address))
