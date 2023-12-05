# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.trial._dist.distreporter}.
"""

from io import StringIO

from twisted.python.failure import Failure
from twisted.trial._dist.distreporter import DistReporter
from twisted.trial.reporter import TreeReporter
from twisted.trial.unittest import TestCase


class DistReporterTests(TestCase):
    """
    Tests for L{DistReporter}.
    """

    def setUp(self) -> None:
        self.stream = StringIO()
        self.distReporter = DistReporter(TreeReporter(self.stream))
        self.test = TestCase()

    def test_startSuccessStop(self) -> None:
        """
        Success output only gets sent to the stream after the test has stopped.
        """
        self.distReporter.startTest(self.test)
        self.assertEqual(self.stream.getvalue(), "")
        self.distReporter.addSuccess(self.test)
        self.assertEqual(self.stream.getvalue(), "")
        self.distReporter.stopTest(self.test)
        self.assertNotEqual(self.stream.getvalue(), "")

    def test_startErrorStop(self) -> None:
        """
        Error output only gets sent to the stream after the test has stopped.
        """
        self.distReporter.startTest(self.test)
        self.assertEqual(self.stream.getvalue(), "")
        self.distReporter.addError(self.test, Failure(Exception("error")))
        self.assertEqual(self.stream.getvalue(), "")
        self.distReporter.stopTest(self.test)
        self.assertNotEqual(self.stream.getvalue(), "")

    def test_forwardedMethods(self) -> None:
        """
        Calling methods of L{DistReporter} add calls to the running queue of
        the test.
        """
        self.distReporter.startTest(self.test)
        self.distReporter.addFailure(self.test, Failure(Exception("foo")))
        self.distReporter.addError(self.test, Failure(Exception("bar")))
        self.distReporter.addSkip(self.test, "egg")
        self.distReporter.addUnexpectedSuccess(self.test, "spam")
        self.distReporter.addExpectedFailure(
            self.test, Failure(Exception("err")), "foo"
        )
        self.assertEqual(len(self.distReporter.running[self.test.id()]), 6)
