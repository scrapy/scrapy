# -*- test-case-name: twisted.pair.test.test_rawudp -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Implementation of raw packet interfaces for UDP
"""

import struct

from zope.interface import implementer

from twisted.internet import protocol
from twisted.pair import raw


class UDPHeader:
    def __init__(self, data):

        (self.source, self.dest, self.len, self.check) = struct.unpack(
            "!HHHH", data[:8]
        )


@implementer(raw.IRawDatagramProtocol)
class RawUDPProtocol(protocol.AbstractDatagramProtocol):
    def __init__(self):
        self.udpProtos = {}

    def addProto(self, num, proto):
        if not isinstance(proto, protocol.DatagramProtocol):
            raise TypeError("Added protocol must be an instance of DatagramProtocol")
        if num < 0:
            raise TypeError("Added protocol must be positive or zero")
        if num >= 2 ** 16:
            raise TypeError("Added protocol must fit in 16 bits")
        if num not in self.udpProtos:
            self.udpProtos[num] = []
        self.udpProtos[num].append(proto)

    def datagramReceived(
        self,
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
        header = UDPHeader(data)
        for proto in self.udpProtos.get(header.dest, ()):
            proto.datagramReceived(data[8:], (source, header.source))
