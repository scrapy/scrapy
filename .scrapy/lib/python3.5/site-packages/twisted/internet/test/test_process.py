# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for implementations of L{IReactorProcess}.

@var properEnv: A copy of L{os.environ} which has L{bytes} keys/values on POSIX
    platforms and native L{str} keys/values on Windows.
"""

from __future__ import division, absolute_import, print_function

import io
import os
import signal
import sys
import threading
import twisted
import subprocess

from twisted.trial.unittest import TestCase
from twisted.internet.test.reactormixins import ReactorBuilder
from twisted.python.log import msg, err
from twisted.python.runtime import platform
from twisted.python.filepath import FilePath, _asFilesystemBytes
from twisted.python.compat import (networkString, _PY3, xrange, items,
                                   bytesEnviron)
from twisted.internet import utils
from twisted.internet.interfaces import IReactorProcess, IProcessTransport
from twisted.internet.defer import Deferred, succeed
from twisted.internet.protocol import ProcessProtocol
from twisted.internet.error import ProcessDone, ProcessTerminated


# Get the current Python executable as a bytestring.
pyExe = FilePath(sys.executable)._asBytesPath()
twistedRoot = FilePath(twisted.__file__).parent().parent()

_uidgidSkip = None
if platform.isWindows():
    resource = None
    process = None
    _uidgidSkip = "Cannot change UID/GID on Windows"

    properEnv = dict(os.environ)
    properEnv["PYTHONPATH"] = os.pathsep.join(sys.path)
else:
    import resource
    from twisted.internet import process
    if os.getuid() != 0:
        _uidgidSkip = "Cannot change UID/GID except as root"

    properEnv = bytesEnviron()
    properEnv[b"PYTHONPATH"] = os.pathsep.join(sys.path).encode(
        sys.getfilesystemencoding())



def onlyOnPOSIX(testMethod):
    """
    Only run this test on POSIX platforms.

    @param testMethod: A test function, being decorated.

    @return: the C{testMethod} argument.
    """
    if resource is None:
        testMethod.skip = "Test only applies to POSIX platforms."
    return testMethod



class _ShutdownCallbackProcessProtocol(ProcessProtocol):
    """
    An L{IProcessProtocol} which fires a Deferred when the process it is
    associated with ends.

    @ivar received: A C{dict} mapping file descriptors to lists of bytes
        received from the child process on those file descriptors.
    """
    def __init__(self, whenFinished):
        self.whenFinished = whenFinished
        self.received = {}


    def childDataReceived(self, fd, bytes):
        self.received.setdefault(fd, []).append(bytes)


    def processEnded(self, reason):
        self.whenFinished.callback(None)



class ProcessTestsBuilderBase(ReactorBuilder):
    """
    Base class for L{IReactorProcess} tests which defines some tests which
    can be applied to PTY or non-PTY uses of C{spawnProcess}.

    Subclasses are expected to set the C{usePTY} attribute to C{True} or
    C{False}.
    """
    requiredInterfaces = [IReactorProcess]


    def test_processTransportInterface(self):
        """
        L{IReactorProcess.spawnProcess} connects the protocol passed to it
        to a transport which provides L{IProcessTransport}.
        """
        ended = Deferred()
        protocol = _ShutdownCallbackProcessProtocol(ended)

        reactor = self.buildReactor()
        transport = reactor.spawnProcess(
            protocol, pyExe, [pyExe, b"-c", b""],
            usePTY=self.usePTY)

        # The transport is available synchronously, so we can check it right
        # away (unlike many transport-based tests).  This is convenient even
        # though it's probably not how the spawnProcess interface should really
        # work.
        # We're not using verifyObject here because part of
        # IProcessTransport is a lie - there are no getHost or getPeer
        # methods.  See #1124.
        self.assertTrue(IProcessTransport.providedBy(transport))

        # Let the process run and exit so we don't leave a zombie around.
        ended.addCallback(lambda ignored: reactor.stop())
        self.runReactor(reactor)


    def _writeTest(self, write):
        """
        Helper for testing L{IProcessTransport} write functionality.  This
        method spawns a child process and gives C{write} a chance to write some
        bytes to it.  It then verifies that the bytes were actually written to
        it (by relying on the child process to echo them back).

        @param write: A two-argument callable.  This is invoked with a process
            transport and some bytes to write to it.
        """
        reactor = self.buildReactor()

        ended = Deferred()
        protocol = _ShutdownCallbackProcessProtocol(ended)

        bytesToSend = b"hello, world" + networkString(os.linesep)
        program = (
            b"import sys\n"
            b"sys.stdout.write(sys.stdin.readline())\n"
            )

        def startup():
            transport = reactor.spawnProcess(
                protocol, pyExe, [pyExe, b"-c", program])
            try:
                write(transport, bytesToSend)
            except:
                err(None, "Unhandled exception while writing")
                transport.signalProcess('KILL')
        reactor.callWhenRunning(startup)

        ended.addCallback(lambda ignored: reactor.stop())

        self.runReactor(reactor)
        self.assertEqual(bytesToSend, b"".join(protocol.received[1]))


    def test_write(self):
        """
        L{IProcessTransport.write} writes the specified C{bytes} to the standard
        input of the child process.
        """
        def write(transport, bytesToSend):
            transport.write(bytesToSend)
        self._writeTest(write)


    def test_writeSequence(self):
        """
        L{IProcessTransport.writeSequence} writes the specified C{list} of
        C{bytes} to the standard input of the child process.
        """
        def write(transport, bytesToSend):
            transport.writeSequence([bytesToSend])
        self._writeTest(write)


    def test_writeToChild(self):
        """
        L{IProcessTransport.writeToChild} writes the specified C{bytes} to the
        specified file descriptor of the child process.
        """
        def write(transport, bytesToSend):
            transport.writeToChild(0, bytesToSend)
        self._writeTest(write)


    def test_writeToChildBadFileDescriptor(self):
        """
        L{IProcessTransport.writeToChild} raises L{KeyError} if passed a file
        descriptor which is was not set up by L{IReactorProcess.spawnProcess}.
        """
        def write(transport, bytesToSend):
            try:
                self.assertRaises(KeyError, transport.writeToChild, 13, bytesToSend)
            finally:
                # Just get the process to exit so the test can complete
                transport.write(bytesToSend)
        self._writeTest(write)


    def test_spawnProcessEarlyIsReaped(self):
        """
        If, before the reactor is started with L{IReactorCore.run}, a
        process is started with L{IReactorProcess.spawnProcess} and
        terminates, the process is reaped once the reactor is started.
        """
        reactor = self.buildReactor()

        # Create the process with no shared file descriptors, so that there
        # are no other events for the reactor to notice and "cheat" with.
        # We want to be sure it's really dealing with the process exiting,
        # not some associated event.
        if self.usePTY:
            childFDs = None
        else:
            childFDs = {}

        # Arrange to notice the SIGCHLD.
        signaled = threading.Event()
        def handler(*args):
            signaled.set()
        signal.signal(signal.SIGCHLD, handler)

        # Start a process - before starting the reactor!
        ended = Deferred()
        reactor.spawnProcess(
            _ShutdownCallbackProcessProtocol(ended), pyExe,
            [pyExe, b"-c", b""], usePTY=self.usePTY, childFDs=childFDs)

        # Wait for the SIGCHLD (which might have been delivered before we got
        # here, but that's okay because the signal handler was installed above,
        # before we could have gotten it).
        signaled.wait(120)
        if not signaled.isSet():
            self.fail("Timed out waiting for child process to exit.")

        # Capture the processEnded callback.
        result = []
        ended.addCallback(result.append)

        if result:
            # The synchronous path through spawnProcess / Process.__init__ /
            # registerReapProcessHandler was encountered.  There's no reason to
            # start the reactor, because everything is done already.
            return

        # Otherwise, though, start the reactor so it can tell us the process
        # exited.
        ended.addCallback(lambda ignored: reactor.stop())
        self.runReactor(reactor)

        # Make sure the reactor stopped because the Deferred fired.
        self.assertTrue(result)

    if getattr(signal, 'SIGCHLD', None) is None:
        test_spawnProcessEarlyIsReaped.skip = (
            "Platform lacks SIGCHLD, early-spawnProcess test can't work.")


    def test_processExitedWithSignal(self):
        """
        The C{reason} argument passed to L{IProcessProtocol.processExited} is a
        L{ProcessTerminated} instance if the child process exits with a signal.
        """
        sigName = 'TERM'
        sigNum = getattr(signal, 'SIG' + sigName)
        exited = Deferred()
        source = (
            b"import sys\n"
            # Talk so the parent process knows the process is running.  This is
            # necessary because ProcessProtocol.makeConnection may be called
            # before this process is exec'd.  It would be unfortunate if we
            # SIGTERM'd the Twisted process while it was on its way to doing
            # the exec.
            b"sys.stdout.write('x')\n"
            b"sys.stdout.flush()\n"
            b"sys.stdin.read()\n")

        class Exiter(ProcessProtocol):
            def childDataReceived(self, fd, data):
                msg('childDataReceived(%d, %r)' % (fd, data))
                self.transport.signalProcess(sigName)

            def childConnectionLost(self, fd):
                msg('childConnectionLost(%d)' % (fd,))

            def processExited(self, reason):
                msg('processExited(%r)' % (reason,))
                # Protect the Deferred from the failure so that it follows
                # the callback chain.  This doesn't use the errback chain
                # because it wants to make sure reason is a Failure.  An
                # Exception would also make an errback-based test pass, and
                # that would be wrong.
                exited.callback([reason])

            def processEnded(self, reason):
                msg('processEnded(%r)' % (reason,))

        reactor = self.buildReactor()
        reactor.callWhenRunning(
            reactor.spawnProcess, Exiter(), pyExe,
            [pyExe, b"-c", source], usePTY=self.usePTY)

        def cbExited(args):
            failure, = args
            # Trapping implicitly verifies that it's a Failure (rather than
            # an exception) and explicitly makes sure it's the right type.
            failure.trap(ProcessTerminated)
            err = failure.value
            if platform.isWindows():
                # Windows can't really /have/ signals, so it certainly can't
                # report them as the reason for termination.  Maybe there's
                # something better we could be doing here, anyway?  Hard to
                # say.  Anyway, this inconsistency between different platforms
                # is extremely unfortunate and I would remove it if I
                # could. -exarkun
                self.assertIsNone(err.signal)
                self.assertEqual(err.exitCode, 1)
            else:
                self.assertEqual(err.signal, sigNum)
                self.assertIsNone(err.exitCode)

        exited.addCallback(cbExited)
        exited.addErrback(err)
        exited.addCallback(lambda ign: reactor.stop())

        self.runReactor(reactor)


    def test_systemCallUninterruptedByChildExit(self):
        """
        If a child process exits while a system call is in progress, the system
        call should not be interfered with.  In particular, it should not fail
        with EINTR.

        Older versions of Twisted installed a SIGCHLD handler on POSIX without
        using the feature exposed by the SA_RESTART flag to sigaction(2).  The
        most noticeable problem this caused was for blocking reads and writes to
        sometimes fail with EINTR.
        """
        reactor = self.buildReactor()
        result = []

        def f():
            try:
                if platform.isWindows():
                    exe = pyExe.decode('mbcs')
                else:
                    exe = pyExe.decode('ascii')

                subprocess.Popen([exe, "-c", "import time; time.sleep(0.1)"])
                f2 = subprocess.Popen([exe, "-c",
                                       ("import time; time.sleep(0.5);"
                                        "print(\'Foo\')")],
                                      stdout=subprocess.PIPE)
                # The read call below will blow up with an EINTR from the
                # SIGCHLD from the first process exiting if we install a
                # SIGCHLD handler without SA_RESTART.  (which we used to do)
                with f2.stdout:
                    result.append(f2.stdout.read())
            finally:
                reactor.stop()

        reactor.callWhenRunning(f)
        self.runReactor(reactor)
        self.assertEqual(result, [b"Foo" + os.linesep.encode('ascii')])


    @onlyOnPOSIX
    def test_openFileDescriptors(self):
        """
        Processes spawned with spawnProcess() close all extraneous file
        descriptors in the parent.  They do have a stdin, stdout, and stderr
        open.
        """

        # To test this, we are going to open a file descriptor in the parent
        # that is unlikely to be opened in the child, then verify that it's not
        # open in the child.
        source = networkString("""
