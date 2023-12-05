# -*- test-case-name: twisted.conch.test.test_conch -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

import os
import socket
import subprocess
import sys
from itertools import count
from unittest import skipIf

from zope.interface import implementer

from twisted.conch.error import ConchError
from twisted.conch.test.keydata import (
    privateDSA_openssh,
    privateRSA_openssh,
    publicDSA_openssh,
    publicRSA_openssh,
)
from twisted.conch.test.test_ssh import ConchTestRealm
from twisted.cred import portal
from twisted.internet import defer, protocol, reactor
from twisted.internet.error import ProcessExitedAlready
from twisted.internet.task import LoopingCall
from twisted.internet.utils import getProcessValue
from twisted.python import filepath, log, runtime
from twisted.python.filepath import FilePath
from twisted.python.procutils import which
from twisted.python.reflect import requireModule
from twisted.trial.unittest import SkipTest, TestCase

try:
    from twisted.conch.test.test_ssh import (
        ConchTestServerFactory,
        conchTestPublicKeyChecker,
    )
except ImportError:
    pass

pyasn1 = requireModule("pyasn1")
cryptography = requireModule("cryptography")

if cryptography:
    from twisted.conch.avatar import ConchUser
    from twisted.conch.ssh.session import ISession, SSHSession, wrapProtocol
else:
    from twisted.conch.interfaces import ISession

    class ConchUser:  # type: ignore[no-redef]
        pass


try:
    from twisted.conch.scripts.conch import SSHSession as _StdioInteractingSession
except ImportError as e:
    StdioInteractingSession = None
    _reason = str(e)
    del e
else:
    StdioInteractingSession = _StdioInteractingSession


def _has_ipv6():
    """Returns True if the system can bind an IPv6 address."""
    sock = None
    has_ipv6 = False

    try:
        sock = socket.socket(socket.AF_INET6)
        sock.bind(("::1", 0))
        has_ipv6 = True
    except OSError:
        pass

    if sock:
        sock.close()
    return has_ipv6


HAS_IPV6 = _has_ipv6()


class FakeStdio:
    """
    A fake for testing L{twisted.conch.scripts.conch.SSHSession.eofReceived} and
    L{twisted.conch.scripts.cftp.SSHSession.eofReceived}.

    @ivar writeConnLost: A flag which records whether L{loserWriteConnection}
        has been called.
    """

    writeConnLost = False

    def loseWriteConnection(self):
        """
        Record the call to loseWriteConnection.
        """
        self.writeConnLost = True


class StdioInteractingSessionTests(TestCase):
    """
    Tests for L{twisted.conch.scripts.conch.SSHSession}.
    """

    if StdioInteractingSession is None:
        skip = _reason

    def test_eofReceived(self):
        """
        L{twisted.conch.scripts.conch.SSHSession.eofReceived} loses the
        write half of its stdio connection.
        """
        stdio = FakeStdio()
        channel = StdioInteractingSession()
        channel.stdio = stdio
        channel.eofReceived()
        self.assertTrue(stdio.writeConnLost)


class Echo(protocol.Protocol):
    def connectionMade(self):
        log.msg("ECHO CONNECTION MADE")

    def connectionLost(self, reason):
        log.msg("ECHO CONNECTION DONE")

    def dataReceived(self, data):
        self.transport.write(data)
        if b"\n" in data:
            self.transport.loseConnection()


class EchoFactory(protocol.Factory):
    protocol = Echo


class ConchTestOpenSSHProcess(protocol.ProcessProtocol):
    """
    Test protocol for launching an OpenSSH client process.

    @ivar deferred: Set by whatever uses this object. Accessed using
    L{_getDeferred}, which destroys the value so the Deferred is not
    fired twice. Fires when the process is terminated.
    """

    deferred = None
    buf = b""
    problems = b""

    def _getDeferred(self):
        d, self.deferred = self.deferred, None
        return d

    def outReceived(self, data):
        self.buf += data

    def errReceived(self, data):
        self.problems += data

    def processEnded(self, reason):
        """
        Called when the process has ended.

        @param reason: a Failure giving the reason for the process' end.
        """
        if reason.value.exitCode != 0:
            self._getDeferred().errback(
                ConchError(
                    "exit code was not 0: {} ({})".format(
                        reason.value.exitCode,
                        self.problems.decode("charmap"),
                    )
                )
            )
        else:
            buf = self.buf.replace(b"\r\n", b"\n")
            self._getDeferred().callback(buf)


