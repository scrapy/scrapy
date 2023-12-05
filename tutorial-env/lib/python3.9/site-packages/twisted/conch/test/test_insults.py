# -*- test-case-name: twisted.conch.test.test_insults -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

import textwrap
from typing import Optional, Type

from twisted.conch.insults.insults import (
    BLINK,
    CS_ALTERNATE,
    CS_ALTERNATE_SPECIAL,
    CS_DRAWING,
    CS_UK,
    CS_US,
    G0,
    G1,
    UNDERLINE,
    ClientProtocol,
    ServerProtocol,
    modes,
    privateModes,
)
from twisted.internet.protocol import Protocol
from twisted.python.compat import iterbytes
from twisted.python.constants import ValueConstant, Values
from twisted.test.proto_helpers import StringTransport
from twisted.trial import unittest


def _getattr(mock, name):
    return super(Mock, mock).__getattribute__(name)


def occurrences(mock):
    return _getattr(mock, "occurrences")


def methods(mock):
    return _getattr(mock, "methods")


def _append(mock, obj):
    occurrences(mock).append(obj)


default = object()


def _ecmaCodeTableCoordinate(column, row):
    """
    Return the byte in 7- or 8-bit code table identified by C{column}
    and C{row}.

    "An 8-bit code table consists of 256 positions arranged in 16
    columns and 16 rows.  The columns and rows are numbered 00 to 15."

    "A 7-bit code table consists of 128 positions arranged in 8
    columns and 16 rows.  The columns are numbered 00 to 07 and the
    rows 00 to 15 (see figure 1)."

    p.5 of "Standard ECMA-35: Character Code Structure and Extension
    Techniques", 6th Edition (December 1994).
    """
    # 8 and 15 both happen to take up 4 bits, so the first number
    # should be shifted by 4 for both the 7- and 8-bit tables.
    return bytes(bytearray([(column << 4) | row]))


def _makeControlFunctionSymbols(name, colOffset, names, doc):
    # the value for each name is the concatenation of the bit values
    # of its x, y locations, with an offset of 4 added to its x value.
    # so CUP is (0 + 4, 8) = (4, 8) = 4||8 = 1001000 = 72 = b"H"
    # this is how it's defined in the standard!
    attrs = {
        name: ValueConstant(_ecmaCodeTableCoordinate(i + colOffset, j))
        for j, row in enumerate(names)
        for i, name in enumerate(row)
        if name
    }
    attrs["__doc__"] = doc
    return type(name, (Values,), attrs)


CSFinalByte = _makeControlFunctionSymbols(
    "CSFinalByte",
    colOffset=4,
    names=[
        # 4,     5,     6
        ["ICH", "DCH", "HPA"],
        ["CUU", "SSE", "HPR"],
        ["CUD", "CPR", "REP"],
        ["CUF", "SU", "DA"],
        ["CUB", "SD", "VPA"],
        ["CNL", "NP", "VPR"],
        ["CPL", "PP", "HVP"],
        ["CHA", "CTC", "TBC"],
        ["CUP", "ECH", "SM"],
        ["CHT", "CVT", "MC"],
        ["ED", "CBT", "HPB"],
        ["EL", "SRS", "VPB"],
        ["IL", "PTX", "RM"],
        ["DL", "SDS", "SGR"],
        ["EF", "SIMD", "DSR"],
        ["EA", None, "DAQ"],
    ],
    doc=textwrap.dedent(
        """
    Symbolic constants for all control sequence final bytes
    that do not imply intermediate bytes.  This happens to cover
    movement control sequences.

    See page 11 of "Standard ECMA 48: Control Functions for Coded
    Character Sets", 5th Edition (June 1991).

    Each L{ValueConstant} maps a control sequence name to L{bytes}
    """
    ),
)


