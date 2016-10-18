# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for interrupting tests with Control-C.
"""

from __future__ import absolute_import, division

from twisted.python.compat import NativeStringIO

from twisted.trial import unittest
from twisted.trial import reporter, runner


class TrialTest(unittest.SynchronousTestCase):
    def setUp(self):
        self.output = NativeStringIO()
        self.reporter = reporter.TestResult()
        self.loader = runner.TestLoader()


class InterruptInTestTests(TrialTest):
    class InterruptedTest(unittest.TestCase):
        def test_02_raiseInterrupt(self):
            raise KeyboardInterrupt

        def test_01_doNothing(self):
            pass

        def test_03_doNothing(self):
            InterruptInTestTests.test_03_doNothing_run = True

    def setUp(self):
        super(InterruptInTestTests, self).setUp()
        self.suite = self.loader.loadClass(InterruptInTestTests.InterruptedTest)
        InterruptInTestTests.test_03_doNothing_run = None

    def test_setUpOK(self):
        self.assertEqual(3, self.suite.countTestCases())
        self.assertEqual(0, self.reporter.testsRun)
        self.assertFalse(self.reporter.shouldStop)

    def test_interruptInTest(self):
        runner.TrialSuite([self.suite]).run(self.reporter)
        self.assertTrue(self.reporter.shouldStop)
        self.assertEqual(2, self.reporter.testsRun)
        self.assertFalse(InterruptInTestTests.test_03_doNothing_run,
                    "test_03_doNothing ran.")


class InterruptInSetUpTests(TrialTest):
    testsRun = 0

    class InterruptedTest(unittest.TestCase):
        def setUp(self):
            if InterruptInSetUpTests.testsRun > 0:
                raise KeyboardInterrupt

        def test_01(self):
            InterruptInSetUpTests.testsRun += 1

        def test_02(self):
            InterruptInSetUpTests.testsRun += 1
            InterruptInSetUpTests.test_02_run = True

    def setUp(self):
        super(InterruptInSetUpTests, self).setUp()
        self.suite = self.loader.loadClass(
            InterruptInSetUpTests.InterruptedTest)
        InterruptInSetUpTests.test_02_run = False
        InterruptInSetUpTests.testsRun = 0

    def test_setUpOK(self):
        self.assertEqual(0, InterruptInSetUpTests.testsRun)
        self.assertEqual(2, self.suite.countTestCases())
        self.assertEqual(0, self.reporter.testsRun)
        self.assertFalse(self.reporter.shouldStop)

    def test_interruptInSetUp(self):
        runner.TrialSuite([self.suite]).run(self.reporter)
        self.assertTrue(self.reporter.shouldStop)
        self.assertEqual(2, self.reporter.testsRun)
        self.assertFalse(InterruptInSetUpTests.test_02_run,
                    "test_02 ran")


class InterruptInTearDownTests(TrialTest):
    testsRun = 0

    class InterruptedTest(unittest.TestCase):
        def tearDown(self):
            if InterruptInTearDownTests.testsRun > 0:
                raise KeyboardInterrupt

        def test_01(self):
            InterruptInTearDownTests.testsRun += 1

        def test_02(self):
            InterruptInTearDownTests.testsRun += 1
            InterruptInTearDownTests.test_02_run = True

    def setUp(self):
        super(InterruptInTearDownTests, self).setUp()
        self.suite = self.loader.loadClass(
            InterruptInTearDownTests.InterruptedTest)
        InterruptInTearDownTests.testsRun = 0
        InterruptInTearDownTests.test_02_run = False

    def test_setUpOK(self):
        self.assertEqual(0, InterruptInTearDownTests.testsRun)
        self.assertEqual(2, self.suite.countTestCases())
        self.assertEqual(0, self.reporter.testsRun)
        self.assertFalse(self.reporter.shouldStop)

    def test_interruptInTearDown(self):
        runner.TrialSuite([self.suite]).run(self.reporter)
        self.assertEqual(1, self.reporter.testsRun)
        self.assertTrue(self.reporter.shouldStop)
        self.assertFalse(InterruptInTearDownTests.test_02_run,
                    "test_02 ran")
