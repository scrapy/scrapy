# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
from zope import interface

from twisted.pair import ip, raw
from twisted.python import components
from twisted.trial import unittest


@interface.implementer(raw.IRawDatagramProtocol)
class MyProtocol:
    def __init__(self, expecting):
        self.expecting = list(expecting)

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
        assert self.expecting, "Got a packet when not expecting anymore."
        expectData, expectKw = self.expecting.pop(0)

        expectKwKeys = expectKw.keys()
        expectKwKeys = list(sorted(expectKwKeys))
        localVariables = locals()

        for k in expectKwKeys:
            assert (
                expectKw[k] == localVariables[k]
            ), f"Expected {k}={expectKw[k]!r}, got {localVariables[k]!r}"
        assert expectData == data, f"Expected {expectData!r}, got {data!r}"

    def addProto(self, num, proto):
        # IRawDatagramProtocol.addProto
        pass


class IPTests(unittest.TestCase):
    def testPacketParsing(self):
        proto = ip.IPProtocol()
        p1 = MyProtocol(
            [
                (
                    b"foobar",
                    {
                        "partial": 0,
                        "dest": "1.2.3.4",
                        "source": "5.6.7.8",
                        "protocol": 0x0F,
                        "version": 4,
                        "ihl": 20,
                        "tos": 7,
                        "tot_len": 20 + 6,
                        "fragment_id": 0xDEAD,
                        "fragment_offset": 0x1EEF,
                        "dont_fragment": 0,
                        "more_fragments": 1,
                        "ttl": 0xC0,
                    },
                ),
            ]
        )
        proto.addProto(0x0F, p1)

        proto.datagramReceived(
            b"\x54"  # ihl version
            + b"\x07"  # tos
            + b"\x00\x1a"  # tot_len
            + b"\xDE\xAD"  # id
            + b"\xBE\xEF"  # frag_off
            + b"\xC0"  # ttl
            + b"\x0F"  # protocol
            + b"FE"  # checksum
            + b"\x05\x06\x07\x08"
            + b"\x01\x02\x03\x04"
            + b"foobar",
            partial=0,
            dest="dummy",
            source="dummy",
            protocol="dummy",
        )

        assert not p1.expecting, (
            "Should not expect any more packets, but still want %r" % p1.expecting
        )

    def testMultiplePackets(self):
        proto = ip.IPProtocol()
        p1 = MyProtocol(
            [
                (
                    b"foobar",
                    {
                        "partial": 0,
                        "dest": "1.2.3.4",
                        "source": "5.6.7.8",
                        "protocol": 0x0F,
                        "version": 4,
                        "ihl": 20,
                        "tos": 7,
                        "tot_len": 20 + 6,
                        "fragment_id": 0xDEAD,
                        "fragment_offset": 0x1EEF,
                        "dont_fragment": 0,
                        "more_fragments": 1,
                        "ttl": 0xC0,
                    },
                ),
                (
                    b"quux",
                    {
                        "partial": 1,
                        "dest": "5.4.3.2",
                        "source": "6.7.8.9",
                        "protocol": 0x0F,
                        "version": 4,
                        "ihl": 20,
                        "tos": 7,
                        "tot_len": 20 + 6,
                        "fragment_id": 0xDEAD,
                        "fragment_offset": 0x1EEF,
                        "dont_fragment": 0,
                        "more_fragments": 1,
                        "ttl": 0xC0,
                    },
                ),
            ]
        )
        proto.addProto(0x0F, p1)
        proto.datagramReceived(
            b"\x54"  # ihl version
            + b"\x07"  # tos
            + b"\x00\x1a"  # tot_len
            + b"\xDE\xAD"  # id
            + b"\xBE\xEF"  # frag_off
            + b"\xC0"  # ttl
            + b"\x0F"  # protocol
            + b"FE"  # checksum
            + b"\x05\x06\x07\x08"
            + b"\x01\x02\x03\x04"
            + b"foobar",
            partial=0,
            dest="dummy",
            source="dummy",
            protocol="dummy",
        )
        proto.datagramReceived(
            b"\x54"  # ihl version
            + b"\x07"  # tos
            + b"\x00\x1a"  # tot_len
            + b"\xDE\xAD"  # id
            + b"\xBE\xEF"  # frag_off
            + b"\xC0"  # ttl
            + b"\x0F"  # protocol
            + b"FE"  # checksum
            + b"\x06\x07\x08\x09"
            + b"\x05\x04\x03\x02"
            + b"quux",
            partial=1,
            dest="dummy",
            source="dummy",
            protocol="dummy",
        )

        assert not p1.expecting, (
            "Should not expect any more packets, but still want %r" % p1.expecting
        )

    def testMultipleSameProtos(self):
        proto = ip.IPProtocol()
        p1 = MyProtocol(
            [
                (
                    b"foobar",
                    {
                        "partial": 0,
                        "dest": "1.2.3.4",
                        "source": "5.6.7.8",
                        "protocol": 0x0F,
                        "version": 4,
                        "ihl": 20,
                        "tos": 7,
                        "tot_len": 20 + 6,
                        "fragment_id": 0xDEAD,
                        "fragment_offset": 0x1EEF,
                        "dont_fragment": 0,
                        "more_fragments": 1,
                        "ttl": 0xC0,
                    },
                ),
            ]
        )

        p2 = MyProtocol(
            [
                (
                    b"foobar",
                    {
                        "partial": 0,
                        "dest": "1.2.3.4",
                        "source": "5.6.7.8",
                        "protocol": 0x0F,
                        "version": 4,
                        "ihl": 20,
                        "tos": 7,
                        "tot_len": 20 + 6,
                        "fragment_id": 0xDEAD,
                        "fragment_offset": 0x1EEF,
                        "dont_fragment": 0,
                        "more_fragments": 1,
                        "ttl": 0xC0,
                    },
                ),
            ]
        )

        proto.addProto(0x0F, p1)
        proto.addProto(0x0F, p2)

        proto.datagramReceived(
            b"\x54"  # ihl version
            + b"\x07"  # tos
            + b"\x00\x1a"  # tot_len
            + b"\xDE\xAD"  # id
            + b"\xBE\xEF"  # frag_off
            + b"\xC0"  # ttl
            + b"\x0F"  # protocol
            + b"FE"  # checksum
            + b"\x05\x06\x07\x08"
            + b"\x01\x02\x03\x04"
            + b"foobar",
            partial=0,
            dest="dummy",
            source="dummy",
            protocol="dummy",
        )

        assert not p1.expecting, (
            "Should not expect any more packets, but still want %r" % p1.expecting
        )
        assert not p2.expecting, (
            "Should not expect any more packets, but still want %r" % p2.expecting
        )

    def testWrongProtoNotSeen(self):
        proto = ip.IPProtocol()
        p1 = MyProtocol([])
        proto.addProto(1, p1)

        proto.datagramReceived(
            b"\x54"  # ihl version
            + b"\x07"  # tos
            + b"\x00\x1a"  # tot_len
            + b"\xDE\xAD"  # id
            + b"\xBE\xEF"  # frag_off
            + b"\xC0"  # ttl
            + b"\x0F"  # protocol
            + b"FE"  # checksum
            + b"\x05\x06\x07\x08"
            + b"\x01\x02\x03\x04"
            + b"foobar",
            partial=0,
            dest="dummy",
            source="dummy",
            protocol="dummy",
        )

    def testDemuxing(self):
        proto = ip.IPProtocol()
        p1 = MyProtocol(
            [
                (
                    b"foobar",
                    {
                        "partial": 0,
                        "dest": "1.2.3.4",
                        "source": "5.6.7.8",
                        "protocol": 0x0F,
                        "version": 4,
                        "ihl": 20,
                        "tos": 7,
                        "tot_len": 20 + 6,
                        "fragment_id": 0xDEAD,
                        "fragment_offset": 0x1EEF,
                        "dont_fragment": 0,
                        "more_fragments": 1,
                        "ttl": 0xC0,
                    },
                ),
                (
                    b"quux",
                    {
                        "partial": 1,
                        "dest": "5.4.3.2",
                        "source": "6.7.8.9",
                        "protocol": 0x0F,
                        "version": 4,
                        "ihl": 20,
                        "tos": 7,
                        "tot_len": 20 + 6,
                        "fragment_id": 0xDEAD,
                        "fragment_offset": 0x1EEF,
                        "dont_fragment": 0,
                        "more_fragments": 1,
                        "ttl": 0xC0,
                    },
                ),
            ]
        )
        proto.addProto(0x0F, p1)

        p2 = MyProtocol(
            [
                (
                    b"quux",
                    {
                        "partial": 1,
                        "dest": "5.4.3.2",
                        "source": "6.7.8.9",
                        "protocol": 0x0A,
                        "version": 4,
                        "ihl": 20,
                        "tos": 7,
                        "tot_len": 20 + 6,
                        "fragment_id": 0xDEAD,
                        "fragment_offset": 0x1EEF,
                        "dont_fragment": 0,
                        "more_fragments": 1,
                        "ttl": 0xC0,
                    },
                ),
                (
                    b"foobar",
                    {
                        "partial": 0,
                        "dest": "1.2.3.4",
                        "source": "5.6.7.8",
                        "protocol": 0x0A,
                        "version": 4,
                        "ihl": 20,
                        "tos": 7,
                        "tot_len": 20 + 6,
                        "fragment_id": 0xDEAD,
                        "fragment_offset": 0x1EEF,
                        "dont_fragment": 0,
                        "more_fragments": 1,
                        "ttl": 0xC0,
                    },
                ),
            ]
        )
        proto.addProto(0x0A, p2)

        proto.datagramReceived(
            b"\x54"  # ihl version
            + b"\x07"  # tos
            + b"\x00\x1a"  # tot_len
            + b"\xDE\xAD"  # id
            + b"\xBE\xEF"  # frag_off
            + b"\xC0"  # ttl
            + b"\x0A"  # protocol
            + b"FE"  # checksum
            + b"\x06\x07\x08\x09"
            + b"\x05\x04\x03\x02"
            + b"quux",
            partial=1,
            dest="dummy",
            source="dummy",
            protocol="dummy",
        )
        proto.datagramReceived(
            b"\x54"  # ihl version
            + b"\x07"  # tos
            + b"\x00\x1a"  # tot_len
            + b"\xDE\xAD"  # id
            + b"\xBE\xEF"  # frag_off
            + b"\xC0"  # ttl
            + b"\x0F"  # protocol
            + b"FE"  # checksum
            + b"\x05\x06\x07\x08"
            + b"\x01\x02\x03\x04"
            + b"foobar",
            partial=0,
            dest="dummy",
            source="dummy",
            protocol="dummy",
        )
        proto.datagramReceived(
            b"\x54"  # ihl version
            + b"\x07"  # tos
            + b"\x00\x1a"  # tot_len
            + b"\xDE\xAD"  # id
            + b"\xBE\xEF"  # frag_off
            + b"\xC0"  # ttl
            + b"\x0F"  # protocol
            + b"FE"  # checksum
            + b"\x06\x07\x08\x09"
            + b"\x05\x04\x03\x02"
            + b"quux",
            partial=1,
            dest="dummy",
            source="dummy",
            protocol="dummy",
        )
        proto.datagramReceived(
            b"\x54"  # ihl version
            + b"\x07"  # tos
            + b"\x00\x1a"  # tot_len
            + b"\xDE\xAD"  # id
            + b"\xBE\xEF"  # frag_off
            + b"\xC0"  # ttl
            + b"\x0A"  # protocol
            + b"FE"  # checksum
            + b"\x05\x06\x07\x08"
            + b"\x01\x02\x03\x04"
            + b"foobar",
            partial=0,
            dest="dummy",
            source="dummy",
            protocol="dummy",
        )

        assert not p1.expecting, (
            "Should not expect any more packets, but still want %r" % p1.expecting
        )
        assert not p2.expecting, (
            "Should not expect any more packets, but still want %r" % p2.expecting
        )

    def testAddingBadProtos_WrongLevel(self):
        """Adding a wrong level protocol raises an exception."""
        e = ip.IPProtocol()
        try:
            e.addProto(42, "silliness")
        except components.CannotAdapt:
            pass
        else:
            raise AssertionError("addProto must raise an exception for bad protocols")

    def testAddingBadProtos_TooSmall(self):
        """Adding a protocol with a negative number raises an exception."""
        e = ip.IPProtocol()
        try:
            e.addProto(-1, MyProtocol([]))
        except TypeError as e:
            if e.args == ("Added protocol must be positive or zero",):
                pass
            else:
                raise
        else:
            raise AssertionError("addProto must raise an exception for bad protocols")

    def testAddingBadProtos_TooBig(self):
        """Adding a protocol with a number >=2**32 raises an exception."""
        e = ip.IPProtocol()
        try:
            e.addProto(2 ** 32, MyProtocol([]))
        except TypeError as e:
            if e.args == ("Added protocol must fit in 32 bits",):
                pass
            else:
                raise
        else:
            raise AssertionError("addProto must raise an exception for bad protocols")

    def testAddingBadProtos_TooBig2(self):
        """Adding a protocol with a number >=2**32 raises an exception."""
        e = ip.IPProtocol()
        try:
            e.addProto(2 ** 32 + 1, MyProtocol([]))
        except TypeError as e:
            if e.args == ("Added protocol must fit in 32 bits",):
                pass
            else:
                raise
        else:
            raise AssertionError("addProto must raise an exception for bad protocols")