C1SevenBit = _makeControlFunctionSymbols(
    "C1SevenBit",
    colOffset=4,
    names=[
        [None, "DCS"],
        [None, "PU1"],
        ["BPH", "PU2"],
        ["NBH", "STS"],
        [None, "CCH"],
        ["NEL", "MW"],
        ["SSA", "SPA"],
        ["ESA", "EPA"],
        ["HTS", "SOS"],
        ["HTJ", None],
        ["VTS", "SCI"],
        ["PLD", "CSI"],
        ["PLU", "ST"],
        ["RI", "OSC"],
        ["SS2", "PM"],
        ["SS3", "APC"],
    ],
    doc=textwrap.dedent(
        """
    Symbolic constants for all 7 bit versions of the C1 control functions

    See page 9 "Standard ECMA 48: Control Functions for Coded
    Character Sets", 5th Edition (June 1991).

    Each L{ValueConstant} maps a control sequence name to L{bytes}
    """
    ),
)


class Mock:
    callReturnValue = default

    def __init__(self, methods=None, callReturnValue=default):
        """
        @param methods: Mapping of names to return values
        @param callReturnValue: object __call__ should return
        """
        self.occurrences = []
        if methods is None:
            methods = {}
        self.methods = methods
        if callReturnValue is not default:
            self.callReturnValue = callReturnValue

    def __call__(self, *a, **kw):
        returnValue = _getattr(self, "callReturnValue")
        if returnValue is default:
            returnValue = Mock()
        # _getattr(self, 'occurrences').append(('__call__', returnValue, a, kw))
        _append(self, ("__call__", returnValue, a, kw))
        return returnValue

    def __getattribute__(self, name):
        methods = _getattr(self, "methods")
        if name in methods:
            attrValue = Mock(callReturnValue=methods[name])
        else:
            attrValue = Mock()
        # _getattr(self, 'occurrences').append((name, attrValue))
        _append(self, (name, attrValue))
        return attrValue


class MockMixin:
    def assertCall(
        self, occurrence, methodName, expectedPositionalArgs=(), expectedKeywordArgs={}
    ):
        attr, mock = occurrence
        self.assertEqual(attr, methodName)
        self.assertEqual(len(occurrences(mock)), 1)
        [(call, result, args, kw)] = occurrences(mock)
        self.assertEqual(call, "__call__")
        self.assertEqual(args, expectedPositionalArgs)
        self.assertEqual(kw, expectedKeywordArgs)
        return result


_byteGroupingTestTemplate = """\
def testByte%(groupName)s(self):
    transport = StringTransport()
    proto = Mock()
    parser = self.protocolFactory(lambda: proto)
    parser.factory = self
    parser.makeConnection(transport)

    bytes = self.TEST_BYTES
    while bytes:
        chunk = bytes[:%(bytesPer)d]
        bytes = bytes[%(bytesPer)d:]
        parser.dataReceived(chunk)

    self.verifyResults(transport, proto, parser)
"""


class ByteGroupingsMixin(MockMixin):
    protocolFactory: Optional[Type[Protocol]] = None

    for word, n in [
        ("Pairs", 2),
        ("Triples", 3),
        ("Quads", 4),
        ("Quints", 5),
        ("Sexes", 6),
    ]:
        exec(_byteGroupingTestTemplate % {"groupName": word, "bytesPer": n})
    del word, n

    def verifyResults(self, transport, proto, parser):
        result = self.assertCall(occurrences(proto).pop(0), "makeConnection", (parser,))
        self.assertEqual(occurrences(result), [])


del _byteGroupingTestTemplate


class ServerArrowKeysTests(ByteGroupingsMixin, unittest.TestCase):
    protocolFactory = ServerProtocol

    # All the arrow keys once
    TEST_BYTES = b"\x1b[A\x1b[B\x1b[C\x1b[D"

    def verifyResults(self, transport, proto, parser):
        ByteGroupingsMixin.verifyResults(self, transport, proto, parser)

        for arrow in (
            parser.UP_ARROW,
            parser.DOWN_ARROW,
            parser.RIGHT_ARROW,
            parser.LEFT_ARROW,
        ):
            result = self.assertCall(
                occurrences(proto).pop(0), "keystrokeReceived", (arrow, None)
            )
            self.assertEqual(occurrences(result), [])
        self.assertFalse(occurrences(proto))


