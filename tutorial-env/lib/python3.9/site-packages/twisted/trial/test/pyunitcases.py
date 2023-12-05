# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Sample test cases defined using the standard library L{unittest.TestCase}
class which are used as data by test cases which are actually part of the
trial test suite to verify handling of handling of such cases.
"""

import unittest
from sys import exc_info

from twisted.python.failure import Failure


class PyUnitTest(unittest.TestCase):
    def test_pass(self):
        """
        A passing test.
        """

    def test_error(self):
        """
        A test which raises an exception to cause an error.
        """
        raise Exception("pyunit error")

    def test_fail(self):
        """
        A test which uses L{unittest.TestCase.fail} to cause a failure.
        """
        self.fail("pyunit failure")

    @unittest.skip("pyunit skip")
    def test_skip(self):
        """
        A test which uses the L{unittest.skip} decorator to cause a skip.
        """


class _NonStringId:
    """
    A class that looks a little like a TestCase, but not enough so to
    actually be used as one.  This helps L{BrokenRunInfrastructure} use some
    interfaces incorrectly to provoke certain failure conditions.
    """

    def id(self) -> object:
        return object()


class BrokenRunInfrastructure(unittest.TestCase):
    """
    A test suite that is broken at the level of integration between
    L{TestCase.run} and the results object.
    """

    def run(self, result):
        """
        Override the normal C{run} behavior to pass the result object
        along to the test method.  Each test method needs the result object so
        that it can implement its particular kind of brokenness.
        """
        return getattr(self, self._testMethodName)(result)

    def test_addSuccess(self, result):
        """
        Violate the L{TestResult.addSuccess} interface.
        """

        result.addSuccess(_NonStringId())

    def test_addError(self, result):
        """
        Violate the L{TestResult.addError} interface.
        """
        try:
            raise Exception("test_addError")
        except BaseException:
            err = exc_info()

        result.addError(_NonStringId(), err)

    def test_addFailure(self, result):
        """
        Violate the L{TestResult.addFailure} interface.
        """
        try:
            raise Exception("test_addFailure")
        except BaseException:
            err = exc_info()

        result.addFailure(_NonStringId(), err)

    def test_addSkip(self, result):
        """
        Violate the L{TestResult.addSkip} interface.
        """
        result.addSkip(_NonStringId(), "test_addSkip")

    def test_addExpectedFailure(self, result):
        """
        Violate the L{TestResult.addExpectedFailure} interface.
        """
        try:
            raise Exception("test_addExpectedFailure")
        except BaseException:
            err = Failure()
        result.addExpectedFailure(_NonStringId(), err)

    def test_addUnexpectedSuccess(self, result):
        """
        Violate the L{TestResult.addUnexpectedSuccess} interface.
        """
        result.addUnexpectedSuccess(_NonStringId())
