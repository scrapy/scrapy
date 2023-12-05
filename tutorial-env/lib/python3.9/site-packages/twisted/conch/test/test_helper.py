# -*- test-case-name: twisted.conch.test.test_helper -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from twisted.conch.insults import helper
from twisted.conch.insults.insults import (
    BLINK,
    BOLD,
    G0,
    G1,
    G2,
    G3,
    NORMAL,
    REVERSE_VIDEO,
    UNDERLINE,
    modes,
    privateModes,
)
from twisted.trial import unittest

WIDTH = 80
HEIGHT = 24


class BufferTests(unittest.TestCase):
    def setUp(self):
        self.term = helper.TerminalBuffer()
        self.term.connectionMade()

    def testInitialState(self):
        self.assertEqual(self.term.width, WIDTH)
        self.assertEqual(self.term.height, HEIGHT)
        self.assertEqual(self.term.__bytes__(), b"\n" * (HEIGHT - 1))
        self.assertEqual(self.term.reportCursorPosition(), (0, 0))

    def test_initialPrivateModes(self):
        """
        Verify that only DEC Auto Wrap Mode (DECAWM) and DEC Text Cursor Enable
        Mode (DECTCEM) are initially in the Set Mode (SM) state.
        """
        self.assertEqual(
            {privateModes.AUTO_WRAP: True, privateModes.CURSOR_MODE: True},
            self.term.privateModes,
        )

    def test_carriageReturn(self):
        """
        C{"\r"} moves the cursor to the first column in the current row.
        """
        self.term.cursorForward(5)
        self.term.cursorDown(3)
        self.assertEqual(self.term.reportCursorPosition(), (5, 3))
        self.term.insertAtCursor(b"\r")
        self.assertEqual(self.term.reportCursorPosition(), (0, 3))

    def test_linefeed(self):
        """
        C{"\n"} moves the cursor to the next row without changing the column.
        """
        self.term.cursorForward(5)
        self.assertEqual(self.term.reportCursorPosition(), (5, 0))
        self.term.insertAtCursor(b"\n")
        self.assertEqual(self.term.reportCursorPosition(), (5, 1))

    def test_newline(self):
        """
        C{write} transforms C{"\n"} into C{"\r\n"}.
        """
        self.term.cursorForward(5)
        self.term.cursorDown(3)
        self.assertEqual(self.term.reportCursorPosition(), (5, 3))
        self.term.write(b"\n")
        self.assertEqual(self.term.reportCursorPosition(), (0, 4))

    def test_setPrivateModes(self):
        """
        Verify that L{helper.TerminalBuffer.setPrivateModes} changes the Set
        Mode (SM) state to "set" for the private modes it is passed.
        """
        expected = self.term.privateModes.copy()
        self.term.setPrivateModes([privateModes.SCROLL, privateModes.SCREEN])
        expected[privateModes.SCROLL] = True
        expected[privateModes.SCREEN] = True
        self.assertEqual(expected, self.term.privateModes)

    def test_resetPrivateModes(self):
        """
        Verify that L{helper.TerminalBuffer.resetPrivateModes} changes the Set
        Mode (SM) state to "reset" for the private modes it is passed.
        """
        expected = self.term.privateModes.copy()
        self.term.resetPrivateModes([privateModes.AUTO_WRAP, privateModes.CURSOR_MODE])
        del expected[privateModes.AUTO_WRAP]
        del expected[privateModes.CURSOR_MODE]
        self.assertEqual(expected, self.term.privateModes)

    def testCursorDown(self):
        self.term.cursorDown(3)
        self.assertEqual(self.term.reportCursorPosition(), (0, 3))
        self.term.cursorDown()
        self.assertEqual(self.term.reportCursorPosition(), (0, 4))
        self.term.cursorDown(HEIGHT)
        self.assertEqual(self.term.reportCursorPosition(), (0, HEIGHT - 1))

    def testCursorUp(self):
        self.term.cursorUp(5)
        self.assertEqual(self.term.reportCursorPosition(), (0, 0))

        self.term.cursorDown(20)
        self.term.cursorUp(1)
        self.assertEqual(self.term.reportCursorPosition(), (0, 19))

        self.term.cursorUp(19)
        self.assertEqual(self.term.reportCursorPosition(), (0, 0))

    def testCursorForward(self):
        self.term.cursorForward(2)
        self.assertEqual(self.term.reportCursorPosition(), (2, 0))
        self.term.cursorForward(2)
        self.assertEqual(self.term.reportCursorPosition(), (4, 0))
        self.term.cursorForward(WIDTH)
        self.assertEqual(self.term.reportCursorPosition(), (WIDTH, 0))

    def testCursorBackward(self):
        self.term.cursorForward(10)
        self.term.cursorBackward(2)
        self.assertEqual(self.term.reportCursorPosition(), (8, 0))
        self.term.cursorBackward(7)
        self.assertEqual(self.term.reportCursorPosition(), (1, 0))
        self.term.cursorBackward(1)
        self.assertEqual(self.term.reportCursorPosition(), (0, 0))
        self.term.cursorBackward(1)
        self.assertEqual(self.term.reportCursorPosition(), (0, 0))

    def testCursorPositioning(self):
        self.term.cursorPosition(3, 9)
        self.assertEqual(self.term.reportCursorPosition(), (3, 9))

    def testSimpleWriting(self):
        s = b"Hello, world."
        self.term.write(s)
        self.assertEqual(self.term.__bytes__(), s + b"\n" + b"\n" * (HEIGHT - 2))

    def testOvertype(self):
        s = b"hello, world."
        self.term.write(s)
        self.term.cursorBackward(len(s))
        self.term.resetModes([modes.IRM])
        self.term.write(b"H")
        self.assertEqual(
            self.term.__bytes__(), (b"H" + s[1:]) + b"\n" + b"\n" * (HEIGHT - 2)
        )

    def testInsert(self):
        s = b"ello, world."
        self.term.write(s)
        self.term.cursorBackward(len(s))
        self.term.setModes([modes.IRM])
        self.term.write(b"H")
        self.assertEqual(
            self.term.__bytes__(), (b"H" + s) + b"\n" + b"\n" * (HEIGHT - 2)
        )

    def testWritingInTheMiddle(self):
        s = b"Hello, world."
        self.term.cursorDown(5)
        self.term.cursorForward(5)
        self.term.write(s)
        self.assertEqual(
            self.term.__bytes__(),
            b"\n" * 5 + (self.term.fill * 5) + s + b"\n" + b"\n" * (HEIGHT - 7),
        )

    def testWritingWrappedAtEndOfLine(self):
        s = b"Hello, world."
        self.term.cursorForward(WIDTH - 5)
        self.term.write(s)
        self.assertEqual(
            self.term.__bytes__(),
            s[:5].rjust(WIDTH) + b"\n" + s[5:] + b"\n" + b"\n" * (HEIGHT - 3),
        )

    def testIndex(self):
        self.term.index()
        self.assertEqual(self.term.reportCursorPosition(), (0, 1))
        self.term.cursorDown(HEIGHT)
        self.assertEqual(self.term.reportCursorPosition(), (0, HEIGHT - 1))
        self.term.index()
        self.assertEqual(self.term.reportCursorPosition(), (0, HEIGHT - 1))

    def testReverseIndex(self):
        self.term.reverseIndex()
        self.assertEqual(self.term.reportCursorPosition(), (0, 0))
        self.term.cursorDown(2)
        self.assertEqual(self.term.reportCursorPosition(), (0, 2))
        self.term.reverseIndex()
        self.assertEqual(self.term.reportCursorPosition(), (0, 1))

    def test_nextLine(self):
        """
        C{nextLine} positions the cursor at the beginning of the row below the
        current row.
        """
        self.term.nextLine()
        self.assertEqual(self.term.reportCursorPosition(), (0, 1))
        self.term.cursorForward(5)
        self.assertEqual(self.term.reportCursorPosition(), (5, 1))
        self.term.nextLine()
        self.assertEqual(self.term.reportCursorPosition(), (0, 2))

    def testSaveCursor(self):
        self.term.cursorDown(5)
        self.term.cursorForward(7)
        self.assertEqual(self.term.reportCursorPosition(), (7, 5))
        self.term.saveCursor()
        self.term.cursorDown(7)
        self.term.cursorBackward(3)
        self.assertEqual(self.term.reportCursorPosition(), (4, 12))
        self.term.restoreCursor()
        self.assertEqual(self.term.reportCursorPosition(), (7, 5))

    def testSingleShifts(self):
        self.term.singleShift2()
        self.term.write(b"Hi")

        ch = self.term.getCharacter(0, 0)
        self.assertEqual(ch[0], b"H")
        self.assertEqual(ch[1].charset, G2)

        ch = self.term.getCharacter(1, 0)
        self.assertEqual(ch[0], b"i")
        self.assertEqual(ch[1].charset, G0)

        self.term.singleShift3()
        self.term.write(b"!!")

        ch = self.term.getCharacter(2, 0)
        self.assertEqual(ch[0], b"!")
        self.assertEqual(ch[1].charset, G3)

        ch = self.term.getCharacter(3, 0)
        self.assertEqual(ch[0], b"!")
        self.assertEqual(ch[1].charset, G0)

    def testShifting(self):
        s1 = b"Hello"
        s2 = b"World"
        s3 = b"Bye!"
        self.term.write(b"Hello\n")
        self.term.shiftOut()
        self.term.write(b"World\n")
        self.term.shiftIn()
        self.term.write(b"Bye!\n")

        g = G0
        h = 0
        for s in (s1, s2, s3):
            for i in range(len(s)):
                ch = self.term.getCharacter(i, h)
                self.assertEqual(ch[0], s[i : i + 1])
                self.assertEqual(ch[1].charset, g)
            g = g == G0 and G1 or G0
            h += 1

    def testGraphicRendition(self):
        self.term.selectGraphicRendition(BOLD, UNDERLINE, BLINK, REVERSE_VIDEO)
        self.term.write(b"W")
        self.term.selectGraphicRendition(NORMAL)
        self.term.write(b"X")
        self.term.selectGraphicRendition(BLINK)
        self.term.write(b"Y")
        self.term.selectGraphicRendition(BOLD)
        self.term.write(b"Z")

        ch = self.term.getCharacter(0, 0)
        self.assertEqual(ch[0], b"W")
        self.assertTrue(ch[1].bold)
        self.assertTrue(ch[1].underline)
        self.assertTrue(ch[1].blink)
        self.assertTrue(ch[1].reverseVideo)

        ch = self.term.getCharacter(1, 0)
        self.assertEqual(ch[0], b"X")
        self.assertFalse(ch[1].bold)
        self.assertFalse(ch[1].underline)
        self.assertFalse(ch[1].blink)
        self.assertFalse(ch[1].reverseVideo)

        ch = self.term.getCharacter(2, 0)
        self.assertEqual(ch[0], b"Y")
        self.assertTrue(ch[1].blink)
        self.assertFalse(ch[1].bold)
        self.assertFalse(ch[1].underline)
        self.assertFalse(ch[1].reverseVideo)

        ch = self.term.getCharacter(3, 0)
        self.assertEqual(ch[0], b"Z")
        self.assertTrue(ch[1].blink)
        self.assertTrue(ch[1].bold)
        self.assertFalse(ch[1].underline)
        self.assertFalse(ch[1].reverseVideo)

    def testColorAttributes(self):
        s1 = b"Merry xmas"
        s2 = b"Just kidding"
        self.term.selectGraphicRendition(
            helper.FOREGROUND + helper.RED, helper.BACKGROUND + helper.GREEN
        )
        self.term.write(s1 + b"\n")
        self.term.selectGraphicRendition(NORMAL)
        self.term.write(s2 + b"\n")

        for i in range(len(s1)):
            ch = self.term.getCharacter(i, 0)
            self.assertEqual(ch[0], s1[i : i + 1])
            self.assertEqual(ch[1].charset, G0)
            self.assertFalse(ch[1].bold)
            self.assertFalse(ch[1].underline)
            self.assertFalse(ch[1].blink)
            self.assertFalse(ch[1].reverseVideo)
            self.assertEqual(ch[1].foreground, helper.RED)
            self.assertEqual(ch[1].background, helper.GREEN)

        for i in range(len(s2)):
            ch = self.term.getCharacter(i, 1)
            self.assertEqual(ch[0], s2[i : i + 1])
            self.assertEqual(ch[1].charset, G0)
            self.assertFalse(ch[1].bold)
            self.assertFalse(ch[1].underline)
            self.assertFalse(ch[1].blink)
            self.assertFalse(ch[1].reverseVideo)
            self.assertEqual(ch[1].foreground, helper.WHITE)
            self.assertEqual(ch[1].background, helper.BLACK)

    def testEraseLine(self):
        s1 = b"line 1"
        s2 = b"line 2"
        s3 = b"line 3"
        self.term.write(b"\n".join((s1, s2, s3)) + b"\n")
        self.term.cursorPosition(1, 1)
        self.term.eraseLine()

        self.assertEqual(
            self.term.__bytes__(),
            s1 + b"\n" + b"\n" + s3 + b"\n" + b"\n" * (HEIGHT - 4),
        )

    def testEraseToLineEnd(self):
        s = b"Hello, world."
        self.term.write(s)
        self.term.cursorBackward(5)
        self.term.eraseToLineEnd()
        self.assertEqual(self.term.__bytes__(), s[:-5] + b"\n" + b"\n" * (HEIGHT - 2))

    def testEraseToLineBeginning(self):
        s = b"Hello, world."
        self.term.write(s)
        self.term.cursorBackward(5)
        self.term.eraseToLineBeginning()
        self.assertEqual(
            self.term.__bytes__(), s[-4:].rjust(len(s)) + b"\n" + b"\n" * (HEIGHT - 2)
        )

    def testEraseDisplay(self):
        self.term.write(b"Hello world\n")
        self.term.write(b"Goodbye world\n")
        self.term.eraseDisplay()

        self.assertEqual(self.term.__bytes__(), b"\n" * (HEIGHT - 1))

    def testEraseToDisplayEnd(self):
        s1 = b"Hello world"
        s2 = b"Goodbye world"
        self.term.write(b"\n".join((s1, s2, b"")))
        self.term.cursorPosition(5, 1)
        self.term.eraseToDisplayEnd()

        self.assertEqual(
            self.term.__bytes__(), s1 + b"\n" + s2[:5] + b"\n" + b"\n" * (HEIGHT - 3)
        )

    def testEraseToDisplayBeginning(self):
        s1 = b"Hello world"
        s2 = b"Goodbye world"
        self.term.write(b"\n".join((s1, s2)))
        self.term.cursorPosition(5, 1)
        self.term.eraseToDisplayBeginning()

        self.assertEqual(
            self.term.__bytes__(),
            b"\n" + s2[6:].rjust(len(s2)) + b"\n" + b"\n" * (HEIGHT - 3),
        )

    def testLineInsertion(self):
        s1 = b"Hello world"
        s2 = b"Goodbye world"
        self.term.write(b"\n".join((s1, s2)))
        self.term.cursorPosition(7, 1)
        self.term.insertLine()

        self.assertEqual(
            self.term.__bytes__(),
            s1 + b"\n" + b"\n" + s2 + b"\n" + b"\n" * (HEIGHT - 4),
        )

    def testLineDeletion(self):
        s1 = b"Hello world"
        s2 = b"Middle words"
        s3 = b"Goodbye world"
        self.term.write(b"\n".join((s1, s2, s3)))
        self.term.cursorPosition(9, 1)
        self.term.deleteLine()

        self.assertEqual(
            self.term.__bytes__(), s1 + b"\n" + s3 + b"\n" + b"\n" * (HEIGHT - 3)
        )


