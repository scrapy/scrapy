# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test running processes with the APIs in L{twisted.internet.utils}.
"""


import os
import signal
import stat
import sys
import warnings
from unittest import skipIf

from twisted.internet import error, interfaces, reactor, utils
from twisted.internet.defer import Deferred
from twisted.python.runtime import platform
from twisted.python.test.test_util import SuppressedWarningsTests
from twisted.trial.unittest import SynchronousTestCase, TestCase


class ProcessUtilsTests(TestCase):
    """
    Test running a process using L{getProcessOutput}, L{getProcessValue}, and
    L{getProcessOutputAndValue}.
    """

    if interfaces.IReactorProcess(reactor, None) is None:
        skip = "reactor doesn't implement IReactorProcess"

    output = None
    value = None
    exe = sys.executable

    def makeSourceFile(self, sourceLines):
        """
        Write the given list of lines to a text file and return the absolute
        path to it.
        """
        script = self.mktemp()
        with open(script, "wt") as scriptFile:
            scriptFile.write(os.linesep.join(sourceLines) + os.linesep)
        return os.path.abspath(script)

    def test_output(self):
        """
        L{getProcessOutput} returns a L{Deferred} which fires with the complete
        output of the process it runs after that process exits.
        """
        scriptFile = self.makeSourceFile(
            [
                "import sys",
                "for s in b'hello world\\n':",
                "    s = bytes([s])",
                "    sys.stdout.buffer.write(s)",
                "    sys.stdout.flush()",
            ]
        )
        d = utils.getProcessOutput(self.exe, ["-u", scriptFile])
        return d.addCallback(self.assertEqual, b"hello world\n")

    def test_outputWithErrorIgnored(self):
        """
        The L{Deferred} returned by L{getProcessOutput} is fired with an
        L{IOError} L{Failure} if the child process writes to stderr.
        """
        # make sure stderr raises an error normally
        scriptFile = self.makeSourceFile(
            ["import sys", 'sys.stderr.write("hello world\\n")']
        )

        d = utils.getProcessOutput(self.exe, ["-u", scriptFile])
        d = self.assertFailure(d, IOError)

        def cbFailed(err):
            return self.assertFailure(err.processEnded, error.ProcessDone)

        d.addCallback(cbFailed)
        return d

    def test_outputWithErrorCollected(self):
        """
        If a C{True} value is supplied for the C{errortoo} parameter to
        L{getProcessOutput}, the returned L{Deferred} fires with the child's
        stderr output as well as its stdout output.
        """
        scriptFile = self.makeSourceFile(
            [
                "import sys",
                # Write the same value to both because ordering isn't guaranteed so
                # this simplifies the test.
                'sys.stdout.write("foo")',
                "sys.stdout.flush()",
                'sys.stderr.write("foo")',
                "sys.stderr.flush()",
            ]
        )

        d = utils.getProcessOutput(self.exe, ["-u", scriptFile], errortoo=True)
        return d.addCallback(self.assertEqual, b"foofoo")

    def test_value(self):
        """
        The L{Deferred} returned by L{getProcessValue} is fired with the exit
        status of the child process.
        """
        scriptFile = self.makeSourceFile(["raise SystemExit(1)"])

        d = utils.getProcessValue(self.exe, ["-u", scriptFile])
        return d.addCallback(self.assertEqual, 1)

    def test_outputAndValue(self):
        """
        The L{Deferred} returned by L{getProcessOutputAndValue} fires with a
        three-tuple, the elements of which give the data written to the child's
        stdout, the data written to the child's stderr, and the exit status of
        the child.
        """
        scriptFile = self.makeSourceFile(
            [
                "import sys",
                "sys.stdout.buffer.write(b'hello world!\\n')",
                "sys.stderr.buffer.write(b'goodbye world!\\n')",
                "sys.exit(1)",
            ]
        )

        def gotOutputAndValue(out_err_code):
            out, err, code = out_err_code
            self.assertEqual(out, b"hello world!\n")
            self.assertEqual(err, b"goodbye world!\n")
            self.assertEqual(code, 1)

        d = utils.getProcessOutputAndValue(self.exe, ["-u", scriptFile])
        return d.addCallback(gotOutputAndValue)

    @skipIf(platform.isWindows(), "Windows doesn't have real signals.")
    def test_outputSignal(self):
        """
        If the child process exits because of a signal, the L{Deferred}
        returned by L{getProcessOutputAndValue} fires a L{Failure} of a tuple
        containing the child's stdout, stderr, and the signal which caused
        it to exit.
        """
        # Use SIGKILL here because it's guaranteed to be delivered. Using
        # SIGHUP might not work in, e.g., a buildbot slave run under the
        # 'nohup' command.
        scriptFile = self.makeSourceFile(
            [
                "import sys, os, signal",
                "sys.stdout.write('stdout bytes\\n')",
                "sys.stderr.write('stderr bytes\\n')",
                "sys.stdout.flush()",
                "sys.stderr.flush()",
                "os.kill(os.getpid(), signal.SIGKILL)",
            ]
        )

        def gotOutputAndValue(out_err_sig):
            out, err, sig = out_err_sig
            self.assertEqual(out, b"stdout bytes\n")
            self.assertEqual(err, b"stderr bytes\n")
            self.assertEqual(sig, signal.SIGKILL)

        d = utils.getProcessOutputAndValue(self.exe, ["-u", scriptFile])
        d = self.assertFailure(d, tuple)
        return d.addCallback(gotOutputAndValue)

    def _pathTest(self, utilFunc, check):
        dir = os.path.abspath(self.mktemp())
        os.makedirs(dir)
        scriptFile = self.makeSourceFile(
            ["import os, sys", "sys.stdout.write(os.getcwd())"]
        )
        d = utilFunc(self.exe, ["-u", scriptFile], path=dir)
        d.addCallback(check, dir.encode(sys.getfilesystemencoding()))
        return d

    def test_getProcessOutputPath(self):
        """
        L{getProcessOutput} runs the given command with the working directory
        given by the C{path} parameter.
        """
        return self._pathTest(utils.getProcessOutput, self.assertEqual)

    def test_getProcessValuePath(self):
        """
        L{getProcessValue} runs the given command with the working directory
        given by the C{path} parameter.
        """

        def check(result, ignored):
            self.assertEqual(result, 0)

        return self._pathTest(utils.getProcessValue, check)

    def test_getProcessOutputAndValuePath(self):
        """
        L{getProcessOutputAndValue} runs the given command with the working
        directory given by the C{path} parameter.
        """

        def check(out_err_status, dir):
            out, err, status = out_err_status
            self.assertEqual(out, dir)
            self.assertEqual(status, 0)

        return self._pathTest(utils.getProcessOutputAndValue, check)

    def _defaultPathTest(self, utilFunc, check):
        # Make another directory to mess around with.
        dir = os.path.abspath(self.mktemp())
        os.makedirs(dir)

        scriptFile = self.makeSourceFile(
            ["import os, sys", "cdir = os.getcwd()", "sys.stdout.write(cdir)"]
        )

        # Switch to it, but make sure we switch back
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(dir)

        # Remember its default permissions.
        originalMode = stat.S_IMODE(os.stat(".").st_mode)

        # On macOS Catalina (and maybe elsewhere), os.getcwd() sometimes fails
        # with EACCES if u+rx is missing from the working directory, so don't
        # reduce it further than this.
        os.chmod(dir, stat.S_IXUSR | stat.S_IRUSR)

        # Restore the permissions to their original state later (probably
        # adding at least u+w), because otherwise it might be hard to delete
        # the trial temporary directory.
        self.addCleanup(os.chmod, dir, originalMode)

        d = utilFunc(self.exe, ["-u", scriptFile])
        d.addCallback(check, dir.encode(sys.getfilesystemencoding()))
        return d

    def test_getProcessOutputDefaultPath(self):
        """
        If no value is supplied for the C{path} parameter, L{getProcessOutput}
        runs the given command in the same working directory as the parent
        process and succeeds even if the current working directory is not
        accessible.
        """
        return self._defaultPathTest(utils.getProcessOutput, self.assertEqual)

    def test_getProcessValueDefaultPath(self):
        """
        If no value is supplied for the C{path} parameter, L{getProcessValue}
        runs the given command in the same working directory as the parent
        process and succeeds even if the current working directory is not
        accessible.
        """

        def check(result, ignored):
            self.assertEqual(result, 0)

        return self._defaultPathTest(utils.getProcessValue, check)

    def test_getProcessOutputAndValueDefaultPath(self):
        """
        If no value is supplied for the C{path} parameter,
        L{getProcessOutputAndValue} runs the given command in the same working
        directory as the parent process and succeeds even if the current
        working directory is not accessible.
        """

        def check(out_err_status, dir):
            out, err, status = out_err_status
            self.assertEqual(out, dir)
            self.assertEqual(status, 0)

        return self._defaultPathTest(utils.getProcessOutputAndValue, check)

    def test_get_processOutputAndValueStdin(self):
        """
        Standard input can be made available to the child process by passing
        bytes for the `stdinBytes` parameter.
        """
        scriptFile = self.makeSourceFile(
            [
                "import sys",
                "sys.stdout.write(sys.stdin.read())",
            ]
        )
        stdinBytes = b"These are the bytes to see."
        d = utils.getProcessOutputAndValue(
            self.exe,
            ["-u", scriptFile],
            stdinBytes=stdinBytes,
        )

        def gotOutputAndValue(out_err_code):
            out, err, code = out_err_code
            # Avoid making an exact equality comparison in case there is extra
            # random output on stdout (warnings, stray print statements,
            # logging, who knows).
            self.assertIn(stdinBytes, out)
            self.assertEqual(0, code)

        d.addCallback(gotOutputAndValue)
        return d


class SuppressWarningsTests(SynchronousTestCase):
    """
    Tests for L{utils.suppressWarnings}.
    """

    def test_suppressWarnings(self):
        """
        L{utils.suppressWarnings} decorates a function so that the given
        warnings are suppressed.
        """
        result = []

        def showwarning(self, *a, **kw):
            result.append((a, kw))

        self.patch(warnings, "showwarning", showwarning)

        def f(msg):
            warnings.warn(msg)

        g = utils.suppressWarnings(f, (("ignore",), dict(message="This is message")))

        # Start off with a sanity check - calling the original function
        # should emit the warning.
        f("Sanity check message")
        self.assertEqual(len(result), 1)

        # Now that that's out of the way, call the wrapped function, and
        # make sure no new warnings show up.
        g("This is message")
        self.assertEqual(len(result), 1)

        # Finally, emit another warning which should not be ignored, and
        # make sure it is not.
        g("Unignored message")
        self.assertEqual(len(result), 2)


class DeferredSuppressedWarningsTests(SuppressedWarningsTests):
    """
    Tests for L{utils.runWithWarningsSuppressed}, the version that supports
    Deferreds.
    """

    # Override the non-Deferred-supporting function from the base class with
    # the function we are testing in this class:
    runWithWarningsSuppressed = staticmethod(utils.runWithWarningsSuppressed)

    def test_deferredCallback(self):
        """
        If the function called by L{utils.runWithWarningsSuppressed} returns a
        C{Deferred}, the warning filters aren't removed until the Deferred
        fires.
        """
        filters = [(("ignore", ".*foo.*"), {}), (("ignore", ".*bar.*"), {})]
        result = Deferred()
        self.runWithWarningsSuppressed(filters, lambda: result)
        warnings.warn("ignore foo")
        result.callback(3)
        warnings.warn("ignore foo 2")
        self.assertEqual(["ignore foo 2"], [w["message"] for w in self.flushWarnings()])

    def test_deferredErrback(self):
        """
        If the function called by L{utils.runWithWarningsSuppressed} returns a
        C{Deferred}, the warning filters aren't removed until the Deferred
        fires with an errback.
        """
        filters = [(("ignore", ".*foo.*"), {}), (("ignore", ".*bar.*"), {})]
        result = Deferred()
        d = self.runWithWarningsSuppressed(filters, lambda: result)
        warnings.warn("ignore foo")
        result.errback(ZeroDivisionError())
        d.addErrback(lambda f: f.trap(ZeroDivisionError))
        warnings.warn("ignore foo 2")
        self.assertEqual(["ignore foo 2"], [w["message"] for w in self.flushWarnings()])
