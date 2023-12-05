# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.trial._dist.workerreporter}.
"""


from unittest import TestCase

from hamcrest import assert_that, equal_to, has_length
from hamcrest.core.matcher import Matcher

from twisted.internet.defer import Deferred
from twisted.test.iosim import connectedServerAndClient
from twisted.trial._dist.worker import LocalWorkerAMP, WorkerProtocol
from twisted.trial.reporter import TestResult
from twisted.trial.test import erroneous, pyunitcases, sample, skipping
from twisted.trial.unittest import SynchronousTestCase
from .matchers import matches_result


def run(case: SynchronousTestCase, target: TestCase) -> TestResult:
    """
    Run C{target} and return a test result as populated by a worker reporter.

    @param case: A test case to use to help run the target.
    """
    result = TestResult()
    worker, local, pump = connectedServerAndClient(LocalWorkerAMP, WorkerProtocol)
    d = Deferred.fromCoroutine(local.run(target, result))
    pump.flush()
    assert_that(case.successResultOf(d), equal_to({"success": True}))
    return result


class WorkerReporterTests(SynchronousTestCase):
    """
    Tests for L{WorkerReporter}.
    """

    def assertTestRun(self, target: TestCase, **expectations: Matcher) -> None:
        """
        Run the given test and assert that the result matches the given
        expectations.
        """
        assert_that(run(self, target), matches_result(**expectations))

    def test_outsideReportingContext(self) -> None:
        """
        L{WorkerReporter}'s implementation of test result methods raise
        L{ValueError} when called outside of the
        L{WorkerReporter.gatherReportingResults} context manager.
        """
        worker, local, pump = connectedServerAndClient(LocalWorkerAMP, WorkerProtocol)

        case = sample.FooTest("test_foo")
        with self.assertRaises(ValueError):
            worker._result.addSuccess(case)

    def test_addSuccess(self) -> None:
        """
        L{WorkerReporter} propagates successes.
        """
        self.assertTestRun(sample.FooTest("test_foo"), successes=equal_to(1))

    def test_addError(self) -> None:
        """
        L{WorkerReporter} propagates errors from trial's TestCases.
        """
        self.assertTestRun(
            erroneous.TestAsynchronousFail("test_exception"), errors=has_length(1)
        )

    def test_addErrorGreaterThan64k(self) -> None:
        """
        L{WorkerReporter} propagates errors with large string representations.
        """
        self.assertTestRun(
            erroneous.TestAsynchronousFail("test_exceptionGreaterThan64k"),
            errors=has_length(1),
        )

    def test_addErrorGreaterThan64kEncoded(self) -> None:
        """
        L{WorkerReporter} propagates errors with a string representation that
        is smaller than an implementation-specific limit but which encode to a
        byte representation that exceeds this limit.
        """
        self.assertTestRun(
            erroneous.TestAsynchronousFail("test_exceptionGreaterThan64kEncoded"),
            errors=has_length(1),
        )

    def test_addErrorTuple(self) -> None:
        """
        L{WorkerReporter} propagates errors from pyunit's TestCases.
        """
        self.assertTestRun(pyunitcases.PyUnitTest("test_error"), errors=has_length(1))

    def test_addFailure(self) -> None:
        """
        L{WorkerReporter} propagates test failures from trial's TestCases.
        """
        self.assertTestRun(
            erroneous.TestRegularFail("test_fail"), failures=has_length(1)
        )

    def test_addFailureGreaterThan64k(self) -> None:
        """
        L{WorkerReporter} propagates test failures with large string representations.
        """
        self.assertTestRun(
            erroneous.TestAsynchronousFail("test_failGreaterThan64k"),
            failures=has_length(1),
        )

    def test_addFailureTuple(self) -> None:
        """
        L{WorkerReporter} propagates test failures from pyunit's TestCases.
        """
        self.assertTestRun(pyunitcases.PyUnitTest("test_fail"), failures=has_length(1))

    def test_addSkip(self) -> None:
        """
        L{WorkerReporter} propagates skips.
        """
        self.assertTestRun(
            skipping.SynchronousSkipping("test_skip1"), skips=has_length(1)
        )

    def test_addSkipPyunit(self) -> None:
        """
        L{WorkerReporter} propagates skips from L{unittest.TestCase} cases.
        """
        self.assertTestRun(
            pyunitcases.PyUnitTest("test_skip"),
            skips=has_length(1),
        )

    def test_addExpectedFailure(self) -> None:
        """
        L{WorkerReporter} propagates expected failures.
        """
        self.assertTestRun(
            skipping.SynchronousStrictTodo("test_todo1"), expectedFailures=has_length(1)
        )

    def test_addExpectedFailureGreaterThan64k(self) -> None:
        """
        WorkerReporter propagates expected failures with large string representations.
        """
        self.assertTestRun(
            skipping.ExpectedFailure("test_expectedFailureGreaterThan64k"),
            expectedFailures=has_length(1),
        )

    def test_addUnexpectedSuccess(self) -> None:
        """
        L{WorkerReporter} propagates unexpected successes.
        """
        self.assertTestRun(
            skipping.SynchronousTodo("test_todo3"), unexpectedSuccesses=has_length(1)
        )
