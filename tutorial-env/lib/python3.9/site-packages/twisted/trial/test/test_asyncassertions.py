# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for async assertions provided by C{twisted.trial.unittest.TestCase}.
"""


import unittest as pyunit

from twisted.internet import defer
from twisted.python import failure
from twisted.trial import unittest


class AsynchronousAssertionsTests(unittest.TestCase):
    """
    Tests for L{TestCase}'s asynchronous extensions to L{SynchronousTestCase}.
    That is, assertFailure.
    """

    def test_assertFailure(self):
        d = defer.maybeDeferred(lambda: 1 / 0)
        return self.assertFailure(d, ZeroDivisionError)

    def test_assertFailure_wrongException(self):
        d = defer.maybeDeferred(lambda: 1 / 0)
        self.assertFailure(d, OverflowError)
        d.addCallbacks(
            lambda x: self.fail("Should have failed"),
            lambda x: x.trap(self.failureException),
        )
        return d

    def test_assertFailure_noException(self):
        d = defer.succeed(None)
        self.assertFailure(d, ZeroDivisionError)
        d.addCallbacks(
            lambda x: self.fail("Should have failed"),
            lambda x: x.trap(self.failureException),
        )
        return d

    def test_assertFailure_moreInfo(self):
        """
        In the case of assertFailure failing, check that we get lots of
        information about the exception that was raised.
        """
        try:
            1 / 0
        except ZeroDivisionError:
            f = failure.Failure()
            d = defer.fail(f)
        d = self.assertFailure(d, RuntimeError)
        d.addErrback(self._checkInfo, f)
        return d

    def _checkInfo(self, assertionFailure, f):
        assert assertionFailure.check(self.failureException)
        output = assertionFailure.getErrorMessage()
        self.assertIn(f.getErrorMessage(), output)
        self.assertIn(f.getBriefTraceback(), output)

    def test_assertFailure_masked(self):
        """
        A single wrong assertFailure should fail the whole test.
        """

        class ExampleFailure(Exception):
            pass

        class TC(unittest.TestCase):
            failureException = ExampleFailure

            def test_assertFailure(self):
                d = defer.maybeDeferred(lambda: 1 / 0)
                self.assertFailure(d, OverflowError)
                self.assertFailure(d, ZeroDivisionError)
                return d

        test = TC("test_assertFailure")
        result = pyunit.TestResult()
        test.run(result)
        self.assertEqual(1, len(result.failures))
