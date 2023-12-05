# -*- test-case-name: twisted.conch.test.test_manhole -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

# pylint: disable=I0011,W9401,W9402

"""
Tests for L{twisted.conch.manhole}.
"""

import sys
import traceback
from typing import Optional

ssh: Optional[bool] = None

from twisted.conch import manhole
from twisted.conch.insults import insults
from twisted.conch.test.test_recvline import (
    _SSHMixin,
    _StdioMixin,
    _TelnetMixin,
    ssh,
    stdio,
)
from twisted.internet import defer, error
from twisted.test.proto_helpers import StringTransport
from twisted.trial import unittest


def determineDefaultFunctionName():
    """
    Return the string used by Python as the name for code objects which are
    compiled from interactive input or at the top-level of modules.
    """
    try:
        1 // 0
    except BaseException:
        # The last frame is this function.  The second to last frame is this
        # function's caller, which is module-scope, which is what we want,
        # so -2.
        return traceback.extract_stack()[-2][2]


defaultFunctionName = determineDefaultFunctionName()


class ManholeInterpreterTests(unittest.TestCase):
    """
    Tests for L{manhole.ManholeInterpreter}.
    """

    def test_resetBuffer(self):
        """
        L{ManholeInterpreter.resetBuffer} should empty the input buffer.
        """
        interpreter = manhole.ManholeInterpreter(None)
        interpreter.buffer.extend(["1", "2"])
        interpreter.resetBuffer()
        self.assertFalse(interpreter.buffer)


class ManholeProtocolTests(unittest.TestCase):
    """
    Tests for L{manhole.Manhole}.
    """

    def test_interruptResetsInterpreterBuffer(self):
        """
        L{manhole.Manhole.handle_INT} should cause the interpreter input buffer
        to be reset.
        """
        transport = StringTransport()
        terminal = insults.ServerProtocol(manhole.Manhole)
        terminal.makeConnection(transport)
        protocol = terminal.terminalProtocol
        interpreter = protocol.interpreter
        interpreter.buffer.extend(["1", "2"])
        protocol.handle_INT()
        self.assertFalse(interpreter.buffer)


class WriterTests(unittest.TestCase):
    def test_Integer(self):
        """
        Colorize an integer.
        """
        manhole.lastColorizedLine("1")

    def test_DoubleQuoteString(self):
        """
        Colorize an integer in double quotes.
        """
        manhole.lastColorizedLine('"1"')

    def test_SingleQuoteString(self):
        """
        Colorize an integer in single quotes.
        """
        manhole.lastColorizedLine("'1'")

    def test_TripleSingleQuotedString(self):
        """
        Colorize an integer in triple quotes.
        """
        manhole.lastColorizedLine("'''1'''")

    def test_TripleDoubleQuotedString(self):
        """
        Colorize an integer in triple and double quotes.
        """
        manhole.lastColorizedLine('"""1"""')

    def test_FunctionDefinition(self):
        """
        Colorize a function definition.
        """
        manhole.lastColorizedLine("def foo():")

    def test_ClassDefinition(self):
        """
        Colorize a class definition.
        """
        manhole.lastColorizedLine("class foo:")

    def test_unicode(self):
        """
        Colorize a Unicode string.
        """
        res = manhole.lastColorizedLine("\u0438")
        self.assertTrue(isinstance(res, bytes))

    def test_bytes(self):
        """
        Colorize a UTF-8 byte string.
        """
        res = manhole.lastColorizedLine(b"\xd0\xb8")
        self.assertTrue(isinstance(res, bytes))

    def test_identicalOutput(self):
        """
        The output of UTF-8 bytestrings and Unicode strings are identical.
        """
        self.assertEqual(
            manhole.lastColorizedLine(b"\xd0\xb8"), manhole.lastColorizedLine("\u0438")
        )