class FakeDelayedCall:
    called = False
    cancelled = False

    def __init__(self, fs, timeout, f, a, kw):
        self.fs = fs
        self.timeout = timeout
        self.f = f
        self.a = a
        self.kw = kw

    def active(self):
        return not (self.cancelled or self.called)

    def cancel(self):
        self.cancelled = True

    #        self.fs.calls.remove(self)

    def call(self):
        self.called = True
        self.f(*self.a, **self.kw)


class FakeScheduler:
    def __init__(self):
        self.calls = []

    def callLater(self, timeout, f, *a, **kw):
        self.calls.append(FakeDelayedCall(self, timeout, f, a, kw))
        return self.calls[-1]


class ExpectTests(unittest.TestCase):
    def setUp(self):
        self.term = helper.ExpectableBuffer()
        self.term.connectionMade()
        self.fs = FakeScheduler()

    def testSimpleString(self):
        result = []
        d = self.term.expect(b"hello world", timeout=1, scheduler=self.fs)
        d.addCallback(result.append)

        self.term.write(b"greeting puny earthlings\n")
        self.assertFalse(result)
        self.term.write(b"hello world\n")
        self.assertTrue(result)
        self.assertEqual(result[0].group(), b"hello world")
        self.assertEqual(len(self.fs.calls), 1)
        self.assertFalse(self.fs.calls[0].active())

    def testBrokenUpString(self):
        result = []
        d = self.term.expect(b"hello world")
        d.addCallback(result.append)

        self.assertFalse(result)
        self.term.write(b"hello ")
        self.assertFalse(result)
        self.term.write(b"worl")
        self.assertFalse(result)
        self.term.write(b"d")
        self.assertTrue(result)
        self.assertEqual(result[0].group(), b"hello world")

    def testMultiple(self):
        result = []
        d1 = self.term.expect(b"hello ")
        d1.addCallback(result.append)
        d2 = self.term.expect(b"world")
        d2.addCallback(result.append)

        self.assertFalse(result)
        self.term.write(b"hello")
        self.assertFalse(result)
        self.term.write(b" ")
        self.assertEqual(len(result), 1)
        self.term.write(b"world")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].group(), b"hello ")
        self.assertEqual(result[1].group(), b"world")

    def testSynchronous(self):
        self.term.write(b"hello world")

        result = []
        d = self.term.expect(b"hello world")
        d.addCallback(result.append)
        self.assertTrue(result)
        self.assertEqual(result[0].group(), b"hello world")

    def testMultipleSynchronous(self):
        self.term.write(b"goodbye world")

        result = []
        d1 = self.term.expect(b"bye")
        d1.addCallback(result.append)
        d2 = self.term.expect(b"world")
        d2.addCallback(result.append)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].group(), b"bye")
        self.assertEqual(result[1].group(), b"world")

    def _cbTestTimeoutFailure(self, res):
        self.assertTrue(hasattr(res, "type"))
        self.assertEqual(res.type, helper.ExpectationTimeout)

    def testTimeoutFailure(self):
        d = self.term.expect(b"hello world", timeout=1, scheduler=self.fs)
        d.addBoth(self._cbTestTimeoutFailure)
        self.fs.calls[0].call()

    def testOverlappingTimeout(self):
        self.term.write(b"not zoomtastic")

        result = []
        d1 = self.term.expect(b"hello world", timeout=1, scheduler=self.fs)
        d1.addBoth(self._cbTestTimeoutFailure)
        d2 = self.term.expect(b"zoom")
        d2.addCallback(result.append)

        self.fs.calls[0].call()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].group(), b"zoom")