class ConchTestForwardingProcess(protocol.ProcessProtocol):
    """
    Manages a third-party process which launches a server.

    Uses L{ConchTestForwardingPort} to connect to the third-party server.
    Once L{ConchTestForwardingPort} has disconnected, kill the process and fire
    a Deferred with the data received by the L{ConchTestForwardingPort}.

    @ivar deferred: Set by whatever uses this object. Accessed using
    L{_getDeferred}, which destroys the value so the Deferred is not
    fired twice. Fires when the process is terminated.
    """

    deferred = None

    def __init__(self, port, data):
        """
        @type port: L{int}
        @param port: The port on which the third-party server is listening.
        (it is assumed that the server is running on localhost).

        @type data: L{str}
        @param data: This is sent to the third-party server. Must end with '\n'
        in order to trigger a disconnect.
        """
        self.port = port
        self.buffer = None
        self.data = data

    def _getDeferred(self):
        d, self.deferred = self.deferred, None
        return d

    def connectionMade(self):
        self._connect()

    def _connect(self):
        """
        Connect to the server, which is often a third-party process.
        Tries to reconnect if it fails because we have no way of determining
        exactly when the port becomes available for listening -- we can only
        know when the process starts.
        """
        cc = protocol.ClientCreator(reactor, ConchTestForwardingPort, self, self.data)
        d = cc.connectTCP("127.0.0.1", self.port)
        d.addErrback(self._ebConnect)
        return d

    def _ebConnect(self, f):
        reactor.callLater(0.1, self._connect)

    def forwardingPortDisconnected(self, buffer):
        """
        The network connection has died; save the buffer of output
        from the network and attempt to quit the process gracefully,
        and then (after the reactor has spun) send it a KILL signal.
        """
        self.buffer = buffer
        self.transport.write(b"\x03")
        self.transport.loseConnection()
        reactor.callLater(0, self._reallyDie)

    def _reallyDie(self):
        try:
            self.transport.signalProcess("KILL")
        except ProcessExitedAlready:
            pass

    def processEnded(self, reason):
        """
        Fire the Deferred at self.deferred with the data collected
        from the L{ConchTestForwardingPort} connection, if any.
        """
        self._getDeferred().callback(self.buffer)


class ConchTestForwardingPort(protocol.Protocol):
    """
    Connects to server launched by a third-party process (managed by
    L{ConchTestForwardingProcess}) sends data, then reports whatever it
    received back to the L{ConchTestForwardingProcess} once the connection
    is ended.
    """

    def __init__(self, protocol, data):
        """
        @type protocol: L{ConchTestForwardingProcess}
        @param protocol: The L{ProcessProtocol} which made this connection.

        @type data: str
        @param data: The data to be sent to the third-party server.
        """
        self.protocol = protocol
        self.data = data

    def connectionMade(self):
        self.buffer = b""
        self.transport.write(self.data)

    def dataReceived(self, data):
        self.buffer += data

    def connectionLost(self, reason):
        self.protocol.forwardingPortDisconnected(self.buffer)


def _makeArgs(args, mod="conch"):
    start = [
        sys.executable,
        "-c"
        """
### Twisted Preamble
import sys, os
path = os.path.abspath(sys.argv[0])
while os.path.dirname(path) != path:
    if os.path.basename(path).startswith('Twisted'):
        sys.path.insert(0, path)
        break
    path = os.path.dirname(path)

from twisted.conch.scripts.%s import run
run()"""
        % mod,
    ]
    madeArgs = []
    for arg in start + list(args):
        if isinstance(arg, str):
            arg = arg.encode("utf-8")
        madeArgs.append(arg)
    return madeArgs