class PrintableCharactersTests(ByteGroupingsMixin, unittest.TestCase):
    protocolFactory = ServerProtocol

    # Some letters and digits, first on their own, then capitalized,
    # then modified with alt

    TEST_BYTES = b"abc123ABC!@#\x1ba\x1bb\x1bc\x1b1\x1b2\x1b3"

    def verifyResults(self, transport, proto, parser):
        ByteGroupingsMixin.verifyResults(self, transport, proto, parser)

        for char in iterbytes(b"abc123ABC!@#"):
            result = self.assertCall(
                occurrences(proto).pop(0), "keystrokeReceived", (char, None)
            )
            self.assertEqual(occurrences(result), [])

        for char in iterbytes(b"abc123"):
            result = self.assertCall(
                occurrences(proto).pop(0), "keystrokeReceived", (char, parser.ALT)
            )
            self.assertEqual(occurrences(result), [])

        occs = occurrences(proto)
        self.assertFalse(occs, f"{occs!r} should have been []")


class ServerFunctionKeysTests(ByteGroupingsMixin, unittest.TestCase):
    """Test for parsing and dispatching function keys (F1 - F12)"""

    protocolFactory = ServerProtocol

    byteList = []
    for byteCodes in (
        b"OP",
        b"OQ",
        b"OR",
        b"OS",  # F1 - F4
        b"15~",
        b"17~",
        b"18~",
        b"19~",  # F5 - F8
        b"20~",
        b"21~",
        b"23~",
        b"24~",
    ):  # F9 - F12
        byteList.append(b"\x1b[" + byteCodes)
    TEST_BYTES = b"".join(byteList)
    del byteList, byteCodes

    def verifyResults(self, transport, proto, parser):
        ByteGroupingsMixin.verifyResults(self, transport, proto, parser)
        for funcNum in range(1, 13):
            funcArg = getattr(parser, "F%d" % (funcNum,))
            result = self.assertCall(
                occurrences(proto).pop(0), "keystrokeReceived", (funcArg, None)
            )
            self.assertEqual(occurrences(result), [])
        self.assertFalse(occurrences(proto))


class ClientCursorMovementTests(ByteGroupingsMixin, unittest.TestCase):
    protocolFactory = ClientProtocol

    d2 = b"\x1b[2B"
    r4 = b"\x1b[4C"
    u1 = b"\x1b[A"
    l2 = b"\x1b[2D"
    # Move the cursor down two, right four, up one, left two, up one, left two
    TEST_BYTES = d2 + r4 + u1 + l2 + u1 + l2
    del d2, r4, u1, l2

    def verifyResults(self, transport, proto, parser):
        ByteGroupingsMixin.verifyResults(self, transport, proto, parser)

        for (method, count) in [
            ("Down", 2),
            ("Forward", 4),
            ("Up", 1),
            ("Backward", 2),
            ("Up", 1),
            ("Backward", 2),
        ]:
            result = self.assertCall(
                occurrences(proto).pop(0), "cursor" + method, (count,)
            )
            self.assertEqual(occurrences(result), [])
        self.assertFalse(occurrences(proto))


