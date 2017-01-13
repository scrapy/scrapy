# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

#
from twisted.trial import unittest

from twisted.internet import protocol
from twisted.pair import rawudp

class MyProtocol(protocol.DatagramProtocol):
    def __init__(self, expecting):
        self.expecting = list(expecting)

    def datagramReceived(self, data, peer):
        (host, port) = peer
        assert self.expecting, 'Got a packet when not expecting anymore.'
        expectData, expectHost, expectPort = self.expecting.pop(0)

        assert expectData == data, "Expected data %r, got %r" % (expectData, data)
        assert expectHost == host, "Expected host %r, got %r" % (expectHost, host)
        assert expectPort == port, "Expected port %d=0x%04x, got %d=0x%04x" % (expectPort, expectPort, port, port)

class RawUDPTests(unittest.TestCase):
    def testPacketParsing(self):
        proto = rawudp.RawUDPProtocol()
        p1 = MyProtocol([

            (b'foobar', b'testHost', 0x43A2),

            ])
        proto.addProto(0xF00F, p1)

        proto.datagramReceived(b"\x43\xA2" #source
                               b"\xf0\x0f" #dest
                               b"\x00\x06" #len
                               b"\xDE\xAD" #check
                               b"foobar",
                               partial=0,
                               dest=b'dummy',
                               source=b'testHost',
                               protocol=b'dummy',
                               version=b'dummy',
                               ihl=b'dummy',
                               tos=b'dummy',
                               tot_len=b'dummy',
                               fragment_id=b'dummy',
                               fragment_offset=b'dummy',
                               dont_fragment=b'dummy',
                               more_fragments=b'dummy',
                               ttl=b'dummy',
                               )

        assert not p1.expecting, \
               'Should not expect any more packets, but still want %r' % p1.expecting

    def testMultiplePackets(self):
        proto = rawudp.RawUDPProtocol()
        p1 = MyProtocol([

            (b'foobar', b'testHost', 0x43A2),
            (b'quux', b'otherHost', 0x33FE),

            ])
        proto.addProto(0xF00F, p1)
        proto.datagramReceived(b"\x43\xA2" #source
                               b"\xf0\x0f" #dest
                               b"\x00\x06" #len
                               b"\xDE\xAD" #check
                               b"foobar",
                               partial=0,
                               dest=b'dummy',
                               source=b'testHost',
                               protocol=b'dummy',
                               version=b'dummy',
                               ihl=b'dummy',
                               tos=b'dummy',
                               tot_len=b'dummy',
                               fragment_id=b'dummy',
                               fragment_offset=b'dummy',
                               dont_fragment=b'dummy',
                               more_fragments=b'dummy',
                               ttl=b'dummy',
                               )
        proto.datagramReceived(b"\x33\xFE" #source
                               b"\xf0\x0f" #dest
                               b"\x00\x05" #len
                               b"\xDE\xAD" #check
                               b"quux",
                               partial=0,
                               dest=b'dummy',
                               source=b'otherHost',
                               protocol=b'dummy',
                               version=b'dummy',
                               ihl=b'dummy',
                               tos=b'dummy',
                               tot_len=b'dummy',
                               fragment_id=b'dummy',
                               fragment_offset=b'dummy',
                               dont_fragment=b'dummy',
                               more_fragments=b'dummy',
                               ttl=b'dummy',
                               )

        assert not p1.expecting, \
               'Should not expect any more packets, but still want %r' % p1.expecting


    def testMultipleSameProtos(self):
        proto = rawudp.RawUDPProtocol()
        p1 = MyProtocol([

            (b'foobar', b'testHost', 0x43A2),

            ])

        p2 = MyProtocol([

            (b'foobar', b'testHost', 0x43A2),

            ])

        proto.addProto(0xF00F, p1)
        proto.addProto(0xF00F, p2)

        proto.datagramReceived(b"\x43\xA2" #source
                               b"\xf0\x0f" #dest
                               b"\x00\x06" #len
                               b"\xDE\xAD" #check
                               b"foobar",
                               partial=0,
                               dest=b'dummy',
                               source=b'testHost',
                               protocol=b'dummy',
                               version=b'dummy',
                               ihl=b'dummy',
                               tos=b'dummy',
                               tot_len=b'dummy',
                               fragment_id=b'dummy',
                               fragment_offset=b'dummy',
                               dont_fragment=b'dummy',
                               more_fragments=b'dummy',
                               ttl=b'dummy',
                               )

        assert not p1.expecting, \
               'Should not expect any more packets, but still want %r' % p1.expecting
        assert not p2.expecting, \
               'Should not expect any more packets, but still want %r' % p2.expecting

    def testWrongProtoNotSeen(self):
        proto = rawudp.RawUDPProtocol()
        p1 = MyProtocol([])
        proto.addProto(1, p1)

        proto.datagramReceived(b"\x43\xA2" #source
                               b"\xf0\x0f" #dest
                               b"\x00\x06" #len
                               b"\xDE\xAD" #check
                               b"foobar",
                               partial=0,
                               dest=b'dummy',
                               source=b'testHost',
                               protocol=b'dummy',
                               version=b'dummy',
                               ihl=b'dummy',
                               tos=b'dummy',
                               tot_len=b'dummy',
                               fragment_id=b'dummy',
                               fragment_offset=b'dummy',
                               dont_fragment=b'dummy',
                               more_fragments=b'dummy',
                               ttl=b'dummy',
                               )

    def testDemuxing(self):
        proto = rawudp.RawUDPProtocol()
        p1 = MyProtocol([

            (b'foobar', b'testHost', 0x43A2),
            (b'quux', b'otherHost', 0x33FE),

            ])
        proto.addProto(0xF00F, p1)

        p2 = MyProtocol([

            (b'quux', b'otherHost', 0xA401),
            (b'foobar', b'testHost', 0xA302),

            ])
        proto.addProto(0xB050, p2)

        proto.datagramReceived(b"\xA4\x01" #source
                               b"\xB0\x50" #dest
                               b"\x00\x05" #len
                               b"\xDE\xAD" #check
                               b"quux",
                               partial=0,
                               dest=b'dummy',
                               source=b'otherHost',
                               protocol=b'dummy',
                               version=b'dummy',
                               ihl=b'dummy',
                               tos=b'dummy',
                               tot_len=b'dummy',
                               fragment_id=b'dummy',
                               fragment_offset=b'dummy',
                               dont_fragment=b'dummy',
                               more_fragments=b'dummy',
                               ttl=b'dummy',
                               )
        proto.datagramReceived(b"\x43\xA2" #source
                               b"\xf0\x0f" #dest
                               b"\x00\x06" #len
                               b"\xDE\xAD" #check
                               b"foobar",
                               partial=0,
                               dest=b'dummy',
                               source=b'testHost',
                               protocol=b'dummy',
                               version=b'dummy',
                               ihl=b'dummy',
                               tos=b'dummy',
                               tot_len=b'dummy',
                               fragment_id=b'dummy',
                               fragment_offset=b'dummy',
                               dont_fragment=b'dummy',
                               more_fragments=b'dummy',
                               ttl=b'dummy',
                               )
        proto.datagramReceived(b"\x33\xFE" #source
                               b"\xf0\x0f" #dest
                               b"\x00\x05" #len
                               b"\xDE\xAD" #check
                               b"quux",
                               partial=0,
                               dest=b'dummy',
                               source=b'otherHost',
                               protocol=b'dummy',
                               version=b'dummy',
                               ihl=b'dummy',
                               tos=b'dummy',
                               tot_len=b'dummy',
                               fragment_id=b'dummy',
                               fragment_offset=b'dummy',
                               dont_fragment=b'dummy',
                               more_fragments=b'dummy',
                               ttl=b'dummy',
                               )
        proto.datagramReceived(b"\xA3\x02" #source
                               b"\xB0\x50" #dest
                               b"\x00\x06" #len
                               b"\xDE\xAD" #check
                               b"foobar",
                               partial=0,
                               dest=b'dummy',
                               source=b'testHost',
                               protocol=b'dummy',
                               version=b'dummy',
                               ihl=b'dummy',
                               tos=b'dummy',
                               tot_len=b'dummy',
                               fragment_id=b'dummy',
                               fragment_offset=b'dummy',
                               dont_fragment=b'dummy',
                               more_fragments=b'dummy',
                               ttl=b'dummy',
                               )

        assert not p1.expecting, \
               'Should not expect any more packets, but still want %r' % p1.expecting
        assert not p2.expecting, \
               'Should not expect any more packets, but still want %r' % p2.expecting

    def testAddingBadProtos_WrongLevel(self):
        """Adding a wrong level protocol raises an exception."""
        e = rawudp.RawUDPProtocol()
        try:
            e.addProto(42, "silliness")
        except TypeError as e:
            if e.args == ('Added protocol must be an instance of DatagramProtocol',):
                pass
            else:
                raise
        else:
            raise AssertionError('addProto must raise an exception for bad protocols')


    def testAddingBadProtos_TooSmall(self):
        """Adding a protocol with a negative number raises an exception."""
        e = rawudp.RawUDPProtocol()
        try:
            e.addProto(-1, protocol.DatagramProtocol())
        except TypeError as e:
            if e.args == ('Added protocol must be positive or zero',):
                pass
            else:
                raise
        else:
            raise AssertionError('addProto must raise an exception for bad protocols')


    def testAddingBadProtos_TooBig(self):
        """Adding a protocol with a number >=2**16 raises an exception."""
        e = rawudp.RawUDPProtocol()
        try:
            e.addProto(2**16, protocol.DatagramProtocol())
        except TypeError as e:
            if e.args == ('Added protocol must fit in 16 bits',):
                pass
            else:
                raise
        else:
            raise AssertionError('addProto must raise an exception for bad protocols')

    def testAddingBadProtos_TooBig2(self):
        """Adding a protocol with a number >=2**16 raises an exception."""
        e = rawudp.RawUDPProtocol()
        try:
            e.addProto(2**16+1, protocol.DatagramProtocol())
        except TypeError as e:
            if e.args == ('Added protocol must fit in 16 bits',):
                pass
            else:
                raise
        else:
            raise AssertionError('addProto must raise an exception for bad protocols')
