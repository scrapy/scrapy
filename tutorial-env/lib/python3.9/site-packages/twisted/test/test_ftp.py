# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
FTP tests.
"""

import errno
import getpass
import os
import random
import string
from io import BytesIO

from zope.interface import implementer
from zope.interface.verify import verifyClass

from twisted.cred import checkers, credentials, portal
from twisted.cred.error import UnauthorizedLogin
from twisted.cred.portal import IRealm
from twisted.internet import defer, error, protocol, reactor, task
from twisted.internet.interfaces import IConsumer
from twisted.protocols import basic, ftp, loopback
from twisted.python import failure, filepath, runtime
from twisted.test import proto_helpers
from twisted.trial.unittest import TestCase

if not runtime.platform.isWindows():
    nonPOSIXSkip = None
else:
    nonPOSIXSkip = "Cannot run on Windows"


class Dummy(basic.LineReceiver):
    logname = None

    def __init__(self):
        self.lines = []
        self.rawData = []

    def connectionMade(self):
        self.f = self.factory  # to save typing in pdb :-)

    def lineReceived(self, line):
        self.lines.append(line)

    def rawDataReceived(self, data):
        self.rawData.append(data)

    def lineLengthExceeded(self, line):
        pass


class _BufferingProtocol(protocol.Protocol):
    def connectionMade(self):
        self.buffer = b""
        self.d = defer.Deferred()

    def dataReceived(self, data):
        self.buffer += data

    def connectionLost(self, reason):
        self.d.callback(self)


def passivemode_msg(protocol, host="127.0.0.1", port=12345):
    """
    Construct a passive mode message with the correct encoding

    @param protocol: the FTP protocol from which to base the encoding
    @param host: the hostname
    @param port: the port
    @return: the passive mode message
    """
    msg = f"227 Entering Passive Mode ({ftp.encodeHostPort(host, port)})."
    return msg.encode(protocol._encoding)


class FTPServerTestCase(TestCase):
    """
    Simple tests for an FTP server with the default settings.

    @ivar clientFactory: class used as ftp client.
    """

    clientFactory = ftp.FTPClientBasic
    userAnonymous = "anonymous"

    def setUp(self):
        # Keep a list of the protocols created so we can make sure they all
        # disconnect before the tests end.
        protocols = []

        # Create a directory
        self.directory = self.mktemp()
        os.mkdir(self.directory)
        self.dirPath = filepath.FilePath(self.directory)

        # Start the server
        p = portal.Portal(
            ftp.FTPRealm(
                anonymousRoot=self.directory,
                userHome=self.directory,
            )
        )
        p.registerChecker(checkers.AllowAnonymousAccess(), credentials.IAnonymous)

        users_checker = checkers.InMemoryUsernamePasswordDatabaseDontUse()
        self.username = "test-user"
        self.password = "test-password"
        users_checker.addUser(self.username, self.password)
        p.registerChecker(users_checker, credentials.IUsernamePassword)

        self.factory = ftp.FTPFactory(portal=p, userAnonymous=self.userAnonymous)
        self.port = port = reactor.listenTCP(0, self.factory, interface="127.0.0.1")
        self.addCleanup(port.stopListening)

        # Hook the server's buildProtocol to make the protocol instance
        # accessible to tests.
        buildProtocol = self.factory.buildProtocol
        d1 = defer.Deferred()

        def _rememberProtocolInstance(addr):
            # Done hooking this.
            del self.factory.buildProtocol

            protocol = buildProtocol(addr)
            self.serverProtocol = protocol.wrappedProtocol

            def cleanupServer():
                if self.serverProtocol.transport is not None:
                    self.serverProtocol.transport.loseConnection()

            self.addCleanup(cleanupServer)
            d1.callback(None)
            protocols.append(protocol)
            return protocol

        self.factory.buildProtocol = _rememberProtocolInstance

        # Connect a client to it
        portNum = port.getHost().port
        clientCreator = protocol.ClientCreator(reactor, self.clientFactory)
        d2 = clientCreator.connectTCP("127.0.0.1", portNum)

        def gotClient(client):
            self.client = client
            self.addCleanup(self.client.transport.loseConnection)
            protocols.append(self.client)

        d2.addCallback(gotClient)

        self.addCleanup(proto_helpers.waitUntilAllDisconnected, reactor, protocols)
        return defer.gatherResults([d1, d2])

    def assertCommandResponse(self, command, expectedResponseLines, chainDeferred=None):
        """
        Asserts that a sending an FTP command receives the expected
        response.

        Returns a Deferred.  Optionally accepts a deferred to chain its actions
        to.
        """
        if chainDeferred is None:
            chainDeferred = defer.succeed(None)

        def queueCommand(ignored):
            d = self.client.queueStringCommand(command)

            def gotResponse(responseLines):
                self.assertEqual(expectedResponseLines, responseLines)

            return d.addCallback(gotResponse)

        return chainDeferred.addCallback(queueCommand)

    def assertCommandFailed(self, command, expectedResponse=None, chainDeferred=None):
        if chainDeferred is None:
            chainDeferred = defer.succeed(None)

        def queueCommand(ignored):
            return self.client.queueStringCommand(command)

        chainDeferred.addCallback(queueCommand)
        self.assertFailure(chainDeferred, ftp.CommandFailed)

        def failed(exception):
            if expectedResponse is not None:
                self.assertEqual(expectedResponse, exception.args[0])

        return chainDeferred.addCallback(failed)

    def _anonymousLogin(self):
        d = self.assertCommandResponse(
            "USER anonymous",
            ["331 Guest login ok, type your email address as password."],
        )
        return self.assertCommandResponse(
            "PASS test@twistedmatrix.com",
            ["230 Anonymous login ok, access restrictions apply."],
            chainDeferred=d,
        )

    def _userLogin(self):
        """
        Authenticates the FTP client using the test account.

        @return: L{Deferred} of command response
        """
        d = self.assertCommandResponse(
            "USER %s" % (self.username),
            ["331 Password required for %s." % (self.username)],
        )
        return self.assertCommandResponse(
            "PASS %s" % (self.password),
            ["230 User logged in, proceed"],
            chainDeferred=d,
        )


class FTPAnonymousTests(FTPServerTestCase):
    """
    Simple tests for an FTP server with different anonymous username.
    The new anonymous username used in this test case is "guest"
    """

    userAnonymous = "guest"

    def test_anonymousLogin(self):
        """
        Tests whether the changing of the anonymous username is working or not.
        The FTP server should not comply about the need of password for the
        username 'guest', letting it login as anonymous asking just an email
        address as password.
        """
        d = self.assertCommandResponse(
            "USER guest", ["331 Guest login ok, type your email address as password."]
        )
        return self.assertCommandResponse(
            "PASS test@twistedmatrix.com",
            ["230 Anonymous login ok, access restrictions apply."],
            chainDeferred=d,
        )


class BasicFTPServerTests(FTPServerTestCase):
    """
    Basic functionality of FTP server.
    """

    def test_tooManyConnections(self):
        """
        When the connection limit is reached, the server should send an
        appropriate response
        """
        self.factory.connectionLimit = 1
        cc = protocol.ClientCreator(reactor, _BufferingProtocol)
        d = cc.connectTCP("127.0.0.1", self.port.getHost().port)

        @d.addCallback
        def gotClient(proto):
            return proto.d

        @d.addCallback
        def onConnectionLost(proto):
            self.assertEqual(
                b"421 Too many users right now, try again in a few minutes." b"\r\n",
                proto.buffer,
            )

        return d

    def test_NotLoggedInReply(self):
        """
        When not logged in, most commands other than USER and PASS should
        get NOT_LOGGED_IN errors, but some can be called before USER and PASS.
        """
        loginRequiredCommandList = [
            "CDUP",
            "CWD",
            "LIST",
            "MODE",
            "PASV",
            "PWD",
            "RETR",
            "STRU",
            "SYST",
            "TYPE",
        ]
        loginNotRequiredCommandList = ["FEAT"]

        # Issue commands, check responses
        def checkFailResponse(exception, command):
            failureResponseLines = exception.args[0]
            self.assertTrue(
                failureResponseLines[-1].startswith("530"),
                "%s - Response didn't start with 530: %r"
                % (
                    command,
                    failureResponseLines[-1],
                ),
            )

        def checkPassResponse(result, command):
            result = result[0]
            self.assertFalse(
                result.startswith("530"),
                "%s - Response start with 530: %r"
                % (
                    command,
                    result,
                ),
            )

        deferreds = []
        for command in loginRequiredCommandList:
            deferred = self.client.queueStringCommand(command)
            self.assertFailure(deferred, ftp.CommandFailed)
            deferred.addCallback(checkFailResponse, command)
            deferreds.append(deferred)

        for command in loginNotRequiredCommandList:
            deferred = self.client.queueStringCommand(command)
            deferred.addCallback(checkPassResponse, command)
            deferreds.append(deferred)

        return defer.DeferredList(deferreds, fireOnOneErrback=True)

    def test_PASSBeforeUSER(self):
        """
        Issuing PASS before USER should give an error.
        """
        return self.assertCommandFailed(
            "PASS foo",
            ["503 Incorrect sequence of commands: " "USER required before PASS"],
        )

    def test_NoParamsForUSER(self):
        """
        Issuing USER without a username is a syntax error.
        """
        return self.assertCommandFailed(
            "USER", ["500 Syntax error: USER requires an argument."]
        )

    def test_NoParamsForPASS(self):
        """
        Issuing PASS without a password is a syntax error.
        """
        d = self.client.queueStringCommand("USER foo")
        return self.assertCommandFailed(
            "PASS", ["500 Syntax error: PASS requires an argument."], chainDeferred=d
        )

    def test_loginError(self):
        """
        Unexpected exceptions from the login handler are caught
        """

        def _fake_loginhandler(*args, **kwargs):
            return defer.fail(AssertionError("test exception"))

        self.serverProtocol.portal.login = _fake_loginhandler
        d = self.client.queueStringCommand("USER foo")
        self.assertCommandFailed(
            "PASS bar",
            ["550 Requested action not taken: internal server error"],
            chainDeferred=d,
        )

        @d.addCallback
        def checkLogs(result):
            logs = self.flushLoggedErrors()
            self.assertEqual(1, len(logs))
            self.assertIsInstance(logs[0].value, AssertionError)

        return d

    def test_AnonymousLogin(self):
        """
        Login with userid 'anonymous'
        """
        return self._anonymousLogin()

    def test_Quit(self):
        """
        Issuing QUIT should return a 221 message.

        @return: L{Deferred} of command response
        """
        d = self._anonymousLogin()
        return self.assertCommandResponse("QUIT", ["221 Goodbye."], chainDeferred=d)

    def test_AnonymousLoginDenied(self):
        """
        Reconfigure the server to disallow anonymous access, and to have an
        IUsernamePassword checker that always rejects.

        @return: L{Deferred} of command response
        """
        self.factory.allowAnonymous = False
        denyAlwaysChecker = checkers.InMemoryUsernamePasswordDatabaseDontUse()
        self.factory.portal.registerChecker(
            denyAlwaysChecker, credentials.IUsernamePassword
        )

        # Same response code as allowAnonymous=True, but different text.
        d = self.assertCommandResponse(
            "USER anonymous", ["331 Password required for anonymous."]
        )

        # It will be denied.  No-one can login.
        d = self.assertCommandFailed(
            "PASS test@twistedmatrix.com",
            ["530 Sorry, Authentication failed."],
            chainDeferred=d,
        )

        # It's not just saying that.  You aren't logged in.
        d = self.assertCommandFailed(
            "PWD", ["530 Please login with USER and PASS."], chainDeferred=d
        )
        return d

    def test_anonymousWriteDenied(self):
        """
        When an anonymous user attempts to edit the server-side filesystem, they
        will receive a 550 error with a descriptive message.

        @return: L{Deferred} of command response
        """
        d = self._anonymousLogin()
        return self.assertCommandFailed(
            "MKD newdir",
            ["550 Anonymous users are forbidden to change the filesystem"],
            chainDeferred=d,
        )

    def test_UnknownCommand(self):
        """
        Send an invalid command.

        @return: L{Deferred} of command response
        """
        d = self._anonymousLogin()
        return self.assertCommandFailed(
            "GIBBERISH", ["502 Command 'GIBBERISH' not implemented"], chainDeferred=d
        )

    def test_RETRBeforePORT(self):
        """
        Send RETR before sending PORT.

        @return: L{Deferred} of command response
        """
        d = self._anonymousLogin()
        return self.assertCommandFailed(
            "RETR foo",
            [
                "503 Incorrect sequence of commands: "
                "PORT or PASV required before RETR"
            ],
            chainDeferred=d,
        )

    def test_STORBeforePORT(self):
        """
        Send STOR before sending PORT.

        @return: L{Deferred} of command response
        """
        d = self._anonymousLogin()
        return self.assertCommandFailed(
            "STOR foo",
            [
                "503 Incorrect sequence of commands: "
                "PORT or PASV required before STOR"
            ],
            chainDeferred=d,
        )

    def test_BadCommandArgs(self):
        """
        Send command with bad arguments.

        @return: L{Deferred} of command response
        """
        d = self._anonymousLogin()
        self.assertCommandFailed(
            "MODE z", ["504 Not implemented for parameter 'z'."], chainDeferred=d
        )
        self.assertCommandFailed(
            "STRU I", ["504 Not implemented for parameter 'I'."], chainDeferred=d
        )
        return d

    def test_DecodeHostPort(self):
        """
        Decode a host port.
        """
        self.assertEqual(
            ftp.decodeHostPort("25,234,129,22,100,23"), ("25.234.129.22", 25623)
        )
        nums = range(6)
        for i in range(6):
            badValue = list(nums)
            badValue[i] = 256
            s = ",".join(map(str, badValue))
            self.assertRaises(ValueError, ftp.decodeHostPort, s)

    def test_PASV(self):
        """
        When the client sends the command C{PASV}, the server responds with a
        host and port, and is listening on that port.
        """
        # Login
        d = self._anonymousLogin()
        # Issue a PASV command
        d.addCallback(lambda _: self.client.queueStringCommand("PASV"))

        def cb(responseLines):
            """
            Extract the host and port from the resonse, and
            verify the server is listening of the port it claims to be.
            """
            host, port = ftp.decodeHostPort(responseLines[-1][4:])
            self.assertEqual(port, self.serverProtocol.dtpPort.getHost().port)

        d.addCallback(cb)
        # Semi-reasonable way to force cleanup
        d.addCallback(lambda _: self.serverProtocol.transport.loseConnection())
        return d

    def test_SYST(self):
        """
        SYST command will always return UNIX Type: L8
        """
        d = self._anonymousLogin()
        self.assertCommandResponse("SYST", ["215 UNIX Type: L8"], chainDeferred=d)
        return d

    def test_RNFRandRNTO(self):
        """
        Sending the RNFR command followed by RNTO, with valid filenames, will
        perform a successful rename operation.
        """
        # Create user home folder with a 'foo' file.
        self.dirPath.child(self.username).createDirectory()
        self.dirPath.child(self.username).child("foo").touch()

        d = self._userLogin()
        self.assertCommandResponse(
            "RNFR foo",
            ["350 Requested file action pending further information."],
            chainDeferred=d,
        )
        self.assertCommandResponse(
            "RNTO bar", ["250 Requested File Action Completed OK"], chainDeferred=d
        )

        def check_rename(result):
            self.assertTrue(self.dirPath.child(self.username).child("bar").exists())
            return result

        d.addCallback(check_rename)
        return d

    def test_RNFRwithoutRNTO(self):
        """
        Sending the RNFR command followed by any command other than RNTO
        should return an error informing users that RNFR should be followed
        by RNTO.
        """
        d = self._anonymousLogin()
        self.assertCommandResponse(
            "RNFR foo",
            ["350 Requested file action pending further information."],
            chainDeferred=d,
        )
        self.assertCommandFailed(
            "OTHER don-tcare",
            ["503 Incorrect sequence of commands: RNTO required after RNFR"],
            chainDeferred=d,
        )
        return d

    def test_portRangeForwardError(self):
        """
        Exceptions other than L{error.CannotListenError} which are raised by
        C{listenFactory} should be raised to the caller of L{FTP.getDTPPort}.
        """

        def listenFactory(portNumber, factory):
            raise RuntimeError()

        self.serverProtocol.listenFactory = listenFactory

        self.assertRaises(
            RuntimeError, self.serverProtocol.getDTPPort, protocol.Factory()
        )

    def test_portRange(self):
        """
        L{FTP.passivePortRange} should determine the ports which
        L{FTP.getDTPPort} attempts to bind. If no port from that iterator can
        be bound, L{error.CannotListenError} should be raised, otherwise the
        first successful result from L{FTP.listenFactory} should be returned.
        """

        def listenFactory(portNumber, factory):
            if portNumber in (22032, 22033, 22034):
                raise error.CannotListenError("localhost", portNumber, "error")
            return portNumber

        self.serverProtocol.listenFactory = listenFactory

        port = self.serverProtocol.getDTPPort(protocol.Factory())
        self.assertEqual(port, 0)

        self.serverProtocol.passivePortRange = range(22032, 65536)
        port = self.serverProtocol.getDTPPort(protocol.Factory())
        self.assertEqual(port, 22035)

        self.serverProtocol.passivePortRange = range(22032, 22035)
        self.assertRaises(
            error.CannotListenError, self.serverProtocol.getDTPPort, protocol.Factory()
        )

    def test_portRangeInheritedFromFactory(self):
        """
        The L{FTP} instances created by L{ftp.FTPFactory.buildProtocol} have
        their C{passivePortRange} attribute set to the same object the
        factory's C{passivePortRange} attribute is set to.
        """
        portRange = range(2017, 2031)
        self.factory.passivePortRange = portRange
        protocol = self.factory.buildProtocol(None)
        self.assertEqual(portRange, protocol.wrappedProtocol.passivePortRange)

    def test_FEAT(self):
        """
        When the server receives 'FEAT', it should report the list of supported
        features. (Additionally, ensure that the server reports various
        particular features that are supported by all Twisted FTP servers.)
        """
        d = self.client.queueStringCommand("FEAT")

        def gotResponse(responseLines):
            self.assertEqual("211-Features:", responseLines[0])
            self.assertIn(" MDTM", responseLines)
            self.assertIn(" PASV", responseLines)
            self.assertIn(" TYPE A;I", responseLines)
            self.assertIn(" SIZE", responseLines)
            self.assertEqual("211 End", responseLines[-1])

        return d.addCallback(gotResponse)

    def test_OPTS(self):
        """
        When the server receives 'OPTS something', it should report
        that the FTP server does not support the option called 'something'.
        """
        d = self._anonymousLogin()
        self.assertCommandFailed(
            "OPTS something",
            ["502 Option 'something' not implemented."],
            chainDeferred=d,
        )
        return d

    def test_STORreturnsErrorFromOpen(self):
        """
        Any FTP error raised inside STOR while opening the file is returned
        to the client.
        """
        # We create a folder inside user's home folder and then
        # we try to write a file with the same name.
        # This will trigger an FTPCmdError.
        self.dirPath.child(self.username).createDirectory()
        self.dirPath.child(self.username).child("folder").createDirectory()
        d = self._userLogin()

        def sendPASV(result):
            """
            Send the PASV command required before port.
            """
            return self.client.queueStringCommand("PASV")

        def mockDTPInstance(result):
            """
            Fake an incoming connection and create a mock DTPInstance so
            that PORT command will start processing the request.
            """
            self.serverProtocol.dtpFactory.deferred.callback(None)
            self.serverProtocol.dtpInstance = object()
            return result

        d.addCallback(sendPASV)
        d.addCallback(mockDTPInstance)
        self.assertCommandFailed(
            "STOR folder",
            ["550 folder: is a directory"],
            chainDeferred=d,
        )
        return d

    def test_STORunknownErrorBecomesFileNotFound(self):
        """
        Any non FTP error raised inside STOR while opening the file is
        converted into FileNotFound error and returned to the client together
        with the path.

        The unknown error is logged.
        """
        d = self._userLogin()

        def failingOpenForWriting(ignore):
            """
            Override openForWriting.

            @param ignore: ignored, used for callback
            @return: an error
            """
            return defer.fail(AssertionError())

        def sendPASV(result):
            """
            Send the PASV command required before port.

            @param result: parameter used in L{Deferred}
            """
            return self.client.queueStringCommand("PASV")

        def mockDTPInstance(result):
            """
            Fake an incoming connection and create a mock DTPInstance so
            that PORT command will start processing the request.

            @param result: parameter used in L{Deferred}
            """
            self.serverProtocol.dtpFactory.deferred.callback(None)
            self.serverProtocol.dtpInstance = object()
            self.serverProtocol.shell.openForWriting = failingOpenForWriting
            return result

        def checkLogs(result):
            """
            Check that unknown errors are logged.

            @param result: parameter used in L{Deferred}
            """
            logs = self.flushLoggedErrors()
            self.assertEqual(1, len(logs))
            self.assertIsInstance(logs[0].value, AssertionError)

        d.addCallback(sendPASV)
        d.addCallback(mockDTPInstance)

        self.assertCommandFailed(
            "STOR something",
            ["550 something: No such file or directory."],
            chainDeferred=d,
        )
        d.addCallback(checkLogs)
        return d


class FTPServerAdvancedClientTests(FTPServerTestCase):
    """
    Test FTP server with the L{ftp.FTPClient} class.
    """

    clientFactory = ftp.FTPClient

    def test_anonymousSTOR(self):
        """
        Try to make an STOR as anonymous, and check that we got a permission
        denied error.
        """

        def eb(res):
            res.trap(ftp.CommandFailed)
            self.assertEqual(res.value.args[0][0], "550 foo: Permission denied.")

        d1, d2 = self.client.storeFile("foo")
        d2.addErrback(eb)
        return defer.gatherResults([d1, d2])

    def test_STORtransferErrorIsReturned(self):
        """
        Any FTP error raised by STOR while transferring the file is returned
        to the client.
        """
        # Make a failing file writer.
        class FailingFileWriter(ftp._FileWriter):
            def receive(self):
                return defer.fail(ftp.IsADirectoryError("failing_file"))

        def failingSTOR(a, b):
            return defer.succeed(FailingFileWriter(None))

        # Monkey patch the shell so it returns a file writer that will
        # fail during transfer.
        self.patch(ftp.FTPAnonymousShell, "openForWriting", failingSTOR)

        def eb(res):
            res.trap(ftp.CommandFailed)
            logs = self.flushLoggedErrors()
            self.assertEqual(1, len(logs))
            self.assertIsInstance(logs[0].value, ftp.IsADirectoryError)
            self.assertEqual(res.value.args[0][0], "550 failing_file: is a directory")

        d1, d2 = self.client.storeFile("failing_file")
        d2.addErrback(eb)
        return defer.gatherResults([d1, d2])

    def test_STORunknownTransferErrorBecomesAbort(self):
        """
        Any non FTP error raised by STOR while transferring the file is
        converted into a critical error and transfer is closed.

        The unknown error is logged.
        """

        class FailingFileWriter(ftp._FileWriter):
            def receive(self):
                return defer.fail(AssertionError())

        def failingSTOR(a, b):
            return defer.succeed(FailingFileWriter(None))

        # Monkey patch the shell so it returns a file writer that will
        # fail during transfer.
        self.patch(ftp.FTPAnonymousShell, "openForWriting", failingSTOR)

        def eb(res):
            res.trap(ftp.CommandFailed)
            logs = self.flushLoggedErrors()
            self.assertEqual(1, len(logs))
            self.assertIsInstance(logs[0].value, AssertionError)
            self.assertEqual(
                res.value.args[0][0], "426 Transfer aborted.  Data connection closed."
            )

        d1, d2 = self.client.storeFile("failing_file")
        d2.addErrback(eb)
        return defer.gatherResults([d1, d2])

    def test_RETRreadError(self):
        """
        Any errors during reading a file inside a RETR should be returned to
        the client.
        """
        # Make a failing file reading.
        class FailingFileReader(ftp._FileReader):
            def send(self, consumer):
                return defer.fail(ftp.IsADirectoryError("blah"))

        def failingRETR(a, b):
            return defer.succeed(FailingFileReader(None))

        # Monkey patch the shell so it returns a file reader that will
        # fail.
        self.patch(ftp.FTPAnonymousShell, "openForReading", failingRETR)

        def check_response(failure):
            self.flushLoggedErrors()
            failure.trap(ftp.CommandFailed)
            self.assertEqual(
                failure.value.args[0][0],
                "125 Data connection already open, starting transfer",
            )
            self.assertEqual(failure.value.args[0][1], "550 blah: is a directory")

        proto = _BufferingProtocol()
        d = self.client.retrieveFile("failing_file", proto)
        d.addErrback(check_response)
        return d


class FTPServerPasvDataConnectionTests(FTPServerTestCase):
    """
    PASV data connection.
    """

    def _makeDataConnection(self, ignored=None):
        """
        Establish a passive data connection (i.e. client connecting to
        server).

        @param ignored: ignored
        @return: L{Deferred.addCallback}
        """
        d = self.client.queueStringCommand("PASV")

        def gotPASV(responseLines):
            host, port = ftp.decodeHostPort(responseLines[-1][4:])
            cc = protocol.ClientCreator(reactor, _BufferingProtocol)
            return cc.connectTCP("127.0.0.1", port)

        return d.addCallback(gotPASV)

    def _download(self, command, chainDeferred=None):
        """
        Download file.

        @param command: command to run
        @param chainDeferred: L{Deferred} used to queue commands.
        @return: L{Deferred} of command response
        """
        if chainDeferred is None:
            chainDeferred = defer.succeed(None)

        chainDeferred.addCallback(self._makeDataConnection)

        def queueCommand(downloader):
            # Wait for the command to return, and the download connection to be
            # closed.
            d1 = self.client.queueStringCommand(command)
            d2 = downloader.d
            return defer.gatherResults([d1, d2])

        chainDeferred.addCallback(queueCommand)

        def downloadDone(result):
            (ignored, downloader) = result
            return downloader.buffer

        return chainDeferred.addCallback(downloadDone)

    def test_LISTEmpty(self):
        """
        When listing empty folders, LIST returns an empty response.
        """
        d = self._anonymousLogin()

        # No files, so the file listing should be empty
        self._download("LIST", chainDeferred=d)

        def checkEmpty(result):
            self.assertEqual(b"", result)

        return d.addCallback(checkEmpty)

    def test_LISTWithBinLsFlags(self):
        """
        LIST ignores requests for folder with names like '-al' and will list
        the content of current folder.
        """
        os.mkdir(os.path.join(self.directory, "foo"))
        os.mkdir(os.path.join(self.directory, "bar"))

        # Login
        d = self._anonymousLogin()

        self._download("LIST -aL", chainDeferred=d)

        def checkDownload(download):
            names = []
            for line in download.splitlines():
                names.append(line.split(b" ")[-1])
            self.assertEqual(2, len(names))
            self.assertIn(b"foo", names)
            self.assertIn(b"bar", names)

        return d.addCallback(checkDownload)

    def test_LISTWithContent(self):
        """
        LIST returns all folder's members, each member listed on a separate
        line and with name and other details.
        """
        os.mkdir(os.path.join(self.directory, "foo"))
        os.mkdir(os.path.join(self.directory, "bar"))

        # Login
        d = self._anonymousLogin()

        # We expect 2 lines because there are two files.
        self._download("LIST", chainDeferred=d)

        def checkDownload(download):
            self.assertEqual(2, len(download[:-2].split(b"\r\n")))

        d.addCallback(checkDownload)

        # Download a names-only listing.
        self._download("NLST ", chainDeferred=d)

        def checkDownload(download):
            filenames = download[:-2].split(b"\r\n")
            filenames.sort()
            self.assertEqual([b"bar", b"foo"], filenames)

        d.addCallback(checkDownload)

        # Download a listing of the 'foo' subdirectory.  'foo' has no files, so
        # the file listing should be empty.
        self._download("LIST foo", chainDeferred=d)

        def checkDownload(download):
            self.assertEqual(b"", download)

        d.addCallback(checkDownload)

        # Change the current working directory to 'foo'.
        def chdir(ignored):
            return self.client.queueStringCommand("CWD foo")

        d.addCallback(chdir)

        # Download a listing from within 'foo', and again it should be empty,
        # because LIST uses the working directory by default.
        self._download("LIST", chainDeferred=d)

        def checkDownload(download):
            self.assertEqual(b"", download)

        return d.addCallback(checkDownload)

    def _listTestHelper(self, command, listOutput, expectedOutput):
        """
        Exercise handling by the implementation of I{LIST} or I{NLST} of certain
        return values and types from an L{IFTPShell.list} implementation.

        This will issue C{command} and assert that if the L{IFTPShell.list}
        implementation includes C{listOutput} as one of the file entries then
        the result given to the client is matches C{expectedOutput}.

        @param command: Either C{b"LIST"} or C{b"NLST"}
        @type command: L{bytes}

        @param listOutput: A value suitable to be used as an element of the list
            returned by L{IFTPShell.list}.  Vary the values and types of the
            contents to exercise different code paths in the server's handling
            of this result.

        @param expectedOutput: A line of output to expect as a result of
            C{listOutput} being transformed into a response to the command
            issued.
        @type expectedOutput: L{bytes}

        @return: A L{Deferred} which fires when the test is done, either with an
            L{Failure} if the test failed or with a function object if it
            succeeds.  The function object is the function which implements
            L{IFTPShell.list} (and is useful to make assertions about what
            warnings might have been emitted).
        @rtype: L{Deferred}
        """
        # Login
        d = self._anonymousLogin()

        def patchedList(segments, keys=()):
            return defer.succeed([listOutput])

        def loggedIn(result):
            self.serverProtocol.shell.list = patchedList
            return result

        d.addCallback(loggedIn)

        self._download(f"{command} something", chainDeferred=d)

        def checkDownload(download):
            self.assertEqual(expectedOutput, download)
            return patchedList

        return d.addCallback(checkDownload)

    def test_LISTUnicode(self):
        """
        Unicode filenames returned from L{IFTPShell.list} are encoded using
        UTF-8 before being sent with the response.
        """
        return self._listTestHelper(
            "LIST",
            (
                "my resum\xe9",
                (0, 1, filepath.Permissions(0o777), 0, 0, "user", "group"),
            ),
            b"drwxrwxrwx   0 user      group                   "
            b"0 Jan 01  1970 my resum\xc3\xa9\r\n",
        )

    def test_LISTNonASCIIBytes(self):
        """
        When LIST receive a filename as byte string from L{IFTPShell.list}
        it will just pass the data to lower level without any change.

        @return: L{_listTestHelper}
        """
        return self._listTestHelper(
            "LIST",
            (
                b"my resum\xc3\xa9",
                (0, 1, filepath.Permissions(0o777), 0, 0, "user", "group"),
            ),
            b"drwxrwxrwx   0 user      group                   "
            b"0 Jan 01  1970 my resum\xc3\xa9\r\n",
        )

    def test_ManyLargeDownloads(self):
        """
        Download many large files.

        @return: L{Deferred}
        """
        # Login
        d = self._anonymousLogin()

        # Download a range of different size files
        for size in range(100000, 110000, 500):
            with open(os.path.join(self.directory, "%d.txt" % (size,)), "wb") as fObj:
                fObj.write(b"x" * size)

            self._download("RETR %d.txt" % (size,), chainDeferred=d)

            def checkDownload(download, size=size):
                self.assertEqual(size, len(download))

            d.addCallback(checkDownload)
        return d

    def test_downloadFolder(self):
        """
        When RETR is called for a folder, it will fail complaining that
        the path is a folder.
        """
        # Make a directory in the current working directory
        self.dirPath.child("foo").createDirectory()
        # Login
        d = self._anonymousLogin()
        d.addCallback(self._makeDataConnection)

        def retrFolder(downloader):
            downloader.transport.loseConnection()
            deferred = self.client.queueStringCommand("RETR foo")
            return deferred

        d.addCallback(retrFolder)

        def failOnSuccess(result):
            raise AssertionError("Downloading a folder should not succeed.")

        d.addCallback(failOnSuccess)

        def checkError(failure):
            failure.trap(ftp.CommandFailed)
            self.assertEqual(["550 foo: is a directory"], failure.value.args[0])
            current_errors = self.flushLoggedErrors()
            self.assertEqual(
                0,
                len(current_errors),
                "No errors should be logged while downloading a folder.",
            )

        d.addErrback(checkError)
        return d

    def test_NLSTEmpty(self):
        """
        NLST with no argument returns the directory listing for the current
        working directory.
        """
        # Login
        d = self._anonymousLogin()

        # Touch a file in the current working directory
        self.dirPath.child("test.txt").touch()
        # Make a directory in the current working directory
        self.dirPath.child("foo").createDirectory()

        self._download("NLST ", chainDeferred=d)

        def checkDownload(download):
            filenames = download[:-2].split(b"\r\n")
            filenames.sort()
            self.assertEqual([b"foo", b"test.txt"], filenames)

        return d.addCallback(checkDownload)

    def test_NLSTNonexistent(self):
        """
        NLST on a non-existent file/directory returns nothing.
        """
        # Login
        d = self._anonymousLogin()

        self._download("NLST nonexistent.txt", chainDeferred=d)

        def checkDownload(download):
            self.assertEqual(b"", download)

        return d.addCallback(checkDownload)

    def test_NLSTUnicode(self):
        """
        NLST will receive Unicode filenames for IFTPShell.list, and will
        encode them using UTF-8.
        """
        return self._listTestHelper(
            "NLST",
            (
                "my resum\xe9",
                (0, 1, filepath.Permissions(0o777), 0, 0, "user", "group"),
            ),
            b"my resum\xc3\xa9\r\n",
        )

    def test_NLSTNonASCIIBytes(self):
        """
        NLST will just pass the non-Unicode data to lower level.
        """
        return self._listTestHelper(
            "NLST",
            (
                b"my resum\xc3\xa9",
                (0, 1, filepath.Permissions(0o777), 0, 0, "user", "group"),
            ),
            b"my resum\xc3\xa9\r\n",
        )

    def test_NLSTOnPathToFile(self):
        """
        NLST on an existent file returns only the path to that file.
        """
        # Login
        d = self._anonymousLogin()

        # Touch a file in the current working directory
        self.dirPath.child("test.txt").touch()

        self._download("NLST test.txt", chainDeferred=d)

        def checkDownload(download):
            filenames = download[:-2].split(b"\r\n")
            self.assertEqual([b"test.txt"], filenames)

        return d.addCallback(checkDownload)


class FTPServerPortDataConnectionTests(FTPServerPasvDataConnectionTests):
    def setUp(self):
        self.dataPorts = []
        return FTPServerPasvDataConnectionTests.setUp(self)

    def _makeDataConnection(self, ignored=None):
        # Establish an active data connection (i.e. server connecting to
        # client).
        deferred = defer.Deferred()

        class DataFactory(protocol.ServerFactory):
            protocol = _BufferingProtocol

            def buildProtocol(self, addr):
                p = protocol.ServerFactory.buildProtocol(self, addr)
                reactor.callLater(0, deferred.callback, p)
                return p

        dataPort = reactor.listenTCP(0, DataFactory(), interface="127.0.0.1")
        self.dataPorts.append(dataPort)
        cmd = "PORT " + ftp.encodeHostPort("127.0.0.1", dataPort.getHost().port)
        self.client.queueStringCommand(cmd)
        return deferred

    def tearDown(self):
        """
        Tear down the connection.

        @return: L{defer.DeferredList}
        """
        l = [defer.maybeDeferred(port.stopListening) for port in self.dataPorts]
        d = defer.maybeDeferred(FTPServerPasvDataConnectionTests.tearDown, self)
        l.append(d)
        return defer.DeferredList(l, fireOnOneErrback=True)

    def test_PORTCannotConnect(self):
        """
        Listen on a port, and immediately stop listening as a way to find a
        port number that is definitely closed.
        """
        # Login
        d = self._anonymousLogin()

        def loggedIn(ignored):
            port = reactor.listenTCP(0, protocol.Factory(), interface="127.0.0.1")
            portNum = port.getHost().port
            d = port.stopListening()
            d.addCallback(lambda _: portNum)
            return d

        d.addCallback(loggedIn)

        # Tell the server to connect to that port with a PORT command, and
        # verify that it fails with the right error.
        def gotPortNum(portNum):
            return self.assertCommandFailed(
                "PORT " + ftp.encodeHostPort("127.0.0.1", portNum),
                ["425 Can't open data connection."],
            )

        return d.addCallback(gotPortNum)

    def test_nlstGlobbing(self):
        """
        When Unix shell globbing is used with NLST only files matching the
        pattern will be returned.
        """
        self.dirPath.child("test.txt").touch()
        self.dirPath.child("ceva.txt").touch()
        self.dirPath.child("no.match").touch()
        d = self._anonymousLogin()

        self._download("NLST *.txt", chainDeferred=d)

        def checkDownload(download):
            filenames = download[:-2].split(b"\r\n")
            filenames.sort()
            self.assertEqual([b"ceva.txt", b"test.txt"], filenames)

        return d.addCallback(checkDownload)


class DTPFactoryTests(TestCase):
    """
    Tests for L{ftp.DTPFactory}.
    """

    def setUp(self):
        """
        Create a fake protocol interpreter and a L{ftp.DTPFactory} instance to
        test.
        """
        self.reactor = task.Clock()

        class ProtocolInterpreter:
            dtpInstance = None

        self.protocolInterpreter = ProtocolInterpreter()
        self.factory = ftp.DTPFactory(self.protocolInterpreter, None, self.reactor)

    def test_setTimeout(self):
        """
        L{ftp.DTPFactory.setTimeout} uses the reactor passed to its initializer
        to set up a timed event to time out the DTP setup after the specified
        number of seconds.
        """
        # Make sure the factory's deferred fails with the right exception, and
        # make it so we can tell exactly when it fires.
        finished = []
        d = self.assertFailure(self.factory.deferred, ftp.PortConnectionError)
        d.addCallback(finished.append)

        self.factory.setTimeout(6)

        # Advance the clock almost to the timeout
        self.reactor.advance(5)

        # Nothing should have happened yet.
        self.assertFalse(finished)

        # Advance it to the configured timeout.
        self.reactor.advance(1)

        # Now the Deferred should have failed with TimeoutError.
        self.assertTrue(finished)

        # There should also be no calls left in the reactor.
        self.assertFalse(self.reactor.calls)

    def test_buildProtocolOnce(self):
        """
        A L{ftp.DTPFactory} instance's C{buildProtocol} method can be used once
        to create a L{ftp.DTP} instance.
        """
        protocol = self.factory.buildProtocol(None)
        self.assertIsInstance(protocol, ftp.DTP)

        # A subsequent call returns None.
        self.assertIsNone(self.factory.buildProtocol(None))

    def test_timeoutAfterConnection(self):
        """
        If a timeout has been set up using L{ftp.DTPFactory.setTimeout}, it is
        cancelled by L{ftp.DTPFactory.buildProtocol}.
        """
        self.factory.setTimeout(10)
        self.factory.buildProtocol(None)
        # Make sure the call is no longer active.
        self.assertFalse(self.reactor.calls)

    def test_connectionAfterTimeout(self):
        """
        If L{ftp.DTPFactory.buildProtocol} is called after the timeout
        specified by L{ftp.DTPFactory.setTimeout} has elapsed, L{None} is
        returned.
        """
        # Handle the error so it doesn't get logged.
        d = self.assertFailure(self.factory.deferred, ftp.PortConnectionError)

        # Set up the timeout and then cause it to elapse so the Deferred does
        # fail.
        self.factory.setTimeout(10)
        self.reactor.advance(10)

        # Try to get a protocol - we should not be able to.
        self.assertIsNone(self.factory.buildProtocol(None))

        # Make sure the Deferred is doing the right thing.
        return d

    def test_timeoutAfterConnectionFailed(self):
        """
        L{ftp.DTPFactory.deferred} fails with L{PortConnectionError} when
        L{ftp.DTPFactory.clientConnectionFailed} is called.  If the timeout
        specified with L{ftp.DTPFactory.setTimeout} expires after that, nothing
        additional happens.
        """
        finished = []
        d = self.assertFailure(self.factory.deferred, ftp.PortConnectionError)
        d.addCallback(finished.append)

        self.factory.setTimeout(10)
        self.assertFalse(finished)
        self.factory.clientConnectionFailed(None, None)
        self.assertTrue(finished)
        self.reactor.advance(10)
        return d

    def test_connectionFailedAfterTimeout(self):
        """
        If L{ftp.DTPFactory.clientConnectionFailed} is called after the timeout
        specified by L{ftp.DTPFactory.setTimeout} has elapsed, nothing beyond
        the normal timeout before happens.
        """
        # Handle the error so it doesn't get logged.
        d = self.assertFailure(self.factory.deferred, ftp.PortConnectionError)

        # Set up the timeout and then cause it to elapse so the Deferred does
        # fail.
        self.factory.setTimeout(10)
        self.reactor.advance(10)

        # Now fail the connection attempt.  This should do nothing.  In
        # particular, it should not raise an exception.
        self.factory.clientConnectionFailed(None, defer.TimeoutError("foo"))

        # Give the Deferred to trial so it can make sure it did what we
        # expected.
        return d


class DTPTests(TestCase):
    """
    Tests for L{ftp.DTP}.

    The DTP instances in these tests are generated using
    DTPFactory.buildProtocol()
    """

    def setUp(self):
        """
        Create a fake protocol interpreter, a L{ftp.DTPFactory} instance,
        and dummy transport to help with tests.
        """
        self.reactor = task.Clock()

        class ProtocolInterpreter:
            dtpInstance = None

        self.protocolInterpreter = ProtocolInterpreter()
        self.factory = ftp.DTPFactory(self.protocolInterpreter, None, self.reactor)
        self.transport = proto_helpers.StringTransportWithDisconnection()

    def test_sendLineNewline(self):
        """
        L{ftp.DTP.sendLine} writes the line passed to it plus a line delimiter
        to its transport.
        """
        dtpInstance = self.factory.buildProtocol(None)
        dtpInstance.makeConnection(self.transport)
        lineContent = b"line content"

        dtpInstance.sendLine(lineContent)

        dataSent = self.transport.value()
        self.assertEqual(lineContent + b"\r\n", dataSent)


# -- Client Tests -----------------------------------------------------------


class PrintLines(protocol.Protocol):
    """
    Helper class used by FTPFileListingTests.
    """

    def __init__(self, lines):
        self._lines = lines

    def connectionMade(self):
        for line in self._lines:
            self.transport.write(line.encode("latin-1") + b"\r\n")
        self.transport.loseConnection()


class MyFTPFileListProtocol(ftp.FTPFileListProtocol):
    def __init__(self):
        self.other = []
        ftp.FTPFileListProtocol.__init__(self)

    def unknownLine(self, line):
        self.other.append(line)


class FTPFileListingTests(TestCase):
    def getFilesForLines(self, lines):
        fileList = MyFTPFileListProtocol()
        d = loopback.loopbackAsync(PrintLines(lines), fileList)
        d.addCallback(lambda _: (fileList.files, fileList.other))
        return d

    def test_OneLine(self):
        """
        This example line taken from the docstring for FTPFileListProtocol

        @return: L{Deferred} of command response
        """
        line = "-rw-r--r--   1 root     other        531 Jan 29 03:26 README"

        def check(fileOther):
            ((file,), other) = fileOther
            self.assertFalse(other, f"unexpect unparsable lines: {repr(other)}")
            self.assertTrue(file["filetype"] == "-", "misparsed fileitem")
            self.assertTrue(file["perms"] == "rw-r--r--", "misparsed perms")
            self.assertTrue(file["owner"] == "root", "misparsed fileitem")
            self.assertTrue(file["group"] == "other", "misparsed fileitem")
            self.assertTrue(file["size"] == 531, "misparsed fileitem")
            self.assertTrue(file["date"] == "Jan 29 03:26", "misparsed fileitem")
            self.assertTrue(file["filename"] == "README", "misparsed fileitem")
            self.assertTrue(file["nlinks"] == 1, "misparsed nlinks")
            self.assertFalse(file["linktarget"], "misparsed linktarget")

        return self.getFilesForLines([line]).addCallback(check)

    def test_VariantLines(self):
        """
        Variant lines.
        """
        line1 = "drw-r--r--   2 root     other        531 Jan  9  2003 A"
        line2 = "lrw-r--r--   1 root     other          1 Jan 29 03:26 B -> A"
        line3 = "woohoo! "

        def check(result):
            ((file1, file2), (other,)) = result
            self.assertTrue(other == "woohoo! \r", "incorrect other line")
            # file 1
            self.assertTrue(file1["filetype"] == "d", "misparsed fileitem")
            self.assertTrue(file1["perms"] == "rw-r--r--", "misparsed perms")
            self.assertTrue(file1["owner"] == "root", "misparsed owner")
            self.assertTrue(file1["group"] == "other", "misparsed group")
            self.assertTrue(file1["size"] == 531, "misparsed size")
            self.assertTrue(file1["date"] == "Jan  9  2003", "misparsed date")
            self.assertTrue(file1["filename"] == "A", "misparsed filename")
            self.assertTrue(file1["nlinks"] == 2, "misparsed nlinks")
            self.assertFalse(file1["linktarget"], "misparsed linktarget")
            # file 2
            self.assertTrue(file2["filetype"] == "l", "misparsed fileitem")
            self.assertTrue(file2["perms"] == "rw-r--r--", "misparsed perms")
            self.assertTrue(file2["owner"] == "root", "misparsed owner")
            self.assertTrue(file2["group"] == "other", "misparsed group")
            self.assertTrue(file2["size"] == 1, "misparsed size")
            self.assertTrue(file2["date"] == "Jan 29 03:26", "misparsed date")
            self.assertTrue(file2["filename"] == "B", "misparsed filename")
            self.assertTrue(file2["nlinks"] == 1, "misparsed nlinks")
            self.assertTrue(file2["linktarget"] == "A", "misparsed linktarget")

        return self.getFilesForLines([line1, line2, line3]).addCallback(check)

    def test_UnknownLine(self):
        """
        Unknown lines.
        """

        def check(result):
            (files, others) = result
            self.assertFalse(files, "unexpected file entries")
            self.assertTrue(
                others == ["ABC\r", "not a file\r"],
                "incorrect unparsable lines: %s" % repr(others),
            )

        return self.getFilesForLines(["ABC", "not a file"]).addCallback(check)

    def test_filenameWithUnescapedSpace(self):
        """
        Will parse filenames and linktargets containing unescaped
        space characters.
        """
        line1 = "drw-r--r--   2 root     other        531 Jan  9  2003 A B"
        line2 = (
            "lrw-r--r--   1 root     other          1 Jan 29 03:26 " "B A -> D C/A B"
        )

        def check(result):
            (files, others) = result
            self.assertEqual([], others, "unexpected others entries")
            self.assertEqual("A B", files[0]["filename"], "misparsed filename")
            self.assertEqual("B A", files[1]["filename"], "misparsed filename")
            self.assertEqual("D C/A B", files[1]["linktarget"], "misparsed linktarget")

        return self.getFilesForLines([line1, line2]).addCallback(check)

    def test_filenameWithEscapedSpace(self):
        """
        Will parse filenames and linktargets containing escaped
        space characters.
        """
        line1 = r"drw-r--r--   2 root     other        531 Jan  9  2003 A\ B"
        line2 = (
            "lrw-r--r--   1 root     other          1 Jan 29 03:26 " r"B A -> D\ C/A B"
        )

        def check(result):
            (files, others) = result
            self.assertEqual([], others, "unexpected others entries")
            self.assertEqual("A B", files[0]["filename"], "misparsed filename")
            self.assertEqual("B A", files[1]["filename"], "misparsed filename")
            self.assertEqual("D C/A B", files[1]["linktarget"], "misparsed linktarget")

        return self.getFilesForLines([line1, line2]).addCallback(check)

    def test_Year(self):
        """
        This example derived from bug description in issue 514.

        @return: L{Deferred} of command response
        """
        fileList = ftp.FTPFileListProtocol()
        exampleLine = b"-rw-r--r--   1 root     other        531 Jan 29 2003 README\n"

        class PrintLine(protocol.Protocol):
            def connectionMade(self):
                self.transport.write(exampleLine)
                self.transport.loseConnection()

        def check(ignored):
            file = fileList.files[0]
            self.assertTrue(file["size"] == 531, "misparsed fileitem")
            self.assertTrue(file["date"] == "Jan 29 2003", "misparsed fileitem")
            self.assertTrue(file["filename"] == "README", "misparsed fileitem")

        d = loopback.loopbackAsync(PrintLine(), fileList)
        return d.addCallback(check)


class FTPClientFailedRETRAndErrbacksUponDisconnectTests(TestCase):
    """
    FTP client fails and RETR fails and disconnects.
    """

    def test_FailedRETR(self):
        """
        RETR fails.
        """
        f = protocol.Factory()
        f.noisy = 0
        port = reactor.listenTCP(0, f, interface="127.0.0.1")
        self.addCleanup(port.stopListening)
        portNum = port.getHost().port
        # This test data derived from a bug report by ranty on #twisted
        responses = [
            "220 ready, dude (vsFTPd 1.0.0: beat me, break me)",
            # USER anonymous
            "331 Please specify the password.",
            # PASS twisted@twistedmatrix.com
            "230 Login successful. Have fun.",
            # TYPE I
            "200 Binary it is, then.",
            # PASV
            "227 Entering Passive Mode (127,0,0,1,%d,%d)"
            % (portNum >> 8, portNum & 0xFF),
            # RETR /file/that/doesnt/exist
            "550 Failed to open file.",
        ]
        f.buildProtocol = lambda addr: PrintLines(responses)

        cc = protocol.ClientCreator(reactor, ftp.FTPClient, passive=1)
        d = cc.connectTCP("127.0.0.1", portNum)

        def gotClient(client):
            p = protocol.Protocol()
            return client.retrieveFile("/file/that/doesnt/exist", p)

        d.addCallback(gotClient)
        return self.assertFailure(d, ftp.CommandFailed)

    def test_errbacksUponDisconnect(self):
        """
        Test the ftp command errbacks when a connection lost happens during
        the operation.
        """
        ftpClient = ftp.FTPClient()
        tr = proto_helpers.StringTransportWithDisconnection()
        ftpClient.makeConnection(tr)
        tr.protocol = ftpClient
        d = ftpClient.list("some path", Dummy())
        m = []

        def _eb(failure):
            m.append(failure)
            return None

        d.addErrback(_eb)
        from twisted.internet.main import CONNECTION_LOST

        ftpClient.connectionLost(failure.Failure(CONNECTION_LOST))
        self.assertTrue(m, m)
        return d


class FTPClientTests(TestCase):
    """
    Test advanced FTP client commands.
    """

    def setUp(self):
        """
        Create a FTP client and connect it to fake transport.
        """
        self.client = ftp.FTPClient()
        self.transport = proto_helpers.StringTransportWithDisconnection()
        self.client.makeConnection(self.transport)
        self.transport.protocol = self.client

    def tearDown(self):
        """
        Deliver disconnection notification to the client so that it can
        perform any cleanup which may be required.
        """
        self.client.connectionLost(error.ConnectionLost())

    def _testLogin(self):
        """
        Test the login part.
        """
        self.assertEqual(self.transport.value(), b"")
        self.client.lineReceived(
            b"331 Guest login ok, type your email address as password."
        )
        self.assertEqual(self.transport.value(), b"USER anonymous\r\n")
        self.transport.clear()
        self.client.lineReceived(b"230 Anonymous login ok, access restrictions apply.")
        self.assertEqual(self.transport.value(), b"TYPE I\r\n")
        self.transport.clear()
        self.client.lineReceived(b"200 Type set to I.")

    def test_sendLine(self):
        """
        Test encoding behaviour of sendLine
        """
        self.assertEqual(self.transport.value(), b"")
        self.client.sendLine(None)
        self.assertEqual(self.transport.value(), b"")
        self.client.sendLine("")
        self.assertEqual(self.transport.value(), b"\r\n")
        self.transport.clear()
        self.client.sendLine("\xe9")
        self.assertEqual(self.transport.value(), b"\xe9\r\n")

    def test_CDUP(self):
        """
        Test the CDUP command.

        L{ftp.FTPClient.cdup} should return a Deferred which fires with a
        sequence of one element which is the string the server sent
        indicating that the command was executed successfully.

        (XXX - This is a bad API)
        """

        def cbCdup(res):
            self.assertEqual(res[0], "250 Requested File Action Completed OK")

        self._testLogin()
        d = self.client.cdup().addCallback(cbCdup)
        self.assertEqual(self.transport.value(), b"CDUP\r\n")
        self.transport.clear()
        self.client.lineReceived(b"250 Requested File Action Completed OK")
        return d

    def test_failedCDUP(self):
        """
        Test L{ftp.FTPClient.cdup}'s handling of a failed CDUP command.

        When the CDUP command fails, the returned Deferred should errback
        with L{ftp.CommandFailed}.
        """
        self._testLogin()
        d = self.client.cdup()
        self.assertFailure(d, ftp.CommandFailed)
        self.assertEqual(self.transport.value(), b"CDUP\r\n")
        self.transport.clear()
        self.client.lineReceived(b"550 ..: No such file or directory")
        return d

    def test_PWD(self):
        """
        Test the PWD command.

        L{ftp.FTPClient.pwd} should return a Deferred which fires with a
        sequence of one element which is a string representing the current
        working directory on the server.

        (XXX - This is a bad API)
        """

        def cbPwd(res):
            self.assertEqual(ftp.parsePWDResponse(res[0]), "/bar/baz")

        self._testLogin()
        d = self.client.pwd().addCallback(cbPwd)
        self.assertEqual(self.transport.value(), b"PWD\r\n")
        self.client.lineReceived(b'257 "/bar/baz"')
        return d

    def test_failedPWD(self):
        """
        Test a failure in PWD command.

        When the PWD command fails, the returned Deferred should errback
        with L{ftp.CommandFailed}.
        """
        self._testLogin()
        d = self.client.pwd()
        self.assertFailure(d, ftp.CommandFailed)
        self.assertEqual(self.transport.value(), b"PWD\r\n")
        self.client.lineReceived(b"550 /bar/baz: No such file or directory")
        return d

    def test_CWD(self):
        """
        Test the CWD command.

        L{ftp.FTPClient.cwd} should return a Deferred which fires with a
        sequence of one element which is the string the server sent
        indicating that the command was executed successfully.

        (XXX - This is a bad API)
        """

        def cbCwd(res):
            self.assertEqual(res[0], "250 Requested File Action Completed OK")

        self._testLogin()
        d = self.client.cwd("bar/foo").addCallback(cbCwd)
        self.assertEqual(self.transport.value(), b"CWD bar/foo\r\n")
        self.client.lineReceived(b"250 Requested File Action Completed OK")
        return d

    def test_failedCWD(self):
        """
        Test a failure in CWD command.

        When the PWD command fails, the returned Deferred should errback
        with L{ftp.CommandFailed}.
        """
        self._testLogin()
        d = self.client.cwd("bar/foo")
        self.assertFailure(d, ftp.CommandFailed)
        self.assertEqual(self.transport.value(), b"CWD bar/foo\r\n")
        self.client.lineReceived(b"550 bar/foo: No such file or directory")
        return d

    def test_passiveRETR(self):
        """
        Test the RETR command in passive mode: get a file and verify its
        content.

        L{ftp.FTPClient.retrieveFile} should return a Deferred which fires
        with the protocol instance passed to it after the download has
        completed.

        (XXX - This API should be based on producers and consumers)
        """

        def cbRetr(res, proto):
            self.assertEqual(proto.buffer, b"x" * 1000)

        def cbConnect(host, port, factory):
            self.assertEqual(host, "127.0.0.1")
            self.assertEqual(port, 12345)
            proto = factory.buildProtocol((host, port))
            proto.makeConnection(proto_helpers.StringTransport())
            self.client.lineReceived(
                b"150 File status okay; about to open data connection."
            )
            proto.dataReceived(b"x" * 1000)
            proto.connectionLost(failure.Failure(error.ConnectionDone("")))

        self.client.connectFactory = cbConnect
        self._testLogin()
        proto = _BufferingProtocol()
        d = self.client.retrieveFile("spam", proto)
        d.addCallback(cbRetr, proto)
        self.assertEqual(self.transport.value(), b"PASV\r\n")
        self.transport.clear()
        self.client.lineReceived(passivemode_msg(self.client))
        self.assertEqual(self.transport.value(), b"RETR spam\r\n")
        self.transport.clear()
        self.client.lineReceived(b"226 Transfer Complete.")
        return d

    def test_RETR(self):
        """
        Test the RETR command in non-passive mode.

        Like L{test_passiveRETR} but in the configuration where the server
        establishes the data connection to the client, rather than the other
        way around.
        """
        self.client.passive = False

        def generatePort(portCmd):
            portCmd.text = "PORT {}".format(ftp.encodeHostPort("127.0.0.1", 9876))
            portCmd.protocol.makeConnection(proto_helpers.StringTransport())
            portCmd.protocol.dataReceived(b"x" * 1000)
            portCmd.protocol.connectionLost(failure.Failure(error.ConnectionDone("")))

        def cbRetr(res, proto):
            self.assertEqual(proto.buffer, b"x" * 1000)

        self.client.generatePortCommand = generatePort
        self._testLogin()
        proto = _BufferingProtocol()
        d = self.client.retrieveFile("spam", proto)
        d.addCallback(cbRetr, proto)
        self.assertEqual(
            self.transport.value(),
            ("PORT {}\r\n".format(ftp.encodeHostPort("127.0.0.1", 9876))).encode(
                self.client._encoding
            ),
        )
        self.transport.clear()
        self.client.lineReceived(b"200 PORT OK")
        self.assertEqual(self.transport.value(), b"RETR spam\r\n")
        self.transport.clear()
        self.client.lineReceived(b"226 Transfer Complete.")
        return d

    def test_failedRETR(self):
        """
        Try to RETR an unexisting file.

        L{ftp.FTPClient.retrieveFile} should return a Deferred which
        errbacks with L{ftp.CommandFailed} if the server indicates the file
        cannot be transferred for some reason.
        """

        def cbConnect(host, port, factory):
            self.assertEqual(host, "127.0.0.1")
            self.assertEqual(port, 12345)
            proto = factory.buildProtocol((host, port))
            proto.makeConnection(proto_helpers.StringTransport())
            self.client.lineReceived(
                b"150 File status okay; about to open data connection."
            )
            proto.connectionLost(failure.Failure(error.ConnectionDone("")))

        self.client.connectFactory = cbConnect
        self._testLogin()
        proto = _BufferingProtocol()
        d = self.client.retrieveFile("spam", proto)
        self.assertFailure(d, ftp.CommandFailed)
        self.assertEqual(self.transport.value(), b"PASV\r\n")
        self.transport.clear()
        self.client.lineReceived(passivemode_msg(self.client))
        self.assertEqual(self.transport.value(), b"RETR spam\r\n")
        self.transport.clear()
        self.client.lineReceived(b"550 spam: No such file or directory")
        return d

    def test_lostRETR(self):
        """
        Try a RETR, but disconnect during the transfer.
        L{ftp.FTPClient.retrieveFile} should return a Deferred which
        errbacks with L{ftp.ConnectionLost)
        """
        self.client.passive = False

        l = []

        def generatePort(portCmd):
            portCmd.text = "PORT {}".format(ftp.encodeHostPort("127.0.0.1", 9876))
            tr = proto_helpers.StringTransportWithDisconnection()
            portCmd.protocol.makeConnection(tr)
            tr.protocol = portCmd.protocol
            portCmd.protocol.dataReceived(b"x" * 500)
            l.append(tr)

        self.client.generatePortCommand = generatePort
        self._testLogin()
        proto = _BufferingProtocol()
        d = self.client.retrieveFile("spam", proto)
        self.assertEqual(
            self.transport.value(),
            ("PORT {}\r\n".format(ftp.encodeHostPort("127.0.0.1", 9876))).encode(
                self.client._encoding
            ),
        )
        self.transport.clear()
        self.client.lineReceived(b"200 PORT OK")
        self.assertEqual(self.transport.value(), b"RETR spam\r\n")

        self.assertTrue(l)
        l[0].loseConnection()
        self.transport.loseConnection()
        self.assertFailure(d, ftp.ConnectionLost)
        return d

    def test_passiveSTOR(self):
        """
        Test the STOR command: send a file and verify its content.

        L{ftp.FTPClient.storeFile} should return a two-tuple of Deferreds.
        The first of which should fire with a protocol instance when the
        data connection has been established and is responsible for sending
        the contents of the file.  The second of which should fire when the
        upload has completed, the data connection has been closed, and the
        server has acknowledged receipt of the file.

        (XXX - storeFile should take a producer as an argument, instead, and
        only return a Deferred which fires when the upload has succeeded or
        failed).
        """
        tr = proto_helpers.StringTransport()

        def cbStore(sender):
            self.client.lineReceived(
                b"150 File status okay; about to open data connection."
            )
            sender.transport.write(b"x" * 1000)
            sender.finish()
            sender.connectionLost(failure.Failure(error.ConnectionDone("")))

        def cbFinish(ign):
            self.assertEqual(tr.value(), b"x" * 1000)

        def cbConnect(host, port, factory):
            self.assertEqual(host, "127.0.0.1")
            self.assertEqual(port, 12345)
            proto = factory.buildProtocol((host, port))
            proto.makeConnection(tr)

        self.client.connectFactory = cbConnect
        self._testLogin()
        d1, d2 = self.client.storeFile("spam")
        d1.addCallback(cbStore)
        d2.addCallback(cbFinish)
        self.assertEqual(self.transport.value(), b"PASV\r\n")
        self.transport.clear()
        self.client.lineReceived(passivemode_msg(self.client))
        self.assertEqual(self.transport.value(), b"STOR spam\r\n")
        self.transport.clear()
        self.client.lineReceived(b"226 Transfer Complete.")
        return defer.gatherResults([d1, d2])

    def test_failedSTOR(self):
        """
        Test a failure in the STOR command.

        If the server does not acknowledge successful receipt of the
        uploaded file, the second Deferred returned by
        L{ftp.FTPClient.storeFile} should errback with L{ftp.CommandFailed}.
        """
        tr = proto_helpers.StringTransport()

        def cbStore(sender):
            self.client.lineReceived(
                b"150 File status okay; about to open data connection."
            )
            sender.transport.write(b"x" * 1000)
            sender.finish()
            sender.connectionLost(failure.Failure(error.ConnectionDone("")))

        def cbConnect(host, port, factory):
            self.assertEqual(host, "127.0.0.1")
            self.assertEqual(port, 12345)
            proto = factory.buildProtocol((host, port))
            proto.makeConnection(tr)

        self.client.connectFactory = cbConnect
        self._testLogin()
        d1, d2 = self.client.storeFile("spam")
        d1.addCallback(cbStore)
        self.assertFailure(d2, ftp.CommandFailed)
        self.assertEqual(self.transport.value(), b"PASV\r\n")
        self.transport.clear()
        self.client.lineReceived(passivemode_msg(self.client))
        self.assertEqual(self.transport.value(), b"STOR spam\r\n")
        self.transport.clear()
        self.client.lineReceived(b"426 Transfer aborted.  Data connection closed.")
        return defer.gatherResults([d1, d2])

    def test_STOR(self):
        """
        Test the STOR command in non-passive mode.

        Like L{test_passiveSTOR} but in the configuration where the server
        establishes the data connection to the client, rather than the other
        way around.
        """
        tr = proto_helpers.StringTransport()
        self.client.passive = False

        def generatePort(portCmd):
            portCmd.text = "PORT " + ftp.encodeHostPort("127.0.0.1", 9876)
            portCmd.protocol.makeConnection(tr)

        def cbStore(sender):
            self.assertEqual(
                self.transport.value(),
                ("PORT {}\r\n".format(ftp.encodeHostPort("127.0.0.1", 9876))).encode(
                    self.client._encoding
                ),
            )
            self.transport.clear()
            self.client.lineReceived(b"200 PORT OK")
            self.assertEqual(self.transport.value(), b"STOR spam\r\n")
            self.transport.clear()
            self.client.lineReceived(
                b"150 File status okay; about to open data connection."
            )
            sender.transport.write(b"x" * 1000)
            sender.finish()
            sender.connectionLost(failure.Failure(error.ConnectionDone("")))
            self.client.lineReceived(b"226 Transfer Complete.")

        def cbFinish(ign):
            self.assertEqual(tr.value(), b"x" * 1000)

        self.client.generatePortCommand = generatePort
        self._testLogin()
        d1, d2 = self.client.storeFile("spam")
        d1.addCallback(cbStore)
        d2.addCallback(cbFinish)
        return defer.gatherResults([d1, d2])

    def test_passiveLIST(self):
        """
        Test the LIST command.

        L{ftp.FTPClient.list} should return a Deferred which fires with a
        protocol instance which was passed to list after the command has
        succeeded.

        (XXX - This is a very unfortunate API; if my understanding is
        correct, the results are always at least line-oriented, so allowing
        a per-line parser function to be specified would make this simpler,
        but a default implementation should really be provided which knows
        how to deal with all the formats used in real servers, so
        application developers never have to care about this insanity.  It
        would also be nice to either get back a Deferred of a list of
        filenames or to be able to consume the files as they are received
        (which the current API does allow, but in a somewhat inconvenient
        fashion) -exarkun)
        """

        def cbList(res, fileList):
            fls = [f["filename"] for f in fileList.files]
            expected = ["foo", "bar", "baz"]
            expected.sort()
            fls.sort()
            self.assertEqual(fls, expected)

        def cbConnect(host, port, factory):
            self.assertEqual(host, "127.0.0.1")
            self.assertEqual(port, 12345)
            proto = factory.buildProtocol((host, port))
            proto.makeConnection(proto_helpers.StringTransport())
            self.client.lineReceived(
                b"150 File status okay; about to open data connection."
            )
            sending = [
                b"-rw-r--r--    0 spam      egg      100 Oct 10 2006 foo\r\n",
                b"-rw-r--r--    3 spam      egg      100 Oct 10 2006 bar\r\n",
                b"-rw-r--r--    4 spam      egg      100 Oct 10 2006 baz\r\n",
            ]
            for i in sending:
                proto.dataReceived(i)
            proto.connectionLost(failure.Failure(error.ConnectionDone("")))

        self.client.connectFactory = cbConnect
        self._testLogin()
        fileList = ftp.FTPFileListProtocol()
        d = self.client.list("foo/bar", fileList).addCallback(cbList, fileList)
        self.assertEqual(self.transport.value(), b"PASV\r\n")
        self.transport.clear()
        self.client.lineReceived(passivemode_msg(self.client))
        self.assertEqual(self.transport.value(), b"LIST foo/bar\r\n")
        self.client.lineReceived(b"226 Transfer Complete.")
        return d

    def test_LIST(self):
        """
        Test the LIST command in non-passive mode.

        Like L{test_passiveLIST} but in the configuration where the server
        establishes the data connection to the client, rather than the other
        way around.
        """
        self.client.passive = False

        def generatePort(portCmd):
            portCmd.text = "PORT {}".format(ftp.encodeHostPort("127.0.0.1", 9876))
            portCmd.protocol.makeConnection(proto_helpers.StringTransport())
            self.client.lineReceived(
                b"150 File status okay; about to open data connection."
            )
            sending = [
                b"-rw-r--r--    0 spam      egg      100 Oct 10 2006 foo\r\n",
                b"-rw-r--r--    3 spam      egg      100 Oct 10 2006 bar\r\n",
                b"-rw-r--r--    4 spam      egg      100 Oct 10 2006 baz\r\n",
            ]
            for i in sending:
                portCmd.protocol.dataReceived(i)
            portCmd.protocol.connectionLost(failure.Failure(error.ConnectionDone("")))

        def cbList(res, fileList):
            fls = [f["filename"] for f in fileList.files]
            expected = ["foo", "bar", "baz"]
            expected.sort()
            fls.sort()
            self.assertEqual(fls, expected)

        self.client.generatePortCommand = generatePort
        self._testLogin()
        fileList = ftp.FTPFileListProtocol()
        d = self.client.list("foo/bar", fileList).addCallback(cbList, fileList)
        self.assertEqual(
            self.transport.value(),
            ("PORT {}\r\n".format(ftp.encodeHostPort("127.0.0.1", 9876))).encode(
                self.client._encoding
            ),
        )
        self.transport.clear()
        self.client.lineReceived(b"200 PORT OK")
        self.assertEqual(self.transport.value(), b"LIST foo/bar\r\n")
        self.transport.clear()
        self.client.lineReceived(b"226 Transfer Complete.")
        return d

    def test_failedLIST(self):
        """
        Test a failure in LIST command.

        L{ftp.FTPClient.list} should return a Deferred which fails with
        L{ftp.CommandFailed} if the server indicates the indicated path is
        invalid for some reason.
        """

        def cbConnect(host, port, factory):
            self.assertEqual(host, "127.0.0.1")
            self.assertEqual(port, 12345)
            proto = factory.buildProtocol((host, port))
            proto.makeConnection(proto_helpers.StringTransport())
            self.client.lineReceived(
                b"150 File status okay; about to open data connection."
            )
            proto.connectionLost(failure.Failure(error.ConnectionDone("")))

        self.client.connectFactory = cbConnect
        self._testLogin()
        fileList = ftp.FTPFileListProtocol()
        d = self.client.list("foo/bar", fileList)
        self.assertFailure(d, ftp.CommandFailed)
        self.assertEqual(self.transport.value(), b"PASV\r\n")
        self.transport.clear()
        self.client.lineReceived(passivemode_msg(self.client))
        self.assertEqual(self.transport.value(), b"LIST foo/bar\r\n")
        self.client.lineReceived(b"550 foo/bar: No such file or directory")
        return d

    def test_NLST(self):
        """
        Test the NLST command in non-passive mode.

        L{ftp.FTPClient.nlst} should return a Deferred which fires with a
        list of filenames when the list command has completed.
        """
        self.client.passive = False

        def generatePort(portCmd):
            portCmd.text = "PORT {}".format(ftp.encodeHostPort("127.0.0.1", 9876))
            portCmd.protocol.makeConnection(proto_helpers.StringTransport())
            self.client.lineReceived(
                b"150 File status okay; about to open data connection."
            )
            portCmd.protocol.dataReceived(b"foo\r\n")
            portCmd.protocol.dataReceived(b"bar\r\n")
            portCmd.protocol.dataReceived(b"baz\r\n")
            portCmd.protocol.connectionLost(failure.Failure(error.ConnectionDone("")))

        def cbList(res, proto):
            fls = proto.buffer.decode(self.client._encoding).splitlines()
            expected = ["foo", "bar", "baz"]
            expected.sort()
            fls.sort()
            self.assertEqual(fls, expected)

        self.client.generatePortCommand = generatePort
        self._testLogin()
        lstproto = _BufferingProtocol()
        d = self.client.nlst("foo/bar", lstproto).addCallback(cbList, lstproto)
        self.assertEqual(
            self.transport.value(),
            ("PORT {}\r\n".format(ftp.encodeHostPort("127.0.0.1", 9876))).encode(
                self.client._encoding
            ),
        )
        self.transport.clear()
        self.client.lineReceived(b"200 PORT OK")
        self.assertEqual(self.transport.value(), b"NLST foo/bar\r\n")
        self.client.lineReceived(b"226 Transfer Complete.")
        return d

    def test_passiveNLST(self):
        """
        Test the NLST command.

        Like L{test_passiveNLST} but in the configuration where the server
        establishes the data connection to the client, rather than the other
        way around.
        """

        def cbList(res, proto):
            fls = proto.buffer.splitlines()
            expected = [b"foo", b"bar", b"baz"]
            expected.sort()
            fls.sort()
            self.assertEqual(fls, expected)

        def cbConnect(host, port, factory):
            self.assertEqual(host, "127.0.0.1")
            self.assertEqual(port, 12345)
            proto = factory.buildProtocol((host, port))
            proto.makeConnection(proto_helpers.StringTransport())
            self.client.lineReceived(
                b"150 File status okay; about to open data connection."
            )
            proto.dataReceived(b"foo\r\n")
            proto.dataReceived(b"bar\r\n")
            proto.dataReceived(b"baz\r\n")
            proto.connectionLost(failure.Failure(error.ConnectionDone("")))

        self.client.connectFactory = cbConnect
        self._testLogin()
        lstproto = _BufferingProtocol()
        d = self.client.nlst("foo/bar", lstproto).addCallback(cbList, lstproto)
        self.assertEqual(self.transport.value(), b"PASV\r\n")
        self.transport.clear()
        self.client.lineReceived(passivemode_msg(self.client))
        self.assertEqual(self.transport.value(), b"NLST foo/bar\r\n")
        self.client.lineReceived(b"226 Transfer Complete.")
        return d

    def test_failedNLST(self):
        """
        Test a failure in NLST command.

        L{ftp.FTPClient.nlst} should return a Deferred which fails with
        L{ftp.CommandFailed} if the server indicates the indicated path is
        invalid for some reason.
        """
        tr = proto_helpers.StringTransport()

        def cbConnect(host, port, factory):
            self.assertEqual(host, "127.0.0.1")
            self.assertEqual(port, 12345)
            proto = factory.buildProtocol((host, port))
            proto.makeConnection(tr)
            self.client.lineReceived(
                b"150 File status okay; about to open data connection."
            )
            proto.connectionLost(failure.Failure(error.ConnectionDone("")))

        self.client.connectFactory = cbConnect
        self._testLogin()
        lstproto = _BufferingProtocol()
        d = self.client.nlst("foo/bar", lstproto)
        self.assertFailure(d, ftp.CommandFailed)
        self.assertEqual(self.transport.value(), b"PASV\r\n")
        self.transport.clear()
        self.client.lineReceived(passivemode_msg(self.client))
        self.assertEqual(self.transport.value(), b"NLST foo/bar\r\n")
        self.client.lineReceived(b"550 foo/bar: No such file or directory")
        return d

    def test_renameFromTo(self):
        """
        L{ftp.FTPClient.rename} issues I{RNTO} and I{RNFR} commands and returns
        a L{Deferred} which fires when a file has successfully been renamed.
        """
        self._testLogin()

        d = self.client.rename("/spam", "/ham")
        self.assertEqual(self.transport.value(), b"RNFR /spam\r\n")
        self.transport.clear()

        fromResponse = "350 Requested file action pending further information.\r\n"
        self.client.lineReceived(fromResponse.encode(self.client._encoding))
        self.assertEqual(self.transport.value(), b"RNTO /ham\r\n")
        toResponse = "250 Requested File Action Completed OK"
        self.client.lineReceived(toResponse.encode(self.client._encoding))

        d.addCallback(self.assertEqual, ([fromResponse], [toResponse]))
        return d

    def test_renameFromToEscapesPaths(self):
        """
        L{ftp.FTPClient.rename} issues I{RNTO} and I{RNFR} commands with paths
        escaped according to U{http://cr.yp.to/ftp/filesystem.html}.
        """
        self._testLogin()

        fromFile = "/foo/ba\nr/baz"
        toFile = "/qu\nux"
        self.client.rename(fromFile, toFile)
        self.client.lineReceived(b"350 ")
        self.client.lineReceived(b"250 ")
        self.assertEqual(
            self.transport.value(), b"RNFR /foo/ba\x00r/baz\r\n" b"RNTO /qu\x00ux\r\n"
        )

    def test_renameFromToFailingOnFirstError(self):
        """
        The L{Deferred} returned by L{ftp.FTPClient.rename} is errbacked with
        L{CommandFailed} if the I{RNFR} command receives an error response code
        (for example, because the file does not exist).
        """
        self._testLogin()

        d = self.client.rename("/spam", "/ham")
        self.assertEqual(self.transport.value(), b"RNFR /spam\r\n")
        self.transport.clear()

        self.client.lineReceived(b"550 Requested file unavailable.\r\n")
        # The RNTO should not execute since the RNFR failed.
        self.assertEqual(self.transport.value(), b"")

        return self.assertFailure(d, ftp.CommandFailed)

    def test_renameFromToFailingOnRenameTo(self):
        """
        The L{Deferred} returned by L{ftp.FTPClient.rename} is errbacked with
        L{CommandFailed} if the I{RNTO} command receives an error response code
        (for example, because the destination directory does not exist).
        """
        self._testLogin()

        d = self.client.rename("/spam", "/ham")
        self.assertEqual(self.transport.value(), b"RNFR /spam\r\n")
        self.transport.clear()

        self.client.lineReceived(
            b"350 Requested file action pending further information.\r\n"
        )
        self.assertEqual(self.transport.value(), b"RNTO /ham\r\n")
        self.client.lineReceived(b"550 Requested file unavailable.\r\n")
        return self.assertFailure(d, ftp.CommandFailed)

    def test_makeDirectory(self):
        """
        L{ftp.FTPClient.makeDirectory} issues a I{MKD} command and returns a
        L{Deferred} which is called back with the server's response if the
        directory is created.
        """
        self._testLogin()

        d = self.client.makeDirectory("/spam")
        self.assertEqual(self.transport.value(), b"MKD /spam\r\n")
        self.client.lineReceived(b'257 "/spam" created.')
        return d.addCallback(self.assertEqual, ['257 "/spam" created.'])

    def test_makeDirectoryPathEscape(self):
        """
        L{ftp.FTPClient.makeDirectory} escapes the path name it sends according
        to U{http://cr.yp.to/ftp/filesystem.html}.
        """
        self._testLogin()
        d = self.client.makeDirectory("/sp\nam")
        self.assertEqual(self.transport.value(), b"MKD /sp\x00am\r\n")
        # This is necessary to make the Deferred fire.  The Deferred needs
        # to fire so that tearDown doesn't cause it to errback and fail this
        # or (more likely) a later test.
        self.client.lineReceived(b"257 win")
        return d

    def test_failedMakeDirectory(self):
        """
        L{ftp.FTPClient.makeDirectory} returns a L{Deferred} which is errbacked
        with L{CommandFailed} if the server returns an error response code.
        """
        self._testLogin()

        d = self.client.makeDirectory("/spam")
        self.assertEqual(self.transport.value(), b"MKD /spam\r\n")
        self.client.lineReceived(b"550 PERMISSION DENIED")
        return self.assertFailure(d, ftp.CommandFailed)

    def test_getDirectory(self):
        """
        Test the getDirectory method.

        L{ftp.FTPClient.getDirectory} should return a Deferred which fires with
        the current directory on the server. It wraps PWD command.
        """

        def cbGet(res):
            self.assertEqual(res, "/bar/baz")

        self._testLogin()
        d = self.client.getDirectory().addCallback(cbGet)
        self.assertEqual(self.transport.value(), b"PWD\r\n")
        self.client.lineReceived(b'257 "/bar/baz"')
        return d

    def test_failedGetDirectory(self):
        """
        Test a failure in getDirectory method.

        The behaviour should be the same as PWD.
        """
        self._testLogin()
        d = self.client.getDirectory()
        self.assertFailure(d, ftp.CommandFailed)
        self.assertEqual(self.transport.value(), b"PWD\r\n")
        self.client.lineReceived(b"550 /bar/baz: No such file or directory")
        return d

    def test_anotherFailedGetDirectory(self):
        """
        Test a different failure in getDirectory method.

        The response should be quoted to be parsed, so it returns an error
        otherwise.
        """
        self._testLogin()
        d = self.client.getDirectory()
        self.assertFailure(d, ftp.CommandFailed)
        self.assertEqual(self.transport.value(), b"PWD\r\n")
        self.client.lineReceived(b"257 /bar/baz")
        return d

    def test_removeFile(self):
        """
        L{ftp.FTPClient.removeFile} sends a I{DELE} command to the server for
        the indicated file and returns a Deferred which fires after the server
        sends a 250 response code.
        """
        self._testLogin()
        d = self.client.removeFile("/tmp/test")
        self.assertEqual(self.transport.value(), b"DELE /tmp/test\r\n")
        response = "250 Requested file action okay, completed."
        self.client.lineReceived(response.encode(self.client._encoding))
        return d.addCallback(self.assertEqual, [response])

    def test_failedRemoveFile(self):
        """
        If the server returns a response code other than 250 in response to a
        I{DELE} sent by L{ftp.FTPClient.removeFile}, the L{Deferred} returned
        by C{removeFile} is errbacked with a L{Failure} wrapping a
        L{CommandFailed}.
        """
        self._testLogin()
        d = self.client.removeFile("/tmp/test")
        self.assertEqual(self.transport.value(), b"DELE /tmp/test\r\n")
        response = "501 Syntax error in parameters or arguments."
        self.client.lineReceived(response.encode(self.client._encoding))
        d = self.assertFailure(d, ftp.CommandFailed)
        d.addCallback(lambda exc: self.assertEqual(exc.args, ([response],)))
        return d

    def test_unparsableRemoveFileResponse(self):
        """
        If the server returns a response line which cannot be parsed, the
        L{Deferred} returned by L{ftp.FTPClient.removeFile} is errbacked with a
        L{BadResponse} containing the response.
        """
        self._testLogin()
        d = self.client.removeFile("/tmp/test")
        response = "765 blah blah blah"
        self.client.lineReceived(response.encode(self.client._encoding))
        d = self.assertFailure(d, ftp.BadResponse)
        d.addCallback(lambda exc: self.assertEqual(exc.args, ([response],)))
        return d

    def test_multilineRemoveFileResponse(self):
        """
        If the server returns multiple response lines, the L{Deferred} returned
        by L{ftp.FTPClient.removeFile} is still fired with a true value if the
        ultimate response code is 250.
        """
        self._testLogin()
        d = self.client.removeFile("/tmp/test")
        self.client.lineReceived(b"250-perhaps a progress report")
        self.client.lineReceived(b"250 okay")
        return d.addCallback(self.assertTrue)

    def test_removeDirectory(self):
        """
        L{ftp.FTPClient.removeDirectory} sends a I{RMD} command to the server
        for the indicated directory and returns a Deferred which fires after
        the server sends a 250 response code.
        """
        self._testLogin()
        d = self.client.removeDirectory("/tmp/test")
        self.assertEqual(self.transport.value(), b"RMD /tmp/test\r\n")
        response = "250 Requested file action okay, completed."
        self.client.lineReceived(response.encode(self.client._encoding))
        return d.addCallback(self.assertEqual, [response])

    def test_failedRemoveDirectory(self):
        """
        If the server returns a response code other than 250 in response to a
        I{RMD} sent by L{ftp.FTPClient.removeDirectory}, the L{Deferred}
        returned by C{removeDirectory} is errbacked with a L{Failure} wrapping
        a L{CommandFailed}.
        """
        self._testLogin()
        d = self.client.removeDirectory("/tmp/test")
        self.assertEqual(self.transport.value(), b"RMD /tmp/test\r\n")
        response = "501 Syntax error in parameters or arguments."
        self.client.lineReceived(response.encode(self.client._encoding))
        d = self.assertFailure(d, ftp.CommandFailed)
        d.addCallback(lambda exc: self.assertEqual(exc.args, ([response],)))
        return d

    def test_unparsableRemoveDirectoryResponse(self):
        """
        If the server returns a response line which cannot be parsed, the
        L{Deferred} returned by L{ftp.FTPClient.removeDirectory} is errbacked
        with a L{BadResponse} containing the response.
        """
        self._testLogin()
        d = self.client.removeDirectory("/tmp/test")
        response = "765 blah blah blah"
        self.client.lineReceived(response.encode(self.client._encoding))
        d = self.assertFailure(d, ftp.BadResponse)
        d.addCallback(lambda exc: self.assertEqual(exc.args, ([response],)))
        return d

    def test_multilineRemoveDirectoryResponse(self):
        """
        If the server returns multiple response lines, the L{Deferred} returned
        by L{ftp.FTPClient.removeDirectory} is still fired with a true value
         if the ultimate response code is 250.
        """
        self._testLogin()
        d = self.client.removeDirectory("/tmp/test")
        self.client.lineReceived(b"250-perhaps a progress report")
        self.client.lineReceived(b"250 okay")
        return d.addCallback(self.assertTrue)


class FTPClientBasicTests(TestCase):
    """
    FTP client
    """

    def test_greeting(self):
        """
        The first response is captured as a greeting.
        """
        ftpClient = ftp.FTPClientBasic()
        ftpClient.lineReceived(b"220 Imaginary FTP.")
        self.assertEqual(["220 Imaginary FTP."], ftpClient.greeting)

    def test_responseWithNoMessage(self):
        """
        Responses with no message are still valid, i.e. three digits
        followed by a space is complete response.
        """
        ftpClient = ftp.FTPClientBasic()
        ftpClient.lineReceived(b"220 ")
        self.assertEqual(["220 "], ftpClient.greeting)

    def test_MultilineResponse(self):
        """
        Multiline response
        """
        ftpClient = ftp.FTPClientBasic()
        ftpClient.transport = proto_helpers.StringTransport()
        ftpClient.lineReceived(b"220 Imaginary FTP.")

        # Queue (and send) a dummy command, and set up a callback
        # to capture the result
        deferred = ftpClient.queueStringCommand("BLAH")
        result = []
        deferred.addCallback(result.append)
        deferred.addErrback(self.fail)

        # Send the first line of a multiline response.
        ftpClient.lineReceived(b"210-First line.")
        self.assertEqual([], result)

        # Send a second line, again prefixed with "nnn-".
        ftpClient.lineReceived(b"123-Second line.")
        self.assertEqual([], result)

        # Send a plain line of text, no prefix.
        ftpClient.lineReceived(b"Just some text.")
        self.assertEqual([], result)

        # Now send a short (less than 4 chars) line.
        ftpClient.lineReceived(b"Hi")
        self.assertEqual([], result)

        # Now send an empty line.
        ftpClient.lineReceived(b"")
        self.assertEqual([], result)

        # And a line with 3 digits in it, and nothing else.
        ftpClient.lineReceived(b"321")
        self.assertEqual([], result)

        # Now finish it.
        ftpClient.lineReceived(b"210 Done.")
        self.assertEqual(
            [
                "210-First line.",
                "123-Second line.",
                "Just some text.",
                "Hi",
                "",
                "321",
                "210 Done.",
            ],
            result[0],
        )

    def test_noPasswordGiven(self):
        """
        Passing None as the password avoids sending the PASS command.
        """
        # Create a client, and give it a greeting.
        ftpClient = ftp.FTPClientBasic()
        ftpClient.transport = proto_helpers.StringTransport()
        ftpClient.lineReceived(b"220 Welcome to Imaginary FTP.")

        # Queue a login with no password
        ftpClient.queueLogin("bob", None)
        self.assertEqual(b"USER bob\r\n", ftpClient.transport.value())

        # Clear the test buffer, acknowledge the USER command.
        ftpClient.transport.clear()
        ftpClient.lineReceived(b"200 Hello bob.")

        # The client shouldn't have sent anything more (i.e. it shouldn't have
        # sent a PASS command).
        self.assertEqual(b"", ftpClient.transport.value())

    def test_noPasswordNeeded(self):
        """
        Receiving a 230 response to USER prevents PASS from being sent.
        """
        # Create a client, and give it a greeting.
        ftpClient = ftp.FTPClientBasic()
        ftpClient.transport = proto_helpers.StringTransport()
        ftpClient.lineReceived(b"220 Welcome to Imaginary FTP.")

        # Queue a login with no password
        ftpClient.queueLogin("bob", "secret")
        self.assertEqual(b"USER bob\r\n", ftpClient.transport.value())

        # Clear the test buffer, acknowledge the USER command with a 230
        # response code.
        ftpClient.transport.clear()
        ftpClient.lineReceived(b"230 Hello bob.  No password needed.")

        # The client shouldn't have sent anything more (i.e. it shouldn't have
        # sent a PASS command).
        self.assertEqual(b"", ftpClient.transport.value())


class PathHandlingTests(TestCase):
    """
    Handling paths.
    """

    def test_Normalizer(self):
        """
        Normalize paths.
        """
        for inp, outp in [
            ("a", ["a"]),
            ("/a", ["a"]),
            ("/", []),
            ("a/b/c", ["a", "b", "c"]),
            ("/a/b/c", ["a", "b", "c"]),
            ("/a/", ["a"]),
            ("a/", ["a"]),
        ]:
            self.assertEqual(ftp.toSegments([], inp), outp)

        for inp, outp in [
            ("b", ["a", "b"]),
            ("b/", ["a", "b"]),
            ("/b", ["b"]),
            ("/b/", ["b"]),
            ("b/c", ["a", "b", "c"]),
            ("b/c/", ["a", "b", "c"]),
            ("/b/c", ["b", "c"]),
            ("/b/c/", ["b", "c"]),
        ]:
            self.assertEqual(ftp.toSegments(["a"], inp), outp)

        for inp, outp in [
            ("//", []),
            ("//a", ["a"]),
            ("a//", ["a"]),
            ("a//b", ["a", "b"]),
        ]:
            self.assertEqual(ftp.toSegments([], inp), outp)

        for inp, outp in [("//", []), ("//b", ["b"]), ("b//c", ["a", "b", "c"])]:
            self.assertEqual(ftp.toSegments(["a"], inp), outp)

        for inp, outp in [
            ("..", []),
            ("../", []),
            ("a/..", ["x"]),
            ("/a/..", []),
            ("/a/b/..", ["a"]),
            ("/a/b/../", ["a"]),
            ("/a/b/../c", ["a", "c"]),
            ("/a/b/../c/", ["a", "c"]),
            ("/a/b/../../c", ["c"]),
            ("/a/b/../../c/", ["c"]),
            ("/a/b/../../c/..", []),
            ("/a/b/../../c/../", []),
        ]:
            self.assertEqual(ftp.toSegments(["x"], inp), outp)

        for inp in [
            "..",
            "../",
            "a/../..",
            "a/../../",
            "/..",
            "/../",
            "/a/../..",
            "/a/../../",
            "/a/b/../../..",
        ]:
            self.assertRaises(ftp.InvalidPath, ftp.toSegments, [], inp)

        for inp in ["../..", "../../", "../a/../.."]:
            self.assertRaises(ftp.InvalidPath, ftp.toSegments, ["x"], inp)


class IsGlobbingExpressionTests(TestCase):
    """
    Tests for _isGlobbingExpression utility function.
    """

    def test_isGlobbingExpressionEmptySegments(self):
        """
        _isGlobbingExpression will return False for None, or empty
        segments.
        """
        self.assertFalse(ftp._isGlobbingExpression())
        self.assertFalse(ftp._isGlobbingExpression([]))
        self.assertFalse(ftp._isGlobbingExpression(None))

    def test_isGlobbingExpressionNoGlob(self):
        """
        _isGlobbingExpression will return False for plain segments.

        Also, it only checks the last segment part (filename) and will not
        check the path name.
        """
        self.assertFalse(ftp._isGlobbingExpression(["ignore", "expr"]))
        self.assertFalse(ftp._isGlobbingExpression(["*.txt", "expr"]))

    def test_isGlobbingExpressionGlob(self):
        """
        _isGlobbingExpression will return True for segments which contains
        globbing characters in the last segment part (filename).
        """
        self.assertTrue(ftp._isGlobbingExpression(["ignore", "*.txt"]))
        self.assertTrue(ftp._isGlobbingExpression(["ignore", "[a-b].txt"]))
        self.assertTrue(ftp._isGlobbingExpression(["ignore", "fil?.txt"]))


class BaseFTPRealmTests(TestCase):
    """
    Tests for L{ftp.BaseFTPRealm}, a base class to help define L{IFTPShell}
    realms with different user home directory policies.
    """

    def test_interface(self):
        """
        L{ftp.BaseFTPRealm} implements L{IRealm}.
        """
        self.assertTrue(verifyClass(IRealm, ftp.BaseFTPRealm))

    def test_getHomeDirectory(self):
        """
        L{ftp.BaseFTPRealm} calls its C{getHomeDirectory} method with the
        avatarId being requested to determine the home directory for that
        avatar.
        """
        result = filepath.FilePath(self.mktemp())
        avatars = []

        class TestRealm(ftp.BaseFTPRealm):
            def getHomeDirectory(self, avatarId):
                avatars.append(avatarId)
                return result

        realm = TestRealm(self.mktemp())
        iface, avatar, logout = realm.requestAvatar(
            "alice@example.com", None, ftp.IFTPShell
        )
        self.assertIsInstance(avatar, ftp.FTPShell)
        self.assertEqual(avatar.filesystemRoot, result)

    def test_anonymous(self):
        """
        L{ftp.BaseFTPRealm} returns an L{ftp.FTPAnonymousShell} instance for
        anonymous avatar requests.
        """
        anonymous = self.mktemp()
        realm = ftp.BaseFTPRealm(anonymous)
        iface, avatar, logout = realm.requestAvatar(
            checkers.ANONYMOUS, None, ftp.IFTPShell
        )
        self.assertIsInstance(avatar, ftp.FTPAnonymousShell)
        self.assertEqual(avatar.filesystemRoot, filepath.FilePath(anonymous))

    def test_notImplemented(self):
        """
        L{ftp.BaseFTPRealm.getHomeDirectory} should be overridden by a subclass
        and raises L{NotImplementedError} if it is not.
        """
        realm = ftp.BaseFTPRealm(self.mktemp())
        self.assertRaises(NotImplementedError, realm.getHomeDirectory, object())


class FTPRealmTests(TestCase):
    """
    Tests for L{ftp.FTPRealm}.
    """

    def test_getHomeDirectory(self):
        """
        L{ftp.FTPRealm} accepts an extra directory to its initializer and treats
        the avatarId passed to L{ftp.FTPRealm.getHomeDirectory} as a single path
        segment to construct a child of that directory.
        """
        base = "/path/to/home"
        realm = ftp.FTPRealm(self.mktemp(), base)
        home = realm.getHomeDirectory("alice@example.com")
        self.assertEqual(filepath.FilePath(base).child("alice@example.com"), home)

    def test_defaultHomeDirectory(self):
        """
        If no extra directory is passed to L{ftp.FTPRealm}, it uses C{"/home"}
        as the base directory containing all user home directories.
        """
        realm = ftp.FTPRealm(self.mktemp())
        home = realm.getHomeDirectory("alice@example.com")
        self.assertEqual(filepath.FilePath("/home/alice@example.com"), home)


class SystemFTPRealmTests(TestCase):
    """
    Tests for L{ftp.SystemFTPRealm}.
    """

    skip = nonPOSIXSkip

    def test_getHomeDirectory(self):
        """
        L{ftp.SystemFTPRealm.getHomeDirectory} treats the avatarId passed to it
        as a username in the underlying platform and returns that account's home
        directory.
        """
        # Try to pick a username that will have a home directory.
        user = getpass.getuser()

        # Try to find their home directory in a different way than used by the
        # implementation.  Maybe this is silly and can only introduce spurious
        # failures due to system-specific configurations.
        import pwd

        expected = pwd.getpwnam(user).pw_dir

        realm = ftp.SystemFTPRealm(self.mktemp())
        home = realm.getHomeDirectory(user)
        self.assertEqual(home, filepath.FilePath(expected))

    def test_noSuchUser(self):
        """
        L{ftp.SystemFTPRealm.getHomeDirectory} raises L{UnauthorizedLogin} when
        passed a username which has no corresponding home directory in the
        system's accounts database.
        """
        # Add a prefix in case starting with a digit is a problem
        user = random.choice(string.ascii_letters) + "".join(
            random.choice(string.ascii_letters + string.digits) for _ in range(4)
        )
        realm = ftp.SystemFTPRealm(self.mktemp())
        self.assertRaises(UnauthorizedLogin, realm.getHomeDirectory, user)


class ErrnoToFailureTests(TestCase):
    """
    Tests for L{ftp.errnoToFailure} errno checking.
    """

    def test_notFound(self):
        """
        C{errno.ENOENT} should be translated to L{ftp.FileNotFoundError}.
        """
        d = ftp.errnoToFailure(errno.ENOENT, "foo")
        return self.assertFailure(d, ftp.FileNotFoundError)

    def test_permissionDenied(self):
        """
        C{errno.EPERM} should be translated to L{ftp.PermissionDeniedError}.
        """
        d = ftp.errnoToFailure(errno.EPERM, "foo")
        return self.assertFailure(d, ftp.PermissionDeniedError)

    def test_accessDenied(self):
        """
        C{errno.EACCES} should be translated to L{ftp.PermissionDeniedError}.
        """
        d = ftp.errnoToFailure(errno.EACCES, "foo")
        return self.assertFailure(d, ftp.PermissionDeniedError)

    def test_notDirectory(self):
        """
        C{errno.ENOTDIR} should be translated to L{ftp.IsNotADirectoryError}.
        """
        d = ftp.errnoToFailure(errno.ENOTDIR, "foo")
        return self.assertFailure(d, ftp.IsNotADirectoryError)

    def test_fileExists(self):
        """
        C{errno.EEXIST} should be translated to L{ftp.FileExistsError}.
        """
        d = ftp.errnoToFailure(errno.EEXIST, "foo")
        return self.assertFailure(d, ftp.FileExistsError)

    def test_isDirectory(self):
        """
        C{errno.EISDIR} should be translated to L{ftp.IsADirectoryError}.
        """
        d = ftp.errnoToFailure(errno.EISDIR, "foo")
        return self.assertFailure(d, ftp.IsADirectoryError)

    def test_passThrough(self):
        """
        If an unknown errno is passed to L{ftp.errnoToFailure}, it should let
        the originating exception pass through.
        """
        try:
            raise RuntimeError("bar")
        except BaseException:
            d = ftp.errnoToFailure(-1, "foo")
            return self.assertFailure(d, RuntimeError)


class AnonymousFTPShellTests(TestCase):
    """
    Test anonymous shell properties.
    """

    def test_anonymousWrite(self):
        """
        Check that L{ftp.FTPAnonymousShell} returns an error when trying to
        open it in write mode.
        """
        shell = ftp.FTPAnonymousShell("")
        d = shell.openForWriting(("foo",))
        self.assertFailure(d, ftp.PermissionDeniedError)
        return d


class IFTPShellTestsMixin:
    """
    Generic tests for the C{IFTPShell} interface.
    """

    def directoryExists(self, path):
        """
        Test if the directory exists at C{path}.

        @param path: the relative path to check.
        @type path: C{str}.

        @return: C{True} if C{path} exists and is a directory, C{False} if
            it's not the case
        @rtype: C{bool}
        """
        raise NotImplementedError()

    def createDirectory(self, path):
        """
        Create a directory in C{path}.

        @param path: the relative path of the directory to create, with one
            segment.
        @type path: C{str}
        """
        raise NotImplementedError()

    def fileExists(self, path):
        """
        Test if the file exists at C{path}.

        @param path: the relative path to check.
        @type path: C{str}.

        @return: C{True} if C{path} exists and is a file, C{False} if it's not
            the case.
        @rtype: C{bool}
        """
        raise NotImplementedError()

    def createFile(self, path, fileContent=b""):
        """
        Create a file named C{path} with some content.

        @param path: the relative path of the file to create, without
            directory.
        @type path: C{str}

        @param fileContent: the content of the file.
        @type fileContent: C{str}
        """
        raise NotImplementedError()

    def test_createDirectory(self):
        """
        C{directoryExists} should report correctly about directory existence,
        and C{createDirectory} should create a directory detectable by
        C{directoryExists}.
        """
        self.assertFalse(self.directoryExists("bar"))
        self.createDirectory("bar")
        self.assertTrue(self.directoryExists("bar"))

    def test_createFile(self):
        """
        C{fileExists} should report correctly about file existence, and
        C{createFile} should create a file detectable by C{fileExists}.
        """
        self.assertFalse(self.fileExists("file.txt"))
        self.createFile("file.txt")
        self.assertTrue(self.fileExists("file.txt"))

    def test_makeDirectory(self):
        """
        Create a directory and check it ends in the filesystem.
        """
        d = self.shell.makeDirectory(("foo",))

        def cb(result):
            self.assertTrue(self.directoryExists("foo"))

        return d.addCallback(cb)

    def test_makeDirectoryError(self):
        """
        Creating a directory that already exists should fail with a
        C{ftp.FileExistsError}.
        """
        self.createDirectory("foo")
        d = self.shell.makeDirectory(("foo",))
        return self.assertFailure(d, ftp.FileExistsError)

    def test_removeDirectory(self):
        """
        Try to remove a directory and check it's removed from the filesystem.
        """
        self.createDirectory("bar")
        d = self.shell.removeDirectory(("bar",))

        def cb(result):
            self.assertFalse(self.directoryExists("bar"))

        return d.addCallback(cb)

    def test_removeDirectoryOnFile(self):
        """
        removeDirectory should not work in file and fail with a
        C{ftp.IsNotADirectoryError}.
        """
        self.createFile("file.txt")
        d = self.shell.removeDirectory(("file.txt",))
        return self.assertFailure(d, ftp.IsNotADirectoryError)

    def test_removeNotExistingDirectory(self):
        """
        Removing directory that doesn't exist should fail with a
        C{ftp.FileNotFoundError}.
        """
        d = self.shell.removeDirectory(("bar",))
        return self.assertFailure(d, ftp.FileNotFoundError)

    def test_removeFile(self):
        """
        Try to remove a file and check it's removed from the filesystem.
        """
        self.createFile("file.txt")
        d = self.shell.removeFile(("file.txt",))

        def cb(res):
            self.assertFalse(self.fileExists("file.txt"))

        d.addCallback(cb)
        return d

    def test_removeFileOnDirectory(self):
        """
        removeFile should not work on directory.
        """
        self.createDirectory("ned")
        d = self.shell.removeFile(("ned",))
        return self.assertFailure(d, ftp.IsADirectoryError)

    def test_removeNotExistingFile(self):
        """
        Try to remove a non existent file, and check it raises a
        L{ftp.FileNotFoundError}.
        """
        d = self.shell.removeFile(("foo",))
        return self.assertFailure(d, ftp.FileNotFoundError)

    def test_list(self):
        """
        Check the output of the list method.
        """
        self.createDirectory("ned")
        self.createFile("file.txt")
        d = self.shell.list((".",))

        def cb(l):
            l.sort()
            self.assertEqual(l, [("file.txt", []), ("ned", [])])

        return d.addCallback(cb)

    def test_listWithStat(self):
        """
        Check the output of list with asked stats.
        """
        self.createDirectory("ned")
        self.createFile("file.txt")
        d = self.shell.list(
            (".",),
            (
                "size",
                "permissions",
            ),
        )

        def cb(l):
            l.sort()
            self.assertEqual(len(l), 2)
            self.assertEqual(l[0][0], "file.txt")
            self.assertEqual(l[1][0], "ned")
            # Size and permissions are reported differently between platforms
            # so just check they are present
            self.assertEqual(len(l[0][1]), 2)
            self.assertEqual(len(l[1][1]), 2)

        return d.addCallback(cb)

    def test_listWithInvalidStat(self):
        """
        Querying an invalid stat should result to a C{AttributeError}.
        """
        self.createDirectory("ned")
        d = self.shell.list(
            (".",),
            (
                "size",
                "whateverstat",
            ),
        )
        return self.assertFailure(d, AttributeError)

    def test_listFile(self):
        """
        Check the output of the list method on a file.
        """
        self.createFile("file.txt")
        d = self.shell.list(("file.txt",))

        def cb(l):
            l.sort()
            self.assertEqual(l, [("file.txt", [])])

        return d.addCallback(cb)

    def test_listNotExistingDirectory(self):
        """
        list on a directory that doesn't exist should fail with a
        L{ftp.FileNotFoundError}.
        """
        d = self.shell.list(("foo",))
        return self.assertFailure(d, ftp.FileNotFoundError)

    def test_access(self):
        """
        Try to access a resource.
        """
        self.createDirectory("ned")
        d = self.shell.access(("ned",))
        return d

    def test_accessNotFound(self):
        """
        access should fail on a resource that doesn't exist.
        """
        d = self.shell.access(("foo",))
        return self.assertFailure(d, ftp.FileNotFoundError)

    def test_openForReading(self):
        """
        Check that openForReading returns an object providing C{ftp.IReadFile}.
        """
        self.createFile("file.txt")
        d = self.shell.openForReading(("file.txt",))

        def cb(res):
            self.assertTrue(ftp.IReadFile.providedBy(res))

        d.addCallback(cb)
        return d

    def test_openForReadingNotFound(self):
        """
        openForReading should fail with a C{ftp.FileNotFoundError} on a file
        that doesn't exist.
        """
        d = self.shell.openForReading(("ned",))
        return self.assertFailure(d, ftp.FileNotFoundError)

    def test_openForReadingOnDirectory(self):
        """
        openForReading should not work on directory.
        """
        self.createDirectory("ned")
        d = self.shell.openForReading(("ned",))
        return self.assertFailure(d, ftp.IsADirectoryError)

    def test_openForWriting(self):
        """
        Check that openForWriting returns an object providing C{ftp.IWriteFile}.
        """
        d = self.shell.openForWriting(("foo",))

        def cb1(res):
            self.assertTrue(ftp.IWriteFile.providedBy(res))
            return res.receive().addCallback(cb2)

        def cb2(res):
            self.assertTrue(IConsumer.providedBy(res))

        d.addCallback(cb1)
        return d

    def test_openForWritingExistingDirectory(self):
        """
        openForWriting should not be able to open a directory that already
        exists.
        """
        self.createDirectory("ned")
        d = self.shell.openForWriting(("ned",))
        return self.assertFailure(d, ftp.IsADirectoryError)

    def test_openForWritingInNotExistingDirectory(self):
        """
        openForWring should fail with a L{ftp.FileNotFoundError} if you specify
        a file in a directory that doesn't exist.
        """
        self.createDirectory("ned")
        d = self.shell.openForWriting(("ned", "idonotexist", "foo"))
        return self.assertFailure(d, ftp.FileNotFoundError)

    def test_statFile(self):
        """
        Check the output of the stat method on a file.
        """
        fileContent = b"wobble\n"
        self.createFile("file.txt", fileContent)
        d = self.shell.stat(("file.txt",), ("size", "directory"))

        def cb(res):
            self.assertEqual(res[0], len(fileContent))
            self.assertFalse(res[1])

        d.addCallback(cb)
        return d

    def test_statDirectory(self):
        """
        Check the output of the stat method on a directory.
        """
        self.createDirectory("ned")
        d = self.shell.stat(("ned",), ("size", "directory"))

        def cb(res):
            self.assertTrue(res[1])

        d.addCallback(cb)
        return d

    def test_statOwnerGroup(self):
        """
        Check the owner and groups stats.
        """
        self.createDirectory("ned")
        d = self.shell.stat(("ned",), ("owner", "group"))

        def cb(res):
            self.assertEqual(len(res), 2)

        d.addCallback(cb)
        return d

    def test_statHardlinksNotImplemented(self):
        """
        If L{twisted.python.filepath.FilePath.getNumberOfHardLinks} is not
        implemented, the number returned is 0
        """
        pathFunc = self.shell._path

        def raiseNotImplemented():
            raise NotImplementedError

        def notImplementedFilePath(path):
            f = pathFunc(path)
            f.getNumberOfHardLinks = raiseNotImplemented
            return f

        self.shell._path = notImplementedFilePath

        self.createDirectory("ned")
        d = self.shell.stat(("ned",), ("hardlinks",))
        self.assertEqual(self.successResultOf(d), [0])

    def test_statOwnerGroupNotImplemented(self):
        """
        If L{twisted.python.filepath.FilePath.getUserID} or
        L{twisted.python.filepath.FilePath.getGroupID} are not implemented,
        the owner returned is "0" and the group is returned as "0"
        """
        pathFunc = self.shell._path

        def raiseNotImplemented():
            raise NotImplementedError

        def notImplementedFilePath(path):
            f = pathFunc(path)
            f.getUserID = raiseNotImplemented
            f.getGroupID = raiseNotImplemented
            return f

        self.shell._path = notImplementedFilePath

        self.createDirectory("ned")
        d = self.shell.stat(("ned",), ("owner", "group"))
        self.assertEqual(self.successResultOf(d), ["0", "0"])

    def test_statNotExisting(self):
        """
        stat should fail with L{ftp.FileNotFoundError} on a file that doesn't
        exist.
        """
        d = self.shell.stat(("foo",), ("size", "directory"))
        return self.assertFailure(d, ftp.FileNotFoundError)

    def test_invalidStat(self):
        """
        Querying an invalid stat should result to a C{AttributeError}.
        """
        self.createDirectory("ned")
        d = self.shell.stat(("ned",), ("size", "whateverstat"))
        return self.assertFailure(d, AttributeError)

    def test_rename(self):
        """
        Try to rename a directory.
        """
        self.createDirectory("ned")
        d = self.shell.rename(("ned",), ("foo",))

        def cb(res):
            self.assertTrue(self.directoryExists("foo"))
            self.assertFalse(self.directoryExists("ned"))

        return d.addCallback(cb)

    def test_renameNotExisting(self):
        """
        Renaming a directory that doesn't exist should fail with
        L{ftp.FileNotFoundError}.
        """
        d = self.shell.rename(("foo",), ("bar",))
        return self.assertFailure(d, ftp.FileNotFoundError)


class FTPShellTests(TestCase, IFTPShellTestsMixin):
    """
    Tests for the C{ftp.FTPShell} object.
    """

    def setUp(self):
        """
        Create a root directory and instantiate a shell.
        """
        self.root = filepath.FilePath(self.mktemp())
        self.root.createDirectory()
        self.shell = ftp.FTPShell(self.root)

    def directoryExists(self, path):
        """
        Test if the directory exists at C{path}.
        """
        return self.root.child(path).isdir()

    def createDirectory(self, path):
        """
        Create a directory in C{path}.
        """
        return self.root.child(path).createDirectory()

    def fileExists(self, path):
        """
        Test if the file exists at C{path}.
        """
        return self.root.child(path).isfile()

    def createFile(self, path, fileContent=b""):
        """
        Create a file named C{path} with some content.
        """
        return self.root.child(path).setContent(fileContent)


@implementer(IConsumer)
class TestConsumer:
    """
    A simple consumer for tests. It only works with non-streaming producers.

    @ivar producer: an object providing
        L{twisted.internet.interfaces.IPullProducer}.
    """

    producer = None

    def registerProducer(self, producer, streaming):
        """
        Simple register of producer, checks that no register has happened
        before.

        @param producer: pull producer to use
        @param streaming: unused
        """
        assert self.producer is None
        self.buffer = []
        self.producer = producer
        self.producer.resumeProducing()

    def unregisterProducer(self):
        """
        Unregister the producer, it should be done after a register.
        """
        assert self.producer is not None
        self.producer = None

    def write(self, data):
        """
        Save the data received.

        @param data: data to append
        """
        self.buffer.append(data)
        self.producer.resumeProducing()


class TestProducer:
    """
    A dumb producer.
    """

    def __init__(self, toProduce, consumer):
        """
        @param toProduce: data to write
        @type toProduce: C{str}
        @param consumer: the consumer of data.
        @type consumer: C{IConsumer}
        """
        self.toProduce = toProduce
        self.consumer = consumer

    def start(self):
        """
        Send the data to consume.
        """
        self.consumer.write(self.toProduce)


class IReadWriteTestsMixin:
    """
    Generic tests for the C{IReadFile} and C{IWriteFile} interfaces.
    """

    def getFileReader(self, content):
        """
        Return an object providing C{IReadFile}, ready to send data C{content}.

        @param content: data to send
        """
        raise NotImplementedError()

    def getFileWriter(self):
        """
        Return an object providing C{IWriteFile}, ready to receive data.
        """
        raise NotImplementedError()

    def getFileContent(self):
        """
        Return the content of the file used.
        """
        raise NotImplementedError()

    def test_read(self):
        """
        Test L{ftp.IReadFile}: the implementation should have a send method
        returning a C{Deferred} which fires when all the data has been sent
        to the consumer, and the data should be correctly send to the consumer.
        """
        content = b"wobble\n"
        consumer = TestConsumer()

        def cbGet(reader):
            return reader.send(consumer).addCallback(cbSend)

        def cbSend(res):
            self.assertEqual(b"".join(consumer.buffer), content)

        return self.getFileReader(content).addCallback(cbGet)

    def test_write(self):
        """
        Test L{ftp.IWriteFile}: the implementation should have a receive
        method returning a C{Deferred} which fires with a consumer ready to
        receive data to be written. It should also have a close() method that
        returns a Deferred.
        """
        content = b"elbbow\n"

        def cbGet(writer):
            return writer.receive().addCallback(cbReceive, writer)

        def cbReceive(consumer, writer):
            producer = TestProducer(content, consumer)
            consumer.registerProducer(None, True)
            producer.start()
            consumer.unregisterProducer()
            return writer.close().addCallback(cbClose)

        def cbClose(ignored):
            self.assertEqual(self.getFileContent(), content)

        return self.getFileWriter().addCallback(cbGet)


class FTPReadWriteTests(TestCase, IReadWriteTestsMixin):
    """
    Tests for C{ftp._FileReader} and C{ftp._FileWriter}, the objects returned
    by the shell in C{openForReading}/C{openForWriting}.
    """

    def setUp(self):
        """
        Create a temporary file used later.
        """
        self.root = filepath.FilePath(self.mktemp())
        self.root.createDirectory()
        self.shell = ftp.FTPShell(self.root)
        self.filename = "file.txt"

    def getFileReader(self, content):
        """
        Return a C{ftp._FileReader} instance with a file opened for reading.
        """
        self.root.child(self.filename).setContent(content)
        return self.shell.openForReading((self.filename,))

    def getFileWriter(self):
        """
        Return a C{ftp._FileWriter} instance with a file opened for writing.
        """
        return self.shell.openForWriting((self.filename,))

    def getFileContent(self):
        """
        Return the content of the temporary file.
        """
        return self.root.child(self.filename).getContent()


@implementer(ftp.IWriteFile)
class CloseTestWriter:
    """
    Close writing to a file.
    """

    closeStarted = False

    def receive(self):
        """
        Receive bytes.

        @return: L{Deferred}
        """
        self.buffer = BytesIO()
        fc = ftp.FileConsumer(self.buffer)
        return defer.succeed(fc)

    def close(self):
        """
        Close bytes.

        @return: L{Deferred}
        """
        self.closeStarted = True
        return self.d


class CloseTestShell:
    """
    Close writing shell.
    """

    def openForWriting(self, segs):
        return defer.succeed(self.writer)


class FTPCloseTests(TestCase):
    """
    Tests that the server invokes IWriteFile.close
    """

    def test_write(self):
        """
        Confirm that FTP uploads (i.e. ftp_STOR) correctly call and wait
        upon the IWriteFile object's close() method
        """
        f = ftp.FTP()
        f.workingDirectory = ["root"]
        f.shell = CloseTestShell()
        f.shell.writer = CloseTestWriter()
        f.shell.writer.d = defer.Deferred()
        f.factory = ftp.FTPFactory()
        f.factory.timeOut = None
        f.makeConnection(BytesIO())

        di = ftp.DTP()
        di.factory = ftp.DTPFactory(f)
        f.dtpInstance = di
        di.makeConnection(None)

        stor_done = []
        d = f.ftp_STOR("path")
        d.addCallback(stor_done.append)
        # the writer is still receiving data
        self.assertFalse(f.shell.writer.closeStarted, "close() called early")
        di.dataReceived(b"some data here")
        self.assertFalse(f.shell.writer.closeStarted, "close() called early")
        di.connectionLost("reason is ignored")
        # now we should be waiting in close()
        self.assertTrue(f.shell.writer.closeStarted, "close() not called")
        self.assertFalse(stor_done)
        f.shell.writer.d.callback("allow close() to finish")
        self.assertTrue(stor_done)

        return d  # just in case an errback occurred


class FTPResponseCodeTests(TestCase):
    """
    Tests relating directly to response codes.
    """

    def test_unique(self):
        """
        All of the response code globals (for example C{RESTART_MARKER_REPLY} or
        C{USR_NAME_OK_NEED_PASS}) have unique values and are present in the
        C{RESPONSE} dictionary.
        """
        allValues = set(ftp.RESPONSE)
        seenValues = set()

        for key, value in vars(ftp).items():
            if isinstance(value, str) and key.isupper():
                self.assertIn(
                    value,
                    allValues,
                    "Code {!r} with value {!r} missing from RESPONSE dict".format(
                        key, value
                    ),
                )
                self.assertNotIn(
                    value,
                    seenValues,
                    f"Duplicate code {key!r} with value {value!r}",
                )
                seenValues.add(value)
