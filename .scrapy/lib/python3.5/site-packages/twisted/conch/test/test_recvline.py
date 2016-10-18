# -*- test-case-name: twisted.conch.test.test_recvline -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.conch.recvline} and fixtures for testing related
functionality.
"""

import os
import sys

from twisted.conch.insults import insults
from twisted.conch import recvline

from twisted.python import reflect, components, filepath
from twisted.python.compat import iterbytes, bytesEnviron
from twisted.python.runtime import platform
from twisted.internet import defer, error
from twisted.trial import unittest
from twisted.cred import portal
from twisted.test.proto_helpers import StringTransport

if platform.isWindows():
    properEnv = dict(os.environ)
    properEnv["PYTHONPATH"] = os.pathsep.join(sys.path)
else:
    properEnv = bytesEnviron()
    properEnv[b"PYTHONPATH"] = os.pathsep.join(sys.path).encode(
        sys.getfilesystemencoding())


class ArrowsTests(unittest.TestCase):
    def setUp(self):
        self.underlyingTransport = StringTransport()
        self.pt = insults.ServerProtocol()
        self.p = recvline.HistoricRecvLine()
        self.pt.protocolFactory = lambda: self.p
        self.pt.factory = self
        self.pt.makeConnection(self.underlyingTransport)
        # self.p.makeConnection(self.pt)


    def test_printableCharacters(self):
        """
        When L{HistoricRecvLine} receives a printable character,
        it adds it to the current line buffer.
        """
        self.p.keystrokeReceived(b'x', None)
        self.p.keystrokeReceived(b'y', None)
        self.p.keystrokeReceived(b'z', None)

        self.assertEqual(self.p.currentLineBuffer(), (b'xyz', b''))


    def test_horizontalArrows(self):
        """
        When L{HistoricRecvLine} receives a LEFT_ARROW or
        RIGHT_ARROW keystroke it moves the cursor left or right
        in the current line buffer, respectively.
        """
        kR = lambda ch: self.p.keystrokeReceived(ch, None)
        for ch in iterbytes(b'xyz'):
            kR(ch)

        self.assertEqual(self.p.currentLineBuffer(), (b'xyz', b''))

        kR(self.pt.RIGHT_ARROW)
        self.assertEqual(self.p.currentLineBuffer(), (b'xyz', b''))

        kR(self.pt.LEFT_ARROW)
        self.assertEqual(self.p.currentLineBuffer(), (b'xy', b'z'))

        kR(self.pt.LEFT_ARROW)
        self.assertEqual(self.p.currentLineBuffer(), (b'x', b'yz'))

        kR(self.pt.LEFT_ARROW)
        self.assertEqual(self.p.currentLineBuffer(), (b'', b'xyz'))

        kR(self.pt.LEFT_ARROW)
        self.assertEqual(self.p.currentLineBuffer(), (b'', b'xyz'))

        kR(self.pt.RIGHT_ARROW)
        self.assertEqual(self.p.currentLineBuffer(), (b'x', b'yz'))

        kR(self.pt.RIGHT_ARROW)
        self.assertEqual(self.p.currentLineBuffer(), (b'xy', b'z'))

        kR(self.pt.RIGHT_ARROW)
        self.assertEqual(self.p.currentLineBuffer(), (b'xyz', b''))

        kR(self.pt.RIGHT_ARROW)
        self.assertEqual(self.p.currentLineBuffer(), (b'xyz', b''))


    def test_newline(self):
        """
        When {HistoricRecvLine} receives a newline, it adds the current
        line buffer to the end of its history buffer.
        """
        kR = lambda ch: self.p.keystrokeReceived(ch, None)

        for ch in iterbytes(b'xyz\nabc\n123\n'):
            kR(ch)

        self.assertEqual(self.p.currentHistoryBuffer(),
                          ((b'xyz', b'abc', b'123'), ()))

        kR(b'c')
        kR(b'b')
        kR(b'a')
        self.assertEqual(self.p.currentHistoryBuffer(),
                          ((b'xyz', b'abc', b'123'), ()))

        kR(b'\n')
        self.assertEqual(self.p.currentHistoryBuffer(),
                          ((b'xyz', b'abc', b'123', b'cba'), ()))


    def test_verticalArrows(self):
        """
        When L{HistoricRecvLine} receives UP_ARROW or DOWN_ARROW
        keystrokes it move the current index in the current history
        buffer up or down, and resets the current line buffer to the
        previous or next line in history, respectively for each.
        """
        kR = lambda ch: self.p.keystrokeReceived(ch, None)

        for ch in iterbytes(b'xyz\nabc\n123\n'):
            kR(ch)

        self.assertEqual(self.p.currentHistoryBuffer(),
                          ((b'xyz', b'abc', b'123'), ()))
        self.assertEqual(self.p.currentLineBuffer(), (b'', b''))

        kR(self.pt.UP_ARROW)
        self.assertEqual(self.p.currentHistoryBuffer(),
                          ((b'xyz', b'abc'), (b'123',)))
        self.assertEqual(self.p.currentLineBuffer(), (b'123', b''))

        kR(self.pt.UP_ARROW)
        self.assertEqual(self.p.currentHistoryBuffer(),
                          ((b'xyz',), (b'abc', b'123')))
        self.assertEqual(self.p.currentLineBuffer(), (b'abc', b''))

        kR(self.pt.UP_ARROW)
        self.assertEqual(self.p.currentHistoryBuffer(),
                          ((), (b'xyz', b'abc', b'123')))
        self.assertEqual(self.p.currentLineBuffer(), (b'xyz', b''))

        kR(self.pt.UP_ARROW)
        self.assertEqual(self.p.currentHistoryBuffer(),
                          ((), (b'xyz', b'abc', b'123')))
        self.assertEqual(self.p.currentLineBuffer(), (b'xyz', b''))

        for i in range(4):
            kR(self.pt.DOWN_ARROW)
        self.assertEqual(self.p.currentHistoryBuffer(),
                          ((b'xyz', b'abc', b'123'), ()))


    def test_home(self):
        """
        When L{HistoricRecvLine} receives a HOME keystroke it moves the
        cursor to the beginning of the current line buffer.
        """
        kR = lambda ch: self.p.keystrokeReceived(ch, None)

        for ch in iterbytes(b'hello, world'):
            kR(ch)
        self.assertEqual(self.p.currentLineBuffer(), (b'hello, world', b''))

        kR(self.pt.HOME)
        self.assertEqual(self.p.currentLineBuffer(), (b'', b'hello, world'))


    def test_end(self):
        """
        When L{HistoricRecvLine} receives an END keystroke it moves the cursor
        to the end of the current line buffer.
        """
        kR = lambda ch: self.p.keystrokeReceived(ch, None)

        for ch in iterbytes(b'hello, world'):
            kR(ch)
        self.assertEqual(self.p.currentLineBuffer(), (b'hello, world', b''))

        kR(self.pt.HOME)
        kR(self.pt.END)
        self.assertEqual(self.p.currentLineBuffer(), (b'hello, world', b''))


    def test_backspace(self):
        """
        When L{HistoricRecvLine} receives a BACKSPACE keystroke it deletes
        the character immediately before the cursor.
        """
        kR = lambda ch: self.p.keystrokeReceived(ch, None)

        for ch in iterbytes(b'xyz'):
            kR(ch)
        self.assertEqual(self.p.currentLineBuffer(), (b'xyz', b''))

        kR(self.pt.BACKSPACE)
        self.assertEqual(self.p.currentLineBuffer(), (b'xy', b''))

        kR(self.pt.LEFT_ARROW)
        kR(self.pt.BACKSPACE)
        self.assertEqual(self.p.currentLineBuffer(), (b'', b'y'))

        kR(self.pt.BACKSPACE)
        self.assertEqual(self.p.currentLineBuffer(), (b'', b'y'))


    def test_delete(self):
        """
        When L{HistoricRecvLine} receives a DELETE keystroke, it
        delets the character immediately after the cursor.
        """
        kR = lambda ch: self.p.keystrokeReceived(ch, None)

        for ch in iterbytes(b'xyz'):
            kR(ch)
        self.assertEqual(self.p.currentLineBuffer(), (b'xyz', b''))

        kR(self.pt.DELETE)
        self.assertEqual(self.p.currentLineBuffer(), (b'xyz', b''))

        kR(self.pt.LEFT_ARROW)
        kR(self.pt.DELETE)
        self.assertEqual(self.p.currentLineBuffer(), (b'xy', b''))

        kR(self.pt.LEFT_ARROW)
        kR(self.pt.DELETE)
        self.assertEqual(self.p.currentLineBuffer(), (b'x', b''))

        kR(self.pt.LEFT_ARROW)
        kR(self.pt.DELETE)
        self.assertEqual(self.p.currentLineBuffer(), (b'', b''))

        kR(self.pt.DELETE)
        self.assertEqual(self.p.currentLineBuffer(), (b'', b''))


    def test_insert(self):
        """
        When not in INSERT mode, L{HistoricRecvLine} inserts the typed
        character at the cursor before the next character.
        """
        kR = lambda ch: self.p.keystrokeReceived(ch, None)

        for ch in iterbytes(b'xyz'):
            kR(ch)

        kR(self.pt.LEFT_ARROW)
        kR(b'A')
        self.assertEqual(self.p.currentLineBuffer(), (b'xyA', b'z'))

        kR(self.pt.LEFT_ARROW)
        kR(b'B')
        self.assertEqual(self.p.currentLineBuffer(), (b'xyB', b'Az'))


    def test_typeover(self):
        """
        When in INSERT mode and upon receiving a keystroke with a printable
        character, L{HistoricRecvLine} replaces the character at
        the cursor with the typed character rather than inserting before.
        Ah, the ironies of INSERT mode.
        """
        kR = lambda ch: self.p.keystrokeReceived(ch, None)

        for ch in iterbytes(b'xyz'):
            kR(ch)

        kR(self.pt.INSERT)

        kR(self.pt.LEFT_ARROW)
        kR(b'A')
        self.assertEqual(self.p.currentLineBuffer(), (b'xyA', b''))

        kR(self.pt.LEFT_ARROW)
        kR(b'B')
        self.assertEqual(self.p.currentLineBuffer(), (b'xyB', b''))


    def test_unprintableCharacters(self):
        """
        When L{HistoricRecvLine} receives a keystroke for an unprintable
        function key with no assigned behavior, the line buffer is unmodified.
        """
        kR = lambda ch: self.p.keystrokeReceived(ch, None)
        pt = self.pt

        for ch in (pt.F1, pt.F2, pt.F3, pt.F4, pt.F5, pt.F6, pt.F7, pt.F8,
                   pt.F9, pt.F10, pt.F11, pt.F12, pt.PGUP, pt.PGDN):
            kR(ch)
            self.assertEqual(self.p.currentLineBuffer(), (b'', b''))



from twisted.conch import telnet
from twisted.conch.insults import helper
from twisted.conch.test.loopback import LoopbackRelay

class EchoServer(recvline.HistoricRecvLine):
    def lineReceived(self, line):
        self.terminal.write(line + b'\n' + self.ps[self.pn])

# An insults API for this would be nice.
left = b"\x1b[D"
right = b"\x1b[C"
up = b"\x1b[A"
down = b"\x1b[B"
insert = b"\x1b[2~"
home = b"\x1b[1~"
delete = b"\x1b[3~"
end = b"\x1b[4~"
backspace = b"\x7f"

from twisted.cred import checkers

try:
    from twisted.conch.ssh import (userauth, transport, channel, connection,
                                   session, keys)
    from twisted.conch.manhole_ssh import TerminalUser, TerminalSession, TerminalRealm, TerminalSessionTransport, ConchFactory
except ImportError:
    ssh = False
else:
    ssh = True
    class SessionChannel(channel.SSHChannel):
        name = b'session'

        def __init__(self, protocolFactory, protocolArgs, protocolKwArgs, width, height, *a, **kw):
            channel.SSHChannel.__init__(self, *a, **kw)

            self.protocolFactory = protocolFactory
            self.protocolArgs = protocolArgs
            self.protocolKwArgs = protocolKwArgs

            self.width = width
            self.height = height


        def channelOpen(self, data):
            term = session.packRequest_pty_req(b"vt102", (self.height, self.width, 0, 0), b'')
            self.conn.sendRequest(self, b'pty-req', term)
            self.conn.sendRequest(self, b'shell', b'')

            self._protocolInstance = self.protocolFactory(*self.protocolArgs, **self.protocolKwArgs)
            self._protocolInstance.factory = self
            self._protocolInstance.makeConnection(self)


        def closed(self):
            self._protocolInstance.connectionLost(error.ConnectionDone())


        def dataReceived(self, data):
            self._protocolInstance.dataReceived(data)


    class TestConnection(connection.SSHConnection):
        def __init__(self, protocolFactory, protocolArgs, protocolKwArgs, width, height, *a, **kw):
            connection.SSHConnection.__init__(self, *a, **kw)

            self.protocolFactory = protocolFactory
            self.protocolArgs = protocolArgs
            self.protocolKwArgs = protocolKwArgs

            self.width = width
            self.height = height


        def serviceStarted(self):
            self.__channel = SessionChannel(self.protocolFactory, self.protocolArgs, self.protocolKwArgs, self.width, self.height)
            self.openChannel(self.__channel)


        def write(self, data):
            return self.__channel.write(data)


    class TestAuth(userauth.SSHUserAuthClient):
        def __init__(self, username, password, *a, **kw):
            userauth.SSHUserAuthClient.__init__(self, username, *a, **kw)
            self.password = password


        def getPassword(self):
            return defer.succeed(self.password)


    class TestTransport(transport.SSHClientTransport):
        def __init__(self, protocolFactory, protocolArgs, protocolKwArgs, username, password, width, height, *a, **kw):
            # transport.SSHClientTransport.__init__(self, *a, **kw)
            self.protocolFactory = protocolFactory
            self.protocolArgs = protocolArgs
            self.protocolKwArgs = protocolKwArgs
            self.username = username
            self.password = password
            self.width = width
            self.height = height


        def verifyHostKey(self, hostKey, fingerprint):
            return defer.succeed(True)


        def connectionSecure(self):
            self.__connection = TestConnection(self.protocolFactory, self.protocolArgs, self.protocolKwArgs, self.width, self.height)
            self.requestService(
                TestAuth(self.username, self.password, self.__connection))


        def write(self, data):
            return self.__connection.write(data)


    class TestSessionTransport(TerminalSessionTransport):
        def protocolFactory(self):
            return self.avatar.conn.transport.factory.serverProtocol()


    class TestSession(TerminalSession):
        transportFactory = TestSessionTransport


    class TestUser(TerminalUser):
        pass

    components.registerAdapter(TestSession, TestUser, session.ISession)


class NotifyingExpectableBuffer(helper.ExpectableBuffer):
    def __init__(self):
        self.onConnection = defer.Deferred()
        self.onDisconnection = defer.Deferred()


    def connectionMade(self):
        helper.ExpectableBuffer.connectionMade(self)
        self.onConnection.callback(self)


    def connectionLost(self, reason):
        self.onDisconnection.errback(reason)



class _BaseMixin:
    WIDTH = 80
    HEIGHT = 24

    def _assertBuffer(self, lines):
        receivedLines = self.recvlineClient.__bytes__().splitlines()
        expectedLines = lines + ([b''] * (self.HEIGHT - len(lines) - 1))
        self.assertEqual(len(receivedLines), len(expectedLines))
        for i in range(len(receivedLines)):
            self.assertEqual(
                receivedLines[i], expectedLines[i],
                b"".join(receivedLines[max(0, i-1):i+1]) +
                b" != " +
                b"".join(expectedLines[max(0, i-1):i+1]))


    def _trivialTest(self, inputLine, output):
        done = self.recvlineClient.expect(b"done")

        self._testwrite(inputLine)

        def finished(ign):
            self._assertBuffer(output)

        return done.addCallback(finished)



class _SSHMixin(_BaseMixin):
    def setUp(self):
        if not ssh:
            raise unittest.SkipTest(
                "cryptography requirements missing, can't run historic "
                "recvline tests over ssh")

        u, p = b'testuser', b'testpass'
        rlm = TerminalRealm()
        rlm.userFactory = TestUser
        rlm.chainedProtocolFactory = lambda: insultsServer

        checker = checkers.InMemoryUsernamePasswordDatabaseDontUse()
        checker.addUser(u, p)
        ptl = portal.Portal(rlm)
        ptl.registerChecker(checker)
        sshFactory = ConchFactory(ptl)

        sshKey = keys._getPersistentRSAKey(filepath.FilePath(self.mktemp()),
                                           keySize=512)
        sshFactory.publicKeys[b"ssh-rsa"] = sshKey
        sshFactory.privateKeys[b"ssh-rsa"] = sshKey

        sshFactory.serverProtocol = self.serverProtocol
        sshFactory.startFactory()

        recvlineServer = self.serverProtocol()
        insultsServer = insults.ServerProtocol(lambda: recvlineServer)
        sshServer = sshFactory.buildProtocol(None)
        clientTransport = LoopbackRelay(sshServer)

        recvlineClient = NotifyingExpectableBuffer()
        insultsClient = insults.ClientProtocol(lambda: recvlineClient)
        sshClient = TestTransport(lambda: insultsClient, (), {}, u, p, self.WIDTH, self.HEIGHT)
        serverTransport = LoopbackRelay(sshClient)

        sshClient.makeConnection(clientTransport)
        sshServer.makeConnection(serverTransport)

        self.recvlineClient = recvlineClient
        self.sshClient = sshClient
        self.sshServer = sshServer
        self.clientTransport = clientTransport
        self.serverTransport = serverTransport

        return recvlineClient.onConnection


    def _testwrite(self, data):
        self.sshClient.write(data)



from twisted.conch.test import test_telnet

class TestInsultsClientProtocol(insults.ClientProtocol,
                                test_telnet.TestProtocol):
    pass



class TestInsultsServerProtocol(insults.ServerProtocol,
                                test_telnet.TestProtocol):
    pass



class _TelnetMixin(_BaseMixin):
    def setUp(self):
        recvlineServer = self.serverProtocol()
        insultsServer = TestInsultsServerProtocol(lambda: recvlineServer)
        telnetServer = telnet.TelnetTransport(lambda: insultsServer)
        clientTransport = LoopbackRelay(telnetServer)

        recvlineClient = NotifyingExpectableBuffer()
        insultsClient = TestInsultsClientProtocol(lambda: recvlineClient)
        telnetClient = telnet.TelnetTransport(lambda: insultsClient)
        serverTransport = LoopbackRelay(telnetClient)

        telnetClient.makeConnection(clientTransport)
        telnetServer.makeConnection(serverTransport)

        serverTransport.clearBuffer()
        clientTransport.clearBuffer()

        self.recvlineClient = recvlineClient
        self.telnetClient = telnetClient
        self.clientTransport = clientTransport
        self.serverTransport = serverTransport

        return recvlineClient.onConnection


    def _testwrite(self, data):
        self.telnetClient.write(data)

try:
    from twisted.conch import stdio
except ImportError:
    stdio = None



class _StdioMixin(_BaseMixin):
    def setUp(self):
        # A memory-only terminal emulator, into which the server will
        # write things and make other state changes.  What ends up
        # here is basically what a user would have seen on their
        # screen.
        testTerminal = NotifyingExpectableBuffer()

        # An insults client protocol which will translate bytes
        # received from the child process into keystroke commands for
        # an ITerminalProtocol.
        insultsClient = insults.ClientProtocol(lambda: testTerminal)

        # A process protocol which will translate stdout and stderr
        # received from the child process to dataReceived calls and
        # error reporting on an insults client protocol.
        processClient = stdio.TerminalProcessProtocol(insultsClient)

        # Run twisted/conch/stdio.py with the name of a class
        # implementing ITerminalProtocol.  This class will be used to
        # handle bytes we send to the child process.
        exe = sys.executable
        module = stdio.__file__
        if module.endswith('.pyc') or module.endswith('.pyo'):
            module = module[:-1]
        args = [exe, module, reflect.qual(self.serverProtocol)]
        if not platform.isWindows():
            args = [arg.encode(sys.getfilesystemencoding()) for arg in args]

        from twisted.internet import reactor
        clientTransport = reactor.spawnProcess(processClient, exe, args,
                                               env=properEnv, usePTY=True)

        self.recvlineClient = self.testTerminal = testTerminal
        self.processClient = processClient
        self.clientTransport = clientTransport

        # Wait for the process protocol and test terminal to become
        # connected before proceeding.  The former should always
        # happen first, but it doesn't hurt to be safe.
        return defer.gatherResults(filter(None, [
            processClient.onConnection,
            testTerminal.expect(b">>> ")]))


    def tearDown(self):
        # Kill the child process.  We're done with it.
        try:
            self.clientTransport.signalProcess("KILL")
        except (error.ProcessExitedAlready, OSError):
            pass
        def trap(failure):
            failure.trap(error.ProcessTerminated)
            self.assertIsNone(failure.value.exitCode)
            self.assertEqual(failure.value.status, 9)
        return self.testTerminal.onDisconnection.addErrback(trap)


    def _testwrite(self, data):
        self.clientTransport.write(data)



class RecvlineLoopbackMixin:
    serverProtocol = EchoServer

    def testSimple(self):
        return self._trivialTest(
            b"first line\ndone",
            [b">>> first line",
             b"first line",
             b">>> done"])


    def testLeftArrow(self):
        return self._trivialTest(
            insert + b'first line' + left * 4 + b"xxxx\ndone",
            [b">>> first xxxx",
             b"first xxxx",
             b">>> done"])


    def testRightArrow(self):
        return self._trivialTest(
            insert + b'right line' + left * 4 + right * 2 + b"xx\ndone",
            [b">>> right lixx",
             b"right lixx",
            b">>> done"])


    def testBackspace(self):
        return self._trivialTest(
            b"second line" + backspace * 4 + b"xxxx\ndone",
            [b">>> second xxxx",
             b"second xxxx",
             b">>> done"])


    def testDelete(self):
        return self._trivialTest(
            b"delete xxxx" + left * 4 + delete * 4 + b"line\ndone",
            [b">>> delete line",
             b"delete line",
             b">>> done"])


    def testInsert(self):
        return self._trivialTest(
            b"third ine" + left * 3 + b"l\ndone",
            [b">>> third line",
             b"third line",
             b">>> done"])


    def testTypeover(self):
        return self._trivialTest(
            b"fourth xine" + left * 4 + insert + b"l\ndone",
            [b">>> fourth line",
             b"fourth line",
             b">>> done"])


    def testHome(self):
        return self._trivialTest(
            insert + b"blah line" + home + b"home\ndone",
            [b">>> home line",
             b"home line",
             b">>> done"])


    def testEnd(self):
        return self._trivialTest(
            b"end " + left * 4 + end + b"line\ndone",
            [b">>> end line",
             b"end line",
             b">>> done"])



class RecvlineLoopbackTelnetTests(_TelnetMixin, unittest.TestCase, RecvlineLoopbackMixin):
    pass



class RecvlineLoopbackSSHTests(_SSHMixin, unittest.TestCase, RecvlineLoopbackMixin):
    pass



class RecvlineLoopbackStdioTests(_StdioMixin, unittest.TestCase, RecvlineLoopbackMixin):
    if stdio is None:
        skip = "Terminal requirements missing, can't run recvline tests over stdio"



class HistoricRecvlineLoopbackMixin:
    serverProtocol = EchoServer

    def testUpArrow(self):
        return self._trivialTest(
            b"first line\n" + up + b"\ndone",
            [b">>> first line",
             b"first line",
             b">>> first line",
             b"first line",
             b">>> done"])


    def testDownArrow(self):
        return self._trivialTest(
            b"first line\nsecond line\n" + up * 2 + down + b"\ndone",
            [b">>> first line",
             b"first line",
             b">>> second line",
             b"second line",
             b">>> second line",
             b"second line",
             b">>> done"])



class HistoricRecvlineLoopbackTelnetTests(_TelnetMixin, unittest.TestCase, HistoricRecvlineLoopbackMixin):
    pass



class HistoricRecvlineLoopbackSSHTests(_SSHMixin, unittest.TestCase, HistoricRecvlineLoopbackMixin):
    pass



class HistoricRecvlineLoopbackStdioTests(_StdioMixin, unittest.TestCase, HistoricRecvlineLoopbackMixin):
    if stdio is None:
        skip = "Terminal requirements missing, can't run historic recvline tests over stdio"
