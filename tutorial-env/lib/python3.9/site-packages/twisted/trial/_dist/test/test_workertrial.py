# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.trial._dist.workertrial}.
"""

import errno
import sys
from io import BytesIO

from twisted.protocols.amp import AMP
from twisted.test.proto_helpers import StringTransport
from twisted.trial._dist import (
    _WORKER_AMP_STDIN,
    _WORKER_AMP_STDOUT,
    managercommands,
    workercommands,
    workertrial,
)
from twisted.trial._dist.workertrial import WorkerLogObserver, main
from twisted.trial.unittest import TestCase


class FakeAMP(AMP):
    """
    A fake amp protocol.
    """


class WorkerLogObserverTests(TestCase):
    """
    Tests for L{WorkerLogObserver}.
    """

    def test_emit(self):
        """
        L{WorkerLogObserver} forwards data to L{managercommands.TestWrite}.
        """
        calls = []

        class FakeClient:
            def callRemote(self, method, **kwargs):
                calls.append((method, kwargs))

        observer = WorkerLogObserver(FakeClient())
        observer.emit({"message": ["Some log"]})
        self.assertEqual(calls, [(managercommands.TestWrite, {"out": "Some log"})])


class MainTests(TestCase):
    """
    Tests for L{main}.
    """

    def setUp(self):
        self.readStream = BytesIO()
        self.writeStream = BytesIO()
        self.patch(
            workertrial, "startLoggingWithObserver", self.startLoggingWithObserver
        )
        self.addCleanup(setattr, sys, "argv", sys.argv)
        sys.argv = ["trial"]

    def fdopen(self, fd, mode=None):
        """
        Fake C{os.fdopen} implementation which returns C{self.readStream} for
        the stdin fd and C{self.writeStream} for the stdout fd.
        """
        if fd == _WORKER_AMP_STDIN:
            self.assertEqual("rb", mode)
            return self.readStream
        elif fd == _WORKER_AMP_STDOUT:
            self.assertEqual("wb", mode)
            return self.writeStream
        else:
            raise AssertionError(f"Unexpected fd {fd!r}")

    def startLoggingWithObserver(self, emit, setStdout):
        """
        Override C{startLoggingWithObserver} for not starting logging.
        """
        self.assertFalse(setStdout)

    def test_empty(self):
        """
        If no data is ever written, L{main} exits without writing data out.
        """
        main(self.fdopen)
        self.assertEqual(b"", self.writeStream.getvalue())

    def test_forwardCommand(self):
        """
        L{main} forwards data from its input stream to a L{WorkerProtocol}
        instance which writes data to the output stream.
        """
        client = FakeAMP()
        clientTransport = StringTransport()
        client.makeConnection(clientTransport)
        client.callRemote(workercommands.Run, testCase="doesntexist")
        self.readStream = clientTransport.io
        self.readStream.seek(0, 0)
        main(self.fdopen)
        # Just brazenly encode irrelevant implementation details here, why
        # not.
        self.assertIn(b"StreamOpen", self.writeStream.getvalue())

    def test_readInterrupted(self):
        """
        If reading the input stream fails with a C{IOError} with errno
        C{EINTR}, L{main} ignores it and continues reading.
        """
        excInfos = []

        class FakeStream:
            count = 0

            def read(oself, size):
                oself.count += 1
                if oself.count == 1:
                    raise OSError(errno.EINTR)
                else:
                    excInfos.append(sys.exc_info())
                return b""

        self.readStream = FakeStream()
        main(self.fdopen)
        self.assertEqual(b"", self.writeStream.getvalue())
        self.assertEqual([(None, None, None)], excInfos)

    def test_otherReadError(self):
        """
        L{main} only ignores C{IOError} with C{EINTR} errno: otherwise, the
        error pops out.
        """

        class FakeStream:
            count = 0

            def read(oself, size):
                oself.count += 1
                if oself.count == 1:
                    raise OSError("Something else")
                return ""

        self.readStream = FakeStream()
        self.assertRaises(IOError, main, self.fdopen)
