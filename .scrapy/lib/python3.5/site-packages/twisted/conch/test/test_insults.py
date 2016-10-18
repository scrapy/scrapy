# -*- test-case-name: twisted.conch.test.test_insults -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from twisted.python.reflect import namedAny
from twisted.trial import unittest
from twisted.test.proto_helpers import StringTransport

from twisted.conch.insults.insults import ServerProtocol, ClientProtocol
from twisted.conch.insults.insults import CS_UK, CS_US, CS_DRAWING, CS_ALTERNATE, CS_ALTERNATE_SPECIAL
from twisted.conch.insults.insults import G0, G1
from twisted.conch.insults.insults import modes
from twisted.python.compat import intToBytes, iterbytes

def _getattr(mock, name):
    return super(Mock, mock).__getattribute__(name)


def occurrences(mock):
    return _getattr(mock, 'occurrences')


def methods(mock):
    return _getattr(mock, 'methods')


def _append(mock, obj):
    occurrences(mock).append(obj)

default = object()



class Mock(object):
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
        returnValue = _getattr(self, 'callReturnValue')
        if returnValue is default:
            returnValue = Mock()
        # _getattr(self, 'occurrences').append(('__call__', returnValue, a, kw))
        _append(self, ('__call__', returnValue, a, kw))
        return returnValue


    def __getattribute__(self, name):
        methods = _getattr(self, 'methods')
        if name in methods:
            attrValue = Mock(callReturnValue=methods[name])
        else:
            attrValue = Mock()
        # _getattr(self, 'occurrences').append((name, attrValue))
        _append(self, (name, attrValue))
        return attrValue



class MockMixin:
    def assertCall(self, occurrence, methodName, expectedPositionalArgs=(),
                   expectedKeywordArgs={}):
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
    protocolFactory = None

    for word, n in [('Pairs', 2), ('Triples', 3), ('Quads', 4), ('Quints', 5), ('Sexes', 6)]:
        exec(_byteGroupingTestTemplate % {'groupName': word, 'bytesPer': n})
    del word, n

    def verifyResults(self, transport, proto, parser):
        result = self.assertCall(occurrences(proto).pop(0), "makeConnection", (parser,))
        self.assertEqual(occurrences(result), [])

del _byteGroupingTestTemplate

class ServerArrowKeysTests(ByteGroupingsMixin, unittest.TestCase):
    protocolFactory = ServerProtocol

    # All the arrow keys once
    TEST_BYTES = b'\x1b[A\x1b[B\x1b[C\x1b[D'

    def verifyResults(self, transport, proto, parser):
        ByteGroupingsMixin.verifyResults(self, transport, proto, parser)

        for arrow in (parser.UP_ARROW, parser.DOWN_ARROW,
                      parser.RIGHT_ARROW, parser.LEFT_ARROW):
            result = self.assertCall(occurrences(proto).pop(0), "keystrokeReceived", (arrow, None))
            self.assertEqual(occurrences(result), [])
        self.assertFalse(occurrences(proto))


class PrintableCharactersTests(ByteGroupingsMixin, unittest.TestCase):
    protocolFactory = ServerProtocol

    # Some letters and digits, first on their own, then capitalized,
    # then modified with alt

    TEST_BYTES = b'abc123ABC!@#\x1ba\x1bb\x1bc\x1b1\x1b2\x1b3'

    def verifyResults(self, transport, proto, parser):
        ByteGroupingsMixin.verifyResults(self, transport, proto, parser)

        for char in iterbytes(b'abc123ABC!@#'):
            result = self.assertCall(occurrences(proto).pop(0), "keystrokeReceived", (char, None))
            self.assertEqual(occurrences(result), [])

        for char in iterbytes(b'abc123'):
            result = self.assertCall(occurrences(proto).pop(0), "keystrokeReceived", (char, parser.ALT))
            self.assertEqual(occurrences(result), [])

        occs = occurrences(proto)
        self.assertFalse(occs, "%r should have been []" % (occs,))



