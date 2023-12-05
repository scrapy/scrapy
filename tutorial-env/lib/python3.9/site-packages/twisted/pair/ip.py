# -*- test-case-name: twisted.pair.test.test_ip -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

#


"""Support for working directly with IP packets"""

import socket
import struct

from zope.interface import implementer

from twisted.internet import protocol
from twisted.pair import raw


class IPHeader:
    def __init__(self, data):

        (
            ihlversion,
            self.tos,
            self.tot_len,
            self.fragment_id,
            frag_off,
            self.ttl,
            self.protocol,
            self.check,
            saddr,
            daddr,
        ) = struct.unpack("!BBHHHBBH4s4s", data[:20])
        self.saddr = socket.inet_ntoa(saddr)
        self.daddr = socket.inet_ntoa(daddr)
        self.version = ihlversion & 0x0F
        self.ihl = ((ihlversion & 0xF0) >> 4) << 2
        self.fragment_offset = frag_off & 0x1FFF
        self.dont_fragment = frag_off & 0x4000 != 0
        self.more_fragments = frag_off & 0x2000 != 0


MAX_SIZE = 2 ** 32


@implementer(raw.IRawPacketProtocol)
class IPProtocol(protocol.AbstractDatagramProtocol):
    def __init__(self):
        self.ipProtos = {}

    def addProto(self, num, proto):
        proto = raw.IRawDatagramProtocol(proto)
        if num < 0:
            raise TypeError("Added protocol must be positive or zero")
        if num >= MAX_SIZE:
            raise TypeError("Added protocol must fit in 32 bits")
        if num not in self.ipProtos:
            self.ipProtos[num] = []
        self.ipProtos[num].append(proto)

    def datagramReceived(self, data, partial, dest, source, protocol):
        header = IPHeader(data)
        for proto in self.ipProtos.get(header.protocol, ()):
            proto.datagramReceived(
                data=data[20:],
                partial=partial,
                source=header.saddr,
                dest=header.daddr,
                protocol=header.protocol,
                version=header.version,
                ihl=header.ihl,
                tos=header.tos,
                tot_len=header.tot_len,
                fragment_id=header.fragment_id,
                fragment_offset=header.fragment_offset,
                dont_fragment=header.dont_fragment,
                more_fragments=header.more_fragments,
                ttl=header.ttl,
            )
