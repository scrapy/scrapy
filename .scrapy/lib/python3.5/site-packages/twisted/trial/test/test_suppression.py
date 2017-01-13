# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for warning suppression features of Trial.
"""

from __future__ import division, absolute_import

import unittest as pyunit

from twisted.python.reflect import namedAny
from twisted.trial import unittest
from twisted.trial.test import suppression


class SuppressionMixin(object):
    """
    Tests for the warning suppression features of
    L{twisted.trial.unittest.SynchronousTestCase}.
    """
    def runTests(self, suite):
        suite.run(pyunit.TestResult())


    def _load(self, cls, methodName):
        """
        Return a new L{unittest.TestSuite} with a single test method in it.

        @param cls: A L{TestCase} subclass defining a test method.

        @param methodName: The name of the test method from C{cls}.
        """
        return pyunit.TestSuite([cls(methodName)])


    def _assertWarnings(self, warnings, which):
        """
        Assert that a certain number of warnings with certain messages were
        emitted in a certain order.

        @param warnings: A list of emitted warnings, as returned by
            C{flushWarnings}.

        @param which: A list of strings giving warning messages that should
            appear in C{warnings}.

        @raise self.failureException: If the warning messages given by C{which}
            do not match the messages in the warning information in C{warnings},
            or if they do not appear in the same order.
        """
        self.assertEqual(
            [warning['message'] for warning in warnings],
            which)


    def test_setUpSuppression(self):
        """
        Suppressions defined by the test method being run are applied to any
        warnings emitted while running the C{setUp} fixture.
        """
        self.runTests(
            self._load(self.TestSetUpSuppression, "testSuppressMethod"))
        warningsShown = self.flushWarnings([
                self.TestSetUpSuppression._emit])
        self._assertWarnings(
            warningsShown,
            [suppression.CLASS_WARNING_MSG, suppression.MODULE_WARNING_MSG,
             suppression.CLASS_WARNING_MSG, suppression.MODULE_WARNING_MSG])


    def test_tearDownSuppression(self):
        """
        Suppressions defined by the test method being run are applied to any
        warnings emitted while running the C{tearDown} fixture.
        """
        self.runTests(
            self._load(self.TestTearDownSuppression, "testSuppressMethod"))
        warningsShown = self.flushWarnings([
                self.TestTearDownSuppression._emit])
        self._assertWarnings(
            warningsShown,
            [suppression.CLASS_WARNING_MSG, suppression.MODULE_WARNING_MSG,
             suppression.CLASS_WARNING_MSG, suppression.MODULE_WARNING_MSG])


    def test_suppressMethod(self):
        """
        A suppression set on a test method prevents warnings emitted by that
        test method which the suppression matches from being emitted.
        """
        self.runTests(
            self._load(self.TestSuppression, "testSuppressMethod"))
        warningsShown = self.flushWarnings([
                self.TestSuppression._emit])
        self._assertWarnings(
            warningsShown,
            [suppression.CLASS_WARNING_MSG, suppression.MODULE_WARNING_MSG])


    def test_suppressClass(self):
        """
        A suppression set on a L{SynchronousTestCase} subclass prevents warnings
        emitted by any test methods defined on that class which match the
        suppression from being emitted.
        """
        self.runTests(
            self._load(self.TestSuppression, "testSuppressClass"))
        warningsShown = self.flushWarnings([
                self.TestSuppression._emit])
        self.assertEqual(
            warningsShown[0]['message'], suppression.METHOD_WARNING_MSG)
        self.assertEqual(
            warningsShown[1]['message'], suppression.MODULE_WARNING_MSG)
        self.assertEqual(len(warningsShown), 2)


    def test_suppressModule(self):
        """
        A suppression set on a module prevents warnings emitted by any test
        mewthods defined in that module which match the suppression from being
        emitted.
        """
        self.runTests(
            self._load(self.TestSuppression2, "testSuppressModule"))
        warningsShown = self.flushWarnings([
                self.TestSuppression._emit])
        self.assertEqual(
            warningsShown[0]['message'], suppression.METHOD_WARNING_MSG)
        self.assertEqual(
            warningsShown[1]['message'], suppression.CLASS_WARNING_MSG)
        self.assertEqual(len(warningsShown), 2)


    def test_overrideSuppressClass(self):
        """
        The suppression set on a test method completely overrides a suppression
        with wider scope; if it does not match a warning emitted by that test
        method, the warning is emitted, even if a wider suppression matches.
        """
        self.runTests(
            self._load(self.TestSuppression, "testOverrideSuppressClass"))
        warningsShown = self.flushWarnings([
                self.TestSuppression._emit])
        self.assertEqual(
            warningsShown[0]['message'], suppression.METHOD_WARNING_MSG)
        self.assertEqual(
            warningsShown[1]['message'], suppression.CLASS_WARNING_MSG)
        self.assertEqual(
            warningsShown[2]['message'], suppression.MODULE_WARNING_MSG)
        self.assertEqual(len(warningsShown), 3)



class SynchronousSuppressionTests(SuppressionMixin, unittest.SynchronousTestCase):
    """
    @see: L{twisted.trial.test.test_tests}
    """
    TestSetUpSuppression = namedAny(
        'twisted.trial.test.suppression.SynchronousTestSetUpSuppression')
    TestTearDownSuppression = namedAny(
        'twisted.trial.test.suppression.SynchronousTestTearDownSuppression')
    TestSuppression = namedAny(
        'twisted.trial.test.suppression.SynchronousTestSuppression')
    TestSuppression2 = namedAny(
        'twisted.trial.test.suppression.SynchronousTestSuppression2')
