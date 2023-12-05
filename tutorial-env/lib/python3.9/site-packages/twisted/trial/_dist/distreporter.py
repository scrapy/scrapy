# -*- test-case-name: twisted.trial._dist.test.test_distreporter -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
The reporter is not made to support concurrent test running, so we will
hold test results in here and only send them to the reporter once the
test is over.

@since: 12.3
"""

from types import TracebackType
from typing import Optional, Tuple, Union

from zope.interface import implementer

from twisted.python.components import proxyForInterface
from twisted.python.failure import Failure
from ..itrial import IReporter, ITestCase

ReporterFailure = Union[Failure, Tuple[type, Exception, TracebackType]]


@implementer(IReporter)
class DistReporter(proxyForInterface(IReporter)):  # type: ignore[misc]
    """
    See module docstring.
    """

    def __init__(self, original):
        super().__init__(original)
        self.running = {}

    def startTest(self, test):
        """
        Queue test starting.
        """
        self.running[test.id()] = []
        self.running[test.id()].append((self.original.startTest, test))

    def addFailure(self, test: ITestCase, fail: ReporterFailure) -> None:
        """
        Queue adding a failure.
        """
        self.running[test.id()].append((self.original.addFailure, test, fail))

    def addError(self, test: ITestCase, error: ReporterFailure) -> None:
        """
        Queue error adding.
        """
        self.running[test.id()].append((self.original.addError, test, error))

    def addSkip(self, test, reason):
        """
        Queue adding a skip.
        """
        self.running[test.id()].append((self.original.addSkip, test, reason))

    def addUnexpectedSuccess(self, test, todo=None):
        """
        Queue adding an unexpected success.
        """
        self.running[test.id()].append((self.original.addUnexpectedSuccess, test, todo))

    def addExpectedFailure(
        self, test: ITestCase, error: ReporterFailure, todo: Optional[str] = None
    ) -> None:
        """
        Queue adding an expected failure.
        """
        self.running[test.id()].append(
            (self.original.addExpectedFailure, test, error, todo)
        )

    def addSuccess(self, test):
        """
        Queue adding a success.
        """
        self.running[test.id()].append((self.original.addSuccess, test))

    def stopTest(self, test):
        """
        Queue stopping the test, then unroll the queue.
        """
        self.running[test.id()].append((self.original.stopTest, test))
        for step in self.running[test.id()]:
            step[0](*step[1:])
        del self.running[test.id()]