class ManholeLoopbackMixin:
    serverProtocol = manhole.ColoredManhole

    def test_SimpleExpression(self):
        """
        Evaluate simple expression.
        """
        done = self.recvlineClient.expect(b"done")

        self._testwrite(b"1 + 1\n" b"done")

        def finished(ign):
            self._assertBuffer([b">>> 1 + 1", b"2", b">>> done"])

        return done.addCallback(finished)

    def test_TripleQuoteLineContinuation(self):
        """
        Evaluate line continuation in triple quotes.
        """
        done = self.recvlineClient.expect(b"done")

        self._testwrite(b"'''\n'''\n" b"done")

        def finished(ign):
            self._assertBuffer([b">>> '''", b"... '''", b"'\\n'", b">>> done"])

        return done.addCallback(finished)

    def test_FunctionDefinition(self):
        """
        Evaluate function definition.
        """
        done = self.recvlineClient.expect(b"done")

        self._testwrite(b"def foo(bar):\n" b"\tprint(bar)\n\n" b"foo(42)\n" b"done")

        def finished(ign):
            self._assertBuffer(
                [
                    b">>> def foo(bar):",
                    b"...     print(bar)",
                    b"... ",
                    b">>> foo(42)",
                    b"42",
                    b">>> done",
                ]
            )

        return done.addCallback(finished)

    def test_ClassDefinition(self):
        """
        Evaluate class definition.
        """
        done = self.recvlineClient.expect(b"done")
        self._testwrite(
            b"class Foo:\n"
            b"\tdef bar(self):\n"
            b"\t\tprint('Hello, world!')\n\n"
            b"Foo().bar()\n"
            b"done"
        )

        def finished(ign):
            self._assertBuffer(
                [
                    b">>> class Foo:",
                    b"...     def bar(self):",
                    b"...         print('Hello, world!')",
                    b"... ",
                    b">>> Foo().bar()",
                    b"Hello, world!",
                    b">>> done",
                ]
            )

        return done.addCallback(finished)

    def test_Exception(self):
        """
        Evaluate raising an exception.
        """
        done = self.recvlineClient.expect(b"done")

        self._testwrite(b"raise Exception('foo bar baz')\n" b"done")

        def finished(ign):
            self._assertBuffer(
                [
                    b">>> raise Exception('foo bar baz')",
                    b"Traceback (most recent call last):",
                    b'  File "<console>", line 1, in '
                    + defaultFunctionName.encode("utf-8"),
                    b"Exception: foo bar baz",
                    b">>> done",
                ],
            )

        done.addCallback(finished)
        return done

    def test_ExceptionWithCustomExcepthook(
        self,
    ):
        """
        Raised exceptions are handled the same way even if L{sys.excepthook}
        has been modified from its original value.
        """
        self.patch(sys, "excepthook", lambda *args: None)
        return self.test_Exception()

    def test_ControlC(self):
        """
        Evaluate interrupting with CTRL-C.
        """
        done = self.recvlineClient.expect(b"done")

        self._testwrite(b"cancelled line" + manhole.CTRL_C + b"done")

        def finished(ign):
            self._assertBuffer(
                [b">>> cancelled line", b"KeyboardInterrupt", b">>> done"]
            )

        return done.addCallback(finished)

    def test_interruptDuringContinuation(self):
        """
        Sending ^C to Manhole while in a state where more input is required to
        complete a statement should discard the entire ongoing statement and
        reset the input prompt to the non-continuation prompt.
        """
        continuing = self.recvlineClient.expect(b"things")

        self._testwrite(b"(\nthings")

        def gotContinuation(ignored):
            self._assertBuffer([b">>> (", b"... things"])
            interrupted = self.recvlineClient.expect(b">>> ")
            self._testwrite(manhole.CTRL_C)
            return interrupted

        continuing.addCallback(gotContinuation)

        def gotInterruption(ignored):
            self._assertBuffer([b">>> (", b"... things", b"KeyboardInterrupt", b">>> "])

        continuing.addCallback(gotInterruption)
        return continuing

    def test_ControlBackslash(self):
        r"""
        Evaluate cancelling with CTRL-\.
        """
        self._testwrite(b"cancelled line")
        partialLine = self.recvlineClient.expect(b"cancelled line")

        def gotPartialLine(ign):
            self._assertBuffer([b">>> cancelled line"])
            self._testwrite(manhole.CTRL_BACKSLASH)

            d = self.recvlineClient.onDisconnection
            return self.assertFailure(d, error.ConnectionDone)

        def gotClearedLine(ign):
            self._assertBuffer([b""])

        return partialLine.addCallback(gotPartialLine).addCallback(gotClearedLine)

    @defer.inlineCallbacks
    def test_controlD(self):
        """
        A CTRL+D in the middle of a line doesn't close a connection,
        but at the beginning of a line it does.
        """
        self._testwrite(b"1 + 1")
        yield self.recvlineClient.expect(br"\+ 1")
        self._assertBuffer([b">>> 1 + 1"])

        self._testwrite(manhole.CTRL_D + b" + 1")
        yield self.recvlineClient.expect(br"\+ 1")
        self._assertBuffer([b">>> 1 + 1 + 1"])

        self._testwrite(b"\n")
        yield self.recvlineClient.expect(b"3\n>>> ")

        self._testwrite(manhole.CTRL_D)
        d = self.recvlineClient.onDisconnection
        yield self.assertFailure(d, error.ConnectionDone)

    @defer.inlineCallbacks
    def test_ControlL(self):
        """
        CTRL+L is generally used as a redraw-screen command in terminal
        applications.  Manhole doesn't currently respect this usage of it,
        but it should at least do something reasonable in response to this
        event (rather than, say, eating your face).
        """
        # Start off with a newline so that when we clear the display we can
        # tell by looking for the missing first empty prompt line.
        self._testwrite(b"\n1 + 1")
        yield self.recvlineClient.expect(br"\+ 1")
        self._assertBuffer([b">>> ", b">>> 1 + 1"])

        self._testwrite(manhole.CTRL_L + b" + 1")
        yield self.recvlineClient.expect(br"1 \+ 1 \+ 1")
        self._assertBuffer([b">>> 1 + 1 + 1"])

    def test_controlA(self):
        """
        CTRL-A can be used as HOME - returning cursor to beginning of
        current line buffer.
        """
        self._testwrite(b'rint "hello"' + b"\x01" + b"p")
        d = self.recvlineClient.expect(b'print "hello"')

        def cb(ignore):
            self._assertBuffer([b'>>> print "hello"'])

        return d.addCallback(cb)

    def test_controlE(self):
        """
        CTRL-E can be used as END - setting cursor to end of current
        line buffer.
        """
        self._testwrite(b'rint "hello' + b"\x01" + b"p" + b"\x05" + b'"')
        d = self.recvlineClient.expect(b'print "hello"')

        def cb(ignore):
            self._assertBuffer([b'>>> print "hello"'])

        return d.addCallback(cb)

    @defer.inlineCallbacks
    def test_deferred(self):
        """
        When a deferred is returned to the manhole REPL, it is displayed with
        a sequence number, and when the deferred fires, the result is printed.
        """
        self._testwrite(
            b"from twisted.internet import defer, reactor\n"
            b"d = defer.Deferred()\n"
            b"d\n"
        )

        yield self.recvlineClient.expect(b"<Deferred #0>")

        self._testwrite(b"c = reactor.callLater(0.1, d.callback, 'Hi!')\n")
        yield self.recvlineClient.expect(b">>> ")

        yield self.recvlineClient.expect(b"Deferred #0 called back: 'Hi!'\n>>> ")
        self._assertBuffer(
            [
                b">>> from twisted.internet import defer, reactor",
                b">>> d = defer.Deferred()",
                b">>> d",
                b"<Deferred #0>",
                b">>> c = reactor.callLater(0.1, d.callback, 'Hi!')",
                b"Deferred #0 called back: 'Hi!'",
                b">>> ",
            ]
        )


class ManholeLoopbackTelnetTests(_TelnetMixin, unittest.TestCase, ManholeLoopbackMixin):
    """
    Test manhole loopback over Telnet.
    """

    pass


class ManholeLoopbackSSHTests(_SSHMixin, unittest.TestCase, ManholeLoopbackMixin):
    """
    Test manhole loopback over SSH.
    """

    if ssh is None:
        skip = "cryptography requirements missing"


class ManholeLoopbackStdioTests(_StdioMixin, unittest.TestCase, ManholeLoopbackMixin):
    """
    Test manhole loopback over standard IO.
    """

    if stdio is None:
        skip = "Terminal requirements missing"
    else:
        serverProtocol = stdio.ConsoleManhole


class ManholeMainTests(unittest.TestCase):
    """
    Test the I{main} method from the I{manhole} module.
    """

    if stdio is None:
        skip = "Terminal requirements missing"

    def test_mainClassNotFound(self):
        """
        Will raise an exception when called with an argument which is a
        dotted patch which can not be imported..
        """
        exception = self.assertRaises(
            ValueError,
            stdio.main,
            argv=["no-such-class"],
        )

        self.assertEqual("Empty module name", exception.args[0])
