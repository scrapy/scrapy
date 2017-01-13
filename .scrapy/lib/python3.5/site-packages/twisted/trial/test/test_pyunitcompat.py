# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from __future__ import division, absolute_import

import sys
import traceback

from zope.interface import implementer

from twisted.python.failure import Failure
from twisted.trial.unittest import SynchronousTestCase, PyUnitResultAdapter
from twisted.trial.itrial import IReporter, ITestCase

import unittest as pyunit


class PyUnitTestTests(SynchronousTestCase):

    class PyUnitTest(pyunit.TestCase):

        def test_pass(self):
            pass


    def setUp(self):
        self.original = self.PyUnitTest('test_pass')
        self.test = ITestCase(self.original)


    def test_callable(self):
        """
        Tests must be callable in order to be used with Python's unittest.py.
        """
        self.assertTrue(callable(self.test),
                        "%r is not callable." % (self.test,))



class PyUnitResultTests(SynchronousTestCase):
    """
    Tests to show that PyUnitResultAdapter wraps TestResult objects from the
    standard library 'unittest' module in such a way as to make them usable and
    useful from Trial.
    """

    # Once erroneous is ported to Python 3 this can be replaced with
    # erroneous.ErrorTest:
    class ErrorTest(SynchronousTestCase):
        """
        A test case which has a L{test_foo} which will raise an error.

        @ivar ran: boolean indicating whether L{test_foo} has been run.
        """
        ran = False

        def test_foo(self):
            """
            Set C{self.ran} to True and raise a C{ZeroDivisionError}
            """
            self.ran = True
            1/0


    def test_dontUseAdapterWhenReporterProvidesIReporter(self):
        """
        The L{PyUnitResultAdapter} is only used when the result passed to
        C{run} does *not* provide L{IReporter}.
        """
        @implementer(IReporter)
        class StubReporter(object):
            """
            A reporter which records data about calls made to it.

            @ivar errors: Errors passed to L{addError}.
            @ivar failures: Failures passed to L{addFailure}.
            """

            def __init__(self):
                self.errors = []
                self.failures = []

            def startTest(self, test):
                """
                Do nothing.
                """

            def stopTest(self, test):
                """
                Do nothing.
                """

            def addError(self, test, error):
                """
                Record the error.
                """
                self.errors.append(error)

        test = self.ErrorTest("test_foo")
        result = StubReporter()
        test.run(result)
        self.assertIsInstance(result.errors[0], Failure)


    def test_success(self):
        class SuccessTest(SynchronousTestCase):
            ran = False
            def test_foo(s):
                s.ran = True
        test = SuccessTest('test_foo')
        result = pyunit.TestResult()
        test.run(result)

        self.assertTrue(test.ran)
        self.assertEqual(1, result.testsRun)
        self.assertTrue(result.wasSuccessful())

    def test_failure(self):
        class FailureTest(SynchronousTestCase):
            ran = False
            def test_foo(s):
                s.ran = True
                s.fail('boom!')
        test = FailureTest('test_foo')
        result = pyunit.TestResult()
        test.run(result)

        self.assertTrue(test.ran)
        self.assertEqual(1, result.testsRun)
        self.assertEqual(1, len(result.failures))
        self.assertFalse(result.wasSuccessful())

    def test_error(self):
        test = self.ErrorTest('test_foo')
        result = pyunit.TestResult()
        test.run(result)

        self.assertTrue(test.ran)
        self.assertEqual(1, result.testsRun)
        self.assertEqual(1, len(result.errors))
        self.assertFalse(result.wasSuccessful())

    def test_setUpError(self):
        class ErrorTest(SynchronousTestCase):
            ran = False
            def setUp(self):
                1/0
            def test_foo(s):
                s.ran = True
        test = ErrorTest('test_foo')
        result = pyunit.TestResult()
        test.run(result)

        self.assertFalse(test.ran)
        self.assertEqual(1, result.testsRun)
        self.assertEqual(1, len(result.errors))
        self.assertFalse(result.wasSuccessful())

    def test_tracebackFromFailure(self):
        """
        Errors added through the L{PyUnitResultAdapter} have the same traceback
        information as if there were no adapter at all.
        """
        try:
            1/0
        except ZeroDivisionError:
            exc_info = sys.exc_info()
            f = Failure()
        pyresult = pyunit.TestResult()
        result = PyUnitResultAdapter(pyresult)
        result.addError(self, f)
        self.assertEqual(pyresult.errors[0][1],
                         ''.join(traceback.format_exception(*exc_info)))


    def test_traceback(self):
        """
        As test_tracebackFromFailure, but covering more code.
        """
        class ErrorTest(SynchronousTestCase):
            exc_info = None
            def test_foo(self):
                try:
                    1/0
                except ZeroDivisionError:
                    self.exc_info = sys.exc_info()
                    raise
        test = ErrorTest('test_foo')
        result = pyunit.TestResult()
        test.run(result)

        # We can't test that the tracebacks are equal, because Trial's
        # machinery inserts a few extra frames on the top and we don't really
        # want to trim them off without an extremely good reason.
        #
        # So, we just test that the result's stack ends with the
        # exception's stack.

        expected_stack = ''.join(traceback.format_tb(test.exc_info[2]))
        observed_stack = '\n'.join(result.errors[0][1].splitlines()[:-1])

        self.assertEqual(expected_stack.strip(),
                         observed_stack[-len(expected_stack):].strip())


    def test_tracebackFromCleanFailure(self):
        """
        Errors added through the L{PyUnitResultAdapter} have the same
        traceback information as if there were no adapter at all, even
        if the Failure that held the information has been cleaned.
        """
        try:
            1/0
        except ZeroDivisionError:
            exc_info = sys.exc_info()
            f = Failure()
        f.cleanFailure()
        pyresult = pyunit.TestResult()
        result = PyUnitResultAdapter(pyresult)
        result.addError(self, f)
        self.assertEqual(pyresult.errors[0][1],
                         ''.join(traceback.format_exception(*exc_info)))


    def test_trialSkip(self):
        """
        Skips using trial's skipping functionality are reported as skips in
        the L{pyunit.TestResult}.
        """
        class SkipTest(SynchronousTestCase):
            def test_skip(self):
                1/0
            test_skip.skip = "Let's skip!"

        test = SkipTest('test_skip')
        result = pyunit.TestResult()
        test.run(result)
        self.assertEqual(result.skipped, [(test, "Let's skip!")])


    def test_pyunitSkip(self):
        """
        Skips using pyunit's skipping functionality are reported as skips in
        the L{pyunit.TestResult}.
        """
        class SkipTest(SynchronousTestCase):
            @pyunit.skip("skippy")
            def test_skip(self):
                1/0

        test = SkipTest('test_skip')
        result = pyunit.TestResult()
        test.run(result)
        self.assertEqual(result.skipped, [(test, "skippy")])