class ServerFunctionKeysTests(ByteGroupingsMixin, unittest.TestCase):
    """Test for parsing and dispatching function keys (F1 - F12)
    """
    protocolFactory = ServerProtocol

    byteList = []
    for byteCodes in (b'OP', b'OQ', b'OR', b'OS', # F1 - F4
                  b'15~', b'17~', b'18~', b'19~', # F5 - F8
                  b'20~', b'21~', b'23~', b'24~'): # F9 - F12
        byteList.append(b'\x1b[' + byteCodes)
    TEST_BYTES = b''.join(byteList)
    del byteList, byteCodes

    def verifyResults(self, transport, proto, parser):
        ByteGroupingsMixin.verifyResults(self, transport, proto, parser)
        for funcNum in range(1, 13):
            funcArg = getattr(parser, 'F%d' % (funcNum,))
            result = self.assertCall(occurrences(proto).pop(0), "keystrokeReceived", (funcArg, None))
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

        for (method, count) in [('Down', 2), ('Forward', 4), ('Up', 1),
                                ('Backward', 2), ('Up', 1), ('Backward', 2)]:
            result = self.assertCall(occurrences(proto).pop(0), "cursor" + method, (count,))
            self.assertEqual(occurrences(result), [])
        self.assertFalse(occurrences(proto))

class ClientControlSequencesTests(unittest.TestCase, MockMixin):
    def setUp(self):
        self.transport = StringTransport()
        self.proto = Mock()
        self.parser = ClientProtocol(lambda: self.proto)
        self.parser.factory = self
        self.parser.makeConnection(self.transport)
        result = self.assertCall(occurrences(self.proto).pop(0), "makeConnection", (self.parser,))
        self.assertFalse(occurrences(result))

    def testSimpleCardinals(self):
        self.parser.dataReceived(
            b''.join(
                    [b''.join([b'\x1b[' + n + ch
                             for n in (b'', intToBytes(2), intToBytes(20), intToBytes(200))]
                           ) for ch in iterbytes(b'BACD')
                    ]))
        occs = occurrences(self.proto)

        for meth in ("Down", "Up", "Forward", "Backward"):
            for count in (1, 2, 20, 200):
                result = self.assertCall(occs.pop(0), "cursor" + meth, (count,))
                self.assertFalse(occurrences(result))
        self.assertFalse(occs)

    def testScrollRegion(self):
        self.parser.dataReceived(b'\x1b[5;22r\x1b[r')
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
            b''.join(
                [b''.join([b'\x1b' + g + n for n in iterbytes(b'AB012')])
                    for g in iterbytes(b'()')
                ]))
        occs = occurrences(self.proto)

        for which in (G0, G1):
            for charset in (CS_UK, CS_US, CS_DRAWING, CS_ALTERNATE, CS_ALTERNATE_SPECIAL):
                result = self.assertCall(occs.pop(0), "selectCharacterSet", (charset, which))
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
            b"\x1b[" + b';'.join(map(intToBytes, [modes.KAM, modes.IRM, modes.LNM])) + b"h")
        self.parser.dataReceived(
            b"\x1b[" + b';'.join(map(intToBytes, [modes.KAM, modes.IRM, modes.LNM])) + b"l")
        occs = occurrences(self.proto)

        result = self.assertCall(occs.pop(0), "setModes", ([modes.KAM, modes.IRM, modes.LNM],))
        self.assertFalse(occurrences(result))

        result = self.assertCall(occs.pop(0), "resetModes", ([modes.KAM, modes.IRM, modes.LNM],))
        self.assertFalse(occurrences(result))
        self.assertFalse(occs)


    def testErasure(self):
        self.parser.dataReceived(
            b"\x1b[K\x1b[1K\x1b[2K\x1b[J\x1b[1J\x1b[2J\x1b[3P")
        occs = occurrences(self.proto)

        for meth in ("eraseToLineEnd", "eraseToLineBeginning", "eraseLine",
                     "eraseToDisplayEnd", "eraseToDisplayBeginning",
                     "eraseDisplay"):
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
        methods(self.proto)['reportCursorPosition'] = (6, 7)
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
        self.parser.dataReceived(b'a')
        self.assertCall(occs.pop(0), "write", (b"a",))
        self.parser.dataReceived(b'bc')
        self.assertCall(occs.pop(0), "write", (b"bc",))


    def _applicationDataTest(self, data, calls):
        occs = occurrences(self.proto)
        self.parser.dataReceived(data)
        while calls:
            self.assertCall(occs.pop(0), *calls.pop(0))
        self.assertFalse(occs, "No other calls should happen: %r" % (occs,))


    def test_shiftInAfterApplicationData(self):
        """
        Application data bytes followed by a shift-in command are passed to a
        call to C{write} before the terminal's C{shiftIn} method is called.
        """
        self._applicationDataTest(
            b'ab\x15', [
                ("write", (b"ab",)),
                ("shiftIn",)])


    def test_shiftOutAfterApplicationData(self):
        """
        Application data bytes followed by a shift-out command are passed to a
        call to C{write} before the terminal's C{shiftOut} method is called.
        """
        self._applicationDataTest(
            b'ab\x14', [
                ("write", (b"ab",)),
                ("shiftOut",)])


    def test_cursorBackwardAfterApplicationData(self):
        """
        Application data bytes followed by a cursor-backward command are passed
        to a call to C{write} before the terminal's C{cursorBackward} method is
        called.
        """
        self._applicationDataTest(
            b'ab\x08', [
                ("write", (b"ab",)),
                ("cursorBackward",)])


    def test_escapeAfterApplicationData(self):
        """
        Application data bytes followed by an escape character are passed to a
        call to C{write} before the terminal's handler method for the escape is
        called.
        """
        # Test a short escape
        self._applicationDataTest(
            b'ab\x1bD', [
                ("write", (b"ab",)),
                ("index",)])

        # And a long escape
        self._applicationDataTest(
            b'ab\x1b[4h', [
                ("write", (b"ab",)),
                ("setModes", ([4],))])

        # There's some other cases too, but they're all handled by the same
        # codepaths as above.