import sys
sys.path.insert(0, '{0}')
from twisted.internet import process
sys.stdout.write(repr(process._listOpenFDs()))
sys.stdout.flush()""".format(twistedRoot.path))

        r, w = os.pipe()
        self.addCleanup(os.close, r)
        self.addCleanup(os.close, w)

        # The call to "os.listdir()" (in _listOpenFDs's implementation) opens a
        # file descriptor (with "opendir"), which shows up in _listOpenFDs's
        # result.  And speaking of "random" file descriptors, the code required
        # for _listOpenFDs itself imports logger, which imports random, which
        # (depending on your Python version) might leave /dev/urandom open.

        # More generally though, even if we were to use an extremely minimal C
        # program, the operating system would be within its rights to open file
        # descriptors we might not know about in the C library's
        # initialization; things like debuggers, profilers, or nsswitch plugins
        # might open some and this test should pass in those environments.

        # Although some of these file descriptors aren't predictable, we should
        # at least be able to select a very large file descriptor which is very
        # unlikely to be opened automatically in the subprocess.  (Apply a
        # fudge factor to avoid hard-coding something too near a limit
        # condition like the maximum possible file descriptor, which a library
        # might at least hypothetically select.)

        fudgeFactor = 17
        unlikelyFD = (resource.getrlimit(resource.RLIMIT_NOFILE)[0]
                      - fudgeFactor)

        os.dup2(w, unlikelyFD)
        self.addCleanup(os.close, unlikelyFD)

        output = io.BytesIO()
        class GatheringProtocol(ProcessProtocol):
            outReceived = output.write
            def processEnded(self, reason):
                reactor.stop()

        reactor = self.buildReactor()

        reactor.callWhenRunning(
            reactor.spawnProcess, GatheringProtocol(), pyExe,
            [pyExe, b"-Wignore", b"-c", source], usePTY=self.usePTY)

        self.runReactor(reactor)
        reportedChildFDs = set(eval(output.getvalue()))

        stdFDs = [0, 1, 2]

        # Unfortunately this assertion is still not *entirely* deterministic,
        # since hypothetically, any library could open any file descriptor at
        # any time.  See comment above.
        self.assertEqual(
            reportedChildFDs.intersection(set(stdFDs + [unlikelyFD])),
            set(stdFDs)
        )


    @onlyOnPOSIX
    def test_errorDuringExec(self):
        """
        When L{os.execvpe} raises an exception, it will format that exception
        on stderr as UTF-8, regardless of system encoding information.
        """

        def execvpe(*args, **kw):
            # Ensure that real traceback formatting has some non-ASCII in it,
            # by forcing the filename of the last frame to contain non-ASCII.
            filename = u"<\N{SNOWMAN}>"
            if not isinstance(filename, str):
                filename = filename.encode("utf-8")
            codeobj = compile("1/0", filename, "single")
            eval(codeobj)

        self.patch(os, "execvpe", execvpe)
        self.patch(sys, "getfilesystemencoding", lambda: "ascii")

        reactor = self.buildReactor()
        output = io.BytesIO()

        @reactor.callWhenRunning
        def whenRunning():
            class TracebackCatcher(ProcessProtocol, object):
                errReceived = output.write
                def processEnded(self, reason):
                    reactor.stop()
            reactor.spawnProcess(TracebackCatcher(), pyExe,
                                 [pyExe, b"-c", b""])

        self.runReactor(reactor, timeout=30)
        self.assertIn(u"\N{SNOWMAN}".encode("utf-8"), output.getvalue())


    def test_timelyProcessExited(self):
        """
        If a spawned process exits, C{processExited} will be called in a
        timely manner.
        """
        reactor = self.buildReactor()

        class ExitingProtocol(ProcessProtocol):
            exited = False

            def processExited(protoSelf, reason):
                protoSelf.exited = True
                reactor.stop()
                self.assertEqual(reason.value.exitCode, 0)

        protocol = ExitingProtocol()
        reactor.callWhenRunning(
            reactor.spawnProcess, protocol, pyExe,
            [pyExe, b"-c", b"raise SystemExit(0)"],
            usePTY=self.usePTY)

        # This will timeout if processExited isn't called:
        self.runReactor(reactor, timeout=30)
        self.assertTrue(protocol.exited)


    def _changeIDTest(self, which):
        """
        Launch a child process, using either the C{uid} or C{gid} argument to
        L{IReactorProcess.spawnProcess} to change either its UID or GID to a
        different value.  If the child process reports this hasn't happened,
        raise an exception to fail the test.

        @param which: Either C{b"uid"} or C{b"gid"}.
        """
        program = [
            "import os",
            "raise SystemExit(os.get%s() != 1)" % (which,)]

        container = []
        class CaptureExitStatus(ProcessProtocol):
            def processEnded(self, reason):
                container.append(reason)
                reactor.stop()

        reactor = self.buildReactor()
        protocol = CaptureExitStatus()
        reactor.callWhenRunning(
            reactor.spawnProcess, protocol, pyExe,
            [pyExe, "-c", "\n".join(program)],
            **{which: 1})

        self.runReactor(reactor)

        self.assertEqual(0, container[0].value.exitCode)


    def test_changeUID(self):
        """
        If a value is passed for L{IReactorProcess.spawnProcess}'s C{uid}, the
        child process is run with that UID.
        """
        self._changeIDTest("uid")
    if _uidgidSkip is not None:
        test_changeUID.skip = _uidgidSkip


    def test_changeGID(self):
        """
        If a value is passed for L{IReactorProcess.spawnProcess}'s C{gid}, the
        child process is run with that GID.
        """
        self._changeIDTest("gid")
    if _uidgidSkip is not None:
        test_changeGID.skip = _uidgidSkip


    def test_processExitedRaises(self):
        """
        If L{IProcessProtocol.processExited} raises an exception, it is logged.
        """
        # Ideally we wouldn't need to poke the process module; see
        # https://twistedmatrix.com/trac/ticket/6889
        reactor = self.buildReactor()

        class TestException(Exception):
            pass

        class Protocol(ProcessProtocol):
            def processExited(self, reason):
                reactor.stop()
                raise TestException("processedExited raised")

        protocol = Protocol()
        transport = reactor.spawnProcess(
               protocol, pyExe, [pyExe, b"-c", b""],
               usePTY=self.usePTY)
        self.runReactor(reactor)

        # Manually clean-up broken process handler.
        # Only required if the test fails on systems that support
        # the process module.
        if process is not None:
            for pid, handler in items(process.reapProcessHandlers):
                if handler is not transport:
                    continue
                process.unregisterReapProcessHandler(pid, handler)
                self.fail("After processExited raised, transport was left in"
                          " reapProcessHandlers")

        self.assertEqual(1, len(self.flushLoggedErrors(TestException)))



class ProcessTestsBuilder(ProcessTestsBuilderBase):
    """
    Builder defining tests relating to L{IReactorProcess} for child processes
    which do not have a PTY.
    """
    usePTY = False

    keepStdioOpenProgram = b'twisted.internet.test.process_helper'
    if platform.isWindows():
        keepStdioOpenArg = b"windows"
    else:
        # Just a value that doesn't equal "windows"
        keepStdioOpenArg = b""


    # Define this test here because PTY-using processes only have stdin and
    # stdout and the test would need to be different for that to work.
    def test_childConnectionLost(self):
        """
        L{IProcessProtocol.childConnectionLost} is called each time a file
        descriptor associated with a child process is closed.
        """
        connected = Deferred()
        lost = {0: Deferred(), 1: Deferred(), 2: Deferred()}

        class Closer(ProcessProtocol):
            def makeConnection(self, transport):
                connected.callback(transport)

            def childConnectionLost(self, childFD):
                lost[childFD].callback(None)

        target = b"twisted.internet.test.process_loseconnection"

        reactor = self.buildReactor()
        reactor.callWhenRunning(
            reactor.spawnProcess, Closer(), pyExe,
            [pyExe, b"-m", target], env=properEnv, usePTY=self.usePTY)

        def cbConnected(transport):
            transport.write(b'2\n')
            return lost[2].addCallback(lambda ign: transport)
        connected.addCallback(cbConnected)

        def lostSecond(transport):
            transport.write(b'1\n')
            return lost[1].addCallback(lambda ign: transport)
        connected.addCallback(lostSecond)

        def lostFirst(transport):
            transport.write(b'\n')
        connected.addCallback(lostFirst)
        connected.addErrback(err)

        def cbEnded(ignored):
            reactor.stop()
        connected.addCallback(cbEnded)

        self.runReactor(reactor)


    # This test is here because PTYProcess never delivers childConnectionLost.
    def test_processEnded(self):
        """
        L{IProcessProtocol.processEnded} is called after the child process
        exits and L{IProcessProtocol.childConnectionLost} is called for each of
        its file descriptors.
        """
        ended = Deferred()
        lost = []

        class Ender(ProcessProtocol):
            def childDataReceived(self, fd, data):
                msg('childDataReceived(%d, %r)' % (fd, data))
                self.transport.loseConnection()

            def childConnectionLost(self, childFD):
                msg('childConnectionLost(%d)' % (childFD,))
                lost.append(childFD)

            def processExited(self, reason):
                msg('processExited(%r)' % (reason,))

            def processEnded(self, reason):
                msg('processEnded(%r)' % (reason,))
                ended.callback([reason])

        reactor = self.buildReactor()
        reactor.callWhenRunning(
            reactor.spawnProcess, Ender(), pyExe,
            [pyExe, b"-m", self.keepStdioOpenProgram, b"child",
             self.keepStdioOpenArg],
            env=properEnv, usePTY=self.usePTY)

        def cbEnded(args):
            failure, = args
            failure.trap(ProcessDone)
            self.assertEqual(set(lost), set([0, 1, 2]))
        ended.addCallback(cbEnded)

        ended.addErrback(err)
        ended.addCallback(lambda ign: reactor.stop())

        self.runReactor(reactor)


    # This test is here because PTYProcess.loseConnection does not actually
    # close the file descriptors to the child process.  This test needs to be
    # written fairly differently for PTYProcess.
    def test_processExited(self):
        """
        L{IProcessProtocol.processExited} is called when the child process
        exits, even if file descriptors associated with the child are still
        open.
        """
        exited = Deferred()
        allLost = Deferred()
        lost = []

        class Waiter(ProcessProtocol):
            def childDataReceived(self, fd, data):
                msg('childDataReceived(%d, %r)' % (fd, data))

            def childConnectionLost(self, childFD):
                msg('childConnectionLost(%d)' % (childFD,))
                lost.append(childFD)
                if len(lost) == 3:
                    allLost.callback(None)

            def processExited(self, reason):
                msg('processExited(%r)' % (reason,))
                # See test_processExitedWithSignal
                exited.callback([reason])
                self.transport.loseConnection()

        reactor = self.buildReactor()
        reactor.callWhenRunning(
            reactor.spawnProcess, Waiter(), pyExe,
            [pyExe, b"-u", b"-m", self.keepStdioOpenProgram, b"child",
             self.keepStdioOpenArg],
            env=properEnv, usePTY=self.usePTY)

        def cbExited(args):
            failure, = args
            failure.trap(ProcessDone)
            msg('cbExited; lost = %s' % (lost,))
            self.assertEqual(lost, [])
            return allLost
        exited.addCallback(cbExited)

        def cbAllLost(ignored):
            self.assertEqual(set(lost), set([0, 1, 2]))
        exited.addCallback(cbAllLost)

        exited.addErrback(err)
        exited.addCallback(lambda ign: reactor.stop())

        self.runReactor(reactor)


    def makeSourceFile(self, sourceLines):
        """
        Write the given list of lines to a text file and return the absolute
        path to it.
        """
        script = _asFilesystemBytes(self.mktemp())
        with open(script, 'wt') as scriptFile:
            scriptFile.write(os.linesep.join(sourceLines) + os.linesep)
        return os.path.abspath(script)


    def test_shebang(self):
        """
        Spawning a process with an executable which is a script starting
        with an interpreter definition line (#!) uses that interpreter to
        evaluate the script.
        """
        shebangOutput = b'this is the shebang output'

        scriptFile = self.makeSourceFile([
                "#!%s" % (pyExe.decode('ascii'),),
                "import sys",
                "sys.stdout.write('%s')" % (shebangOutput.decode('ascii'),),
                "sys.stdout.flush()"])
        os.chmod(scriptFile, 0o700)

        reactor = self.buildReactor()

        def cbProcessExited(args):
            out, err, code = args
            msg("cbProcessExited((%r, %r, %d))" % (out, err, code))
            self.assertEqual(out, shebangOutput)
            self.assertEqual(err, b"")
            self.assertEqual(code, 0)

        def shutdown(passthrough):
            reactor.stop()
            return passthrough

        def start():
            d = utils.getProcessOutputAndValue(scriptFile, reactor=reactor)
            d.addBoth(shutdown)
            d.addCallback(cbProcessExited)
            d.addErrback(err)

        reactor.callWhenRunning(start)
        self.runReactor(reactor)


    def test_processCommandLineArguments(self):
        """
        Arguments given to spawnProcess are passed to the child process as
        originally intended.
        """
        us = b"twisted.internet.test.process_cli"

        args = [b'hello', b'"', b' \t|<>^&', br'"\\"hello\\"', br'"foo\ bar baz\""']
        # Ensure that all non-NUL characters can be passed too.
        if _PY3:
            args.append("".join(map(chr, xrange(1,255))).encode("utf8"))
        else:
            args.append("".join(map(chr, xrange(1,255))))

        reactor = self.buildReactor()

        def processFinished(finishedArgs):
            output, err, code = finishedArgs
            output = output.split(b'\0')
            # Drop the trailing \0.
            output.pop()
            self.assertEqual(args, output)

        def shutdown(result):
            reactor.stop()
            return result

        def spawnChild():
            d = succeed(None)
            d.addCallback(lambda dummy: utils.getProcessOutputAndValue(
                pyExe, [b"-m", us] + args, env=properEnv,
                reactor=reactor))
            d.addCallback(processFinished)
            d.addBoth(shutdown)

        reactor.callWhenRunning(spawnChild)
        self.runReactor(reactor)
globals().update(ProcessTestsBuilder.makeTestCaseClasses())



class PTYProcessTestsBuilder(ProcessTestsBuilderBase):
    """
    Builder defining tests relating to L{IReactorProcess} for child processes
    which have a PTY.
    """
    usePTY = True

    if platform.isWindows():
        skip = "PTYs are not supported on Windows."
    elif platform.isMacOSX():
        skippedReactors = {
            "twisted.internet.pollreactor.PollReactor":
                "OS X's poll() does not support PTYs"}
globals().update(PTYProcessTestsBuilder.makeTestCaseClasses())



class PotentialZombieWarningTests(TestCase):
    """
    Tests for L{twisted.internet.error.PotentialZombieWarning}.
    """
    def test_deprecated(self):
        """
        Accessing L{PotentialZombieWarning} via the
        I{PotentialZombieWarning} attribute of L{twisted.internet.error}
        results in a deprecation warning being emitted.
        """
        from twisted.internet import error
        error.PotentialZombieWarning

        warnings = self.flushWarnings([self.test_deprecated])
        self.assertEqual(warnings[0]['category'], DeprecationWarning)
        self.assertEqual(
            warnings[0]['message'],
            "twisted.internet.error.PotentialZombieWarning was deprecated in "
            "Twisted 10.0.0: There is no longer any potential for zombie "
            "process.")
        self.assertEqual(len(warnings), 1)



class ProcessIsUnimportableOnUnsupportedPlatormsTests(TestCase):
    """
    Tests to ensure that L{twisted.internet.process} is unimportable on
    platforms where it does not work (namely Windows).
    """
    def test_unimportableOnWindows(self):
        """
        L{twisted.internet.process} is unimportable on Windows.
        """
        with self.assertRaises(ImportError):
            import twisted.internet.process
            twisted.internet.process # shh pyflakes

    if not platform.isWindows():
        test_unimportableOnWindows.skip = "Only relevant on Windows."