class ConchServerSetupMixin:
    if not cryptography:
        skip = "can't run without cryptography"

    if not pyasn1:
        skip = "Cannot run without PyASN1"

    @staticmethod
    def realmFactory():
        return ConchTestRealm(b"testuser")

    def _createFiles(self):
        for f in ["rsa_test", "rsa_test.pub", "dsa_test", "dsa_test.pub", "kh_test"]:
            if os.path.exists(f):
                os.remove(f)
        with open("rsa_test", "wb") as f:
            f.write(privateRSA_openssh)
        with open("rsa_test.pub", "wb") as f:
            f.write(publicRSA_openssh)
        with open("dsa_test.pub", "wb") as f:
            f.write(publicDSA_openssh)
        with open("dsa_test", "wb") as f:
            f.write(privateDSA_openssh)
        os.chmod("dsa_test", 0o600)
        os.chmod("rsa_test", 0o600)
        permissions = FilePath("dsa_test").getPermissions()
        if permissions.group.read or permissions.other.read:
            raise SkipTest(
                "private key readable by others despite chmod;"
                " possible windows permission issue?"
                " see https://tm.tl/9767"
            )
        with open("kh_test", "wb") as f:
            f.write(b"127.0.0.1 " + publicRSA_openssh)

    def _getFreePort(self):
        s = socket.socket()
        s.bind(("", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def _makeConchFactory(self):
        """
        Make a L{ConchTestServerFactory}, which allows us to start a
        L{ConchTestServer} -- i.e. an actually listening conch.
        """
        realm = self.realmFactory()
        p = portal.Portal(realm)
        p.registerChecker(conchTestPublicKeyChecker())
        factory = ConchTestServerFactory()
        factory.portal = p
        return factory

    def setUp(self):
        self._createFiles()
        self.conchFactory = self._makeConchFactory()
        self.conchFactory.expectedLoseConnection = 1
        self.conchServer = reactor.listenTCP(
            0, self.conchFactory, interface="127.0.0.1"
        )
        self.echoServer = reactor.listenTCP(0, EchoFactory())
        self.echoPort = self.echoServer.getHost().port
        if HAS_IPV6:
            self.echoServerV6 = reactor.listenTCP(0, EchoFactory(), interface="::1")
            self.echoPortV6 = self.echoServerV6.getHost().port

    def tearDown(self):
        try:
            self.conchFactory.proto.done = 1
        except AttributeError:
            pass
        else:
            self.conchFactory.proto.transport.loseConnection()
        deferreds = [
            defer.maybeDeferred(self.conchServer.stopListening),
            defer.maybeDeferred(self.echoServer.stopListening),
        ]
        if HAS_IPV6:
            deferreds.append(defer.maybeDeferred(self.echoServerV6.stopListening))
        return defer.gatherResults(deferreds)


class ForwardingMixin(ConchServerSetupMixin):
    """
    Template class for tests of the Conch server's ability to forward arbitrary
    protocols over SSH.

    These tests are integration tests, not unit tests. They launch a Conch
    server, a custom TCP server (just an L{EchoProtocol}) and then call
    L{execute}.

    L{execute} is implemented by subclasses of L{ForwardingMixin}. It should
    cause an SSH client to connect to the Conch server, asking it to forward
    data to the custom TCP server.
    """

    def test_exec(self):
        """
        Test that we can use whatever client to send the command "echo goodbye"
        to the Conch server. Make sure we receive "goodbye" back from the
        server.
        """
        d = self.execute("echo goodbye", ConchTestOpenSSHProcess())
        return d.addCallback(self.assertEqual, b"goodbye\n")

    def test_localToRemoteForwarding(self):
        """
        Test that we can use whatever client to forward a local port to a
        specified port on the server.
        """
        localPort = self._getFreePort()
        process = ConchTestForwardingProcess(localPort, b"test\n")
        d = self.execute(
            "", process, sshArgs="-N -L%i:127.0.0.1:%i" % (localPort, self.echoPort)
        )
        d.addCallback(self.assertEqual, b"test\n")
        return d

    def test_remoteToLocalForwarding(self):
        """
        Test that we can use whatever client to forward a port from the server
        to a port locally.
        """
        localPort = self._getFreePort()
        process = ConchTestForwardingProcess(localPort, b"test\n")
        d = self.execute(
            "", process, sshArgs="-N -R %i:127.0.0.1:%i" % (localPort, self.echoPort)
        )
        d.addCallback(self.assertEqual, b"test\n")
        return d


# Conventionally there is a separate adapter object which provides ISession for
# the user, but making the user provide ISession directly works too. This isn't
# a full implementation of ISession though, just enough to make these tests
# pass.
@implementer(ISession)
class RekeyAvatar(ConchUser):
    """
    This avatar implements a shell which sends 60 numbered lines to whatever
    connects to it, then closes the session with a 0 exit status.

    60 lines is selected as being enough to send more than 2kB of traffic, the
    amount the client is configured to initiate a rekey after.
    """

    def __init__(self):
        ConchUser.__init__(self)
        self.channelLookup[b"session"] = SSHSession

    def openShell(self, transport):
        """
        Write 60 lines of data to the transport, then exit.
        """
        proto = protocol.Protocol()
        proto.makeConnection(transport)
        transport.makeConnection(wrapProtocol(proto))

        # Send enough bytes to the connection so that a rekey is triggered in
        # the client.
        def write(counter):
            i = next(counter)
            if i == 60:
                call.stop()
                transport.session.conn.sendRequest(
                    transport.session, b"exit-status", b"\x00\x00\x00\x00"
                )
                transport.loseConnection()
            else:
                line = "line #%02d\n" % (i,)
                line = line.encode("utf-8")
                transport.write(line)

        # The timing for this loop is an educated guess (and/or the result of
        # experimentation) to exercise the case where a packet is generated
        # mid-rekey.  Since the other side of the connection is (so far) the
        # OpenSSH command line client, there's no easy way to determine when the
        # rekey has been initiated.  If there were, then generating a packet
        # immediately at that time would be a better way to test the
        # functionality being tested here.
        call = LoopingCall(write, count())
        call.start(0.01)

    def closed(self):
        """
        Ignore the close of the session.
        """

    def eofReceived(self):
        # ISession.eofReceived
        pass

    def execCommand(self, proto, command):
        # ISession.execCommand
        pass

    def getPty(self, term, windowSize, modes):
        # ISession.getPty
        pass

    def windowChanged(self, newWindowSize):
        # ISession.windowChanged
        pass


class RekeyRealm:
    """
    This realm gives out new L{RekeyAvatar} instances for any avatar request.
    """

    def requestAvatar(self, avatarID, mind, *interfaces):
        return interfaces[0], RekeyAvatar(), lambda: None


class RekeyTestsMixin(ConchServerSetupMixin):
    """
    TestCase mixin which defines tests exercising L{SSHTransportBase}'s handling
    of rekeying messages.
    """

    realmFactory = RekeyRealm

    def test_clientRekey(self):
        """
        After a client-initiated rekey is completed, application data continues
        to be passed over the SSH connection.
        """
        process = ConchTestOpenSSHProcess()
        d = self.execute("", process, "-o RekeyLimit=2K")

        def finished(result):
            expectedResult = "\n".join(["line #%02d" % (i,) for i in range(60)]) + "\n"
            expectedResult = expectedResult.encode("utf-8")
            self.assertEqual(result, expectedResult)

        d.addCallback(finished)
        return d


class OpenSSHClientMixin:
    if not which("ssh"):
        skip = "no ssh command-line client available"

    def execute(self, remoteCommand, process, sshArgs=""):
        """
        Connects to the SSH server started in L{ConchServerSetupMixin.setUp} by
        running the 'ssh' command line tool.

        @type remoteCommand: str
        @param remoteCommand: The command (with arguments) to run on the
        remote end.

        @type process: L{ConchTestOpenSSHProcess}

        @type sshArgs: str
        @param sshArgs: Arguments to pass to the 'ssh' process.

        @return: L{defer.Deferred}
        """
        # PubkeyAcceptedKeyTypes does not exist prior to OpenSSH 7.0 so we
        # first need to check if we can set it. If we can, -V will just print
        # the version without doing anything else; if we can't, we will get a
        # configuration error.
        d = getProcessValue(
            which("ssh")[0], ("-o", "PubkeyAcceptedKeyTypes=ssh-dss", "-V")
        )

        def hasPAKT(status):
            if status == 0:
                opts = "-oPubkeyAcceptedKeyTypes=ssh-dss "
            else:
                opts = ""

            process.deferred = defer.Deferred()
            # Pass -F /dev/null to avoid the user's configuration file from
            # being loaded, as it may contain settings that cause our tests to
            # fail or hang.
            cmdline = (
                (
                    "ssh -2 -l testuser -p %i "
                    "-F /dev/null "
                    "-oUserKnownHostsFile=kh_test "
                    "-oPasswordAuthentication=no "
                    # Always use the RSA key, since that's the one in kh_test.
                    "-oHostKeyAlgorithms=ssh-rsa "
                    "-a "
                    "-i dsa_test "
                )
                + opts
                + sshArgs
                + " 127.0.0.1 "
                + remoteCommand
            )
            port = self.conchServer.getHost().port
            cmds = (cmdline % port).split()
            encodedCmds = []
            for cmd in cmds:
                if isinstance(cmd, str):
                    cmd = cmd.encode("utf-8")
                encodedCmds.append(cmd)
            reactor.spawnProcess(process, which("ssh")[0], encodedCmds)
            return process.deferred

        return d.addCallback(hasPAKT)


class OpenSSHKeyExchangeTests(ConchServerSetupMixin, OpenSSHClientMixin, TestCase):
    """
    Tests L{SSHTransportBase}'s key exchange algorithm compatibility with
    OpenSSH.
    """

    def assertExecuteWithKexAlgorithm(self, keyExchangeAlgo):
        """
        Call execute() method of L{OpenSSHClientMixin} with an ssh option that
        forces the exclusive use of the key exchange algorithm specified by
        keyExchangeAlgo

        @type keyExchangeAlgo: L{str}
        @param keyExchangeAlgo: The key exchange algorithm to use

        @return: L{defer.Deferred}
        """
        kexAlgorithms = []
        try:
            output = subprocess.check_output(
                [which("ssh")[0], "-Q", "kex"], stderr=subprocess.STDOUT
            )
            if not isinstance(output, str):
                output = output.decode("utf-8")
            kexAlgorithms = output.split()
        except BaseException:
            pass

        if keyExchangeAlgo not in kexAlgorithms:
            raise SkipTest(f"{keyExchangeAlgo} not supported by ssh client")

        d = self.execute(
            "echo hello",
            ConchTestOpenSSHProcess(),
            "-oKexAlgorithms=" + keyExchangeAlgo,
        )
        return d.addCallback(self.assertEqual, b"hello\n")

    def test_ECDHSHA256(self):
        """
        The ecdh-sha2-nistp256 key exchange algorithm is compatible with
        OpenSSH
        """
        return self.assertExecuteWithKexAlgorithm("ecdh-sha2-nistp256")

    def test_ECDHSHA384(self):
        """
        The ecdh-sha2-nistp384 key exchange algorithm is compatible with
        OpenSSH
        """
        return self.assertExecuteWithKexAlgorithm("ecdh-sha2-nistp384")

    def test_ECDHSHA521(self):
        """
        The ecdh-sha2-nistp521 key exchange algorithm is compatible with
        OpenSSH
        """
        return self.assertExecuteWithKexAlgorithm("ecdh-sha2-nistp521")

    def test_DH_GROUP14(self):
        """
        The diffie-hellman-group14-sha1 key exchange algorithm is compatible
        with OpenSSH.
        """
        return self.assertExecuteWithKexAlgorithm("diffie-hellman-group14-sha1")

    def test_DH_GROUP_EXCHANGE_SHA1(self):
        """
        The diffie-hellman-group-exchange-sha1 key exchange algorithm is
        compatible with OpenSSH.
        """
        return self.assertExecuteWithKexAlgorithm("diffie-hellman-group-exchange-sha1")

    def test_DH_GROUP_EXCHANGE_SHA256(self):
        """
        The diffie-hellman-group-exchange-sha256 key exchange algorithm is
        compatible with OpenSSH.
        """
        return self.assertExecuteWithKexAlgorithm(
            "diffie-hellman-group-exchange-sha256"
        )

    def test_unsupported_algorithm(self):
        """
        The list of key exchange algorithms supported
        by OpenSSH client is obtained with C{ssh -Q kex}.
        """
        self.assertRaises(
            SkipTest, self.assertExecuteWithKexAlgorithm, "unsupported-algorithm"
        )


class OpenSSHClientForwardingTests(ForwardingMixin, OpenSSHClientMixin, TestCase):
    """
    Connection forwarding tests run against the OpenSSL command line client.
    """

    @skipIf(not HAS_IPV6, "Requires IPv6 support")
    def test_localToRemoteForwardingV6(self):
        """
        Forwarding of arbitrary IPv6 TCP connections via SSH.
        """
        localPort = self._getFreePort()
        process = ConchTestForwardingProcess(localPort, b"test\n")
        d = self.execute(
            "", process, sshArgs="-N -L%i:[::1]:%i" % (localPort, self.echoPortV6)
        )
        d.addCallback(self.assertEqual, b"test\n")
        return d


class OpenSSHClientRekeyTests(RekeyTestsMixin, OpenSSHClientMixin, TestCase):
    """
    Rekeying tests run against the OpenSSL command line client.
    """


class CmdLineClientTests(ForwardingMixin, TestCase):
    """
    Connection forwarding tests run against the Conch command line client.
    """

    if runtime.platformType == "win32":
        skip = "can't run cmdline client on win32"

    def execute(self, remoteCommand, process, sshArgs="", conchArgs=None):
        """
        As for L{OpenSSHClientTestCase.execute}, except it runs the 'conch'
        command line tool, not 'ssh'.
        """
        if conchArgs is None:
            conchArgs = []

        process.deferred = defer.Deferred()
        port = self.conchServer.getHost().port
        cmd = (
            "-p {} -l testuser "
            "--known-hosts kh_test "
            "--user-authentications publickey "
            "-a "
            "-i dsa_test "
            "-v ".format(port) + sshArgs + " 127.0.0.1 " + remoteCommand
        )
        cmds = _makeArgs(conchArgs + cmd.split())
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(sys.path)
        encodedCmds = []
        encodedEnv = {}
        for cmd in cmds:
            if isinstance(cmd, str):
                cmd = cmd.encode("utf-8")
            encodedCmds.append(cmd)
        for var in env:
            val = env[var]
            if isinstance(var, str):
                var = var.encode("utf-8")
            if isinstance(val, str):
                val = val.encode("utf-8")
            encodedEnv[var] = val
        reactor.spawnProcess(process, sys.executable, encodedCmds, env=encodedEnv)
        return process.deferred

    def test_runWithLogFile(self):
        """
        It can store logs to a local file.
        """

        def cb_check_log(result):
            logContent = logPath.getContent()
            self.assertIn(b"Log opened.", logContent)

        logPath = filepath.FilePath(self.mktemp())

        d = self.execute(
            remoteCommand="echo goodbye",
            process=ConchTestOpenSSHProcess(),
            conchArgs=[
                "--log",
                "--logfile",
                logPath.path,
                "--host-key-algorithms",
                "ssh-rsa",
            ],
        )

        d.addCallback(self.assertEqual, b"goodbye\n")
        d.addCallback(cb_check_log)
        return d

    def test_runWithNoHostAlgorithmsSpecified(self):
        """
        Do not use --host-key-algorithms flag on command line.
        """
        d = self.execute(
            remoteCommand="echo goodbye", process=ConchTestOpenSSHProcess()
        )

        d.addCallback(self.assertEqual, b"goodbye\n")
        return d
