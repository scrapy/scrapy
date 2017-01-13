# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
"""
Interface definitions for working with raw packets
"""

from zope.interface import Interface


class IRawDatagramProtocol(Interface):
    """
    An interface for protocols such as UDP, ICMP and TCP.
    """

    def addProto():
        """
        Add a protocol on top of this one.
        """

    def datagramReceived():
        """
        An IP datagram has been received. Parse and process it.
        """



class IRawPacketProtocol(Interface):
    """
    An interface for low-level protocols such as IP and ARP.
    """

    def addProto():
        """
        Add a protocol on top of this one.
        """

    def datagramReceived():
        """
        An IP datagram has been received. Parse and process it.
        """
