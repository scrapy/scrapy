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

    def addProto(num, proto):
        """
        Add a protocol on top of this one.
        """

    def datagramReceived(
        data,
        partial,
        source,
        dest,
        protocol,
        version,
        ihl,
        tos,
        tot_len,
        fragment_id,
        fragment_offset,
        dont_fragment,
        more_fragments,
        ttl,
    ):
        """
        An IP datagram has been received. Parse and process it.
        """


class IRawPacketProtocol(Interface):
    """
    An interface for low-level protocols such as IP and ARP.
    """

    def addProto(num, proto):
        """
        Add a protocol on top of this one.
        """

    def datagramReceived(data, partial, dest, source, protocol):
        """
        An IP datagram has been received. Parse and process it.
        """
