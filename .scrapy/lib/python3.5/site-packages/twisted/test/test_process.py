# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test running processes.

@var CONCURRENT_PROCESS_TEST_COUNT: The number of concurrent processes to use
    to stress-test the spawnProcess API.  This value is tuned to a number of
    processes which has been determined to stay below various
    experimentally-determined limitations of our supported platforms.
    Particularly, Windows XP seems to have some undocumented limitations which
    cause spurious failures if this value is pushed too high.  U{Please see
    this ticket for a discussion of how we arrived at its current value.
    <http://twistedmatrix.com/trac/ticket/3404>}

@var properEnv: A copy of L{os.environ} which has L{bytes} keys/values on POSIX
    platforms and native L{str} keys/values on Windows.
"""

from __future__ import division, absolute_import, print_function

import gzip
import os
import sys
import signal
import errno
import gc
import stat
import operator


try:
    import fcntl
except ImportError:
    fcntl = process = None
else:
    from twisted.internet import process

from zope.interface.verify import verifyObject

from io import BytesIO

from twisted.python.log import msg
from twisted.internet import reactor, protocol, error, interfaces, defer
from twisted.trial import unittest
from twisted.python import util, runtime, procutils
from twisted.python.compat import _PY3, networkString, xrange, bytesEnviron
from twisted.python.filepath import FilePath


# Get the current Python executable as a bytestring.
pyExe = FilePath(sys.executable)._asBytesPath()
CONCURRENT_PROCESS_TEST_COUNT = 25
if not runtime.platform.isWindows():
    properEnv = bytesEnviron()
    properEnv[b"PYTHONPATH"] = os.pathsep.join(sys.path).encode(
        sys.getfilesystemencoding())
else:
    properEnv = dict(os.environ)
    properEnv["PYTHONPATH"] = os.pathsep.join(sys.path)


class StubProcessProtocol(protocol.ProcessProtocol):
    """
    ProcessProtocol counter-implementation: all methods on this class raise an
    exception, so instances of this may be used to verify that only certain
    methods are called.
    """
    def outReceived(self, data):
        raise NotImplementedError()

    def errReceived(self, data):
        raise NotImplementedError()

    def inConnectionLost(self):
        raise NotImplementedError()

    def outConnectionLost(self):
        raise NotImplementedError()

    def errConnectionLost(self):
        raise NotImplementedError()



class ProcessProtocolTests(unittest.TestCase):
    """
    Tests for behavior provided by the process protocol base class,
    L{protocol.ProcessProtocol}.
    """
    def test_interface(self):
        """
        L{ProcessProtocol} implements L{IProcessProtocol}.
        """
        verifyObject(interfaces.IProcessProtocol, protocol.ProcessProtocol())


    def test_outReceived(self):
        """
        Verify that when stdout is delivered to
        L{ProcessProtocol.childDataReceived}, it is forwarded to
        L{ProcessProtocol.outReceived}.
        """
        received = []
        class OutProtocol(StubProcessProtocol):
            def outReceived(self, data):
                received.append(data)

        bytesToSend = b"bytes"
        p = OutProtocol()
        p.childDataReceived(1, bytesToSend)
        self.assertEqual(received, [bytesToSend])


    def test_errReceived(self):
        """
        Similar to L{test_outReceived}, but for stderr.
        """
        received = []
        class ErrProtocol(StubProcessProtocol):
            def errReceived(self, data):
                received.append(data)

        bytesToSend = b"bytes"
        p = ErrProtocol()
        p.childDataReceived(2, bytesToSend)
        self.assertEqual(received, [bytesToSend])


    def test_inConnectionLost(self):
        """
        Verify that when stdin close notification is delivered to
        L{ProcessProtocol.childConnectionLost}, it is forwarded to
        L{ProcessProtocol.inConnectionLost}.
        """
        lost = []
        class InLostProtocol(StubProcessProtocol):
            def inConnectionLost(self):
                lost.append(None)

        p = InLostProtocol()
        p.childConnectionLost(0)
        self.assertEqual(lost, [None])


    def test_outConnectionLost(self):
        """
        Similar to L{test_inConnectionLost}, but for stdout.
        """
        lost = []
        class OutLostProtocol(StubProcessProtocol):
            def outConnectionLost(self):
                lost.append(None)

        p = OutLostProtocol()
        p.childConnectionLost(1)
        self.assertEqual(lost, [None])


    def test_errConnectionLost(self):
        """
        Similar to L{test_inConnectionLost}, but for stderr.
        """
        lost = []
        class ErrLostProtocol(StubProcessProtocol):
            def errConnectionLost(self):
                lost.append(None)

        p = ErrLostProtocol()
        p.childConnectionLost(2)
        self.assertEqual(lost, [None])



class TrivialProcessProtocol(protocol.ProcessProtocol):
    """
    Simple process protocol for tests purpose.

    @ivar outData: data received from stdin
    @ivar errData: data received from stderr
    """

    def __init__(self, d):
        """
        Create the deferred that will be fired at the end, and initialize
        data structures.
        """
        self.deferred = d
        self.outData = []
        self.errData = []

    def processEnded(self, reason):
        self.reason = reason
        self.deferred.callback(None)

    def outReceived(self, data):
        self.outData.append(data)

    def errReceived(self, data):
        self.errData.append(data)


class TestProcessProtocol(protocol.ProcessProtocol):

    def connectionMade(self):
        self.stages = [1]
        self.data = b''
        self.err = b''
        self.transport.write(b"abcd")

    def childDataReceived(self, childFD, data):
        """
        Override and disable the dispatch provided by the base class to ensure
        that it is really this method which is being called, and the transport
        is not going directly to L{outReceived} or L{errReceived}.
        """
        if childFD == 1:
            self.data += data
        elif childFD == 2:
            self.err += data


    def childConnectionLost(self, childFD):
        """
        Similarly to L{childDataReceived}, disable the automatic dispatch
        provided by the base implementation to verify that the transport is
        calling this method directly.
        """
        if childFD == 1:
            self.stages.append(2)
            if self.data != b"abcd":
                raise RuntimeError(
                    "Data was %r instead of 'abcd'" % (self.data,))
            self.transport.write(b"1234")
        elif childFD == 2:
            self.stages.append(3)
            if self.err != b"1234":
                raise RuntimeError(
                    "Err was %r instead of '1234'" % (self.err,))
            self.transport.write(b"abcd")
            self.stages.append(4)
        elif childFD == 0:
            self.stages.append(5)

    def processEnded(self, reason):
        self.reason = reason
        self.deferred.callback(None)


class EchoProtocol(protocol.ProcessProtocol):

    s = b"1234567" * 1001
    n = 10
    finished = 0

    failure = None

    def __init__(self, onEnded):
        self.onEnded = onEnded
        self.count = 0

    def connectionMade(self):
        assert self.n > 2
        for i in range(self.n - 2):
            self.transport.write(self.s)
        # test writeSequence
        self.transport.writeSequence([self.s, self.s])
        self.buffer = self.s * self.n

    def outReceived(self, data):
        if self.buffer[self.count:self.count+len(data)] != data:
            self.failure = ("wrong bytes received", data, self.count)
            self.transport.closeStdin()
        else:
            self.count += len(data)
            if self.count == len(self.buffer):
                self.transport.closeStdin()

    def processEnded(self, reason):
        self.finished = 1
        if not reason.check(error.ProcessDone):
            self.failure = "process didn't terminate normally: " + str(reason)
        self.onEnded.callback(self)



class SignalProtocol(protocol.ProcessProtocol):
    """
    A process protocol that sends a signal when data is first received.

    @ivar deferred: deferred firing on C{processEnded}.
    @type deferred: L{defer.Deferred}

    @ivar signal: the signal to send to the process.
    @type signal: C{str}

    @ivar signaled: A flag tracking whether the signal has been sent to the
        child or not yet.  C{False} until it is sent, then C{True}.
    @type signaled: C{bool}
    """

    def __init__(self, deferred, sig):
        self.deferred = deferred
        self.signal = sig
        self.signaled = False


    def outReceived(self, data):
        """
        Handle the first output from the child process (which indicates it
        is set up and ready to receive the signal) by sending the signal to
        it.  Also log all output to help with debugging.
        """
        msg("Received %r from child stdout" % (data,))
        if not self.signaled:
            self.signaled = True
            self.transport.signalProcess(self.signal)


    def errReceived(self, data):
        """
        Log all data received from the child's stderr to help with
        debugging.
        """
        msg("Received %r from child stderr" % (data,))


    def processEnded(self, reason):
        """
        Callback C{self.deferred} with L{None} if C{reason} is a
        L{error.ProcessTerminated} failure with C{exitCode} set to L{None},
        C{signal} set to C{self.signal}, and C{status} holding the status code
        of the exited process. Otherwise, errback with a C{ValueError}
        describing the problem.
        """
        msg("Child exited: %r" % (reason.getTraceback(),))
        if not reason.check(error.ProcessTerminated):
            return self.deferred.errback(
                ValueError("wrong termination: %s" % (reason,)))
        v = reason.value
        if isinstance(self.signal, str):
            signalValue = getattr(signal, 'SIG' + self.signal)
        else:
            signalValue = self.signal
        if v.exitCode is not None:
            return self.deferred.errback(
                ValueError("SIG%s: exitCode is %s, not None" %
                           (self.signal, v.exitCode)))
        if v.signal != signalValue:
            return self.deferred.errback(
                ValueError("SIG%s: .signal was %s, wanted %s" %
                           (self.signal, v.signal, signalValue)))
        if os.WTERMSIG(v.status) != signalValue:
            return self.deferred.errback(
                ValueError('SIG%s: %s' % (self.signal, os.WTERMSIG(v.status))))
        self.deferred.callback(None)



class TestManyProcessProtocol(TestProcessProtocol):
    def __init__(self):
        self.deferred = defer.Deferred()

    def processEnded(self, reason):
        self.reason = reason
        if reason.check(error.ProcessDone):
            self.deferred.callback(None)
        else:
            self.deferred.errback(reason)



class UtilityProcessProtocol(protocol.ProcessProtocol):
    """
    Helper class for launching a Python process and getting a result from it.

    @ivar programName: The name of the program to run.
    """
    programName = None

    @classmethod
    def run(cls, reactor, argv, env):
        """
        Run a Python process connected to a new instance of this protocol
        class.  Return the protocol instance.

        The Python process is given C{self.program} on the command line to
        execute, in addition to anything specified by C{argv}.  C{env} is
        the complete environment.
        """
        self = cls()
        reactor.spawnProcess(
            self, pyExe, [pyExe, b"-u", b"-m", self.programName] + argv,
            env=env)
        return self


    def __init__(self):
        self.bytes = []
        self.requests = []


    def parseChunks(self, bytes):
        """
        Called with all bytes received on stdout when the process exits.
        """
        raise NotImplementedError()


    def getResult(self):
        """
        Return a Deferred which will fire with the result of L{parseChunks}
        when the child process exits.
        """
        d = defer.Deferred()
        self.requests.append(d)
        return d


    def _fireResultDeferreds(self, result):
        """
        Callback all Deferreds returned up until now by L{getResult}
        with the given result object.
        """
        requests = self.requests
        self.requests = None
        for d in requests:
            d.callback(result)


    def outReceived(self, bytes):
        """
        Accumulate output from the child process in a list.
        """
        self.bytes.append(bytes)


    def processEnded(self, reason):
        """
        Handle process termination by parsing all received output and firing
        any waiting Deferreds.
        """
        self._fireResultDeferreds(self.parseChunks(self.bytes))



class GetArgumentVector(UtilityProcessProtocol):
    """
    Protocol which will read a serialized argv from a process and
    expose it to interested parties.
    """
    programName = b"twisted.test.process_getargv"

    def parseChunks(self, chunks):
        """
        Parse the output from the process to which this protocol was
        connected, which is a single unterminated line of \\0-separated
        strings giving the argv of that process.  Return this as a list of
        str objects.
        """
        return b''.join(chunks).split(b'\0')



class GetEnvironmentDictionary(UtilityProcessProtocol):
    """
    Protocol which will read a serialized environment dict from a process
    and expose it to interested parties.
    """
    programName = b"twisted.test.process_getenv"

    def parseChunks(self, chunks):
        """
        Parse the output from the process to which this protocol was
        connected, which is a single unterminated line of \\0-separated
        strings giving key value pairs of the environment from that process.
        Return this as a dictionary.
        """
        environString = b''.join(chunks)
        if not environString:
            return {}
        environ = iter(environString.split(b'\0'))
        d = {}
        while 1:
            try:
                k = next(environ)
            except StopIteration:
                break
            else:
                v = next(environ)
                d[k] = v
        return d



class ProcessTests(unittest.TestCase):
    """
    Test running a process.
    """
    usePTY = False

    def test_stdio(self):
        """
        L{twisted.internet.stdio} test.
        """
        scriptPath = b"twisted.test.process_twisted"
        p = Accumulator()
        d = p.endedDeferred = defer.Deferred()
        reactor.spawnProcess(p, pyExe, [pyExe, b'-u', b"-m", scriptPath],
                             env=properEnv,
                             path=None, usePTY=self.usePTY)
        p.transport.write(b"hello, world")
        p.transport.write(b"abc")
        p.transport.write(b"123")
        p.transport.closeStdin()

        def processEnded(ign):
            self.assertEqual(p.outF.getvalue(), b"hello, worldabc123",
                              "Output follows:\n"
                              "%s\n"
                              "Error message from process_twisted follows:\n"
                              "%s\n" % (p.outF.getvalue(), p.errF.getvalue()))
        return d.addCallback(processEnded)


    def test_unsetPid(self):
        """
        Test if pid is None/non-None before/after process termination.  This
        reuses process_echoer.py to get a process that blocks on stdin.
        """
        finished = defer.Deferred()
        p = TrivialProcessProtocol(finished)
        scriptPath = b"twisted.test.process_echoer"
        procTrans = reactor.spawnProcess(p, pyExe,
                                         [pyExe, b'-u', b"-m", scriptPath],
                                         env=properEnv)
        self.assertTrue(procTrans.pid)

        def afterProcessEnd(ignored):
            self.assertIsNone(procTrans.pid)

        p.transport.closeStdin()
        return finished.addCallback(afterProcessEnd)


    def test_process(self):
        """
        Test running a process: check its output, it exitCode, some property of
        signalProcess.
        """
        scriptPath = b"twisted.test.process_tester"
        d = defer.Deferred()
        p = TestProcessProtocol()
        p.deferred = d
        reactor.spawnProcess(p, pyExe, [pyExe, b"-u", b"-m", scriptPath],
                             env=properEnv)
        def check(ignored):
            self.assertEqual(p.stages, [1, 2, 3, 4, 5])
            f = p.reason
            f.trap(error.ProcessTerminated)
            self.assertEqual(f.value.exitCode, 23)
            # would .signal be available on non-posix?
            # self.assertIsNone(f.value.signal)
            self.assertRaises(
                error.ProcessExitedAlready, p.transport.signalProcess, 'INT')
            try:
                import process_tester, glob
                for f in glob.glob(process_tester.test_file_match):
                    os.remove(f)
            except:
                pass
        d.addCallback(check)
        return d


    def test_manyProcesses(self):

        def _check(results, protocols):
            for p in protocols:
                self.assertEqual(p.stages, [1, 2, 3, 4, 5],
                                 "[%d] stages = %s" % (id(p.transport),
                                                       str(p.stages)))
                # test status code
                f = p.reason
                f.trap(error.ProcessTerminated)
                self.assertEqual(f.value.exitCode, 23)

        scriptPath = b"twisted.test.process_tester"
        args = [pyExe, b'-u', b"-m", scriptPath]
        protocols = []
        deferreds = []

        for i in xrange(CONCURRENT_PROCESS_TEST_COUNT):
            p = TestManyProcessProtocol()
            protocols.append(p)
            reactor.spawnProcess(p, pyExe, args, env=properEnv)
            deferreds.append(p.deferred)

        deferredList = defer.DeferredList(deferreds, consumeErrors=True)
        deferredList.addCallback(_check, protocols)
        return deferredList


    def test_echo(self):
        """
        A spawning a subprocess which echoes its stdin to its stdout via
        L{IReactorProcess.spawnProcess} will result in that echoed output being
        delivered to outReceived.
        """
        finished = defer.Deferred()
        p = EchoProtocol(finished)

        scriptPath = b"twisted.test.process_echoer"
        reactor.spawnProcess(p, pyExe, [pyExe, b'-u', b"-m", scriptPath],
                             env=properEnv)

        def asserts(ignored):
            self.assertFalse(p.failure, p.failure)
            self.assertTrue(hasattr(p, 'buffer'))
            self.assertEqual(len(p.buffer), len(p.s * p.n))

        def takedownProcess(err):
            p.transport.closeStdin()
            return err

        return finished.addCallback(asserts).addErrback(takedownProcess)


    def test_commandLine(self):
        args = [br'a\"b ', br'a\b ', br' a\\"b', br' a\\b', br'"foo bar" "',
                b'\tab', b'"\\', b'a"b', b"a'b"]
        scriptPath = b"twisted.test.process_cmdline"
        p = Accumulator()
        d = p.endedDeferred = defer.Deferred()
        reactor.spawnProcess(p, pyExe,
                             [pyExe, b"-u", b"-m", scriptPath] + args,
                             env=properEnv, path=None)

        def processEnded(ign):
            self.assertEqual(p.errF.getvalue(), b"")
            recvdArgs = p.outF.getvalue().splitlines()
            self.assertEqual(recvdArgs, args)
        return d.addCallback(processEnded)


    def test_wrongArguments(self):
        """
        Test invalid arguments to spawnProcess: arguments and environment
        must only contains string or unicode, and not null bytes.
        """
        p = protocol.ProcessProtocol()

        badEnvs = [
            {b"foo": 2},
            {b"foo": b"egg\0a"},
            {3: b"bar"},
            {b"bar\0foo": b"bar"}]

        badArgs = [
            [pyExe, 2],
            b"spam",
            [pyExe, b"foo\0bar"]]

        # Sanity check - this will fail for people who have mucked with
        # their site configuration in a stupid way, but there's nothing we
        # can do about that.
        badUnicode = u'\N{SNOWMAN}'
        try:
            badUnicode.encode(sys.getdefaultencoding())
        except UnicodeEncodeError:
            # Okay, that unicode doesn't encode, put it in as a bad environment
            # key.
            badEnvs.append({badUnicode: 'value for bad unicode key'})
            badEnvs.append({'key for bad unicode value': badUnicode})
            badArgs.append([pyExe, badUnicode])
        else:
            # It _did_ encode.  Most likely, Gtk2 is being used and the
            # default system encoding is UTF-8, which can encode anything.
            # In any case, if implicit unicode -> str conversion works for
            # that string, we can't test that TypeError gets raised instead,
            # so just leave it off.
            pass

        for env in badEnvs:
            self.assertRaises(
                TypeError,
                reactor.spawnProcess, p, pyExe, [pyExe, b"-c", b""], env=env)

        for args in badArgs:
            self.assertRaises(
                TypeError,
                reactor.spawnProcess, p, pyExe, args, env=None)


    # Use upper-case so that the environment key test uses an upper case
    # name: some versions of Windows only support upper case environment
    # variable names, and I think Python (as of 2.5) doesn't use the right
    # syscall for lowercase or mixed case names to work anyway.
    okayUnicode = u"UNICODE"
    encodedValue = b"UNICODE"

    def _deprecatedUnicodeSupportTest(self, processProtocolClass, argv=[],
                                      env={}):
        """
        Check that a deprecation warning is emitted when passing unicode to
        spawnProcess for an argv value or an environment key or value.
        Check that the warning is of the right type, has the right message,
        and refers to the correct file.  Unfortunately, don't check that the
        line number is correct, because that is too hard for me to figure
        out.

        @param processProtocolClass: A L{UtilityProcessProtocol} subclass
        which will be instantiated to communicate with the child process.

        @param argv: The argv argument to spawnProcess.

        @param env: The env argument to spawnProcess.

        @return: A Deferred which fires when the test is complete.
        """
        # Sanity to check to make sure we can actually encode this unicode
        # with the default system encoding.  This may be excessively
        # paranoid. -exarkun
        self.assertEqual(
            self.okayUnicode.encode(sys.getdefaultencoding()),
            self.encodedValue)

        pEnv = properEnv.copy()
        pEnv.update(env)

        d = processProtocolClass.run(reactor, argv, pEnv)

        warnings = self.flushWarnings([UtilityProcessProtocol.run])

        # We only want the first warning, which will be the code we are
        # testing and not the reactor which may raise its own deprecation
        # warnings (like gireactor).
        warning = warnings[0]
        self.assertEqual(
            warning["message"],
            ("Argument strings and environment keys/values passed to "
             "reactor.spawnProcess should be str, not unicode."))
        self.assertTrue(__file__.startswith(warning["filename"]))

        return d.getResult()


    def test_deprecatedUnicodeArgvSupport(self):
        """
        Test that a unicode string passed for an argument value is allowed
        if it can be encoded with the default system encoding, but that a
        deprecation warning is emitted.
        """
        d = self._deprecatedUnicodeSupportTest(GetArgumentVector,
                                               argv=[self.okayUnicode])
        def gotArgVector(argv):
            self.assertEqual(argv[1], self.encodedValue)
        d.addCallback(gotArgVector)
        return d


    def test_deprecatedUnicodeEnvKeySupport(self):
        """
        Test that a unicode string passed for the key of the environment
        dictionary is allowed if it can be encoded with the default system
        encoding, but that a deprecation warning is emitted.
        """
        d = self._deprecatedUnicodeSupportTest(
            GetEnvironmentDictionary, env={self.okayUnicode: self.encodedValue})
        def gotEnvironment(environ):
            self.assertEqual(environ[self.encodedValue], self.encodedValue)
        d.addCallback(gotEnvironment)
        return d


    def test_deprecatedUnicodeEnvValueSupport(self):
        """
        Test that a unicode string passed for the value of the environment
        dictionary is allowed if it can be encoded with the default system
        encoding, but that a deprecation warning is emitted.
        """
        d = self._deprecatedUnicodeSupportTest(
            GetEnvironmentDictionary, env={self.encodedValue: self.okayUnicode})
        def gotEnvironment(environ):
            # On Windows, the environment contains more things than we
            # specified, so only make sure that at least the key we wanted
            # is there, rather than testing the dictionary for exact
            # equality.
            self.assertEqual(environ[self.encodedValue], self.encodedValue)
        d.addCallback(gotEnvironment)
        return d



class TwoProcessProtocol(protocol.ProcessProtocol):
    num = -1
    finished = 0
    def __init__(self):
        self.deferred = defer.Deferred()
    def outReceived(self, data):
        pass
    def processEnded(self, reason):
        self.finished = 1
        self.deferred.callback(None)

class TestTwoProcessesBase:
    def setUp(self):
        self.processes = [None, None]
        self.pp = [None, None]
        self.done = 0
        self.verbose = 0

    def createProcesses(self, usePTY=0):
        scriptPath = b"twisted.test.process_reader"
        for num in (0,1):
            self.pp[num] = TwoProcessProtocol()
            self.pp[num].num = num
            p = reactor.spawnProcess(self.pp[num], pyExe,
                                     [pyExe, b"-u", b"-m", scriptPath],
                                     env=properEnv, usePTY=usePTY)
            self.processes[num] = p

    def close(self, num):
        if self.verbose: print("closing stdin [%d]" % num)
        p = self.processes[num]
        pp = self.pp[num]
        self.assertFalse(pp.finished, "Process finished too early")
        p.loseConnection()
        if self.verbose: print(self.pp[0].finished, self.pp[1].finished)

    def _onClose(self):
        return defer.gatherResults([ p.deferred for p in self.pp ])

    def test_close(self):
        if self.verbose: print("starting processes")
        self.createProcesses()
        reactor.callLater(1, self.close, 0)
        reactor.callLater(2, self.close, 1)
        return self._onClose()

class TwoProcessesNonPosixTests(TestTwoProcessesBase, unittest.TestCase):
    pass

class TwoProcessesPosixTests(TestTwoProcessesBase, unittest.TestCase):
    def tearDown(self):
        for pp, pr in zip(self.pp, self.processes):
            if not pp.finished:
                try:
                    os.kill(pr.pid, signal.SIGTERM)
                except OSError:
                    # If the test failed the process may already be dead
                    # The error here is only noise
                    pass
        return self._onClose()

    def kill(self, num):
        if self.verbose: print("kill [%d] with SIGTERM" % num)
        p = self.processes[num]
        pp = self.pp[num]
        self.assertFalse(pp.finished, "Process finished too early")
        os.kill(p.pid, signal.SIGTERM)
        if self.verbose: print(self.pp[0].finished, self.pp[1].finished)

    def test_kill(self):
        if self.verbose: print("starting processes")
        self.createProcesses(usePTY=0)
        reactor.callLater(1, self.kill, 0)
        reactor.callLater(2, self.kill, 1)
        return self._onClose()

    def test_closePty(self):
        if self.verbose: print("starting processes")
        self.createProcesses(usePTY=1)
        reactor.callLater(1, self.close, 0)
        reactor.callLater(2, self.close, 1)
        return self._onClose()

    def test_killPty(self):
        if self.verbose: print("starting processes")
        self.createProcesses(usePTY=1)
        reactor.callLater(1, self.kill, 0)
        reactor.callLater(2, self.kill, 1)
        return self._onClose()

class FDChecker(protocol.ProcessProtocol):
    state = 0
    data = b""
    failed = None

    def __init__(self, d):
        self.deferred = d

    def fail(self, why):
        self.failed = why
        self.deferred.callback(None)

    def connectionMade(self):
        self.transport.writeToChild(0, b"abcd")
        self.state = 1

    def childDataReceived(self, childFD, data):
        if self.state == 1:
            if childFD != 1:
                self.fail("read '%s' on fd %d (not 1) during state 1" \
                          % (childFD, data))
                return
            self.data += data
            #print "len", len(self.data)
            if len(self.data) == 6:
                if self.data != b"righto":
                    self.fail("got '%s' on fd1, expected 'righto'" \
                              % self.data)
                    return
                self.data = b""
                self.state = 2
                #print "state2", self.state
                self.transport.writeToChild(3, b"efgh")
                return
        if self.state == 2:
            self.fail("read '%s' on fd %s during state 2" % (childFD, data))
            return
        if self.state == 3:
            if childFD != 1:
                self.fail("read '%s' on fd %s (not 1) during state 3" \
                          % (childFD, data))
                return
            self.data += data
            if len(self.data) == 6:
                if self.data != b"closed":
                    self.fail("got '%s' on fd1, expected 'closed'" \
                              % self.data)
                    return
                self.state = 4
            return
        if self.state == 4:
            self.fail("read '%s' on fd %s during state 4" % (childFD, data))
            return

    def childConnectionLost(self, childFD):
        if self.state == 1:
            self.fail("got connectionLost(%d) during state 1" % childFD)
            return
        if self.state == 2:
            if childFD != 4:
                self.fail("got connectionLost(%d) (not 4) during state 2" \
                          % childFD)
                return
            self.state = 3
            self.transport.closeChildFD(5)
            return

    def processEnded(self, status):
        rc = status.value.exitCode
        if self.state != 4:
            self.fail("processEnded early, rc %d" % rc)
            return
        if status.value.signal != None:
            self.fail("processEnded with signal %s" % status.value.signal)
            return
        if rc != 0:
            self.fail("processEnded with rc %d" % rc)
            return
        self.deferred.callback(None)


class FDTests(unittest.TestCase):

    def test_FD(self):
        scriptPath = b"twisted.test.process_fds"
        d = defer.Deferred()
        p = FDChecker(d)
        reactor.spawnProcess(p, pyExe, [pyExe, b"-u", b"-m", scriptPath],
                             env=properEnv,
                             childFDs={0:"w", 1:"r", 2:2,
                                       3:"w", 4:"r", 5:"w"})
        d.addCallback(lambda x : self.assertFalse(p.failed, p.failed))
        return d

    def test_linger(self):
        # See what happens when all the pipes close before the process
        # actually stops. This test *requires* SIGCHLD catching to work,
        # as there is no other way to find out the process is done.
        scriptPath = b"twisted.test.process_linger"
        p = Accumulator()
        d = p.endedDeferred = defer.Deferred()
        reactor.spawnProcess(p, pyExe, [pyExe, b"-u", b"-m", scriptPath],
                             env=properEnv,
                             childFDs={1:"r", 2:2},
                             )
        def processEnded(ign):
            self.assertEqual(p.outF.getvalue(),
                             b"here is some text\ngoodbye\n")
        return d.addCallback(processEnded)



class Accumulator(protocol.ProcessProtocol):
    """Accumulate data from a process."""

    closed = 0
    endedDeferred = None

    def connectionMade(self):
        self.outF = BytesIO()
        self.errF = BytesIO()

    def outReceived(self, d):
        self.outF.write(d)

    def errReceived(self, d):
        self.errF.write(d)

    def outConnectionLost(self):
        pass

    def errConnectionLost(self):
        pass

    def processEnded(self, reason):
        self.closed = 1
        if self.endedDeferred is not None:
            d, self.endedDeferred = self.endedDeferred, None
            d.callback(None)


class PosixProcessBase(object):
    """
    Test running processes.
    """
    usePTY = False

    def getCommand(self, commandName):
        """
        Return the path of the shell command named C{commandName}, looking at
        common locations.
        """
        binLoc = FilePath('/bin').child(commandName)
        usrbinLoc = FilePath('/usr/bin').child(commandName)

        if binLoc.exists():
            return binLoc._asBytesPath()
        elif usrbinLoc.exists():
            return usrbinLoc._asBytesPath()
        else:
            raise RuntimeError(
                "%s not found in /bin or /usr/bin" % (commandName,))


    def test_normalTermination(self):
        cmd = self.getCommand('true')

        d = defer.Deferred()
        p = TrivialProcessProtocol(d)
        reactor.spawnProcess(p, cmd, [b'true'], env=None,
                             usePTY=self.usePTY)
        def check(ignored):
            p.reason.trap(error.ProcessDone)
            self.assertEqual(p.reason.value.exitCode, 0)
            self.assertIsNone(p.reason.value.signal)
        d.addCallback(check)
        return d


    def test_abnormalTermination(self):
        """
        When a process terminates with a system exit code set to 1,
        C{processEnded} is called with a L{error.ProcessTerminated} error,
        the C{exitCode} attribute reflecting the system exit code.
        """
        d = defer.Deferred()
        p = TrivialProcessProtocol(d)
        reactor.spawnProcess(p, pyExe,
                             [pyExe, b'-c', b'import sys; sys.exit(1)'],
                             env=None, usePTY=self.usePTY)

        def check(ignored):
            p.reason.trap(error.ProcessTerminated)
            self.assertEqual(p.reason.value.exitCode, 1)
            self.assertIsNone(p.reason.value.signal)
        d.addCallback(check)
        return d


    def _testSignal(self, sig):
        scriptPath = b"twisted.test.process_signal"
        d = defer.Deferred()
        p = SignalProtocol(d, sig)
        reactor.spawnProcess(p, pyExe, [pyExe, b"-u", "-m", scriptPath],
                             env=properEnv, usePTY=self.usePTY)
        return d


    def test_signalHUP(self):
        """
        Sending the SIGHUP signal to a running process interrupts it, and
        C{processEnded} is called with a L{error.ProcessTerminated} instance
        with the C{exitCode} set to L{None} and the C{signal} attribute set to
        C{signal.SIGHUP}. C{os.WTERMSIG} can also be used on the C{status}
        attribute to extract the signal value.
        """
        return self._testSignal('HUP')


    def test_signalINT(self):
        """
        Sending the SIGINT signal to a running process interrupts it, and
        C{processEnded} is called with a L{error.ProcessTerminated} instance
        with the C{exitCode} set to L{None} and the C{signal} attribute set to
        C{signal.SIGINT}. C{os.WTERMSIG} can also be used on the C{status}
        attribute to extract the signal value.
        """
        return self._testSignal('INT')


    def test_signalKILL(self):
        """
        Sending the SIGKILL signal to a running process interrupts it, and
        C{processEnded} is called with a L{error.ProcessTerminated} instance
        with the C{exitCode} set to L{None} and the C{signal} attribute set to
        C{signal.SIGKILL}. C{os.WTERMSIG} can also be used on the C{status}
        attribute to extract the signal value.
        """
        return self._testSignal('KILL')


    def test_signalTERM(self):
        """
        Sending the SIGTERM signal to a running process interrupts it, and
        C{processEnded} is called with a L{error.ProcessTerminated} instance
        with the C{exitCode} set to L{None} and the C{signal} attribute set to
        C{signal.SIGTERM}. C{os.WTERMSIG} can also be used on the C{status}
        attribute to extract the signal value.
        """
        return self._testSignal('TERM')


    def test_childSignalHandling(self):
        """
        The disposition of signals which are ignored in the parent
        process is reset to the default behavior for the child
        process.
        """
        # Somewhat arbitrarily select SIGUSR1 here.  It satisfies our
        # requirements that:
        #    - The interpreter not fiddle around with the handler
        #      behind our backs at startup time (this disqualifies
        #      signals like SIGINT and SIGPIPE).
        #    - The default behavior is to exit.
        #
        # This lets us send the signal to the child and then verify
        # that it exits with a status code indicating that it was
        # indeed the signal which caused it to exit.
        which = signal.SIGUSR1

        # Ignore the signal in the parent (and make sure we clean it
        # up).
        handler = signal.signal(which, signal.SIG_IGN)
        self.addCleanup(signal.signal, signal.SIGUSR1, handler)

        # Now do the test.
        return self._testSignal(signal.SIGUSR1)


    def test_executionError(self):
        """
        Raise an error during execvpe to check error management.
        """
        cmd = self.getCommand('false')

        d = defer.Deferred()
        p = TrivialProcessProtocol(d)
        def buggyexecvpe(command, args, environment):
            raise RuntimeError("Ouch")
        oldexecvpe = os.execvpe
        os.execvpe = buggyexecvpe
        try:
            reactor.spawnProcess(p, cmd, [b'false'], env=None,
                                 usePTY=self.usePTY)

            def check(ignored):
                errData = b"".join(p.errData + p.outData)
                self.assertIn(b"Upon execvpe", errData)
                self.assertIn(b"Ouch", errData)
            d.addCallback(check)
        finally:
            os.execvpe = oldexecvpe
        return d


    def test_errorInProcessEnded(self):
        """
        The handler which reaps a process is removed when the process is
        reaped, even if the protocol's C{processEnded} method raises an
        exception.
        """
        connected = defer.Deferred()
        ended = defer.Deferred()

        # This script runs until we disconnect its transport.
        scriptPath = b"twisted.test.process_echoer"

        class ErrorInProcessEnded(protocol.ProcessProtocol):
            """
            A protocol that raises an error in C{processEnded}.
            """
            def makeConnection(self, transport):
                connected.callback(transport)

            def processEnded(self, reason):
                reactor.callLater(0, ended.callback, None)
                raise RuntimeError("Deliberate error")

        # Launch the process.
        reactor.spawnProcess(
            ErrorInProcessEnded(), pyExe,
            [pyExe, b"-u", b"-m", scriptPath],
            env=properEnv, path=None)

        pid = []
        def cbConnected(transport):
            pid.append(transport.pid)
            # There's now a reap process handler registered.
            self.assertIn(transport.pid, process.reapProcessHandlers)

            # Kill the process cleanly, triggering an error in the protocol.
            transport.loseConnection()
        connected.addCallback(cbConnected)

        def checkTerminated(ignored):
            # The exception was logged.
            excs = self.flushLoggedErrors(RuntimeError)
            self.assertEqual(len(excs), 1)
            # The process is no longer scheduled for reaping.
            self.assertNotIn(pid[0], process.reapProcessHandlers)
        ended.addCallback(checkTerminated)

        return ended



class MockSignal(object):
    """
    Neuter L{signal.signal}, but pass other attributes unscathed
    """
    def signal(self, sig, action):
        return signal.getsignal(sig)

    def __getattr__(self, attr):
        return getattr(signal, attr)


class MockOS(object):
    """
    The mock OS: overwrite L{os}, L{fcntl} and {sys} functions with fake ones.

    @ivar exited: set to True when C{_exit} is called.
    @type exited: C{bool}

    @ivar O_RDWR: dumb value faking C{os.O_RDWR}.
    @type O_RDWR: C{int}

    @ivar O_NOCTTY: dumb value faking C{os.O_NOCTTY}.
    @type O_NOCTTY: C{int}

    @ivar WNOHANG: dumb value faking C{os.WNOHANG}.
    @type WNOHANG: C{int}

    @ivar raiseFork: if not L{None}, subsequent calls to fork will raise this
        object.
    @type raiseFork: L{None} or C{Exception}

    @ivar raiseExec: if set, subsequent calls to execvpe will raise an error.
    @type raiseExec: C{bool}

    @ivar fdio: fake file object returned by calls to fdopen.
    @type fdio: C{BytesIO} or C{BytesIO}

    @ivar actions: hold names of some actions executed by the object, in order
        of execution.

    @type actions: C{list} of C{str}

    @ivar closed: keep track of the file descriptor closed.
    @type closed: C{list} of C{int}

    @ivar child: whether fork return for the child or the parent.
    @type child: C{bool}

    @ivar pipeCount: count the number of time that C{os.pipe} has been called.
    @type pipeCount: C{int}

    @ivar raiseWaitPid: if set, subsequent calls to waitpid will raise
        the error specified.
    @type raiseWaitPid: L{None} or a class

    @ivar waitChild: if set, subsequent calls to waitpid will return it.
    @type waitChild: L{None} or a tuple

    @ivar euid: the uid returned by the fake C{os.geteuid}
    @type euid: C{int}

    @ivar egid: the gid returned by the fake C{os.getegid}
    @type egid: C{int}

    @ivar seteuidCalls: stored results of C{os.seteuid} calls.
    @type seteuidCalls: C{list}

    @ivar setegidCalls: stored results of C{os.setegid} calls.
    @type setegidCalls: C{list}

    @ivar path: the path returned by C{os.path.expanduser}.
    @type path: C{str}

    @ivar raiseKill: if set, subsequent call to kill will raise the error
        specified.
    @type raiseKill: L{None} or an exception instance.

    @ivar readData: data returned by C{os.read}.
    @type readData: C{str}
    """
    exited = False
    raiseExec = False
    fdio = None
    child = True
    raiseWaitPid = None
    raiseFork = None
    waitChild = None
    euid = 0
    egid = 0
    path = None
    raiseKill = None
    readData = b""

    def __init__(self):
        """
        Initialize data structures.
        """
        self.actions = []
        self.closed = []
        self.pipeCount = 0
        self.O_RDWR = -1
        self.O_NOCTTY = -2
        self.WNOHANG = -4
        self.WEXITSTATUS = lambda x: 0
        self.WIFEXITED = lambda x: 1
        self.seteuidCalls = []
        self.setegidCalls = []


    def open(self, dev, flags):
        """
        Fake C{os.open}. Return a non fd number to be sure it's not used
        elsewhere.
        """
        return -3


    def fstat(self, fd):
        """
        Fake C{os.fstat}.  Return a C{os.stat_result} filled with garbage.
        """
        return os.stat_result((0,) * 10)


    def fdopen(self, fd, flag):
        """
        Fake C{os.fdopen}. Return a file-like object whose content can
        be tested later via C{self.fdio}.
        """
        if flag == "wb":
            self.fdio = BytesIO()
        else:
            assert False
        return self.fdio


    def setsid(self):
        """
        Fake C{os.setsid}. Save action.
        """
        self.actions.append('setsid')


    def fork(self):
        """
        Fake C{os.fork}. Save the action in C{self.actions}, and return 0 if
        C{self.child} is set, or a dumb number.
        """
        self.actions.append(('fork', gc.isenabled()))
        if self.raiseFork is not None:
            raise self.raiseFork
        elif self.child:
            # Child result is 0
            return 0
        else:
            return 21


    def close(self, fd):
        """
        Fake C{os.close}, saving the closed fd in C{self.closed}.
        """
        self.closed.append(fd)


    def dup2(self, fd1, fd2):
        """
        Fake C{os.dup2}. Do nothing.
        """


    def write(self, fd, data):
        """
        Fake C{os.write}. Save action.
        """
        self.actions.append(("write", fd, data))


    def read(self, fd, size):
        """
        Fake C{os.read}: save action, and return C{readData} content.

        @param fd: The file descriptor to read.

        @param size: The maximum number of bytes to read.

        @return: A fixed C{bytes} buffer.
        """
        self.actions.append(('read', fd, size))
        return self.readData


    def execvpe(self, command, args, env):
        """
        Fake C{os.execvpe}. Save the action, and raise an error if
        C{self.raiseExec} is set.
        """
        self.actions.append('exec')
        if self.raiseExec:
            raise RuntimeError("Bar")


    def pipe(self):
        """
        Fake C{os.pipe}. Return non fd numbers to be sure it's not used
        elsewhere, and increment C{self.pipeCount}. This is used to uniquify
        the result.
        """
        self.pipeCount += 1
        return - 2 * self.pipeCount + 1,  - 2 * self.pipeCount


    def ttyname(self, fd):
        """
        Fake C{os.ttyname}. Return a dumb string.
        """
        return "foo"


    def _exit(self, code):
        """
        Fake C{os._exit}. Save the action, set the C{self.exited} flag, and
        raise C{SystemError}.
        """
        self.actions.append(('exit', code))
        self.exited = True
        # Don't forget to raise an error, or you'll end up in parent
        # code path.
        raise SystemError()


    def ioctl(self, fd, flags, arg):
        """
        Override C{fcntl.ioctl}. Do nothing.
        """


    def setNonBlocking(self, fd):
        """
        Override C{fdesc.setNonBlocking}. Do nothing.
        """


    def waitpid(self, pid, options):
        """
        Override C{os.waitpid}. Return values meaning that the child process
        has exited, save executed action.
        """
        self.actions.append('waitpid')
        if self.raiseWaitPid is not None:
            raise self.raiseWaitPid
        if self.waitChild is not None:
            return self.waitChild
        return 1, 0


    def settrace(self, arg):
        """
        Override C{sys.settrace} to keep coverage working.
        """


    def getgid(self):
        """
        Override C{os.getgid}. Return a dumb number.
        """
        return 1235


    def getuid(self):
        """
        Override C{os.getuid}. Return a dumb number.
        """
        return 1237


    def setuid(self, val):
        """
        Override C{os.setuid}. Do nothing.
        """
        self.actions.append(('setuid', val))


    def setgid(self, val):
        """
        Override C{os.setgid}. Do nothing.
        """
        self.actions.append(('setgid', val))


    def setregid(self, val1, val2):
        """
        Override C{os.setregid}. Do nothing.
        """
        self.actions.append(('setregid', val1, val2))


    def setreuid(self, val1, val2):
        """
        Override C{os.setreuid}.  Save the action.
        """
        self.actions.append(('setreuid', val1, val2))


    def switchUID(self, uid, gid):
        """
        Override C{util.switchuid}. Save the action.
        """
        self.actions.append(('switchuid', uid, gid))


    def openpty(self):
        """
        Override C{pty.openpty}, returning fake file descriptors.
        """
        return -12, -13


    def chdir(self, path):
        """
        Override C{os.chdir}. Save the action.

        @param path: The path to change the current directory to.
        """
        self.actions.append(('chdir', path))


    def geteuid(self):
        """
        Mock C{os.geteuid}, returning C{self.euid} instead.
        """
        return self.euid


    def getegid(self):
        """
        Mock C{os.getegid}, returning C{self.egid} instead.
        """
        return self.egid


    def seteuid(self, egid):
        """
        Mock C{os.seteuid}, store result.
        """
        self.seteuidCalls.append(egid)


    def setegid(self, egid):
        """
        Mock C{os.setegid}, store result.
        """
        self.setegidCalls.append(egid)


    def expanduser(self, path):
        """
        Mock C{os.path.expanduser}.
        """
        return self.path


    def getpwnam(self, user):
        """
        Mock C{pwd.getpwnam}.
        """
        return 0, 0, 1, 2


    def listdir(self, path):
        """
        Override C{os.listdir}, returning fake contents of '/dev/fd'
        """
        return "-1", "-2"


    def kill(self, pid, signalID):
        """
        Override C{os.kill}: save the action and raise C{self.raiseKill} if
        specified.
        """
        self.actions.append(('kill', pid, signalID))
        if self.raiseKill is not None:
            raise self.raiseKill


    def unlink(self, filename):
        """
        Override C{os.unlink}. Save the action.

        @param filename: The file name to remove.
        """
        self.actions.append(('unlink', filename))


    def umask(self, mask):
        """
        Override C{os.umask}. Save the action.

        @param mask: The new file mode creation mask.
        """
        self.actions.append(('umask', mask))


    def getpid(self):
        """
        Return a fixed PID value.

        @return: A fixed value.
        """
        return 6789


    def getfilesystemencoding(self):
        """
        Return a fixed filesystem encoding.

        @return: A fixed value of "utf8".
        """
        return "utf8"


if process is not None:
    class DumbProcessWriter(process.ProcessWriter):
        """
        A fake L{process.ProcessWriter} used for tests.
        """

        def startReading(self):
            """
            Here's the faking: don't do anything here.
            """



    class DumbProcessReader(process.ProcessReader):
        """
        A fake L{process.ProcessReader} used for tests.
        """

        def startReading(self):
            """
            Here's the faking: don't do anything here.
            """



    class DumbPTYProcess(process.PTYProcess):
        """
        A fake L{process.PTYProcess} used for tests.
        """

        def startReading(self):
            """
            Here's the faking: don't do anything here.
            """



class MockProcessTests(unittest.TestCase):
    """
    Mock a process runner to test forked child code path.
    """
    if process is None:
        skip = "twisted.internet.process is never used on Windows"

    def setUp(self):
        """
        Replace L{process} os, fcntl, sys, switchUID, fdesc and pty modules
        with the mock class L{MockOS}.
        """
        if gc.isenabled():
            self.addCleanup(gc.enable)
        else:
            self.addCleanup(gc.disable)
        self.mockos = MockOS()
        self.mockos.euid = 1236
        self.mockos.egid = 1234
        self.patch(process, "os", self.mockos)
        self.patch(process, "fcntl", self.mockos)
        self.patch(process, "sys", self.mockos)
        self.patch(process, "switchUID", self.mockos.switchUID)
        self.patch(process, "fdesc", self.mockos)
        self.patch(process.Process, "processReaderFactory", DumbProcessReader)
        self.patch(process.Process, "processWriterFactory", DumbProcessWriter)
        self.patch(process, "pty", self.mockos)

        self.mocksig = MockSignal()
        self.patch(process, "signal", self.mocksig)


    def tearDown(self):
        """
        Reset processes registered for reap.
        """
        process.reapProcessHandlers = {}


    def test_mockFork(self):
        """
        Test a classic spawnProcess. Check the path of the client code:
        fork, exec, exit.
        """
        gc.enable()

        cmd = b'/mock/ouch'

        d = defer.Deferred()
        p = TrivialProcessProtocol(d)
        try:
            reactor.spawnProcess(p, cmd, [b'ouch'], env=None,
                                 usePTY=False)
        except SystemError:
            self.assertTrue(self.mockos.exited)
            self.assertEqual(
                self.mockos.actions, [("fork", False), "exec", ("exit", 1)])
        else:
            self.fail("Should not be here")

        # It should leave the garbage collector disabled.
        self.assertFalse(gc.isenabled())


    def _mockForkInParentTest(self):
        """
        Assert that in the main process, spawnProcess disables the garbage
        collector, calls fork, closes the pipe file descriptors it created for
        the child process, and calls waitpid.
        """
        self.mockos.child = False
        cmd = b'/mock/ouch'

        d = defer.Deferred()
        p = TrivialProcessProtocol(d)
        reactor.spawnProcess(p, cmd, [b'ouch'], env=None,
                             usePTY=False)
        # It should close the first read pipe, and the 2 last write pipes
        self.assertEqual(set(self.mockos.closed), set([-1, -4, -6]))
        self.assertEqual(self.mockos.actions, [("fork", False), "waitpid"])


    def test_mockForkInParentGarbageCollectorEnabled(self):
        """
        The garbage collector should be enabled when L{reactor.spawnProcess}
        returns if it was initially enabled.

        @see L{_mockForkInParentTest}
        """
        gc.enable()
        self._mockForkInParentTest()
        self.assertTrue(gc.isenabled())


    def test_mockForkInParentGarbageCollectorDisabled(self):
        """
        The garbage collector should be disabled when L{reactor.spawnProcess}
        returns if it was initially disabled.

        @see L{_mockForkInParentTest}
        """
        gc.disable()
        self._mockForkInParentTest()
        self.assertFalse(gc.isenabled())


    def test_mockForkTTY(self):
        """
        Test a TTY spawnProcess: check the path of the client code:
        fork, exec, exit.
        """
        cmd = b'/mock/ouch'

        d = defer.Deferred()
        p = TrivialProcessProtocol(d)
        self.assertRaises(SystemError, reactor.spawnProcess, p, cmd, [b'ouch'],
                          env=None, usePTY=True)
        self.assertTrue(self.mockos.exited)
        self.assertEqual(
            self.mockos.actions,
            [("fork", False), "setsid", "exec", ("exit", 1)])


    def _mockWithForkError(self):
        """
        Assert that if the fork call fails, no other process setup calls are
        made and that spawnProcess raises the exception fork raised.
        """
        self.mockos.raiseFork = OSError(errno.EAGAIN, None)
        protocol = TrivialProcessProtocol(None)
        self.assertRaises(OSError, reactor.spawnProcess, protocol, None)
        self.assertEqual(self.mockos.actions, [("fork", False)])


    def test_mockWithForkErrorGarbageCollectorEnabled(self):
        """
        The garbage collector should be enabled when L{reactor.spawnProcess}
        raises because L{os.fork} raised, if it was initially enabled.
        """
        gc.enable()
        self._mockWithForkError()
        self.assertTrue(gc.isenabled())


    def test_mockWithForkErrorGarbageCollectorDisabled(self):
        """
        The garbage collector should be disabled when
        L{reactor.spawnProcess} raises because L{os.fork} raised, if it was
        initially disabled.
        """
        gc.disable()
        self._mockWithForkError()
        self.assertFalse(gc.isenabled())


    def test_mockForkErrorCloseFDs(self):
        """
        When C{os.fork} raises an exception, the file descriptors created
        before are closed and don't leak.
        """
        self._mockWithForkError()
        self.assertEqual(set(self.mockos.closed), set([-1, -4, -6, -2, -3, -5]))


    def test_mockForkErrorGivenFDs(self):
        """
        When C{os.forks} raises an exception and that file descriptors have
        been specified with the C{childFDs} arguments of
        L{reactor.spawnProcess}, they are not closed.
        """
        self.mockos.raiseFork = OSError(errno.EAGAIN, None)
        protocol = TrivialProcessProtocol(None)
        self.assertRaises(OSError, reactor.spawnProcess, protocol, None,
            childFDs={0: -10, 1: -11, 2: -13})
        self.assertEqual(self.mockos.actions, [("fork", False)])
        self.assertEqual(self.mockos.closed, [])

        # We can also put "r" or "w" to let twisted create the pipes
        self.assertRaises(OSError, reactor.spawnProcess, protocol, None,
            childFDs={0: "r", 1: -11, 2: -13})
        self.assertEqual(set(self.mockos.closed), set([-1, -2]))


    def test_mockForkErrorClosePTY(self):
        """
        When C{os.fork} raises an exception, the file descriptors created by
        C{pty.openpty} are closed and don't leak, when C{usePTY} is set to
        C{True}.
        """
        self.mockos.raiseFork = OSError(errno.EAGAIN, None)
        protocol = TrivialProcessProtocol(None)
        self.assertRaises(OSError, reactor.spawnProcess, protocol, None,
                          usePTY=True)
        self.assertEqual(self.mockos.actions, [("fork", False)])
        self.assertEqual(set(self.mockos.closed), set([-12, -13]))


    def test_mockForkErrorPTYGivenFDs(self):
        """
        If a tuple is passed to C{usePTY} to specify slave and master file
        descriptors and that C{os.fork} raises an exception, these file
        descriptors aren't closed.
        """
        self.mockos.raiseFork = OSError(errno.EAGAIN, None)
        protocol = TrivialProcessProtocol(None)
        self.assertRaises(OSError, reactor.spawnProcess, protocol, None,
                          usePTY=(-20, -21, 'foo'))
        self.assertEqual(self.mockos.actions, [("fork", False)])
        self.assertEqual(self.mockos.closed, [])


    def test_mockWithExecError(self):
        """
        Spawn a process but simulate an error during execution in the client
        path: C{os.execvpe} raises an error. It should close all the standard
        fds, try to print the error encountered, and exit cleanly.
        """
        cmd = b'/mock/ouch'

        d = defer.Deferred()
        p = TrivialProcessProtocol(d)
        self.mockos.raiseExec = True
        try:
            reactor.spawnProcess(p, cmd, [b'ouch'], env=None,
                                 usePTY=False)
        except SystemError:
            self.assertTrue(self.mockos.exited)
            self.assertEqual(
                self.mockos.actions, [("fork", False), "exec", ("exit", 1)])
            # Check that fd have been closed
            self.assertIn(0, self.mockos.closed)
            self.assertIn(1, self.mockos.closed)
            self.assertIn(2, self.mockos.closed)
            # Check content of traceback
            self.assertIn(b"RuntimeError: Bar", self.mockos.fdio.getvalue())
        else:
            self.fail("Should not be here")


    def test_mockSetUid(self):
        """
        Try creating a process with setting its uid: it's almost the same path
        as the standard path, but with a C{switchUID} call before the exec.
        """
        cmd = b'/mock/ouch'

        d = defer.Deferred()
        p = TrivialProcessProtocol(d)
        try:
            reactor.spawnProcess(p, cmd, [b'ouch'], env=None,
                                 usePTY=False, uid=8080)
        except SystemError:
            self.assertTrue(self.mockos.exited)
            self.assertEqual(
                self.mockos.actions,
                [('fork', False), ('setuid', 0), ('setgid', 0),
                 ('switchuid', 8080, 1234), 'exec', ('exit', 1)])
        else:
            self.fail("Should not be here")


    def test_mockSetUidInParent(self):
        """
        When spawning a child process with a UID different from the UID of the
        current process, the current process does not have its UID changed.
        """
        self.mockos.child = False
        cmd = b'/mock/ouch'

        d = defer.Deferred()
        p = TrivialProcessProtocol(d)
        reactor.spawnProcess(p, cmd, [b'ouch'], env=None,
                             usePTY=False, uid=8080)
        self.assertEqual(self.mockos.actions, [('fork', False), 'waitpid'])


    def test_mockPTYSetUid(self):
        """
        Try creating a PTY process with setting its uid: it's almost the same
        path as the standard path, but with a C{switchUID} call before the
        exec.
        """
        cmd = b'/mock/ouch'

        d = defer.Deferred()
        p = TrivialProcessProtocol(d)
        try:
            reactor.spawnProcess(p, cmd, [b'ouch'], env=None,
                                 usePTY=True, uid=8081)
        except SystemError:
            self.assertTrue(self.mockos.exited)
            self.assertEqual(
                self.mockos.actions,
                [('fork', False), 'setsid', ('setuid', 0), ('setgid', 0),
                 ('switchuid', 8081, 1234), 'exec', ('exit', 1)])
        else:
            self.fail("Should not be here")


    def test_mockPTYSetUidInParent(self):
        """
        When spawning a child process with PTY and a UID different from the UID
        of the current process, the current process does not have its UID
        changed.
        """
        self.mockos.child = False
        cmd = b'/mock/ouch'

        d = defer.Deferred()
        p = TrivialProcessProtocol(d)
        oldPTYProcess = process.PTYProcess
        try:
            process.PTYProcess = DumbPTYProcess
            reactor.spawnProcess(p, cmd, [b'ouch'], env=None,
                                 usePTY=True, uid=8080)
        finally:
            process.PTYProcess = oldPTYProcess
        self.assertEqual(self.mockos.actions, [('fork', False), 'waitpid'])


    def test_mockWithWaitError(self):
        """
        Test that reapProcess logs errors raised.
        """
        self.mockos.child = False
        cmd = b'/mock/ouch'
        self.mockos.waitChild = (0, 0)

        d = defer.Deferred()
        p = TrivialProcessProtocol(d)
        proc = reactor.spawnProcess(p, cmd, [b'ouch'], env=None,
                             usePTY=False)
        self.assertEqual(self.mockos.actions, [("fork", False), "waitpid"])

        self.mockos.raiseWaitPid = OSError()
        proc.reapProcess()
        errors = self.flushLoggedErrors()
        self.assertEqual(len(errors), 1)
        errors[0].trap(OSError)


    def test_mockErrorECHILDInReapProcess(self):
        """
        Test that reapProcess doesn't log anything when waitpid raises a
        C{OSError} with errno C{ECHILD}.
        """
        self.mockos.child = False
        cmd = b'/mock/ouch'
        self.mockos.waitChild = (0, 0)

        d = defer.Deferred()
        p = TrivialProcessProtocol(d)
        proc = reactor.spawnProcess(p, cmd, [b'ouch'], env=None,
                                    usePTY=False)
        self.assertEqual(self.mockos.actions, [("fork", False), "waitpid"])

        self.mockos.raiseWaitPid = OSError()
        self.mockos.raiseWaitPid.errno = errno.ECHILD
        # This should not produce any errors
        proc.reapProcess()


    def test_mockErrorInPipe(self):
        """
        If C{os.pipe} raises an exception after some pipes where created, the
        created pipes are closed and don't leak.
        """
        pipes = [-1, -2, -3, -4]
        def pipe():
            try:
                return pipes.pop(0), pipes.pop(0)
            except IndexError:
                raise OSError()
        self.mockos.pipe = pipe
        protocol = TrivialProcessProtocol(None)
        self.assertRaises(OSError, reactor.spawnProcess, protocol, None)
        self.assertEqual(self.mockos.actions, [])
        self.assertEqual(set(self.mockos.closed), set([-4, -3, -2, -1]))


    def test_kill(self):
        """
        L{process.Process.signalProcess} calls C{os.kill} translating the given
        signal string to the PID.
        """
        self.mockos.child = False
        self.mockos.waitChild = (0, 0)
        cmd = b'/mock/ouch'
        p = TrivialProcessProtocol(None)
        proc = reactor.spawnProcess(p, cmd, [b'ouch'], env=None, usePTY=False)
        proc.signalProcess("KILL")
        self.assertEqual(self.mockos.actions,
            [('fork', False), 'waitpid', ('kill', 21, signal.SIGKILL)])


    def test_killExited(self):
        """
        L{process.Process.signalProcess} raises L{error.ProcessExitedAlready}
        if the process has exited.
        """
        self.mockos.child = False
        cmd = b'/mock/ouch'
        p = TrivialProcessProtocol(None)
        proc = reactor.spawnProcess(p, cmd, [b'ouch'], env=None, usePTY=False)
        # We didn't specify a waitpid value, so the waitpid call in
        # registerReapProcessHandler has already reaped the process
        self.assertRaises(error.ProcessExitedAlready,
                          proc.signalProcess, "KILL")


    def test_killExitedButNotDetected(self):
        """
        L{process.Process.signalProcess} raises L{error.ProcessExitedAlready}
        if the process has exited but that twisted hasn't seen it (for example,
        if the process has been waited outside of twisted): C{os.kill} then
        raise C{OSError} with C{errno.ESRCH} as errno.
        """
        self.mockos.child = False
        self.mockos.waitChild = (0, 0)
        cmd = b'/mock/ouch'
        p = TrivialProcessProtocol(None)
        proc = reactor.spawnProcess(p, cmd, [b'ouch'], env=None, usePTY=False)
        self.mockos.raiseKill = OSError(errno.ESRCH, "Not found")
        self.assertRaises(error.ProcessExitedAlready,
                          proc.signalProcess, "KILL")


    def test_killErrorInKill(self):
        """
        L{process.Process.signalProcess} doesn't mask C{OSError} exceptions if
        the errno is different from C{errno.ESRCH}.
        """
        self.mockos.child = False
        self.mockos.waitChild = (0, 0)
        cmd = b'/mock/ouch'
        p = TrivialProcessProtocol(None)
        proc = reactor.spawnProcess(p, cmd, [b'ouch'], env=None, usePTY=False)
        self.mockos.raiseKill = OSError(errno.EINVAL, "Invalid signal")
        err = self.assertRaises(OSError,
                                proc.signalProcess, "KILL")
        self.assertEqual(err.errno, errno.EINVAL)



class PosixProcessTests(unittest.TestCase, PosixProcessBase):
    # add two non-pty test cases

    def test_stderr(self):
        """
        Bytes written to stderr by the spawned process are passed to the
        C{errReceived} callback on the C{ProcessProtocol} passed to
        C{spawnProcess}.
        """
        value = "42"

        p = Accumulator()
        d = p.endedDeferred = defer.Deferred()
        reactor.spawnProcess(p, pyExe,
                             [pyExe, b"-c",
                              networkString("import sys; sys.stderr.write"
                                            "('{0}')".format(value))],
                             env=None, path="/tmp",
                             usePTY=self.usePTY)

        def processEnded(ign):
            self.assertEqual(b"42", p.errF.getvalue())
        return d.addCallback(processEnded)


    def test_process(self):
        cmd = self.getCommand('gzip')
        s = b"there's no place like home!\n" * 3
        p = Accumulator()
        d = p.endedDeferred = defer.Deferred()
        reactor.spawnProcess(p, cmd, [cmd, b"-c"], env=None, path="/tmp",
                             usePTY=self.usePTY)
        p.transport.write(s)
        p.transport.closeStdin()

        def processEnded(ign):
            f = p.outF
            f.seek(0, 0)
            with gzip.GzipFile(fileobj=f) as gf:
                self.assertEqual(gf.read(), s)
        return d.addCallback(processEnded)



class PosixProcessPTYTests(unittest.TestCase, PosixProcessBase):
    """
    Just like PosixProcessTests, but use ptys instead of pipes.
    """
    usePTY = True
    # PTYs only offer one input and one output. What still makes sense?
    # testNormalTermination
    # test_abnormalTermination
    # testSignal
    # testProcess, but not without p.transport.closeStdin
    #  might be solveable: TODO: add test if so

    def test_openingTTY(self):
        scriptPath = b"twisted.test.process_tty"
        p = Accumulator()
        d = p.endedDeferred = defer.Deferred()
        reactor.spawnProcess(p, pyExe, [pyExe, b"-u", b"-m", scriptPath],
                             env=properEnv, usePTY=self.usePTY)
        p.transport.write(b"hello world!\n")

        def processEnded(ign):
            self.assertRaises(
                error.ProcessExitedAlready, p.transport.signalProcess, 'HUP')
            self.assertEqual(
                p.outF.getvalue(),
                b"hello world!\r\nhello world!\r\n",
                ("Error message from process_tty "
                 "follows:\n\n%s\n\n" % (p.outF.getvalue(),)))
        return d.addCallback(processEnded)


    def test_badArgs(self):
        pyArgs = [pyExe, b"-u", b"-c", b"print('hello')"]
        p = Accumulator()
        self.assertRaises(ValueError, reactor.spawnProcess, p, pyExe, pyArgs,
            usePTY=1, childFDs={1:b'r'})



class Win32SignalProtocol(SignalProtocol):
    """
    A win32-specific process protocol that handles C{processEnded}
    differently: processes should exit with exit code 1.
    """

    def processEnded(self, reason):
        """
        Callback C{self.deferred} with L{None} if C{reason} is a
        L{error.ProcessTerminated} failure with C{exitCode} set to 1.
        Otherwise, errback with a C{ValueError} describing the problem.
        """
        if not reason.check(error.ProcessTerminated):
            return self.deferred.errback(
                ValueError("wrong termination: %s" % (reason,)))
        v = reason.value
        if v.exitCode != 1:
            return self.deferred.errback(
                ValueError("Wrong exit code: %s" % (v.exitCode,)))
        self.deferred.callback(None)



class Win32ProcessTests(unittest.TestCase):
    """
    Test process programs that are packaged with twisted.
    """

    def test_stdinReader(self):
        scriptPath = b"twisted.test.process_stdinreader"
        p = Accumulator()
        d = p.endedDeferred = defer.Deferred()
        reactor.spawnProcess(p, pyExe, [pyExe, b"-u", b"-m", scriptPath],
                             env=properEnv)
        p.transport.write(b"hello, world")
        p.transport.closeStdin()

        def processEnded(ign):
            self.assertEqual(p.errF.getvalue(), "err\nerr\n")
            self.assertEqual(p.outF.getvalue(), "out\nhello, world\nout\n")
        return d.addCallback(processEnded)


    def test_badArgs(self):
        pyArgs = [pyExe, b"-u", b"-c", b"print('hello')"]
        p = Accumulator()
        self.assertRaises(ValueError,
                          reactor.spawnProcess, p, pyExe, pyArgs, uid=1)
        self.assertRaises(ValueError,
                          reactor.spawnProcess, p, pyExe, pyArgs, gid=1)
        self.assertRaises(ValueError,
                          reactor.spawnProcess, p, pyExe, pyArgs, usePTY=1)
        self.assertRaises(ValueError,
                          reactor.spawnProcess, p, pyExe, pyArgs, childFDs={1:'r'})


    def _testSignal(self, sig):
        scriptPath = b"twisted.test.process_signal"
        d = defer.Deferred()
        p = Win32SignalProtocol(d, sig)
        reactor.spawnProcess(p, pyExe, [pyExe, b"-u", b"-m", scriptPath],
                             env=properEnv)
        return d


    def test_signalTERM(self):
        """
        Sending the SIGTERM signal terminates a created process, and
        C{processEnded} is called with a L{error.ProcessTerminated} instance
        with the C{exitCode} attribute set to 1.
        """
        return self._testSignal('TERM')


    def test_signalINT(self):
        """
        Sending the SIGINT signal terminates a created process, and
        C{processEnded} is called with a L{error.ProcessTerminated} instance
        with the C{exitCode} attribute set to 1.
        """
        return self._testSignal('INT')


    def test_signalKILL(self):
        """
        Sending the SIGKILL signal terminates a created process, and
        C{processEnded} is called with a L{error.ProcessTerminated} instance
        with the C{exitCode} attribute set to 1.
        """
        return self._testSignal('KILL')


    def test_closeHandles(self):
        """
        The win32 handles should be properly closed when the process exits.
        """
        import win32api

        connected = defer.Deferred()
        ended = defer.Deferred()

        class SimpleProtocol(protocol.ProcessProtocol):
            """
            A protocol that fires deferreds when connected and disconnected.
            """
            def makeConnection(self, transport):
                connected.callback(transport)

            def processEnded(self, reason):
                ended.callback(None)

        p = SimpleProtocol()
        pyArgs = [pyExe, b"-u", b"-c", b"print('hello')"]
        proc = reactor.spawnProcess(p, pyExe, pyArgs)

        def cbConnected(transport):
            self.assertIs(transport, proc)
            # perform a basic validity test on the handles
            win32api.GetHandleInformation(proc.hProcess)
            win32api.GetHandleInformation(proc.hThread)
            # And save their values for later
            self.hProcess = proc.hProcess
            self.hThread = proc.hThread
        connected.addCallback(cbConnected)

        def checkTerminated(ignored):
            # The attributes on the process object must be reset...
            self.assertIsNone(proc.pid)
            self.assertIsNone(proc.hProcess)
            self.assertIsNone(proc.hThread)
            # ...and the handles must be closed.
            self.assertRaises(win32api.error,
                              win32api.GetHandleInformation, self.hProcess)
            self.assertRaises(win32api.error,
                              win32api.GetHandleInformation, self.hThread)
        ended.addCallback(checkTerminated)

        return defer.gatherResults([connected, ended])



class Win32UnicodeEnvironmentTests(unittest.TestCase):
    """
    Tests for Unicode environment on Windows
    """
    goodKey = u'UNICODE'
    goodValue = u'UNICODE'

    def test_encodableUnicodeEnvironment(self):
        """
        Test C{os.environ} (inherited by every subprocess on Windows) that
        contains an ascii-encodable Unicode string. This is different from
        passing Unicode environment explicitly to spawnProcess (which is not
        supported on Python 2).
        """
        os.environ[self.goodKey] = self.goodValue
        self.addCleanup(operator.delitem, os.environ, self.goodKey)

        p = GetEnvironmentDictionary.run(reactor, [], properEnv)
        def gotEnvironment(environ):
            self.assertEqual(
                environ[self.goodKey.encode('ascii')],
                self.goodValue.encode('ascii'))
        return p.getResult().addCallback(gotEnvironment)



class DumbWin32ProcTests(unittest.TestCase):
    """
    L{twisted.internet._dumbwin32proc} tests.
    """
    def test_pid(self):
        """
        Simple test for the pid attribute of Process on win32.
        Launch process with mock win32process. The only mock aspect of this
        module is that the pid of the process created will always be 42.
        """
        from twisted.internet import _dumbwin32proc
        from twisted.test import mock_win32process
        self.patch(_dumbwin32proc, "win32process", mock_win32process)
        scriptPath = util.sibpath(__file__, "process_cmdline.py")

        d = defer.Deferred()
        processProto = TrivialProcessProtocol(d)
        comspec = bytes(os.environ["COMSPEC"])
        cmd = [comspec, b"/c", pyExe, scriptPath]

        p = _dumbwin32proc.Process(reactor,
                                  processProto,
                                  None,
                                  cmd,
                                  {},
                                  None)
        self.assertEqual(42, p.pid)
        self.assertEqual("<Process pid=42>", repr(p))

        def pidCompleteCb(result):
            self.assertIsNone(p.pid)
        return d.addCallback(pidCompleteCb)


    def test_findShebang(self):
        """
        Look for the string after the shebang C{#!}
        in a file.
        """
        from twisted.internet._dumbwin32proc import _findShebang
        cgiScript = FilePath(b"example.cgi")
        cgiScript.setContent(b"#!/usr/bin/python")
        program = _findShebang(cgiScript.path)
        self.assertEqual(program, "/usr/bin/python")


class UtilTests(unittest.TestCase):
    """
    Tests for process-related helper functions (currently only
    L{procutils.which}.
    """
    def setUp(self):
        """
        Create several directories and files, some of which are executable
        and some of which are not.  Save the current PATH setting.
        """
        j = os.path.join

        base = self.mktemp()

        self.foo = j(base, "foo")
        self.baz = j(base, "baz")
        self.foobar = j(self.foo, "bar")
        self.foobaz = j(self.foo, "baz")
        self.bazfoo = j(self.baz, "foo")
        self.bazbar = j(self.baz, "bar")

        for d in self.foobar, self.foobaz, self.bazfoo, self.bazbar:
            os.makedirs(d)

        for name, mode in [(j(self.foobaz, "executable"), 0o700),
                           (j(self.foo, "executable"), 0o700),
                           (j(self.bazfoo, "executable"), 0o700),
                           (j(self.bazfoo, "executable.bin"), 0o700),
                           (j(self.bazbar, "executable"), 0)]:
            open(name, "wb").close()
            os.chmod(name, mode)

        self.oldPath = os.environ.get('PATH', None)
        os.environ['PATH'] = os.pathsep.join((
            self.foobar, self.foobaz, self.bazfoo, self.bazbar))


    def tearDown(self):
        """
        Restore the saved PATH setting, and set all created files readable
        again so that they can be deleted easily.
        """
        os.chmod(os.path.join(self.bazbar, "executable"), stat.S_IWUSR)
        if self.oldPath is None:
            try:
                del os.environ['PATH']
            except KeyError:
                pass
        else:
            os.environ['PATH'] = self.oldPath


    def test_whichWithoutPATH(self):
        """
        Test that if C{os.environ} does not have a C{'PATH'} key,
        L{procutils.which} returns an empty list.
        """
        del os.environ['PATH']
        self.assertEqual(procutils.which("executable"), [])


    def test_which(self):
        j = os.path.join
        paths = procutils.which("executable")
        expectedPaths = [j(self.foobaz, "executable"),
                         j(self.bazfoo, "executable")]
        if runtime.platform.isWindows():
            expectedPaths.append(j(self.bazbar, "executable"))
        self.assertEqual(paths, expectedPaths)


    def test_whichPathExt(self):
        j = os.path.join
        old = os.environ.get('PATHEXT', None)
        os.environ['PATHEXT'] = os.pathsep.join(('.bin', '.exe', '.sh'))
        try:
            paths = procutils.which("executable")
        finally:
            if old is None:
                del os.environ['PATHEXT']
            else:
                os.environ['PATHEXT'] = old
        expectedPaths = [j(self.foobaz, "executable"),
                         j(self.bazfoo, "executable"),
                         j(self.bazfoo, "executable.bin")]
        if runtime.platform.isWindows():
            expectedPaths.append(j(self.bazbar, "executable"))
        self.assertEqual(paths, expectedPaths)



class ClosingPipesProcessProtocol(protocol.ProcessProtocol):
    output = b''
    errput = b''

    def __init__(self, outOrErr):
        self.deferred = defer.Deferred()
        self.outOrErr = outOrErr

    def processEnded(self, reason):
        self.deferred.callback(reason)

    def outReceived(self, data):
        self.output += data

    def errReceived(self, data):
        self.errput += data



class ClosingPipesTests(unittest.TestCase):

    def doit(self, fd):
        """
        Create a child process and close one of its output descriptors using
        L{IProcessTransport.closeStdout} or L{IProcessTransport.closeStderr}.
        Return a L{Deferred} which fires after verifying that the descriptor was
        really closed.
        """
        p = ClosingPipesProcessProtocol(True)
        self.assertFailure(p.deferred, error.ProcessTerminated)
        p.deferred.addCallback(self._endProcess, p)
        reactor.spawnProcess(
            p, pyExe, [
                pyExe, b'-u', b'-c',
                networkString('try: input = raw_input\n'
                'except NameError: pass\n'
                'input()\n'
                'import sys, os, time\n'
                # Give the system a bit of time to notice the closed
                # descriptor.  Another option would be to poll() for HUP
                # instead of relying on an os.write to fail with SIGPIPE.
                # However, that wouldn't work on OS X (or Windows?).
                'for i in range(1000):\n'
                '    os.write(%d, b"foo\\n")\n'
                '    time.sleep(0.01)\n'
                'sys.exit(42)\n' % (fd,))
                ],
            env=None)

        if fd == 1:
            p.transport.closeStdout()
        elif fd == 2:
            p.transport.closeStderr()
        else:
            raise RuntimeError

        # Give the close time to propagate
        p.transport.write(b'go\n')

        # make the buggy case not hang
        p.transport.closeStdin()
        return p.deferred


    def _endProcess(self, reason, p):
        """
        Check that a failed write prevented the process from getting to its
        custom exit code.
        """
        # child must not get past that write without raising
        self.assertNotEqual(
            reason.exitCode, 42, 'process reason was %r' % reason)
        self.assertEqual(p.output, b'')
        return p.errput


    def test_stdout(self):
        """
        ProcessProtocol.transport.closeStdout actually closes the pipe.
        """
        d = self.doit(1)
        def _check(errput):
            if _PY3:
                self.assertIn(b'BrokenPipeError', errput)
            else:
                self.assertIn(b'OSError', errput)
            if runtime.platform.getType() != 'win32':
                self.assertIn(b'Broken pipe', errput)
        d.addCallback(_check)
        return d


    def test_stderr(self):
        """
        ProcessProtocol.transport.closeStderr actually closes the pipe.
        """
        d = self.doit(2)
        def _check(errput):
            # there should be no stderr open, so nothing for it to
            # write the error to.
            self.assertEqual(errput, b'')
        d.addCallback(_check)
        return d


skipMessage = "wrong platform or reactor doesn't support IReactorProcess"
if (runtime.platform.getType() != 'posix') or (not interfaces.IReactorProcess(reactor, None)):
    PosixProcessTests.skip = skipMessage
    PosixProcessPTYTests.skip = skipMessage
    TwoProcessesPosixTests.skip = skipMessage
    FDTests.skip = skipMessage

if (runtime.platform.getType() != 'win32') or (not interfaces.IReactorProcess(reactor, None)):
    Win32ProcessTests.skip = skipMessage
    TwoProcessesNonPosixTests.skip = skipMessage
    DumbWin32ProcTests.skip = skipMessage
    Win32UnicodeEnvironmentTests.skip = skipMessage

if not interfaces.IReactorProcess(reactor, None):
    ProcessTests.skip = skipMessage
    ClosingPipesTests.skip = skipMessage
