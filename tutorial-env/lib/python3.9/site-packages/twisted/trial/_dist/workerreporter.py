# -*- test-case-name: twisted.trial._dist.test.test_workerreporter -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test reporter forwarding test results over trial distributed AMP commands.

@since: 12.3
"""

from types import TracebackType
from typing import Callable, List, Optional, Sequence, Type, TypeVar
from unittest import TestCase as PyUnitTestCase

from attrs import Factory, define
from typing_extensions import Literal

from twisted.internet.defer import Deferred, maybeDeferred
from twisted.protocols.amp import AMP, MAX_VALUE_LENGTH
from twisted.python.failure import Failure
from twisted.python.reflect import qual
from twisted.trial._dist import managercommands
from twisted.trial.reporter import TestResult
from ..reporter import TrialFailure
from .stream import chunk, stream

T = TypeVar("T")


async def addError(
    amp: AMP, testName: str, errorClass: str, error: str, frames: List[str]
) -> None:
    """
    Send an error to the worker manager over an AMP connection.

    First the pieces which can be large are streamed over the connection.
    Then, L{managercommands.AddError} is called with the rest of the
    information and the stream IDs.

    :param amp: The connection to use.
    :param testName: The name (or ID) of the test the error relates to.
    :param errorClass: The fully qualified name of the error type.
    :param error: The string representation of the error.
    :param frames: The lines of the traceback associated with the error.
    """

    errorStreamId = await stream(amp, chunk(error.encode("utf-8"), MAX_VALUE_LENGTH))
    framesStreamId = await stream(amp, (frame.encode("utf-8") for frame in frames))

    await amp.callRemote(
        managercommands.AddError,
        testName=testName,
        errorClass=errorClass,
        errorStreamId=errorStreamId,
        framesStreamId=framesStreamId,
    )


async def addFailure(
    amp: AMP, testName: str, fail: str, failClass: str, frames: List[str]
) -> None:
    """
    Like L{addError} but for failures.

    :param amp: See L{addError}
    :param testName: See L{addError}
    :param failClass: The fully qualified name of the exception associated
        with the failure.
    :param fail: The string representation of the failure.
    :param frames: The lines of the traceback associated with the error.
    """
    failStreamId = await stream(amp, chunk(fail.encode("utf-8"), MAX_VALUE_LENGTH))
    framesStreamId = await stream(amp, (frame.encode("utf-8") for frame in frames))

    await amp.callRemote(
        managercommands.AddFailure,
        testName=testName,
        failClass=failClass,
        failStreamId=failStreamId,
        framesStreamId=framesStreamId,
    )


async def addExpectedFailure(amp: AMP, testName: str, error: str, todo: str) -> None:
    """
    Like L{addError} but for expected failures.

    :param amp: See L{addError}
    :param testName: See L{addError}
    :param error: The string representation of the expected failure.
    :param todo: The string description of the expectation.
    """
    errorStreamId = await stream(amp, chunk(error.encode("utf-8"), MAX_VALUE_LENGTH))

    await amp.callRemote(
        managercommands.AddExpectedFailure,
        testName=testName,
        errorStreamId=errorStreamId,
        todo=todo,
    )


@define
class ReportingResults:
    """
    A mutable container for the result of sending test results back to the
    parent process.

    Since it is possible for these sends to fail asynchronously but the
    L{TestResult} protocol is not well suited for asynchronous result
    reporting, results are collected on an instance of this class and when the
    runner believes the test is otherwise complete, it can collect the results
    and do something with any errors.

    :ivar _reporter: The L{WorkerReporter} this object is associated with.
        This is the object doing the result reporting.

    :ivar _results: A list of L{Deferred} instances representing the results
        of reporting operations.  This is expected to grow over the course of
        the test run and then be inspected by the runner once the test is
        over.  The public interface to this list is via the context manager
        interface.
    """

    _reporter: "WorkerReporter"
    _results: List[Deferred[object]] = Factory(list)

    def __enter__(self) -> Sequence[Deferred[object]]:
        """
        Begin a new reportable context in which results can be collected.

        :return: A sequence which will contain the L{Deferred} instances
            representing the results of all test result reporting that happens
            while the context manager is active.  The sequence is extended as
            the test runs so its value should not be consumed until the test
            is over.
        """
        return self._results

    def __exit__(
        self,
        excType: Type[BaseException],
        excValue: BaseException,
        excTraceback: TracebackType,
    ) -> Literal[False]:
        """
        End the reportable context.
        """
        self._reporter._reporting = None
        return False

    def record(self, result: Deferred[object]) -> None:
        """
        Record a L{Deferred} instance representing one test result reporting
        operation.
        """
        self._results.append(result)


class WorkerReporter(TestResult):
    """
    Reporter for trial's distributed workers. We send things not through a
    stream, but through an C{AMP} protocol's C{callRemote} method.

    @ivar _DEFAULT_TODO: Default message for expected failures and
        unexpected successes, used only if a C{Todo} is not provided.

    @ivar _reporting: When a "result reporting" context is active, the
        corresponding context manager.  Otherwise, L{None}.
    """

    _DEFAULT_TODO = "Test expected to fail"

    ampProtocol: AMP
    _reporting: Optional[ReportingResults] = None

    def __init__(self, ampProtocol):
        """
        @param ampProtocol: The communication channel with the trial
            distributed manager which collects all test results.
        """
        super().__init__()
        self.ampProtocol = ampProtocol

    def gatherReportingResults(self) -> ReportingResults:
        """
        Get a "result reporting" context manager.

        In a "result reporting" context, asynchronous test result reporting
        methods may be used safely.  Their results (in particular, failures)
        are available from the context manager.
        """
        self._reporting = ReportingResults(self)
        return self._reporting

    def _getFailure(self, error: TrialFailure) -> Failure:
        """
        Convert a C{sys.exc_info()}-style tuple to a L{Failure}, if necessary.
        """
        if isinstance(error, tuple):
            return Failure(error[1], error[0], error[2])
        return error

    def _getFrames(self, failure: Failure) -> List[str]:
        """
        Extract frames from a C{Failure} instance.
        """
        frames: List[str] = []
        for frame in failure.frames:
            # The code object's name, the code object's filename, and the line
            # number.
            frames.extend([frame[0], frame[1], str(frame[2])])
        return frames

    def _call(self, f: Callable[[], T]) -> None:
        """
        Call L{f} if and only if a "result reporting" context is active.

        @param f: A function to call.  Its result is accumulated into the
            result reporting context.  It may return a L{Deferred} or a
            coroutine or synchronously raise an exception or return a result
            value.

        @raise ValueError: If no result reporting context is active.
        """
        if self._reporting is not None:
            self._reporting.record(maybeDeferred(f))
        else:
            raise ValueError(
                "Cannot call command outside of reporting context manager."
            )

    def addSuccess(self, test: PyUnitTestCase) -> None:
        """
        Send a success to the parent process.

        This must be called in context managed by L{gatherReportingResults}.
        """
        super().addSuccess(test)
        testName = test.id()
        self._call(
            lambda: self.ampProtocol.callRemote(  # type: ignore[no-any-return]
                managercommands.AddSuccess, testName=testName
            )
        )

    async def addErrorFallible(self, testName: str, errorObj: TrialFailure) -> None:
        """
        Attempt to report an error to the parent process.

        Unlike L{addError} this can fail asynchronously.  This version is for
        infrastructure code that can apply its own failure handling.

        @return: A L{Deferred} that fires with the result of the attempt.
        """
        failure = self._getFailure(errorObj)
        errorStr = failure.getErrorMessage()
        errorClass = qual(failure.type)
        frames = self._getFrames(failure)
        await addError(
            self.ampProtocol,
            testName,
            errorClass,
            errorStr,
            frames,
        )

    def addError(self, test: PyUnitTestCase, error: TrialFailure) -> None:
        """
        Send an error to the parent process.
        """
        super().addError(test, error)
        testName = test.id()
        self._call(lambda: self.addErrorFallible(testName, error))

    def addFailure(self, test: PyUnitTestCase, fail: TrialFailure) -> None:
        """
        Send a Failure over.
        """
        super().addFailure(test, fail)
        testName = test.id()
        failure = self._getFailure(fail)
        failureMessage = failure.getErrorMessage()
        failClass = qual(failure.type)
        frames = self._getFrames(failure)
        self._call(
            lambda: addFailure(
                self.ampProtocol,
                testName,
                failureMessage,
                failClass,
                frames,
            ),
        )

    def addSkip(self, test, reason):
        """
        Send a skip over.
        """
        super().addSkip(test, reason)
        reason = str(reason)
        testName = test.id()
        self._call(
            lambda: self.ampProtocol.callRemote(
                managercommands.AddSkip, testName=testName, reason=reason
            )
        )

    def _getTodoReason(self, todo):
        """
        Get the reason for a C{Todo}.

        If C{todo} is L{None}, return a sensible default.
        """
        if todo is None:
            return self._DEFAULT_TODO
        else:
            return todo.reason

    def addExpectedFailure(self, test, error, todo=None):
        """
        Send an expected failure over.
        """
        super().addExpectedFailure(test, error, todo)
        errorMessage = error.getErrorMessage()
        testName = test.id()
        self._call(
            lambda: addExpectedFailure(
                self.ampProtocol,
                testName=testName,
                error=errorMessage,
                todo=self._getTodoReason(todo),
            )
        )

    def addUnexpectedSuccess(self, test, todo=None):
        """
        Send an unexpected success over.
        """
        super().addUnexpectedSuccess(test, todo)
        testName = test.id()
        self._call(
            lambda: self.ampProtocol.callRemote(
                managercommands.AddUnexpectedSuccess,
                testName=testName,
                todo=self._getTodoReason(todo),
            )
        )

    def printSummary(self):
        """
        I{Don't} print a summary
        """
