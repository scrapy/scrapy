import fcntl
import os
import pty
import struct
import sys
import termios
import textwrap
import unittest

from bpython.test import TEST_CONFIG
from bpython.config import getpreferredencoding

try:
    from twisted.internet import reactor
    from twisted.internet.defer import Deferred
    from twisted.internet.protocol import ProcessProtocol
    from twisted.trial.unittest import TestCase as TrialTestCase
except ImportError:

    class TrialTestCase:  # type: ignore [no-redef]
        pass

    reactor = None  # type: ignore

try:
    import urwid

    have_urwid = True
except ImportError:
    have_urwid = False


def set_win_size(fd, rows, columns):
    s = struct.pack("HHHH", rows, columns, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, s)


class CrashersTest:
    backend = "cli"

    def run_bpython(self, input):
        """
        Run bpython (with `backend` as backend) in a subprocess and
        enter the given input. Uses a test config that disables the
        paste detection.

        Returns bpython's output.
        """
        result = Deferred()
        encoding = getpreferredencoding()

        class Protocol(ProcessProtocol):
            STATES = (SEND_INPUT, COLLECT) = range(2)

            def __init__(self):
                self.data = ""
                self.delayed_call = None
                self.states = iter(self.STATES)
                self.state = next(self.states)

            def outReceived(self, data):
                self.data += data.decode(encoding)
                if self.delayed_call is not None:
                    self.delayed_call.cancel()
                self.delayed_call = reactor.callLater(0.5, self.next)

            def next(self):
                self.delayed_call = None
                if self.state == self.SEND_INPUT:
                    index = self.data.find(">>> ")
                    if index >= 0:
                        self.data = self.data[index + 4 :]
                        self.transport.write(input.encode(encoding))
                        self.state = next(self.states)
                    elif self.data == "\x1b[6n":
                        # this is a cursor position query
                        # respond that cursor is on row 2, column 1
                        self.transport.write("\x1b[2;1R".encode(encoding))
                else:
                    self.transport.closeStdin()
                    if self.transport.pid is not None:
                        self.delayed_call = None
                        self.transport.signalProcess("TERM")

            def processExited(self, reason):
                if self.delayed_call is not None:
                    self.delayed_call.cancel()
                result.callback(self.data)

        (master, slave) = pty.openpty()
        set_win_size(slave, 25, 80)
        reactor.spawnProcess(
            Protocol(),
            sys.executable,
            (
                sys.executable,
                "-m",
                f"bpython.{self.backend}",
                "--config",
                str(TEST_CONFIG),
                "-q",  # prevents version greeting
            ),
            env={
                "TERM": "vt100",
                "LANG": os.environ.get("LANG", "C.UTF-8"),
            },
            usePTY=(master, slave, os.ttyname(slave)),
        )
        return result

    def test_issue108(self):
        input = textwrap.dedent(
            """\
            def spam():
            u"y\\xe4y"
            \b
            spam("""
        )
        deferred = self.run_bpython(input)
        return deferred.addCallback(self.check_no_traceback)

    def test_issue133(self):
        input = textwrap.dedent(
            """\
            def spam(a, (b, c)):
            pass
            \b
            spam(1"""
        )
        return self.run_bpython(input).addCallback(self.check_no_traceback)

    def check_no_traceback(self, data):
        self.assertNotIn("Traceback", data)


@unittest.skipIf(reactor is None, "twisted is not available")
class CurtsiesCrashersTest(TrialTestCase, CrashersTest):
    backend = "curtsies"


@unittest.skipIf(reactor is None, "twisted is not available")
class CursesCrashersTest(TrialTestCase, CrashersTest):
    backend = "cli"


@unittest.skipUnless(have_urwid, "urwid is required")
@unittest.skipIf(reactor is None, "twisted is not available")
class UrwidCrashersTest(TrialTestCase, CrashersTest):
    backend = "urwid"


if __name__ == "__main__":
    unittest.main()