class ClientControlSequencesTests(unittest.TestCase, MockMixin):
    def setUp(self):
        self.transport = StringTransport()
        self.proto = Mock()
        self.parser = ClientProtocol(lambda: self.proto)
        self.parser.factory = self
        self.parser.makeConnection(self.transport)
        result = self.assertCall(
            occurrences(self.proto).pop(0), "makeConnection", (self.parser,)
        )
        self.assertFalse(occurrences(result))

    def testSimpleCardinals(self):
        self.parser.dataReceived(
            b"".join(
                b"\x1b[" + n + ch
                for ch in iterbytes(b"BACD")
                for n in (b"", b"2", b"20", b"200")
            )
        )
        occs = occurrences(self.proto)

        for meth in ("Down", "Up", "Forward", "Backward"):
            for count in (1, 2, 20, 200):
                result = self.assertCall(occs.pop(0), "cursor" + meth, (count,))
                self.assertFalse(occurrences(result))
        self.assertFalse(occs)

    def testScrollRegion(self):
        self.parser.dataReceived(b"\x1b[5;22r\x1b[r")
        occs = occurrences(self.proto)

        result = self.assertCall(occs.pop(0), "setScrollRegion", (5, 22))
        self.assertFalse(occurrences(result))

        result = self.assertCall(occs.pop(0), "setScrollRegion", (None, None))
        self.assertFalse(occurrences(result))
        self.assertFalse(occs)

    def testHeightAndWidth(self):
        self.parser.dataReceived(b"\x1b#3\x1b#4\x1b#5\x1b#6")
        occs = occurrences(self.proto)

        result = self.assertCall(occs.pop(0), "doubleHeightLine", (True,))
        self.assertFalse(occurrences(result))

        result = self.assertCall(occs.pop(0), "doubleHeightLine", (False,))
        self.assertFalse(occurrences(result))

        result = self.assertCall(occs.pop(0), "singleWidthLine")
        self.assertFalse(occurrences(result))

        result = self.assertCall(occs.pop(0), "doubleWidthLine")
        self.assertFalse(occurrences(result))
        self.assertFalse(occs)

    def testCharacterSet(self):
        self.parser.dataReceived(
            b"".join(
                [
                    b"".join([b"\x1b" + g + n for n in iterbytes(b"AB012")])
                    for g in iterbytes(b"()")
                ]
            )
        )
        occs = occurrences(self.proto)

        for which in (G0, G1):
            for charset in (
                CS_UK,
                CS_US,
                CS_DRAWING,
                CS_ALTERNATE,
                CS_ALTERNATE_SPECIAL,
            ):
                result = self.assertCall(
                    occs.pop(0), "selectCharacterSet", (charset, which)
                )
                self.assertFalse(occurrences(result))
        self.assertFalse(occs)

    def testShifting(self):
        self.parser.dataReceived(b"\x15\x14")
        occs = occurrences(self.proto)

        result = self.assertCall(occs.pop(0), "shiftIn")
        self.assertFalse(occurrences(result))

        result = self.assertCall(occs.pop(0), "shiftOut")
        self.assertFalse(occurrences(result))
        self.assertFalse(occs)

    def testSingleShifts(self):
        self.parser.dataReceived(b"\x1bN\x1bO")
        occs = occurrences(self.proto)

        result = self.assertCall(occs.pop(0), "singleShift2")
        self.assertFalse(occurrences(result))

        result = self.assertCall(occs.pop(0), "singleShift3")
        self.assertFalse(occurrences(result))
        self.assertFalse(occs)

    def testKeypadMode(self):
        self.parser.dataReceived(b"\x1b=\x1b>")
        occs = occurrences(self.proto)

        result = self.assertCall(occs.pop(0), "applicationKeypadMode")
        self.assertFalse(occurrences(result))

        result = self.assertCall(occs.pop(0), "numericKeypadMode")
        self.assertFalse(occurrences(result))
        self.assertFalse(occs)

    def testCursor(self):
        self.parser.dataReceived(b"\x1b7\x1b8")
        occs = occurrences(self.proto)

        result = self.assertCall(occs.pop(0), "saveCursor")
        self.assertFalse(occurrences(result))

        result = self.assertCall(occs.pop(0), "restoreCursor")
        self.assertFalse(occurrences(result))
        self.assertFalse(occs)

    def testReset(self):
        self.parser.dataReceived(b"\x1bc")
        occs = occurrences(self.proto)

        result = self.assertCall(occs.pop(0), "reset")
        self.assertFalse(occurrences(result))
        self.assertFalse(occs)

    def testIndex(self):
        self.parser.dataReceived(b"\x1bD\x1bM\x1bE")
        occs = occurrences(self.proto)

        result = self.assertCall(occs.pop(0), "index")
        self.assertFalse(occurrences(result))

        result = self.assertCall(occs.pop(0), "reverseIndex")
        self.assertFalse(occurrences(result))

        result = self.assertCall(occs.pop(0), "nextLine")
        self.assertFalse(occurrences(result))
        self.assertFalse(occs)

    def testModes(self):
        self.parser.dataReceived(
            b"\x1b["
            + b";".join(b"%d" % (m,) for m in [modes.KAM, modes.IRM, modes.LNM])
            + b"h"
        )
        self.parser.dataReceived(
            b"\x1b["
            + b";".join(b"%d" % (m,) for m in [modes.KAM, modes.IRM, modes.LNM])
            + b"l"
        )
        occs = occurrences(self.proto)

        result = self.assertCall(
            occs.pop(0), "setModes", ([modes.KAM, modes.IRM, modes.LNM],)
        )
        self.assertFalse(occurrences(result))

        result = self.assertCall(
            occs.pop(0), "resetModes", ([modes.KAM, modes.IRM, modes.LNM],)
        )
        self.assertFalse(occurrences(result))
        self.assertFalse(occs)

    def testErasure(self):
        self.parser.dataReceived(b"\x1b[K\x1b[1K\x1b[2K\x1b[J\x1b[1J\x1b[2J\x1b[3P")
        occs = occurrences(self.proto)

        for meth in (
            "eraseToLineEnd",
            "eraseToLineBeginning",
            "eraseLine",
            "eraseToDisplayEnd",
            "eraseToDisplayBeginning",
            "eraseDisplay",
        ):
            result = self.assertCall(occs.pop(0), meth)
            self.assertFalse(occurrences(result))

        result = self.assertCall(occs.pop(0), "deleteCharacter", (3,))
        self.assertFalse(occurrences(result))
        self.assertFalse(occs)

    def testLineDeletion(self):
        self.parser.dataReceived(b"\x1b[M\x1b[3M")
        occs = occurrences(self.proto)

        for arg in (1, 3):
            result = self.assertCall(occs.pop(0), "deleteLine", (arg,))
            self.assertFalse(occurrences(result))
        self.assertFalse(occs)

    def testLineInsertion(self):
        self.parser.dataReceived(b"\x1b[L\x1b[3L")
        occs = occurrences(self.proto)

        for arg in (1, 3):
            result = self.assertCall(occs.pop(0), "insertLine", (arg,))
            self.assertFalse(occurrences(result))
        self.assertFalse(occs)

    def testCursorPosition(self):
        methods(self.proto)["reportCursorPosition"] = (6, 7)
        self.parser.dataReceived(b"\x1b[6n")
        self.assertEqual(self.transport.value(), b"\x1b[7;8R")
        occs = occurrences(self.proto)

        result = self.assertCall(occs.pop(0), "reportCursorPosition")
        # This isn't really an interesting assert, since it only tests that
        # our mock setup is working right, but I'll include it anyway.
        self.assertEqual(result, (6, 7))

    def test_applicationDataBytes(self):
        """
        Contiguous non-control bytes are passed to a single call to the
        C{write} method of the terminal to which the L{ClientProtocol} is
        connected.
        """
        occs = occurrences(self.proto)
        self.parser.dataReceived(b"a")
        self.assertCall(occs.pop(0), "write", (b"a",))
        self.parser.dataReceived(b"bc")
        self.assertCall(occs.pop(0), "write", (b"bc",))

    def _applicationDataTest(self, data, calls):
        occs = occurrences(self.proto)
        self.parser.dataReceived(data)
        while calls:
            self.assertCall(occs.pop(0), *calls.pop(0))
        self.assertFalse(occs, f"No other calls should happen: {occs!r}")

    def test_shiftInAfterApplicationData(self):
        """
        Application data bytes followed by a shift-in command are passed to a
        call to C{write} before the terminal's C{shiftIn} method is called.
        """
        self._applicationDataTest(b"ab\x15", [("write", (b"ab",)), ("shiftIn",)])

    def test_shiftOutAfterApplicationData(self):
        """
        Application data bytes followed by a shift-out command are passed to a
        call to C{write} before the terminal's C{shiftOut} method is called.
        """
        self._applicationDataTest(b"ab\x14", [("write", (b"ab",)), ("shiftOut",)])

    def test_cursorBackwardAfterApplicationData(self):
        """
        Application data bytes followed by a cursor-backward command are passed
        to a call to C{write} before the terminal's C{cursorBackward} method is
        called.
        """
        self._applicationDataTest(b"ab\x08", [("write", (b"ab",)), ("cursorBackward",)])

    def test_escapeAfterApplicationData(self):
        """
        Application data bytes followed by an escape character are passed to a
        call to C{write} before the terminal's handler method for the escape is
        called.
        """
        # Test a short escape
        self._applicationDataTest(b"ab\x1bD", [("write", (b"ab",)), ("index",)])

        # And a long escape
        self._applicationDataTest(
            b"ab\x1b[4h", [("write", (b"ab",)), ("setModes", ([4],))]
        )

        # There's some other cases too, but they're all handled by the same
        # codepaths as above.