class ServerProtocolOutputTests(unittest.TestCase):
    """
    Tests for the bytes L{ServerProtocol} writes to its transport when its
    methods are called.
    """
    def test_nextLine(self):
        """
        L{ServerProtocol.nextLine} writes C{"\r\n"} to its transport.
        """
        # Why doesn't it write ESC E?  Because ESC E is poorly supported.  For
        # example, gnome-terminal (many different versions) fails to scroll if
        # it receives ESC E and the cursor is already on the last row.
        protocol = ServerProtocol()
        transport = StringTransport()
        protocol.makeConnection(transport)
        protocol.nextLine()
        self.assertEqual(transport.value(), b"\r\n")



class DeprecationsTests(unittest.TestCase):
    """
    Tests to ensure deprecation of L{insults.colors} and L{insults.client}
    """

    def ensureDeprecated(self, message):
        """
        Ensures that the correct deprecation warning was issued.
        """
        warnings = self.flushWarnings()
        self.assertIs(warnings[0]['category'], DeprecationWarning)
        self.assertEqual(warnings[0]['message'], message)
        self.assertEqual(len(warnings), 1)


    def test_colors(self):
        """
        The L{insults.colors} module is deprecated
        """
        namedAny('twisted.conch.insults.colors')
        self.ensureDeprecated("twisted.conch.insults.colors was deprecated "
                              "in Twisted 10.1.0: Please use "
                              "twisted.conch.insults.helper instead.")


    def test_client(self):
        """
        The L{insults.client} module is deprecated
        """
        namedAny('twisted.conch.insults.client')
        self.ensureDeprecated("twisted.conch.insults.client was deprecated "
                              "in Twisted 10.1.0: Please use "
                              "twisted.conch.insults.insults instead.")