class CharacterAttributeTests(unittest.TestCase):
    """
    Tests for L{twisted.conch.insults.helper.CharacterAttribute}.
    """

    def test_equality(self):
        """
        L{CharacterAttribute}s must have matching character attribute values
        (bold, blink, underline, etc) with the same values to be considered
        equal.
        """
        self.assertEqual(helper.CharacterAttribute(), helper.CharacterAttribute())

        self.assertEqual(
            helper.CharacterAttribute(), helper.CharacterAttribute(charset=G0)
        )

        self.assertEqual(
            helper.CharacterAttribute(
                bold=True,
                underline=True,
                blink=False,
                reverseVideo=True,
                foreground=helper.BLUE,
            ),
            helper.CharacterAttribute(
                bold=True,
                underline=True,
                blink=False,
                reverseVideo=True,
                foreground=helper.BLUE,
            ),
        )

        self.assertNotEqual(
            helper.CharacterAttribute(), helper.CharacterAttribute(charset=G1)
        )

        self.assertNotEqual(
            helper.CharacterAttribute(bold=True), helper.CharacterAttribute(bold=False)
        )

    def test_wantOneDeprecated(self):
        """
        L{twisted.conch.insults.helper.CharacterAttribute.wantOne} emits
        a deprecation warning when invoked.
        """
        # Trigger the deprecation warning.
        helper._FormattingState().wantOne(bold=True)

        warningsShown = self.flushWarnings([self.test_wantOneDeprecated])
        self.assertEqual(len(warningsShown), 1)
        self.assertEqual(warningsShown[0]["category"], DeprecationWarning)
        deprecatedClass = "twisted.conch.insults.helper._FormattingState.wantOne"
        self.assertEqual(
            warningsShown[0]["message"],
            "%s was deprecated in Twisted 13.1.0" % (deprecatedClass),
        )
