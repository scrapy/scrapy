# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.sendmsg}.
"""

import sys
import errno
import warnings
from os import devnull, pipe, read, close, pathsep
from struct import pack
from socket import SOL_SOCKET, AF_INET, AF_INET6, socket, error

try:
    from socket import AF_UNIX, socketpair
except ImportError:
    nonUNIXSkip = "Platform does not support AF_UNIX sockets"
else:
    nonUNIXSkip = None

from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.error import ProcessDone
from twisted.internet.protocol import ProcessProtocol
from twisted.python.compat import _PY3, intToBytes, bytesEnviron
from twisted.python.filepath import FilePath
from twisted.python.runtime import platform

from twisted.trial.unittest import TestCase

if platform.isLinux():
    from socket import MSG_DONTWAIT
    dontWaitSkip = None
else:
    # It would be nice to be able to test flags on more platforms, but finding
    # a flag that works *at all* is somewhat challenging.
    dontWaitSkip = "MSG_DONTWAIT is only known to work as intended on Linux"


try:
    from twisted.python.sendmsg import sendmsg, recvmsg
    from twisted.python.sendmsg import SCM_RIGHTS, getSocketFamily
except ImportError:
    importSkip = "Platform doesn't support sendmsg."
else:
    importSkip = None


try:
    from twisted.python.sendmsg import send1msg, recv1msg
    from twisted.python.sendmsg import getsockfam
except ImportError:
    CModuleImportSkip = "Cannot import twisted.python.sendmsg"
else:
    CModuleImportSkip = None



class _FDHolder(object):
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
            if not _PY3:
                ResourceWarning = Warning
            warnings.warn("FD %s was not closed!" % (self._fd,),
                          ResourceWarning)
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

    def __str__(self):
        """
        Dump the errors in a pretty way in the event of a subprocess traceback.
        """
        result = b'\n'.join([b''] + list(self.args))
        if _PY3:
            result = repr(result)
        return result



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
        self.output = b''
        self.errors = b''


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
            self.stopped.errback(ExitedWithStderr(
                    self.errors, self.output))



def _spawn(script, outputFD):
    """
    Start a script that is a peer of this test as a subprocess.

    @param script: the module name of the script in this directory (no
        package prefix, no '.py')
    @type script: C{str}

    @rtype: L{StartStopProcessProtocol}
    """
    pyExe = FilePath(sys.executable).asBytesMode().path
    env = bytesEnviron()
    env[b"PYTHONPATH"] = FilePath(
        pathsep.join(sys.path)).asBytesMode().path
    sspp = StartStopProcessProtocol()
    reactor.spawnProcess(
        sspp, pyExe, [
            pyExe,
            FilePath(__file__).sibling(script + ".py").asBytesMode().path,
            intToBytes(outputFD),
        ],
        env=env,
        childFDs={0: "w", 1: "r", 2: "r", outputFD: outputFD}
    )
    return sspp



class BadList(list):
    """
    A list which cannot be iterated sometimes.

    This is a C{list} subclass to get past the type check in L{send1msg}, not
    as an example of how real programs might want to interact with L{send1msg}
    (or anything else).  A custom C{list} subclass makes it easier to trigger
    certain error cases in the implementation.

    @ivar iterate: A flag which indicates whether an instance of L{BadList}
        will allow iteration over itself or not.  If C{False}, an attempt to
        iterate over the instance will raise an exception.
    """
    iterate = True

    def __iter__(self):
        """
        Allow normal list iteration, or raise an exception.

        If C{self.iterate} is C{True}, it will be flipped to C{False} and then
        normal iteration will proceed.  If C{self.iterate} is C{False},
        L{RuntimeError} is raised instead.
        """
        if self.iterate:
            self.iterate = False
            return super(BadList, self).__iter__()
        raise RuntimeError("Something bad happened")



class WorseList(list):
    """
    A list which at first gives the appearance of being iterable, but then
    raises an exception.

    See L{BadList} for a warning about not writing code like this.
    """
    def __iter__(self):
        """
        Return an iterator which will raise an exception as soon as C{next} is
        called on it.
        """
        class BadIterator(object):
            def next(self):
                raise RuntimeError("This is a really bad case.")
        return BadIterator()



class CModuleSendmsgTests(TestCase):
    """
    Tests for sendmsg extension module and associated file-descriptor sending
    functionality.
    """
    if nonUNIXSkip is not None:
        skip = nonUNIXSkip
    elif CModuleImportSkip is not None:
        skip = CModuleImportSkip

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


    def test_sendmsgBadArguments(self):
        """
        The argument types accepted by L{send1msg} are:

          1. C{int}
          2. read-only character buffer
          3. C{int}
          4. sequence

        The 3rd and 4th arguments are optional.  If fewer than two arguments or
        more than four arguments are passed, or if any of the arguments passed
        are not compatible with these types, L{TypeError} is raised.
        """
        # Exercise the wrong number of arguments cases
        self.assertRaises(TypeError, send1msg)
        self.assertRaises(TypeError, send1msg, 1)
        self.assertRaises(TypeError, send1msg,
                          1, "hello world", 2, [], object())

        # Exercise the wrong type of arguments cases
        self.assertRaises(TypeError, send1msg, object(), "hello world", 2, [])
        self.assertRaises(TypeError, send1msg, 1, object(), 2, [])
        self.assertRaises(TypeError, send1msg, 1, "hello world", object(), [])
        self.assertRaises(TypeError, send1msg, 1, "hello world", 2, object())


    def test_badAncillaryIter(self):
        """
        If iteration over the ancillary data list fails (at the point of the
        C{__iter__} call), the exception with which it fails is propagated to
        the caller of L{send1msg}.
        """
        badList = BadList()
        badList.append((1, 2, "hello world"))
        badList.iterate = False

        self.assertRaises(RuntimeError, send1msg, 1, "hello world", 2, badList)

        # Hit the second iteration
        badList.iterate = True
        self.assertRaises(RuntimeError, send1msg, 1, "hello world", 2, badList)


    def test_badAncillaryNext(self):
        """
        If iteration over the ancillary data list fails (at the point of a
        C{next} call), the exception with which it fails is propagated to the
        caller of L{send1msg}.
        """
        worseList = WorseList()
        self.assertRaises(RuntimeError, send1msg,
                          1, "hello world", 2,worseList)


    def test_sendmsgBadAncillaryItem(self):
        """
        The ancillary data list contains three-tuples with element types of:

          1. C{int}
          2. C{int}
          3. read-only character buffer

        If a tuple in the ancillary data list does not elements of these types,
        L{TypeError} is raised.
        """
        # Exercise the wrong number of arguments cases
        self.assertRaises(TypeError, send1msg, 1, "hello world", 2, [()])
        self.assertRaises(TypeError, send1msg, 1, "hello world", 2, [(1,)])
        self.assertRaises(TypeError, send1msg, 1, "hello world", 2, [(1, 2)])
        self.assertRaises(
            TypeError,
            send1msg, 1, "hello world", 2, [(1, 2, "goodbye", object())])

        # Exercise the wrong type of arguments cases
        exc = self.assertRaises(
            TypeError, send1msg, 1, "hello world", 2, [object()])
        self.assertEqual(
            "send1msg argument 3 expected list of tuple, "
            "got list containing object",
            str(exc))
        self.assertRaises(
            TypeError,
            send1msg, 1, "hello world", 2, [(object(), 1, "goodbye")])
        self.assertRaises(
            TypeError,
            send1msg, 1, "hello world", 2, [(1, object(), "goodbye")])
        self.assertRaises(
            TypeError,
            send1msg, 1, "hello world", 2, [(1, 1, object())])


    def test_syscallError(self):
        """
        If the underlying C{sendmsg} call fails, L{send1msg} raises
        L{socket.error} with its errno set to the underlying errno value.
        """
        with open(devnull) as probe:
            fd = probe.fileno()
        exc = self.assertRaises(error, send1msg, fd, "hello, world")
        self.assertEqual(exc.args[0], errno.EBADF)


    def test_syscallErrorWithControlMessage(self):
        """
        The behavior when the underlying C{sendmsg} call fails is the same
        whether L{send1msg} is passed ancillary data or not.
        """
        with open(devnull) as probe:
            fd = probe.fileno()
        exc = self.assertRaises(
            error, send1msg, fd, "hello, world", 0, [(0, 0, "0123")])
        self.assertEqual(exc.args[0], errno.EBADF)


    def test_roundtrip(self):
        """
        L{recv1msg} will retrieve a message sent via L{send1msg}.
        """
        message = "hello, world!"
        self.assertEqual(
            len(message),
            send1msg(self.input.fileno(), message, 0))

        result = recv1msg(fd=self.output.fileno())
        self.assertEqual(result, (message, 0, []))


    def test_shortsend(self):
        """
        L{send1msg} returns the number of bytes which it was able to send.
        """
        message = "x" * 1024 * 1024
        self.input.setblocking(False)
        sent = send1msg(self.input.fileno(), message)
        # Sanity check - make sure the amount of data we sent was less than the
        # message, but not the whole message, as we should have filled the send
        # buffer. This won't work if the send buffer is more than 1MB, though.
        self.assertTrue(sent < len(message))
        received = recv1msg(self.output.fileno(), 0, len(message))
        self.assertEqual(len(received[0]), sent)


    def test_roundtripEmptyAncillary(self):
        """
        L{send1msg} treats an empty ancillary data list the same way it treats
        receiving no argument for the ancillary parameter at all.
        """
        send1msg(self.input.fileno(), "hello, world!", 0, [])

        result = recv1msg(fd=self.output.fileno())
        self.assertEqual(result, ("hello, world!", 0, []))


    def test_flags(self):
        """
        The C{flags} argument to L{send1msg} is passed on to the underlying
        C{sendmsg} call, to affect it in whatever way is defined by those
        flags.
        """
        # Just exercise one flag with simple, well-known behavior. MSG_DONTWAIT
        # makes the send a non-blocking call, even if the socket is in blocking
        # mode.  See also test_flags in RecvmsgTests
        for i in range(1024):
            try:
                send1msg(self.input.fileno(), "x" * 1024, MSG_DONTWAIT)
            except error as e:
                self.assertEqual(e.args[0], errno.EAGAIN)
                break
        else:
            self.fail(
                "Failed to fill up the send buffer, "
                "or maybe send1msg blocked for a while")
    if dontWaitSkip is not None:
        test_flags.skip = dontWaitSkip


    def test_wrongTypeAncillary(self):
        """
        L{send1msg} will show a helpful exception message when given the wrong
        type of object for the 'ancillary' argument.
        """
        error = self.assertRaises(TypeError,
                                  send1msg, self.input.fileno(),
                                  "hello, world!", 0, 4321)
        self.assertEqual(str(error),
                         "send1msg argument 3 expected list, got int")


    @inlineCallbacks
    def test_sendSubProcessFD(self):
        """
        Calling L{sendsmsg} with SOL_SOCKET, SCM_RIGHTS, and a platform-endian
        packed file descriptor number should send that file descriptor to a
        different process, where it can be retrieved by using L{recv1msg}.
        """
        sspp = _spawn("cmodulepullpipe", self.output.fileno())
        yield sspp.started
        pipeOut, pipeIn = _makePipe()
        self.addCleanup(pipeOut.close)
        self.addCleanup(pipeIn.close)

        with pipeIn:
            send1msg(
                self.input.fileno(), "blonk", 0,
                [(SOL_SOCKET, SCM_RIGHTS, pack("i", pipeIn.fileno()))])

        yield sspp.stopped
        self.assertEqual(read(pipeOut.fileno(), 1024),
                         "Test fixture data: blonk.\n")
        # Make sure that the pipe is actually closed now.
        self.assertEqual(read(pipeOut.fileno(), 1024), "")



class CModuleRecvmsgTests(TestCase):
    """
    Tests for L{recv1msg} (primarily error handling cases).
    """
    if CModuleImportSkip is not None:
        skip = CModuleImportSkip

    def test_badArguments(self):
        """
        The argument types accepted by L{recv1msg} are:

          1. C{int}
          2. C{int}
          3. C{int}
          4. C{int}

        The 2nd, 3rd, and 4th arguments are optional.  If fewer than one
        argument or more than four arguments are passed, or if any of the
        arguments passed are not compatible with these types, L{TypeError} is
        raised.
        """
        # Exercise the wrong number of arguments cases
        self.assertRaises(TypeError, recv1msg)
        self.assertRaises(TypeError, recv1msg, 1, 2, 3, 4, object())

        # Exercise the wrong type of arguments cases
        self.assertRaises(TypeError, recv1msg, object(), 2, 3, 4)
        self.assertRaises(TypeError, recv1msg, 1, object(), 3, 4)
        self.assertRaises(TypeError, recv1msg, 1, 2, object(), 4)
        self.assertRaises(TypeError, recv1msg, 1, 2, 3, object())


    def test_cmsgSpaceOverflow(self):
        """
        L{recv1msg} raises L{OverflowError} if passed a value for the
        C{cmsg_size} argument which exceeds C{SOCKLEN_MAX}.
        """
        self.assertRaises(OverflowError, recv1msg, 0, 0, 0, 0x7FFFFFFF)


    def test_syscallError(self):
        """
        If the underlying C{recvmsg} call fails, L{recv1msg} raises
        L{socket.error} with its errno set to the underlying errno value.
        """
        with open(devnull) as probe:
            fd = probe.fileno()
        exc = self.assertRaises(error, recv1msg, fd)
        self.assertEqual(exc.args[0], errno.EBADF)


    def test_flags(self):
        """
        The C{flags} argument to L{recv1msg} is passed on to the underlying
        C{recvmsg} call, to affect it in whatever way is defined by those
        flags.
        """
        # See test_flags in SendmsgTests
        reader, writer = socketpair(AF_UNIX)
        exc = self.assertRaises(
            error, recv1msg, reader.fileno(), MSG_DONTWAIT)
        self.assertEqual(exc.args[0], errno.EAGAIN)
    if dontWaitSkip is not None:
        test_flags.skip = dontWaitSkip



class CModuleGetSocketFamilyTests(TestCase):
    """
    Tests for L{getsockfam}, a helper which reveals the address family of an
    arbitrary socket.
    """
    if CModuleImportSkip is not None:
        skip = CModuleImportSkip

    def _socket(self, addressFamily):
        """
        Create a new socket using the given address family and return that
        socket's file descriptor.  The socket will automatically be closed when
        the test is torn down.
        """
        s = socket(addressFamily)
        self.addCleanup(s.close)
        return s.fileno()


    def test_badArguments(self):
        """
        L{getsockfam} accepts a single C{int} argument.  If it is called in
        some other way, L{TypeError} is raised.
        """
        self.assertRaises(TypeError, getsockfam)
        self.assertRaises(TypeError, getsockfam, 1, 2)
        self.assertRaises(TypeError, getsockfam, object())


    def test_syscallError(self):
        """
        If the underlying C{getsockname} call fails, L{getsockfam} raises
        L{socket.error} with its errno set to the underlying errno value.
        """
        with open(devnull) as probe:
            fd = probe.fileno()
        exc = self.assertRaises(error, getsockfam, fd)
        self.assertEqual(errno.EBADF, exc.args[0])


    def test_inet(self):
        """
        When passed the file descriptor of a socket created with the C{AF_INET}
        address family, L{getsockfam} returns C{AF_INET}.
        """
        self.assertEqual(AF_INET, getsockfam(self._socket(AF_INET)))


    def test_inet6(self):
        """
        When passed the file descriptor of a socket created with the
        C{AF_INET6} address family, L{getsockfam} returns C{AF_INET6}.
        """
        self.assertEqual(AF_INET6, getsockfam(self._socket(AF_INET6)))


    def test_unix(self):
        """
        When passed the file descriptor of a socket created with the C{AF_UNIX}
        address family, L{getsockfam} returns C{AF_UNIX}.
        """
        self.assertEqual(AF_UNIX, getsockfam(self._socket(AF_UNIX)))
    if nonUNIXSkip is not None:
        test_unix.skip = nonUNIXSkip



class SendmsgTests(TestCase):
    """
    Tests for the Python2/3 compatible L{sendmsg} interface.
    """
    if importSkip is not None:
        skip = importSkip

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
            error, sendmsg, self.input, b"hello, world", [(0, 0, b"0123")], 0)
        self.assertEqual(exc.args[0], errno.EBADF)


    def test_roundtrip(self):
        """
        L{recvmsg} will retrieve a message sent via L{sendmsg}.
        """
        message = b"hello, world!"
        self.assertEqual(
            len(message),
            sendmsg(self.input, message))

        result = recvmsg(self.output)
        self.assertEqual(result.data, b"hello, world!")
        self.assertEqual(result.flags, 0)
        self.assertEqual(result.ancillary, [])


    def test_shortsend(self):
        """
        L{sendmsg} returns the number of bytes which it was able to send.
        """
        message = b"x" * 1024 * 1024
        self.input.setblocking(False)
        sent = sendmsg(self.input, message)
        # Sanity check - make sure the amount of data we sent was less than the
        # message, but not the whole message, as we should have filled the send
        # buffer. This won't work if the send buffer is more than 1MB, though.
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


    def test_flags(self):
        """
        The C{flags} argument to L{sendmsg} is passed on to the underlying
        C{sendmsg} call, to affect it in whatever way is defined by those
        flags.
        """
        # Just exercise one flag with simple, well-known behavior. MSG_DONTWAIT
        # makes the send a non-blocking call, even if the socket is in blocking
        # mode.  See also test_flags in RecvmsgTests
        for i in range(1024):
            try:
                sendmsg(self.input, b"x" * 1024, flags=MSG_DONTWAIT)
            except error as e:
                self.assertEqual(e.args[0], errno.EAGAIN)
                break
        else:
            self.fail(
                "Failed to fill up the send buffer, "
                "or maybe send1msg blocked for a while")
    if dontWaitSkip is not None:
        test_flags.skip = dontWaitSkip


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
                self.input, b"blonk",
                [(SOL_SOCKET, SCM_RIGHTS, pack("i", pipeIn.fileno()))])

        yield sspp.stopped
        self.assertEqual(read(pipeOut.fileno(), 1024),
                         b"Test fixture data: blonk.\n")
        # Make sure that the pipe is actually closed now.
        self.assertEqual(read(pipeOut.fileno(), 1024), b"")



class GetSocketFamilyTests(TestCase):
    """
    Tests for L{getSocketFamily}.
    """
    if importSkip is not None:
        skip = importSkip

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


    def test_unix(self):
        """
        When passed the file descriptor of a socket created with the C{AF_UNIX}
        address family, L{getSocketFamily} returns C{AF_UNIX}.
        """
        self.assertEqual(AF_UNIX, getSocketFamily(self._socket(AF_UNIX)))
    if nonUNIXSkip is not None:
        test_unix.skip = nonUNIXSkip
