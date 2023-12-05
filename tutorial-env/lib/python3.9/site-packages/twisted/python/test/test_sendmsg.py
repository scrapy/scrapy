# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.sendmsg}.
"""

import errno
import os
import sys
import warnings
from os import close, pathsep, pipe, read
from socket import AF_INET, AF_INET6, SOL_SOCKET, error, socket
from struct import pack

try:
    from socket import AF_UNIX, socketpair
except ImportError:
    nonUNIXSkip = True
else:
    nonUNIXSkip = False

from unittest import skipIf

from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.error import ProcessDone
from twisted.internet.protocol import ProcessProtocol
from twisted.python.filepath import FilePath
from twisted.python.runtime import platform
from twisted.trial.unittest import TestCase

if platform.isLinux():
    from socket import MSG_DONTWAIT

    dontWaitSkip = False
else:
    # It would be nice to be able to test flags on more platforms, but finding
    # a flag that works *at all* is somewhat challenging.
    dontWaitSkip = True


try:
    from twisted.python.sendmsg import SCM_RIGHTS, getSocketFamily, recvmsg, sendmsg
except ImportError:
    doImportSkip = True
    importSkipReason = "Platform doesn't support sendmsg."
else:
    doImportSkip = False
    importSkipReason = ""


class _FDHolder:
    """
    A wrapper around a FD that will remember if it has been closed or not.
    """

    def __init__(self, fd):
        self._fd = fd

    def fileno(self):
        """
        Return the fileno of this FD.
        """
        return self._fd

    def close(self):
        """
        Close the FD. If it's already been closed, do nothing.
        """
        if self._fd:
            close(self._fd)
            self._fd = None

    def __del__(self):
        """
        If C{self._fd} is unclosed, raise a warning.
        """
        if self._fd:
            warnings.warn(f"FD {self._fd} was not closed!", ResourceWarning)
            self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


def _makePipe():
    """
    Create a pipe, and return the two FDs wrapped in L{_FDHolders}.
    """
    r, w = pipe()
    return (_FDHolder(r), _FDHolder(w))


class ExitedWithStderr(Exception):
    """
    A process exited with some stderr.
    """

    def __str__(self) -> str:
        """
        Dump the errors in a pretty way in the event of a subprocess traceback.
        """
        result = b"\n".join([b""] + list(self.args))
        return repr(result)


class StartStopProcessProtocol(ProcessProtocol):
    """
    An L{IProcessProtocol} with a Deferred for events where the subprocess
    starts and stops.

    @ivar started: A L{Deferred} which fires with this protocol's
        L{IProcessTransport} provider when it is connected to one.

    @ivar stopped: A L{Deferred} which fires with the process output or a
        failure if the process produces output on standard error.

    @ivar output: A C{str} used to accumulate standard output.

    @ivar errors: A C{str} used to accumulate standard error.
    """

    def __init__(self):
        self.started = Deferred()
        self.stopped = Deferred()
        self.output = b""
        self.errors = b""

    def connectionMade(self):
        self.started.callback(self.transport)

    def outReceived(self, data):
        self.output += data

    def errReceived(self, data):
        self.errors += data

    def processEnded(self, reason):
        if reason.check(ProcessDone):
            self.stopped.callback(self.output)
        else:
            self.stopped.errback(ExitedWithStderr(self.errors, self.output))


def _spawn(script, outputFD):
    """
    Start a script that is a peer of this test as a subprocess.

    @param script: the module name of the script in this directory (no
        package prefix, no '.py')
    @type script: C{str}

    @rtype: L{StartStopProcessProtocol}
    """
    pyExe = FilePath(sys.executable).asTextMode().path
    env = dict(os.environ)
    env["PYTHONPATH"] = FilePath(pathsep.join(sys.path)).asTextMode().path
    sspp = StartStopProcessProtocol()
    reactor.spawnProcess(
        sspp,
        pyExe,
        [
            pyExe,
            FilePath(__file__).sibling(script + ".py").asTextMode().path,
            b"%d" % (outputFD,),
        ],
        env=env,
        childFDs={0: "w", 1: "r", 2: "r", outputFD: outputFD},
    )
    return sspp


@skipIf(doImportSkip, importSkipReason)
class SendmsgTests(TestCase):
    """
    Tests for the Python2/3 compatible L{sendmsg} interface.
    """

    def setUp(self):
        """
        Create a pair of UNIX sockets.
        """
        self.input, self.output = socketpair(AF_UNIX)

    def tearDown(self):
        """
        Close the sockets opened by setUp.
        """
        self.input.close()
        self.output.close()

    def test_syscallError(self):
        """
        If the underlying C{sendmsg} call fails, L{send1msg} raises
        L{socket.error} with its errno set to the underlying errno value.
        """
        self.input.close()
        exc = self.assertRaises(error, sendmsg, self.input, b"hello, world")
        self.assertEqual(exc.args[0], errno.EBADF)

    def test_syscallErrorWithControlMessage(self):
        """
        The behavior when the underlying C{sendmsg} call fails is the same
        whether L{sendmsg} is passed ancillary data or not.
        """
        self.input.close()
        exc = self.assertRaises(
            error, sendmsg, self.input, b"hello, world", [(0, 0, b"0123")], 0
        )
        self.assertEqual(exc.args[0], errno.EBADF)

    def test_roundtrip(self):
        """
        L{recvmsg} will retrieve a message sent via L{sendmsg}.
        """
        message = b"hello, world!"
        self.assertEqual(len(message), sendmsg(self.input, message))

        result = recvmsg(self.output)
        self.assertEqual(result.data, b"hello, world!")
        self.assertEqual(result.flags, 0)
        self.assertEqual(result.ancillary, [])

    def test_shortsend(self):
        """
        L{sendmsg} returns the number of bytes which it was able to send.
        """
        message = b"x" * 1024 * 1024 * 16
        self.input.setblocking(False)
        sent = sendmsg(self.input, message)
        # Sanity check - make sure the amount of data we sent was less than the
        # message, but not the whole message, as we should have filled the send
        # buffer. This won't work if the send buffer is large enough for
        # message, though.
        self.assertTrue(sent < len(message))
        received = recvmsg(self.output, len(message))
        self.assertEqual(len(received[0]), sent)

    def test_roundtripEmptyAncillary(self):
        """
        L{sendmsg} treats an empty ancillary data list the same way it treats
        receiving no argument for the ancillary parameter at all.
        """
        sendmsg(self.input, b"hello, world!", [], 0)

        result = recvmsg(self.output)
        self.assertEqual(result, (b"hello, world!", [], 0))

    @skipIf(dontWaitSkip, "MSG_DONTWAIT is only known to work as intended on Linux")
    def test_flags(self):
        """
        The C{flags} argument to L{sendmsg} is passed on to the underlying
        C{sendmsg} call, to affect it in whatever way is defined by those
        flags.
        """
        # Just exercise one flag with simple, well-known behavior. MSG_DONTWAIT
        # makes the send a non-blocking call, even if the socket is in blocking
        # mode.  See also test_flags in RecvmsgTests
        for i in range(8 * 1024):
            try:
                sendmsg(self.input, b"x" * 1024, flags=MSG_DONTWAIT)
            except OSError as e:
                self.assertEqual(e.args[0], errno.EAGAIN)
                break
        else:
            self.fail(
                "Failed to fill up the send buffer, "
                "or maybe send1msg blocked for a while"
            )

    @inlineCallbacks
    def test_sendSubProcessFD(self):
        """
        Calling L{sendmsg} with SOL_SOCKET, SCM_RIGHTS, and a platform-endian
        packed file descriptor number should send that file descriptor to a
        different process, where it can be retrieved by using L{recv1msg}.
        """
        sspp = _spawn("pullpipe", self.output.fileno())
        yield sspp.started
        pipeOut, pipeIn = _makePipe()
        self.addCleanup(pipeOut.close)
        self.addCleanup(pipeIn.close)

        with pipeIn:
            sendmsg(
                self.input,
                b"blonk",
                [(SOL_SOCKET, SCM_RIGHTS, pack("i", pipeIn.fileno()))],
            )

        yield sspp.stopped
        self.assertEqual(read(pipeOut.fileno(), 1024), b"Test fixture data: blonk.\n")
        # Make sure that the pipe is actually closed now.
        self.assertEqual(read(pipeOut.fileno(), 1024), b"")


@skipIf(doImportSkip, importSkipReason)
class GetSocketFamilyTests(TestCase):
    """
    Tests for L{getSocketFamily}.
    """

    def _socket(self, addressFamily):
        """
        Create a new socket using the given address family and return that
        socket's file descriptor.  The socket will automatically be closed when
        the test is torn down.
        """
        s = socket(addressFamily)
        self.addCleanup(s.close)
        return s

    def test_inet(self):
        """
        When passed the file descriptor of a socket created with the C{AF_INET}
        address family, L{getSocketFamily} returns C{AF_INET}.
        """
        self.assertEqual(AF_INET, getSocketFamily(self._socket(AF_INET)))

    def test_inet6(self):
        """
        When passed the file descriptor of a socket created with the
        C{AF_INET6} address family, L{getSocketFamily} returns C{AF_INET6}.
        """
        self.assertEqual(AF_INET6, getSocketFamily(self._socket(AF_INET6)))

    @skipIf(nonUNIXSkip, "Platform does not support AF_UNIX sockets")
    def test_unix(self):
        """
        When passed the file descriptor of a socket created with the C{AF_UNIX}
        address family, L{getSocketFamily} returns C{AF_UNIX}.
        """
        self.assertEqual(AF_UNIX, getSocketFamily(self._socket(AF_UNIX)))
