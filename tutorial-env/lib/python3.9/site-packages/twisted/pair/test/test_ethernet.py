# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
from zope.interface import implementer

from twisted.pair import ethernet, raw
from twisted.python import components
from twisted.trial import unittest


@implementer(raw.IRawPacketProtocol)
class MyProtocol:
    def __init__(self, expecting):
        self.expecting = list(expecting)

    def addProto(self, num, proto):
        """
        Not implemented
        """

    def datagramReceived(self, data, partial, dest, source, protocol):
        assert self.expecting, "Got a packet when not expecting anymore."
        expect = self.expecting.pop(0)
        localVariables = locals()
        params = {
            "partial": partial,
            "dest": dest,
            "source": source,
            "protocol": protocol,
        }
        assert expect == (data, params), "Expected {!r}, got {!r}".format(
            expect, (data, params)
        )


class EthernetTests(unittest.TestCase):
    def testPacketParsing(self):
        proto = ethernet.EthernetProtocol()
        p1 = MyProtocol(
            [
                (
                    b"foobar",
                    {
                        "partial": 0,
                        "dest": b"123456",
                        "source": b"987654",
                        "protocol": 0x0800,
                    },
                ),
            ]
        )
        proto.addProto(0x0800, p1)

        proto.datagramReceived(b"123456987654\x08\x00foobar", partial=0)

        assert not p1.expecting, (
            "Should not expect any more packets, but still want %r" % p1.expecting
        )

    def testMultiplePackets(self):
        proto = ethernet.EthernetProtocol()
        p1 = MyProtocol(
            [
                (
                    b"foobar",
                    {
                        "partial": 0,
                        "dest": b"123456",
                        "source": b"987654",
                        "protocol": 0x0800,
                    },
                ),
                (
                    b"quux",
                    {
                        "partial": 1,
                        "dest": b"012345",
                        "source": b"abcdef",
                        "protocol": 0x0800,
                    },
                ),
            ]
        )
        proto.addProto(0x0800, p1)

        proto.datagramReceived(b"123456987654\x08\x00foobar", partial=0)
        proto.datagramReceived(b"012345abcdef\x08\x00quux", partial=1)

        assert not p1.expecting, (
            "Should not expect any more packets, but still want %r" % p1.expecting
        )

    def testMultipleSameProtos(self):
        proto = ethernet.EthernetProtocol()
        p1 = MyProtocol(
            [
                (
                    b"foobar",
                    {
                        "partial": 0,
                        "dest": b"123456",
                        "source": b"987654",
                        "protocol": 0x0800,
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
                        "dest": b"123456",
                        "source": b"987654",
                        "protocol": 0x0800,
                    },
                ),
            ]
        )

        proto.addProto(0x0800, p1)
        proto.addProto(0x0800, p2)

        proto.datagramReceived(b"123456987654\x08\x00foobar", partial=0)

        assert (
            not p1.expecting
        ), "Should not expect any more packets, " "but still want {!r}".format(
            p1.expecting
        )
        assert (
            not p2.expecting
        ), "Should not expect any more packets," " but still want {!r}".format(
            p2.expecting
        )

    def testWrongProtoNotSeen(self):
        proto = ethernet.EthernetProtocol()
        p1 = MyProtocol([])
        proto.addProto(0x0801, p1)

        proto.datagramReceived(b"123456987654\x08\x00foobar", partial=0)
        proto.datagramReceived(b"012345abcdef\x08\x00quux", partial=1)

    def testDemuxing(self):
        proto = ethernet.EthernetProtocol()
        p1 = MyProtocol(
            [
                (
                    b"foobar",
                    {
                        "partial": 0,
                        "dest": b"123456",
                        "source": b"987654",
                        "protocol": 0x0800,
                    },
                ),
                (
                    b"quux",
                    {
                        "partial": 1,
                        "dest": b"012345",
                        "source": b"abcdef",
                        "protocol": 0x0800,
                    },
                ),
            ]
        )
        proto.addProto(0x0800, p1)

        p2 = MyProtocol(
            [
                (
                    b"quux",
                    {
                        "partial": 1,
                        "dest": b"012345",
                        "source": b"abcdef",
                        "protocol": 0x0806,
                    },
                ),
                (
                    b"foobar",
                    {
                        "partial": 0,
                        "dest": b"123456",
                        "source": b"987654",
                        "protocol": 0x0806,
                    },
                ),
            ]
        )
        proto.addProto(0x0806, p2)

        proto.datagramReceived(b"123456987654\x08\x00foobar", partial=0)
        proto.datagramReceived(b"012345abcdef\x08\x06quux", partial=1)
        proto.datagramReceived(b"123456987654\x08\x06foobar", partial=0)
        proto.datagramReceived(b"012345abcdef\x08\x00quux", partial=1)

        assert not p1.expecting, (
            "Should not expect any more packets, but still want %r" % p1.expecting
        )
        assert not p2.expecting, (
            "Should not expect any more packets, but still want %r" % p2.expecting
        )

    def testAddingBadProtos_WrongLevel(self):
        """Adding a wrong level protocol raises an exception."""
        e = ethernet.EthernetProtocol()
        try:
            e.addProto(42, "silliness")
        except components.CannotAdapt:
            pass
        else:
            raise AssertionError("addProto must raise an exception for bad protocols")

    def testAddingBadProtos_TooSmall(self):
        """Adding a protocol with a negative number raises an exception."""
        e = ethernet.EthernetProtocol()
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
        """Adding a protocol with a number >=2**16 raises an exception."""
        e = ethernet.EthernetProtocol()
        try:
            e.addProto(2 ** 16, MyProtocol([]))
        except TypeError as e:
            if e.args == ("Added protocol must fit in 16 bits",):
                pass
            else:
                raise
        else:
            raise AssertionError("addProto must raise an exception for bad protocols")

    def testAddingBadProtos_TooBig2(self):
        """Adding a protocol with a number >=2**16 raises an exception."""
        e = ethernet.EthernetProtocol()
        try:
            e.addProto(2 ** 16 + 1, MyProtocol([]))
        except TypeError as e:
            if e.args == ("Added protocol must fit in 16 bits",):
                pass
            else:
                raise
        else:
            raise AssertionError("addProto must raise an exception for bad protocols")