class ServerProtocolOutputTests(unittest.TestCase):
    """
    Tests for the bytes L{ServerProtocol} writes to its transport when its
    methods are called.
    """

    # From ECMA 48: CSI is represented by bit combinations 01/11
    # (representing ESC) and 05/11 in a 7-bit code or by bit
    # combination 09/11 in an 8-bit code
    ESC = _ecmaCodeTableCoordinate(1, 11)
    CSI = ESC + _ecmaCodeTableCoordinate(5, 11)

    def setUp(self):
        self.protocol = ServerProtocol()
        self.transport = StringTransport()
        self.protocol.makeConnection(self.transport)

    def test_cursorUp(self):
        """
        L{ServerProtocol.cursorUp} writes the control sequence
        ending with L{CSFinalByte.CUU} to its transport.
        """
        self.protocol.cursorUp(1)
        self.assertEqual(
            self.transport.value(), self.CSI + b"1" + CSFinalByte.CUU.value
        )

    def test_cursorDown(self):
        """
        L{ServerProtocol.cursorDown} writes the control sequence
        ending with L{CSFinalByte.CUD} to its transport.
        """
        self.protocol.cursorDown(1)
        self.assertEqual(
            self.transport.value(), self.CSI + b"1" + CSFinalByte.CUD.value
        )

    def test_cursorForward(self):
        """
        L{ServerProtocol.cursorForward} writes the control sequence
        ending with L{CSFinalByte.CUF} to its transport.
        """
        self.protocol.cursorForward(1)
        self.assertEqual(
            self.transport.value(), self.CSI + b"1" + CSFinalByte.CUF.value
        )

    def test_cursorBackward(self):
        """
        L{ServerProtocol.cursorBackward} writes the control sequence
        ending with L{CSFinalByte.CUB} to its transport.
        """
        self.protocol.cursorBackward(1)
        self.assertEqual(
            self.transport.value(), self.CSI + b"1" + CSFinalByte.CUB.value
        )

    def test_cursorPosition(self):
        """
        L{ServerProtocol.cursorPosition} writes a control sequence
        ending with L{CSFinalByte.CUP} and containing the expected
        coordinates to its transport.
        """
        self.protocol.cursorPosition(0, 0)
        self.assertEqual(
            self.transport.value(), self.CSI + b"1;1" + CSFinalByte.CUP.value
        )

    def test_cursorHome(self):
        """
        L{ServerProtocol.cursorHome} writes a control sequence ending
        with L{CSFinalByte.CUP} and no parameters, so that the client
        defaults to (1, 1).
        """
        self.protocol.cursorHome()
        self.assertEqual(self.transport.value(), self.CSI + CSFinalByte.CUP.value)

    def test_index(self):
        """
        L{ServerProtocol.index} writes the control sequence ending in
        the 8-bit code table coordinates 4, 4.

        Note that ECMA48 5th Edition removes C{IND}.
        """
        self.protocol.index()
        self.assertEqual(
            self.transport.value(), self.ESC + _ecmaCodeTableCoordinate(4, 4)
        )

    def test_reverseIndex(self):
        """
        L{ServerProtocol.reverseIndex} writes the control sequence
        ending in the L{C1SevenBit.RI}.
        """
        self.protocol.reverseIndex()
        self.assertEqual(self.transport.value(), self.ESC + C1SevenBit.RI.value)

    def test_nextLine(self):
        """
        L{ServerProtocol.nextLine} writes C{"\r\n"} to its transport.
        """
        # Why doesn't it write ESC E?  Because ESC E is poorly supported.  For
        # example, gnome-terminal (many different versions) fails to scroll if
        # it receives ESC E and the cursor is already on the last row.
        self.protocol.nextLine()
        self.assertEqual(self.transport.value(), b"\r\n")

    def test_setModes(self):
        """
        L{ServerProtocol.setModes} writes a control sequence
        containing the requested modes and ending in the
        L{CSFinalByte.SM}.
        """
        modesToSet = [modes.KAM, modes.IRM, modes.LNM]
        self.protocol.setModes(modesToSet)
        self.assertEqual(
            self.transport.value(),
            self.CSI
            + b";".join(b"%d" % (m,) for m in modesToSet)
            + CSFinalByte.SM.value,
        )

    def test_setPrivateModes(self):
        """
        L{ServerProtocol.setPrivatesModes} writes a control sequence
        containing the requested private modes and ending in the
        L{CSFinalByte.SM}.
        """
        privateModesToSet = [
            privateModes.ERROR,
            privateModes.COLUMN,
            privateModes.ORIGIN,
        ]
        self.protocol.setModes(privateModesToSet)
        self.assertEqual(
            self.transport.value(),
            self.CSI
            + b";".join(b"%d" % (m,) for m in privateModesToSet)
            + CSFinalByte.SM.value,
        )

    def test_resetModes(self):
        """
        L{ServerProtocol.resetModes} writes the control sequence
        ending in the L{CSFinalByte.RM}.
        """
        modesToSet = [modes.KAM, modes.IRM, modes.LNM]
        self.protocol.resetModes(modesToSet)
        self.assertEqual(
            self.transport.value(),
            self.CSI
            + b";".join(b"%d" % (m,) for m in modesToSet)
            + CSFinalByte.RM.value,
        )

    def test_singleShift2(self):
        """
        L{ServerProtocol.singleShift2} writes an escape sequence
        followed by L{C1SevenBit.SS2}
        """
        self.protocol.singleShift2()
        self.assertEqual(self.transport.value(), self.ESC + C1SevenBit.SS2.value)

    def test_singleShift3(self):
        """
        L{ServerProtocol.singleShift3} writes an escape sequence
        followed by L{C1SevenBit.SS3}
        """
        self.protocol.singleShift3()
        self.assertEqual(self.transport.value(), self.ESC + C1SevenBit.SS3.value)

    def test_selectGraphicRendition(self):
        """
        L{ServerProtocol.selectGraphicRendition} writes a control
        sequence containing the requested attributes and ending with
        L{CSFinalByte.SGR}
        """
        self.protocol.selectGraphicRendition(str(BLINK), str(UNDERLINE))
        self.assertEqual(
            self.transport.value(),
            self.CSI + b"%d;%d" % (BLINK, UNDERLINE) + CSFinalByte.SGR.value,
        )

    def test_horizontalTabulationSet(self):
        """
        L{ServerProtocol.horizontalTabulationSet} writes the escape
        sequence ending in L{C1SevenBit.HTS}
        """
        self.protocol.horizontalTabulationSet()
        self.assertEqual(self.transport.value(), self.ESC + C1SevenBit.HTS.value)

    def test_eraseToLineEnd(self):
        """
        L{ServerProtocol.eraseToLineEnd} writes the control sequence
        sequence ending in L{CSFinalByte.EL} and no parameters,
        forcing the client to default to 0 (from the active present
        position's current location to the end of the line.)
        """
        self.protocol.eraseToLineEnd()
        self.assertEqual(self.transport.value(), self.CSI + CSFinalByte.EL.value)

    def test_eraseToLineBeginning(self):
        """
        L{ServerProtocol.eraseToLineBeginning} writes the control
        sequence sequence ending in L{CSFinalByte.EL} and a parameter
        of 1 (from the beginning of the line up to and include the
        active present position's current location.)
        """
        self.protocol.eraseToLineBeginning()
        self.assertEqual(self.transport.value(), self.CSI + b"1" + CSFinalByte.EL.value)

    def test_eraseLine(self):
        """
        L{ServerProtocol.eraseLine} writes the control
        sequence sequence ending in L{CSFinalByte.EL} and a parameter
        of 2 (the entire line.)
        """
        self.protocol.eraseLine()
        self.assertEqual(self.transport.value(), self.CSI + b"2" + CSFinalByte.EL.value)

    def test_eraseToDisplayEnd(self):
        """
        L{ServerProtocol.eraseToDisplayEnd} writes the control
        sequence sequence ending in L{CSFinalByte.ED} and no parameters,
        forcing the client to default to 0 (from the active present
        position's current location to the end of the page.)
        """
        self.protocol.eraseToDisplayEnd()
        self.assertEqual(self.transport.value(), self.CSI + CSFinalByte.ED.value)

    def test_eraseToDisplayBeginning(self):
        """
        L{ServerProtocol.eraseToDisplayBeginning} writes the control
        sequence sequence ending in L{CSFinalByte.ED} a parameter of 1
        (from the beginning of the page up to and include the active
        present position's current location.)
        """
        self.protocol.eraseToDisplayBeginning()
        self.assertEqual(self.transport.value(), self.CSI + b"1" + CSFinalByte.ED.value)

    def test_eraseToDisplay(self):
        """
        L{ServerProtocol.eraseDisplay} writes the control sequence
        sequence ending in L{CSFinalByte.ED} a parameter of 2 (the
        entire page)
        """
        self.protocol.eraseDisplay()
        self.assertEqual(self.transport.value(), self.CSI + b"2" + CSFinalByte.ED.value)

    def test_deleteCharacter(self):
        """
        L{ServerProtocol.deleteCharacter} writes the control sequence
        containing the number of characters to delete and ending in
        L{CSFinalByte.DCH}
        """
        self.protocol.deleteCharacter(4)
        self.assertEqual(
            self.transport.value(), self.CSI + b"4" + CSFinalByte.DCH.value
        )

    def test_insertLine(self):
        """
        L{ServerProtocol.insertLine} writes the control sequence
        containing the number of lines to insert and ending in
        L{CSFinalByte.IL}
        """
        self.protocol.insertLine(5)
        self.assertEqual(self.transport.value(), self.CSI + b"5" + CSFinalByte.IL.value)

    def test_deleteLine(self):
        """
        L{ServerProtocol.deleteLine} writes the control sequence
        containing the number of lines to delete and ending in
        L{CSFinalByte.DL}
        """
        self.protocol.deleteLine(6)
        self.assertEqual(self.transport.value(), self.CSI + b"6" + CSFinalByte.DL.value)

    def test_setScrollRegionNoArgs(self):
        """
        With no arguments, L{ServerProtocol.setScrollRegion} writes a
        control sequence with no parameters, but a parameter
        separator, and ending in C{b'r'}.
        """
        self.protocol.setScrollRegion()
        self.assertEqual(self.transport.value(), self.CSI + b";" + b"r")

    def test_setScrollRegionJustFirst(self):
        """
        With just a value for its C{first} argument,
        L{ServerProtocol.setScrollRegion} writes a control sequence with
        that parameter, a parameter separator, and finally a C{b'r'}.
        """
        self.protocol.setScrollRegion(first=1)
        self.assertEqual(self.transport.value(), self.CSI + b"1;" + b"r")

    def test_setScrollRegionJustLast(self):
        """
        With just a value for its C{last} argument,
        L{ServerProtocol.setScrollRegion} writes a control sequence with
        a parameter separator, that parameter, and finally a C{b'r'}.
        """
        self.protocol.setScrollRegion(last=1)
        self.assertEqual(self.transport.value(), self.CSI + b";1" + b"r")

    def test_setScrollRegionFirstAndLast(self):
        """
        When given both C{first} and C{last}
        L{ServerProtocol.setScrollRegion} writes a control sequence with
        the first parameter, a parameter separator, the last
        parameter, and finally a C{b'r'}.
        """
        self.protocol.setScrollRegion(first=1, last=2)
        self.assertEqual(self.transport.value(), self.CSI + b"1;2" + b"r")

    def test_reportCursorPosition(self):
        """
        L{ServerProtocol.reportCursorPosition} writes a control
        sequence ending in L{CSFinalByte.DSR} with a parameter of 6
        (the Device Status Report returns the current active
        position.)
        """
        self.protocol.reportCursorPosition()
        self.assertEqual(
            self.transport.value(), self.CSI + b"6" + CSFinalByte.DSR.value
        )
