# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for the 'session' channel implementation in twisted.conch.ssh.session.

See also RFC 4254.
"""


import os
import signal
import struct
import sys
from unittest import skipIf

from zope.interface import implementer

from twisted.internet import defer, error, protocol
from twisted.internet.address import IPv4Address
from twisted.internet.error import ProcessDone, ProcessTerminated
from twisted.python import components, failure
from twisted.python.failure import Failure
from twisted.python.reflect import requireModule
from twisted.python.test.test_components import RegistryUsingMixin
from twisted.trial.unittest import TestCase

cryptography = requireModule("cryptography")

if cryptography:
    from twisted.conch.ssh import common, connection, session
else:

    class session:  # type: ignore[no-redef]
        from twisted.conch.interfaces import (
            EnvironmentVariableNotPermitted,
            ISession,
            ISessionSetEnv,
        )


class SubsystemOnlyAvatar:
    """
    A stub class representing an avatar that is only useful for
    getting a subsystem.
    """

    def lookupSubsystem(self, name, data):
        """
        If the other side requests the 'subsystem' subsystem, allow it by
        returning a MockProtocol to implement it. Otherwise raise an assertion.
        """
        assert name == b"subsystem"
        return MockProtocol()


class StubAvatar:
    """
    A stub class representing the avatar representing the authenticated user.
    It implements the I{ISession} interface.
    """

    def lookupSubsystem(self, name, data):
        """
        If the user requests the TestSubsystem subsystem, connect them to a
        MockProtocol.  If they request neither, then None is returned which is
        interpreted by SSHSession as a failure.
        """
        if name == b"TestSubsystem":
            self.subsystem = MockProtocol()
            self.subsystem.packetData = data
            return self.subsystem


@implementer(session.ISession)
class StubSessionForStubAvatar:
    """
    A stub ISession implementation for our StubAvatar.  The instance
    variables generally keep track of method invocations so that we can test
    that the methods were called.

    @ivar avatar: the L{StubAvatar} we are adapting.
    @ivar ptyRequest: if present, the terminal, window size, and modes passed
        to the getPty method.
    @ivar windowChange: if present, the window size passed to the
        windowChangned method.
    @ivar shellProtocol: if present, the L{SSHSessionProcessProtocol} passed
        to the openShell method.
    @ivar shellTransport: if present, the L{EchoTransport} connected to
        shellProtocol.
    @ivar execProtocol: if present, the L{SSHSessionProcessProtocol} passed
        to the execCommand method.
    @ivar execTransport: if present, the L{EchoTransport} connected to
        execProtocol.
    @ivar execCommandLine: if present, the command line passed to the
        execCommand method.
    @ivar gotEOF: if present, an EOF message was received.
    @ivar gotClosed: if present, a closed message was received.
    """

    def __init__(self, avatar):
        """
        Store the avatar we're adapting.
        """
        self.avatar = avatar
        self.shellProtocol = None

    def getPty(self, terminal, window, modes):
        """
        If the terminal is 'bad', fail.  Otherwise, store the information in
        the ptyRequest variable.
        """
        if terminal != b"bad":
            self.ptyRequest = (terminal, window, modes)
        else:
            raise RuntimeError("not getting a pty")

    def windowChanged(self, window):
        """
        If all the window sizes are 0, fail.  Otherwise, store the size in the
        windowChange variable.
        """
        if window == (0, 0, 0, 0):
            raise RuntimeError("not changing the window size")
        else:
            self.windowChange = window

    def openShell(self, pp):
        """
        If we have gotten a shell request before, fail.  Otherwise, store the
        process protocol in the shellProtocol variable, connect it to the
        EchoTransport and store that as shellTransport.
        """
        if self.shellProtocol is not None:
            raise RuntimeError("not getting a shell this time")
        else:
            self.shellProtocol = pp
            self.shellTransport = EchoTransport(pp)

    def execCommand(self, pp, command):
        """
        If the command is 'true', store the command, the process protocol, and
        the transport we connect to the process protocol.  Otherwise, just
        store the command and raise an error.
        """
        self.execCommandLine = command
        if command == b"success":
            self.execProtocol = pp
        elif command[:6] == b"repeat":
            self.execProtocol = pp
            self.execTransport = EchoTransport(pp)
            pp.outReceived(command[7:])
        else:
            raise RuntimeError("not getting a command")

    def eofReceived(self):
        """
        Note that EOF has been received.
        """
        self.gotEOF = True

    def closed(self):
        """
        Note that close has been received.
        """
        self.gotClosed = True


@implementer(session.ISessionSetEnv)
class StubSessionForStubAvatarWithEnv(StubSessionForStubAvatar):
    """
    Same as StubSessionForStubAvatar, but supporting environment variables
    setting.

    End users would want to have the same class annotated with
    C{@implementer(session.ISession, session.ISessionSetEnv)}. The interfaces
    are split for backwards compatibility, so we split it here to test
    this compatibility too.

    @ivar environ: a L{dict} of environment variables passed to the setEnv
    method.
    """

    def __init__(self, avatar):
        super().__init__(avatar)
        # The representation of the environment as updated by remote requests.
        self.environ = {}
        # A snapshot of the environment when PTY request is received.
        self.environAtPty = {}

    def setEnv(self, name, value):
        """
        If the requested environment variable is 'FAIL', fail.  If it is
        'IGNORED', raise EnvironmentVariableNotPermitted, which should cause
        it to be silently ignored.  Otherwise, store the requested
        environment variable.

        (Real applications should normally implement an allowed list rather
        than a blocked list.)
        """
        if name == b"FAIL":
            raise RuntimeError("disallowed environment variable name")
        elif name == b"IGNORED":
            raise session.EnvironmentVariableNotPermitted(
                "ignored environment variable name"
            )
        else:
            self.environ[name] = value

    def getPty(self, term, windowSize, modes):
        """
        Just a simple implementation which records the current environment
        when PTY is requested.
        """
        self.environAtPty = self.environ.copy()


class EchoTransport:
    """
    A transport for a ProcessProtocol which echos data that is sent to it with
    a Window newline (CR LF) appended to it.  If a null byte is in the data,
    disconnect.  When we are asked to disconnect, disconnect the
    C{ProcessProtocol} with a 0 exit code.

    @ivar proto: the C{ProcessProtocol} connected to us.
    @ivar data: a L{bytes} of data written to us.
    """

    def __init__(self, processProtocol):
        """
        Initialize our instance variables.

        @param processProtocol: a C{ProcessProtocol} to connect to ourself.
        """
        self.proto = processProtocol
        self.closed = False
        self.data = b""
        processProtocol.makeConnection(self)

    def write(self, data):
        """
        We got some data.  Give it back to our C{ProcessProtocol} with
        a newline attached.  Disconnect if there's a null byte.
        """
        self.data += data
        self.proto.outReceived(data)
        self.proto.outReceived(b"\r\n")
        if b"\x00" in data:  # mimic 'exit' for the shell test
            self.loseConnection()

    def loseConnection(self):
        """
        If we're asked to disconnect (and we haven't already) shut down
        the C{ProcessProtocol} with a 0 exit code.
        """
        if self.closed:
            return
        self.closed = 1
        self.proto.inConnectionLost()
        self.proto.outConnectionLost()
        self.proto.errConnectionLost()
        self.proto.processEnded(failure.Failure(error.ProcessTerminated(0, None, None)))


class MockProtocol(protocol.Protocol):
    """
    A sample Protocol which stores the data passed to it.

    @ivar packetData: a L{bytes} of data to be sent when the connection is
        made.
    @ivar data: a L{bytes} of the data passed to us.
    @ivar open: True if the channel is open.
    @ivar reason: if not None, the reason the protocol was closed.
    """

    packetData = b""

    def connectionMade(self):
        """
        Set up the instance variables.  If we have any packetData, send it
        along.
        """

        self.data = b""
        self.open = True
        self.reason = None
        if self.packetData:
            self.dataReceived(self.packetData)

    def dataReceived(self, data):
        """
        Store the received data and write it back with a tilde appended.
        The tilde is appended so that the tests can verify that we processed
        the data.
        """
        self.data += data
        self.transport.write(data + b"~")

    def connectionLost(self, reason):
        """
        Close the protocol and store the reason.
        """
        self.open = False
        self.reason = reason


class StubConnection:
    """
    A stub for twisted.conch.ssh.connection.SSHConnection.  Record the data
    that channels send, and when they try to close the connection.

    @ivar data: a L{dict} mapping C{SSHChannel}s to a C{list} of L{bytes} of
        data they sent.
    @ivar extData: a L{dict} mapping L{SSHChannel}s to a C{list} of L{tuple} of
        (L{int}, L{bytes}) of extended data they sent.
    @ivar requests: a L{dict} mapping L{SSHChannel}s to a C{list} of L{tuple}
        of (L{str}, L{bytes}) of channel requests they made.
    @ivar eofs: a L{dict} mapping L{SSHChannel}s to C{true} if they have sent
        an EOF.
    @ivar closes: a L{dict} mapping L{SSHChannel}s to C{true} if they have sent
        a close.
    """

    def __init__(self, transport=None):
        """
        Initialize our instance variables.
        """
        self.data = {}
        self.extData = {}
        self.requests = {}
        self.eofs = {}
        self.closes = {}
        self.transport = transport

    def logPrefix(self):
        """
        Return our logging prefix.
        """
        return "MockConnection"

    def sendData(self, channel, data):
        """
        Record the sent data.
        """
        if self.closes.get(channel):
            return
        self.data.setdefault(channel, []).append(data)

    def sendExtendedData(self, channel, type, data):
        """
        Record the sent extended data.
        """
        if self.closes.get(channel):
            return
        self.extData.setdefault(channel, []).append((type, data))

    def sendRequest(self, channel, request, data, wantReply=False):
        """
        Record the sent channel request.
        """
        if self.closes.get(channel):
            return
        self.requests.setdefault(channel, []).append((request, data, wantReply))
        if wantReply:
            return defer.succeed(None)

    def sendEOF(self, channel):
        """
        Record the sent EOF.
        """
        if self.closes.get(channel):
            return
        self.eofs[channel] = True

    def sendClose(self, channel):
        """
        Record the sent close.
        """
        self.closes[channel] = True


class StubTransport:
    """
    A stub transport which records the data written.

    @ivar buf: the data sent to the transport.
    @type buf: L{bytes}

    @ivar close: flags indicating if the transport has been closed.
    @type close: L{bool}
    """

    buf = b""
    close = False

    def getPeer(self):
        """
        Return an arbitrary L{IAddress}.
        """
        return IPv4Address("TCP", "remotehost", 8888)

    def getHost(self):
        """
        Return an arbitrary L{IAddress}.
        """
        return IPv4Address("TCP", "localhost", 9999)

    def write(self, data):
        """
        Record data in the buffer.
        """
        self.buf += data

    def loseConnection(self):
        """
        Note that the connection was closed.
        """
        self.close = True

    def setTcpNoDelay(self, enabled):
        """
        Pretend to set C{TCP_NODELAY}.
        """
        # Required for testing SSHSessionForUnixConchUser.


class StubTransportWithWriteErr(StubTransport):
    """
    A version of StubTransport which records the error data sent to it.

    @ivar err: the extended data sent to the transport.
    @type err: L{bytes}
    """

    err = b""

    def writeErr(self, data):
        """
        Record the extended data in the buffer.  This was an old interface
        that allowed the Transports from ISession.openShell() or
        ISession.execCommand() to receive extended data from the client.
        """
        self.err += data


class StubClient:
    """
    A stub class representing the client to a SSHSession.

    @ivar transport: A L{StubTransport} object which keeps track of the data
        passed to it.
    """

    def __init__(self):
        self.transport = StubTransportWithWriteErr()


class SessionInterfaceTests(RegistryUsingMixin, TestCase):
    """
    Tests for the SSHSession class interface.  This interface is not ideal, but
    it is tested in order to maintain backwards compatibility.
    """

    if not cryptography:
        skip = "cannot run without cryptography"

    def setUp(self, register_adapters=True):
        """
        Make an SSHSession object to test.  Give the channel some window
        so that it's allowed to send packets.  500 and 100 are arbitrary
        values.
        """
        RegistryUsingMixin.setUp(self)
        self.session = self.getSSHSession()
        if register_adapters:
            components.registerAdapter(
                StubSessionForStubAvatarWithEnv, StubAvatar, session.ISession
            )
        self.session = self.getSSHSession()

    def getSSHSession(self, register_adapters=True):
        """
        Return a new SSH session.
        """
        return session.SSHSession(
            remoteWindow=500,
            remoteMaxPacket=100,
            conn=StubConnection(),
            avatar=StubAvatar(),
        )

    def assertSessionIsStubSession(self):
        """
        Asserts that self.session.session is an instance of
        StubSessionForStubOldAvatar.
        """
        self.assertIsInstance(self.session.session, StubSessionForStubAvatar)

    def test_init(self):
        """
        SSHSession initializes its buffer (buf), client, and ISession adapter.
        The avatar should not need to be adaptable to an ISession immediately.
        """
        s = session.SSHSession(avatar=object)  # use object because it doesn't
        # have an adapter
        self.assertEqual(s.buf, b"")
        self.assertIsNone(s.client)
        self.assertIsNone(s.session)

    def test_client_dataReceived(self):
        """
        SSHSession.dataReceived() passes data along to a client.  If the data
        comes before there is a client, the data should be discarded.
        """
        self.session.dataReceived(b"1")
        self.session.client = StubClient()
        self.session.dataReceived(b"2")
        self.assertEqual(self.session.client.transport.buf, b"2")

    def test_client_extReceived(self):
        """
        SSHSession.extReceived() passed data of type EXTENDED_DATA_STDERR along
        to the client.  If the data comes before there is a client, or if the
        data is not of type EXTENDED_DATA_STDERR, it is discared.
        """
        self.session.extReceived(connection.EXTENDED_DATA_STDERR, b"1")
        self.session.extReceived(255, b"2")  # 255 is arbitrary
        self.session.client = StubClient()
        self.session.extReceived(connection.EXTENDED_DATA_STDERR, b"3")
        self.assertEqual(self.session.client.transport.err, b"3")

    def test_client_extReceivedWithoutWriteErr(self):
        """
        SSHSession.extReceived() should handle the case where the transport
        on the client doesn't have a writeErr method.
        """
        client = self.session.client = StubClient()
        client.transport = StubTransport()  # doesn't have writeErr

        # should not raise an error
        self.session.extReceived(connection.EXTENDED_DATA_STDERR, b"ignored")

    def test_client_closed(self):
        """
        SSHSession.closed() should tell the transport connected to the client
        that the connection was lost.
        """
        self.session.client = StubClient()
        self.session.closed()
        self.assertTrue(self.session.client.transport.close)
        self.session.client.transport.close = False

    def test_client_closed_with_env_subsystem(self):
        """
        If the peer requests an environment variable in its setup process
        followed by requesting a subsystem, SSHSession.closed() should tell
        the transport connected to the client that the connection was lost.
        """
        self.assertTrue(
            self.session.requestReceived(b"env", common.NS(b"FOO") + common.NS(b"bar"))
        )
        self.assertTrue(
            self.session.requestReceived(
                b"subsystem", common.NS(b"TestSubsystem") + b"data"
            )
        )
        self.session.client = StubClient()
        self.session.closed()
        self.assertTrue(self.session.client.transport.close)
        self.session.client.transport.close = False

    def test_badSubsystemDoesNotCreateClient(self):
        """
        When a subsystem request fails, SSHSession.client should not be set.
        """
        ret = self.session.requestReceived(b"subsystem", common.NS(b"BadSubsystem"))
        self.assertFalse(ret)
        self.assertIsNone(self.session.client)

    def test_lookupSubsystem(self):
        """
        When a client requests a subsystem, the SSHSession object should get
        the subsystem by calling avatar.lookupSubsystem, and attach it as
        the client.
        """
        ret = self.session.requestReceived(
            b"subsystem", common.NS(b"TestSubsystem") + b"data"
        )
        self.assertTrue(ret)
        self.assertIsInstance(self.session.client, protocol.ProcessProtocol)
        self.assertIs(
            self.session.client.transport.proto, self.session.avatar.subsystem
        )

    def test_lookupSubsystemDoesNotNeedISession(self):
        """
        Previously, if one only wanted to implement a subsystem, an ISession
        adapter wasn't needed because subsystems were looked up using the
        lookupSubsystem method on the avatar.
        """
        s = session.SSHSession(avatar=SubsystemOnlyAvatar(), conn=StubConnection())
        ret = s.request_subsystem(common.NS(b"subsystem") + b"data")
        self.assertTrue(ret)
        self.assertIsNotNone(s.client)
        self.assertIsNone(s.conn.closes.get(s))
        s.eofReceived()
        self.assertTrue(s.conn.closes.get(s))
        # these should not raise errors
        s.loseConnection()
        s.closed()

    def test_lookupSubsystem_data(self):
        """
        After having looked up a subsystem, data should be passed along to the
        client.  Additionally, subsystems were passed the entire request packet
        as data, instead of just the additional data.

        We check for the additional tidle to verify that the data passed
        through the client.
        """
        # self.session.dataReceived('1')
        # subsystems didn't get extended data
        # self.session.extReceived(connection.EXTENDED_DATA_STDERR, '2')

        self.session.requestReceived(
            b"subsystem", common.NS(b"TestSubsystem") + b"data"
        )

        self.assertEqual(
            self.session.conn.data[self.session],
            [b"\x00\x00\x00\x0dTestSubsystemdata~"],
        )
        self.session.dataReceived(b"more data")
        self.assertEqual(self.session.conn.data[self.session][-1], b"more data~")

    def test_lookupSubsystem_closeReceived(self):
        """
        SSHSession.closeReceived() should sent a close message to the remote
        side.
        """
        self.session.requestReceived(
            b"subsystem", common.NS(b"TestSubsystem") + b"data"
        )

        self.session.closeReceived()
        self.assertTrue(self.session.conn.closes[self.session])

    def assertRequestRaisedRuntimeError(self):
        """
        Assert that the request we just made raised a RuntimeError (and only a
        RuntimeError).
        """
        errors = self.flushLoggedErrors(RuntimeError)
        self.assertEqual(
            len(errors),
            1,
            "Multiple RuntimeErrors raised: %s"
            % "\n".join([repr(error) for error in errors]),
        )
        errors[0].trap(RuntimeError)

    def test_requestShell(self):
        """
        When a client requests a shell, the SSHSession object should get
        the shell by getting an ISession adapter for the avatar, then
        calling openShell() with a ProcessProtocol to attach.
        """
        # gets a shell the first time
        ret = self.session.requestReceived(b"shell", b"")
        self.assertTrue(ret)
        self.assertSessionIsStubSession()
        self.assertIsInstance(self.session.client, session.SSHSessionProcessProtocol)
        self.assertIs(self.session.session.shellProtocol, self.session.client)
        # doesn't get a shell the second time
        self.assertFalse(self.session.requestReceived(b"shell", b""))
        self.assertRequestRaisedRuntimeError()

    def test_requestShellWithData(self):
        """
        When a client executes a shell, it should be able to give pass data
        back and forth between the local and the remote side.
        """
        ret = self.session.requestReceived(b"shell", b"")
        self.assertTrue(ret)
        self.assertSessionIsStubSession()
        self.session.dataReceived(b"some data\x00")
        self.assertEqual(self.session.session.shellTransport.data, b"some data\x00")
        self.assertEqual(
            self.session.conn.data[self.session], [b"some data\x00", b"\r\n"]
        )
        self.assertTrue(self.session.session.shellTransport.closed)
        self.assertEqual(
            self.session.conn.requests[self.session],
            [(b"exit-status", b"\x00\x00\x00\x00", False)],
        )

    def test_requestExec(self):
        """
        When a client requests a command, the SSHSession object should get
        the command by getting an ISession adapter for the avatar, then
        calling execCommand with a ProcessProtocol to attach and the
        command line.
        """
        ret = self.session.requestReceived(b"exec", common.NS(b"failure"))
        self.assertFalse(ret)
        self.assertRequestRaisedRuntimeError()
        self.assertIsNone(self.session.client)

        self.assertTrue(self.session.requestReceived(b"exec", common.NS(b"success")))
        self.assertSessionIsStubSession()
        self.assertIsInstance(self.session.client, session.SSHSessionProcessProtocol)
        self.assertIs(self.session.session.execProtocol, self.session.client)
        self.assertEqual(self.session.session.execCommandLine, b"success")

    def test_requestExecWithData(self):
        """
        When a client executes a command, it should be able to give pass data
        back and forth.
        """
        ret = self.session.requestReceived(b"exec", common.NS(b"repeat hello"))
        self.assertTrue(ret)
        self.assertSessionIsStubSession()
        self.session.dataReceived(b"some data")
        self.assertEqual(self.session.session.execTransport.data, b"some data")
        self.assertEqual(
            self.session.conn.data[self.session], [b"hello", b"some data", b"\r\n"]
        )
        self.session.eofReceived()
        self.session.closeReceived()
        self.session.closed()
        self.assertTrue(self.session.session.execTransport.closed)
        self.assertEqual(
            self.session.conn.requests[self.session],
            [(b"exit-status", b"\x00\x00\x00\x00", False)],
        )

    def test_requestPty(self):
        """
        When a client requests a PTY, the SSHSession object should make
        the request by getting an ISession adapter for the avatar, then
        calling getPty with the terminal type, the window size, and any modes
        the client gave us.
        """
        # Cleanup the registered adapters from setUp.
        self.doCleanups()
        self.setUp(register_adapters=False)
        components.registerAdapter(
            StubSessionForStubAvatar, StubAvatar, session.ISession
        )
        test_session = self.getSSHSession()

        # 'bad' terminal type fails
        ret = test_session.requestReceived(
            b"pty_req", session.packRequest_pty_req(b"bad", (1, 2, 3, 4), b"")
        )
        self.assertFalse(ret)
        self.assertIsInstance(test_session.session, StubSessionForStubAvatar)
        self.assertRequestRaisedRuntimeError()
        # 'good' terminal type succeeds
        self.assertTrue(
            test_session.requestReceived(
                b"pty_req", session.packRequest_pty_req(b"good", (1, 2, 3, 4), b"")
            )
        )
        self.assertEqual(test_session.session.ptyRequest, (b"good", (1, 2, 3, 4), []))

    def test_setEnv(self):
        """
        When a client requests passing an environment variable, the
        SSHSession object should make the request by getting an
        ISessionSetEnv adapter for the avatar, then calling setEnv with the
        environment variable name and value.
        """
        # Blocked environment variable name fails.
        self.assertFalse(
            self.session.requestReceived(b"env", common.NS(b"FAIL") + common.NS(b"bad"))
        )
        self.assertIsInstance(self.session.session, StubSessionForStubAvatarWithEnv)
        self.assertRequestRaisedRuntimeError()
        # An environment variable name for which setEnv raises
        # EnvironmentVariableNotPermitted is silently ignored.
        self.assertFalse(
            self.session.requestReceived(
                b"env", common.NS(b"IGNORED") + common.NS(b"ignored")
            )
        )
        self.assertEqual(self.flushLoggedErrors(), [])
        # Allowed environment variable name succeeds.
        self.assertTrue(
            self.session.requestReceived(
                b"env", common.NS(b"NAME") + common.NS(b"value")
            )
        )
        self.assertEqual(self.session.session.environ, {b"NAME": b"value"})

    def test_setEnvSessionShare(self):
        """
        Multiple setenv requests will share the same session.
        """
        test_session = self.getSSHSession()

        self.assertTrue(
            test_session.requestReceived(
                b"env", common.NS(b"Key1") + common.NS(b"Value 1")
            )
        )
        self.assertTrue(
            test_session.requestReceived(
                b"env", common.NS(b"Key2") + common.NS(b"Value2")
            )
        )

        self.assertIsInstance(test_session.session, StubSessionForStubAvatarWithEnv)
        self.assertEqual(
            {b"Key1": b"Value 1", b"Key2": b"Value2"}, test_session.session.environ
        )

    def test_setEnvMultiplexShare(self):
        """
        Calling another session service after setenv will provide the
        previous session with the environment variables.
        """
        test_session = self.getSSHSession()

        test_session.requestReceived(b"env", common.NS(b"Key1") + common.NS(b"Value 1"))
        test_session.requestReceived(b"env", common.NS(b"Key2") + common.NS(b"Value2"))
        test_session.requestReceived(
            b"pty_req", session.packRequest_pty_req(b"term", (0, 0, 0, 0), b"")
        )

        self.assertIsInstance(test_session.session, StubSessionForStubAvatarWithEnv)
        self.assertEqual(
            {b"Key1": b"Value 1", b"Key2": b"Value2"}, test_session.session.environAtPty
        )

    def test_setEnvNotProvidingISessionSetEnv(self):
        """
        If the avatar does not have an ISessionSetEnv adapter, then a
        request to pass an environment variable fails gracefully.
        """
        # Cleanup the registered adapters.
        self.doCleanups()
        self.setUp(register_adapters=False)
        # Register a ISession adapter that does not support ISessionSetEnv.
        components.registerAdapter(
            StubSessionForStubAvatar, StubAvatar, session.ISession
        )
        self.assertFalse(
            self.session.requestReceived(
                b"env", common.NS(b"NAME") + common.NS(b"value")
            )
        )

    def test_requestWindowChange(self):
        """
        When the client requests to change the window size, the SSHSession
        object should make the request by getting an ISession adapter for the
        avatar, then calling windowChanged with the new window size.
        """
        ret = self.session.requestReceived(
            b"window_change", session.packRequest_window_change((0, 0, 0, 0))
        )
        self.assertFalse(ret)
        self.assertRequestRaisedRuntimeError()
        self.assertSessionIsStubSession()
        self.assertTrue(
            self.session.requestReceived(
                b"window_change", session.packRequest_window_change((1, 2, 3, 4))
            )
        )
        self.assertEqual(self.session.session.windowChange, (1, 2, 3, 4))

    def test_eofReceived(self):
        """
        When an EOF is received and an ISession adapter is present, it should
        be notified of the EOF message.
        """
        self.session.session = session.ISession(self.session.avatar)
        self.session.eofReceived()
        self.assertTrue(self.session.session.gotEOF)

    def test_closeReceived(self):
        """
        When a close is received, the session should send a close message.
        """
        ret = self.session.closeReceived()
        self.assertIsNone(ret)
        self.assertTrue(self.session.conn.closes[self.session])

    def test_closed(self):
        """
        When a close is received and an ISession adapter is present, it should
        be notified of the close message.
        """
        self.session.session = session.ISession(self.session.avatar)
        self.session.closed()
        self.assertTrue(self.session.session.gotClosed)


class SessionWithNoAvatarTests(RegistryUsingMixin, TestCase):
    """
    Test for the SSHSession interface.  Several of the methods (request_shell,
    request_exec, request_pty_req, request_env, request_window_change) would
    create a 'session' instance variable from the avatar if one didn't exist
    when they were called.
    """

    if not cryptography:
        skip = "cannot run without cryptography"

    def setUp(self):
        RegistryUsingMixin.setUp(self)
        components.registerAdapter(
            StubSessionForStubAvatar, StubAvatar, session.ISession
        )
        self.session = session.SSHSession()
        self.session.avatar = StubAvatar()
        self.assertIsNone(self.session.session)

    def assertSessionProvidesISession(self):
        """
        self.session.session should provide I{ISession}.
        """
        self.assertTrue(
            session.ISession.providedBy(self.session.session),
            "ISession not provided by %r" % self.session.session,
        )

    def test_requestShellGetsSession(self):
        """
        If an ISession adapter isn't already present, request_shell should get
        one.
        """
        self.session.requestReceived(b"shell", b"")
        self.assertSessionProvidesISession()

    def test_requestExecGetsSession(self):
        """
        If an ISession adapter isn't already present, request_exec should get
        one.
        """
        self.session.requestReceived(b"exec", common.NS(b"success"))
        self.assertSessionProvidesISession()

    def test_requestPtyReqGetsSession(self):
        """
        If an ISession adapter isn't already present, request_pty_req should
        get one.
        """
        self.session.requestReceived(
            b"pty_req", session.packRequest_pty_req(b"term", (0, 0, 0, 0), b"")
        )
        self.assertSessionProvidesISession()

    def test_requestWindowChangeGetsSession(self):
        """
        If an ISession adapter isn't already present, request_window_change
        should get one.
        """
        self.session.requestReceived(
            b"window_change", session.packRequest_window_change((1, 1, 1, 1))
        )
        self.assertSessionProvidesISession()


class WrappersTests(TestCase):
    """
    A test for the wrapProtocol and wrapProcessProtocol functions.
    """

    if not cryptography:
        skip = "cannot run without cryptography"

    def test_wrapProtocol(self):
        """
        L{wrapProtocol}, when passed a L{Protocol} should return something that
        has write(), writeSequence(), loseConnection() methods which call the
        Protocol's dataReceived() and connectionLost() methods, respectively.
        """
        protocol = MockProtocol()
        protocol.transport = StubTransport()
        protocol.connectionMade()
        wrapped = session.wrapProtocol(protocol)
        wrapped.dataReceived(b"dataReceived")
        self.assertEqual(protocol.transport.buf, b"dataReceived")
        wrapped.write(b"data")
        wrapped.writeSequence([b"1", b"2"])
        wrapped.loseConnection()
        self.assertEqual(protocol.data, b"data12")
        protocol.reason.trap(error.ConnectionDone)

    def test_wrapProcessProtocol_Protocol(self):
        """
        L{wrapPRocessProtocol}, when passed a L{Protocol} should return
        something that follows the L{IProcessProtocol} interface, with
        connectionMade() mapping to connectionMade(), outReceived() mapping to
        dataReceived() and processEnded() mapping to connectionLost().
        """
        protocol = MockProtocol()
        protocol.transport = StubTransport()
        process_protocol = session.wrapProcessProtocol(protocol)
        process_protocol.connectionMade()
        process_protocol.outReceived(b"data")
        self.assertEqual(protocol.transport.buf, b"data~")
        process_protocol.processEnded(
            failure.Failure(error.ProcessTerminated(0, None, None))
        )
        protocol.reason.trap(error.ProcessTerminated)


class HelpersTests(TestCase):
    """
    Tests for the 4 helper functions: parseRequest_* and packRequest_*.
    """

    if not cryptography:
        skip = "cannot run without cryptography"

    def test_parseRequest_pty_req(self):
        """
        The payload of a pty-req message is::
            string  terminal
            uint32  columns
            uint32  rows
            uint32  x pixels
            uint32  y pixels
            string  modes

        Modes are::
            byte    mode number
            uint32  mode value
        """
        self.assertEqual(
            session.parseRequest_pty_req(
                common.NS(b"xterm")
                + struct.pack(">4L", 1, 2, 3, 4)
                + common.NS(struct.pack(">BL", 5, 6))
            ),
            (b"xterm", (2, 1, 3, 4), [(5, 6)]),
        )

    def test_packRequest_pty_req_old(self):
        """
        See test_parseRequest_pty_req for the payload format.
        """
        packed = session.packRequest_pty_req(
            b"xterm", (2, 1, 3, 4), b"\x05\x00\x00\x00\x06"
        )

        self.assertEqual(
            packed,
            common.NS(b"xterm")
            + struct.pack(">4L", 1, 2, 3, 4)
            + common.NS(struct.pack(">BL", 5, 6)),
        )

    def test_packRequest_pty_req(self):
        """
        See test_parseRequest_pty_req for the payload format.
        """
        packed = session.packRequest_pty_req(
            b"xterm", (2, 1, 3, 4), b"\x05\x00\x00\x00\x06"
        )
        self.assertEqual(
            packed,
            common.NS(b"xterm")
            + struct.pack(">4L", 1, 2, 3, 4)
            + common.NS(struct.pack(">BL", 5, 6)),
        )

    def test_parseRequest_window_change(self):
        """
        The payload of a window_change request is::
            uint32  columns
            uint32  rows
            uint32  x pixels
            uint32  y pixels

        parseRequest_window_change() returns (rows, columns, x pixels,
        y pixels).
        """
        self.assertEqual(
            session.parseRequest_window_change(struct.pack(">4L", 1, 2, 3, 4)),
            (2, 1, 3, 4),
        )

    def test_packRequest_window_change(self):
        """
        See test_parseRequest_window_change for the payload format.
        """
        self.assertEqual(
            session.packRequest_window_change((2, 1, 3, 4)),
            struct.pack(">4L", 1, 2, 3, 4),
        )


class SSHSessionProcessProtocolTests(TestCase):
    """
    Tests for L{SSHSessionProcessProtocol}.
    """

    if not cryptography:
        skip = "cannot run without cryptography"

    def setUp(self):
        self.transport = StubTransport()
        self.session = session.SSHSession(
            conn=StubConnection(self.transport), remoteWindow=500, remoteMaxPacket=100
        )
        self.pp = session.SSHSessionProcessProtocol(self.session)
        self.pp.makeConnection(self.transport)

    def assertSessionClosed(self):
        """
        Assert that C{self.session} is closed.
        """
        self.assertTrue(self.session.conn.closes[self.session])

    def assertRequestsEqual(self, expectedRequests):
        """
        Assert that C{self.session} has sent the C{expectedRequests}.
        """
        self.assertEqual(self.session.conn.requests[self.session], expectedRequests)

    def test_init(self):
        """
        SSHSessionProcessProtocol should set self.session to the session passed
        to the __init__ method.
        """
        self.assertEqual(self.pp.session, self.session)

    def test_getHost(self):
        """
        SSHSessionProcessProtocol.getHost() just delegates to its
        session.conn.transport.getHost().
        """
        self.assertEqual(self.session.conn.transport.getHost(), self.pp.getHost())

    def test_getPeer(self):
        """
        SSHSessionProcessProtocol.getPeer() just delegates to its
        session.conn.transport.getPeer().
        """
        self.assertEqual(self.session.conn.transport.getPeer(), self.pp.getPeer())

    def test_connectionMade(self):
        """
        SSHSessionProcessProtocol.connectionMade() should check if there's a
        'buf' attribute on its session and write it to the transport if so.
        """
        self.session.buf = b"buffer"
        self.pp.connectionMade()
        self.assertEqual(self.transport.buf, b"buffer")

    @skipIf(not hasattr(signal, "SIGALRM"), "Not all signals available")
    def test_getSignalName(self):
        """
        _getSignalName should return the name of a signal when given the
        signal number.
        """
        for signalName in session.SUPPORTED_SIGNALS:
            signalName = "SIG" + signalName
            signalValue = getattr(signal, signalName)
            sshName = self.pp._getSignalName(signalValue)
            self.assertEqual(
                sshName, signalName, "%i: %s != %s" % (signalValue, sshName, signalName)
            )

    @skipIf(not hasattr(signal, "SIGALRM"), "Not all signals available")
    def test_getSignalNameWithLocalSignal(self):
        """
        If there are signals in the signal module which aren't in the SSH RFC,
        we map their name to [signal name]@[platform].
        """
        signal.SIGTwistedTest = signal.NSIG + 1  # value can't exist normally
        # Force reinitialization of signals
        self.pp._signalValuesToNames = None
        self.assertEqual(
            self.pp._getSignalName(signal.SIGTwistedTest),
            "SIGTwistedTest@" + sys.platform,
        )

    def test_outReceived(self):
        """
        When data is passed to the outReceived method, it should be sent to
        the session's write method.
        """
        self.pp.outReceived(b"test data")
        self.assertEqual(self.session.conn.data[self.session], [b"test data"])

    def test_write(self):
        """
        When data is passed to the write method, it should be sent to the
        session channel's write method.
        """
        self.pp.write(b"test data")
        self.assertEqual(self.session.conn.data[self.session], [b"test data"])

    def test_writeSequence(self):
        """
        When a sequence is passed to the writeSequence method, it should be
        joined together and sent to the session channel's write method.
        """
        self.pp.writeSequence([b"test ", b"data"])
        self.assertEqual(self.session.conn.data[self.session], [b"test data"])

    def test_errReceived(self):
        """
        When data is passed to the errReceived method, it should be sent to
        the session's writeExtended method.
        """
        self.pp.errReceived(b"test data")
        self.assertEqual(self.session.conn.extData[self.session], [(1, b"test data")])

    def test_outConnectionLost(self):
        """
        When outConnectionLost and errConnectionLost are both called, we should
        send an EOF message.
        """
        self.pp.outConnectionLost()
        self.assertFalse(self.session in self.session.conn.eofs)
        self.pp.errConnectionLost()
        self.assertTrue(self.session.conn.eofs[self.session])

    def test_errConnectionLost(self):
        """
        Make sure reverse ordering of events in test_outConnectionLost also
        sends EOF.
        """
        self.pp.errConnectionLost()
        self.assertFalse(self.session in self.session.conn.eofs)
        self.pp.outConnectionLost()
        self.assertTrue(self.session.conn.eofs[self.session])

    def test_loseConnection(self):
        """
        When loseConnection() is called, it should call loseConnection
        on the session channel.
        """
        self.pp.loseConnection()
        self.assertTrue(self.session.conn.closes[self.session])

    def test_connectionLost(self):
        """
        When connectionLost() is called, it should call loseConnection()
        on the session channel.
        """
        self.pp.connectionLost(failure.Failure(ProcessDone(0)))

    def test_processEndedWithExitCode(self):
        """
        When processEnded is called, if there is an exit code in the reason
        it should be sent in an exit-status method.  The connection should be
        closed.
        """
        self.pp.processEnded(Failure(ProcessDone(None)))
        self.assertRequestsEqual([(b"exit-status", struct.pack(">I", 0), False)])
        self.assertSessionClosed()

    @skipIf(not hasattr(os, "WCOREDUMP"), "can't run this w/o os.WCOREDUMP")
    def test_processEndedWithExitSignalCoreDump(self):
        """
        When processEnded is called, if there is an exit signal in the reason
        it should be sent in an exit-signal message.  The connection should be
        closed.
        """
        self.pp.processEnded(
            Failure(ProcessTerminated(1, signal.SIGTERM, 1 << 7))
        )  # 7th bit means core dumped
        self.assertRequestsEqual(
            [
                (
                    b"exit-signal",
                    common.NS(b"TERM")  # signal name
                    + b"\x01"  # core dumped is true
                    + common.NS(b"")  # error message
                    + common.NS(b""),  # language tag
                    False,
                )
            ]
        )
        self.assertSessionClosed()

    @skipIf(not hasattr(os, "WCOREDUMP"), "can't run this w/o os.WCOREDUMP")
    def test_processEndedWithExitSignalNoCoreDump(self):
        """
        When processEnded is called, if there is an exit signal in the
        reason it should be sent in an exit-signal message.  If no
        core was dumped, don't set the core-dump bit.
        """
        self.pp.processEnded(Failure(ProcessTerminated(1, signal.SIGTERM, 0)))
        # see comments in test_processEndedWithExitSignalCoreDump for the
        # meaning of the parts in the request
        self.assertRequestsEqual(
            [
                (
                    b"exit-signal",
                    common.NS(b"TERM") + b"\x00" + common.NS(b"") + common.NS(b""),
                    False,
                )
            ]
        )
        self.assertSessionClosed()


class SSHSessionClientTests(TestCase):
    """
    SSHSessionClient is an obsolete class used to connect standard IO to
    an SSHSession.
    """

    if not cryptography:
        skip = "cannot run without cryptography"

    def test_dataReceived(self):
        """
        When data is received, it should be sent to the transport.
        """
        client = session.SSHSessionClient()
        client.transport = StubTransport()
        client.dataReceived(b"test data")
        self.assertEqual(client.transport.buf, b"test data")
