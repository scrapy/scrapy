# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
#
# Maintainer: Jonathan Lange
# Author: Robert Collins

from __future__ import absolute_import, division

import os
import pdb
import sys

from zope.interface import implementer
from zope.interface.verify import verifyObject

from twisted.trial.itrial import IReporter, ITestCase
from twisted.trial import unittest, runner, reporter, util
from twisted.trial._asyncrunner import _ForceGarbageCollectionDecorator
from twisted.python import failure, log, reflect
from twisted.python.filepath import FilePath
from twisted.python.reflect import namedAny
from twisted.python.compat import NativeStringIO
from twisted.scripts import trial
from twisted.plugins import twisted_trial
from twisted import plugin
from twisted.internet import defer


pyunit = __import__('unittest')


class CapturingDebugger(object):

    def __init__(self):
        self._calls = []

    def runcall(self, *args, **kwargs):
        self._calls.append('runcall')
        args[0](*args[1:], **kwargs)



@implementer(IReporter)
class CapturingReporter(object):
    """
    Reporter that keeps a log of all actions performed on it.
    """

    stream = None
    tbformat = None
    args = None
    separator = None
    testsRun = None

    def __init__(self, stream=None, tbformat=None, rterrors=None,
                 publisher=None):
        """
        Create a capturing reporter.
        """
        self._calls = []
        self.shouldStop = False
        self._stream = stream
        self._tbformat = tbformat
        self._rterrors = rterrors
        self._publisher = publisher


    def startTest(self, method):
        """
        Report the beginning of a run of a single test method
        @param method: an object that is adaptable to ITestMethod
        """
        self._calls.append('startTest')


    def stopTest(self, method):
        """
        Report the status of a single test method
        @param method: an object that is adaptable to ITestMethod
        """
        self._calls.append('stopTest')


    def cleanupErrors(self, errs):
        """called when the reactor has been left in a 'dirty' state
        @param errs: a list of L{twisted.python.failure.Failure}s
        """
        self._calls.append('cleanupError')


    def addSuccess(self, test):
        self._calls.append('addSuccess')


    def done(self):
        """
        Do nothing. These tests don't care about done.
        """



class TrialRunnerTestsMixin:
    """
    Mixin defining tests for L{runner.TrialRunner}.
    """
    def tearDown(self):
        self.runner._tearDownLogFile()


    def test_empty(self):
        """
        Empty test method, used by the other tests.
        """


    def _getObservers(self):
        return log.theLogPublisher.observers


    def test_addObservers(self):
        """
        Any log system observers L{TrialRunner.run} adds are removed by the
        time it returns.
        """
        originalCount = len(self._getObservers())
        self.runner.run(self.test)
        newCount = len(self._getObservers())
        self.assertEqual(newCount, originalCount)


    def test_logFileAlwaysActive(self):
        """
        Test that a new file is opened on each run.
        """
        oldSetUpLogFile = self.runner._setUpLogFile
        l = []
        def setUpLogFile():
            oldSetUpLogFile()
            l.append(self.runner._logFileObserver)
        self.runner._setUpLogFile = setUpLogFile
        self.runner.run(self.test)
        self.runner.run(self.test)
        self.assertEqual(len(l), 2)
        self.assertFalse(l[0] is l[1], "Should have created a new file observer")


    def test_logFileGetsClosed(self):
        """
        Test that file created is closed during the run.
        """
        oldSetUpLogFile = self.runner._setUpLogFile
        l = []
        def setUpLogFile():
            oldSetUpLogFile()
            l.append(self.runner._logFileObject)
        self.runner._setUpLogFile = setUpLogFile
        self.runner.run(self.test)
        self.assertEqual(len(l), 1)
        self.assertTrue(l[0].closed)



class TrialRunnerTests(TrialRunnerTestsMixin, unittest.SynchronousTestCase):
    """
    Tests for L{runner.TrialRunner} with the feature to turn unclean errors
    into warnings disabled.
    """
    def setUp(self):
        self.stream = NativeStringIO()
        self.runner = runner.TrialRunner(CapturingReporter, stream=self.stream)
        self.test = TrialRunnerTests('test_empty')


    def test_publisher(self):
        """
        The reporter constructed by L{runner.TrialRunner} is passed
        L{twisted.python.log} as the value for the C{publisher} parameter.
        """
        result = self.runner._makeResult()
        self.assertIdentical(result._publisher, log)



class TrialRunnerWithUncleanWarningsReporterTests(TrialRunnerTestsMixin,
                                                  unittest.SynchronousTestCase):
    """
    Tests for the TrialRunner's interaction with an unclean-error suppressing
    reporter.
    """

    def setUp(self):
        self.stream = NativeStringIO()
        self.runner = runner.TrialRunner(CapturingReporter, stream=self.stream,
                                         uncleanWarnings=True)
        self.test = TrialRunnerTests('test_empty')



class DryRunMixin(object):
    """
    Mixin for testing that 'dry run' mode works with various
    L{pyunit.TestCase} subclasses.
    """

    def setUp(self):
        self.log = []
        self.stream = NativeStringIO()
        self.runner = runner.TrialRunner(CapturingReporter,
                                         runner.TrialRunner.DRY_RUN,
                                         stream=self.stream)
        self.makeTestFixtures()


    def makeTestFixtures(self):
        """
        Set C{self.test} and C{self.suite}, where C{self.suite} is an empty
        TestSuite.
        """


    def test_empty(self):
        """
        If there are no tests, the reporter should not receive any events to
        report.
        """
        result = self.runner.run(runner.TestSuite())
        self.assertEqual(result._calls, [])


    def test_singleCaseReporting(self):
        """
        If we are running a single test, check the reporter starts, passes and
        then stops the test during a dry run.
        """
        result = self.runner.run(self.test)
        self.assertEqual(result._calls, ['startTest', 'addSuccess', 'stopTest'])


    def test_testsNotRun(self):
        """
        When we are doing a dry run, the tests should not actually be run.
        """
        self.runner.run(self.test)
        self.assertEqual(self.log, [])



class SynchronousDryRunTests(DryRunMixin, unittest.SynchronousTestCase):
    """
    Check that 'dry run' mode works well with trial's L{SynchronousTestCase}.
    """
    def makeTestFixtures(self):
        class PyunitCase(unittest.SynchronousTestCase):
            def test_foo(self):
                pass
        self.test = PyunitCase('test_foo')
        self.suite = pyunit.TestSuite()



class DryRunTests(DryRunMixin, unittest.SynchronousTestCase):
    """
    Check that 'dry run' mode works well with Trial tests.
    """
    def makeTestFixtures(self):
        class MockTest(unittest.TestCase):
            def test_foo(test):
                self.log.append('test_foo')
        self.test = MockTest('test_foo')
        self.suite = runner.TestSuite()



class PyUnitDryRunTests(DryRunMixin, unittest.SynchronousTestCase):
    """
    Check that 'dry run' mode works well with stdlib unittest tests.
    """
    def makeTestFixtures(self):
        class PyunitCase(pyunit.TestCase):
            def test_foo(self):
                pass
        self.test = PyunitCase('test_foo')
        self.suite = pyunit.TestSuite()



class RunnerTests(unittest.SynchronousTestCase):
    def setUp(self):
        self.config = trial.Options()
        # whitebox hack a reporter in, because plugins are CACHED and will
        # only reload if the FILE gets changed.

        parts = reflect.qual(CapturingReporter).split('.')
        package = '.'.join(parts[:-1])
        klass = parts[-1]
        plugins = [twisted_trial._Reporter(
            "Test Helper Reporter",
            package,
            description="Utility for unit testing.",
            longOpt="capturing",
            shortOpt=None,
            klass=klass)]


        # XXX There should really be a general way to hook the plugin system
        # for tests.
        def getPlugins(iface, *a, **kw):
            self.assertEqual(iface, IReporter)
            return plugins + list(self.original(iface, *a, **kw))

        self.original = plugin.getPlugins
        plugin.getPlugins = getPlugins

        self.standardReport = ['startTest', 'addSuccess', 'stopTest',
                               'startTest', 'addSuccess', 'stopTest',
                               'startTest', 'addSuccess', 'stopTest',
                               'startTest', 'addSuccess', 'stopTest',
                               'startTest', 'addSuccess', 'stopTest',
                               'startTest', 'addSuccess', 'stopTest',
                               'startTest', 'addSuccess', 'stopTest',
                               'startTest', 'addSuccess', 'stopTest',
                               'startTest', 'addSuccess', 'stopTest',
                               'startTest', 'addSuccess', 'stopTest']


    def tearDown(self):
        plugin.getPlugins = self.original


    def parseOptions(self, args):
        self.config.parseOptions(args)


    def getRunner(self):
        r = trial._makeRunner(self.config)
        r.stream = NativeStringIO()
        # XXX The runner should always take care of cleaning this up itself.
        # It's not clear why this is necessary.  The runner always tears down
        # its log file.
        self.addCleanup(r._tearDownLogFile)
        # XXX The runner should always take care of cleaning this up itself as
        # well.  It's necessary because TrialRunner._setUpTestdir might raise
        # an exception preventing Reporter.done from being run, leaving the
        # observer added by Reporter.__init__ still present in the system.
        # Something better needs to happen inside
        # TrialRunner._runWithoutDecoration to remove the need for this cludge.
        r._log = log.LogPublisher()
        return r


    def test_runner_can_get_reporter(self):
        self.parseOptions([])
        result = self.config['reporter']
        runner = self.getRunner()
        self.assertEqual(result, runner._makeResult().__class__)


    def test_runner_get_result(self):
        self.parseOptions([])
        runner = self.getRunner()
        result = runner._makeResult()
        self.assertEqual(result.__class__, self.config['reporter'])


    def test_uncleanWarningsOffByDefault(self):
        """
        By default Trial sets the 'uncleanWarnings' option on the runner to
        False. This means that dirty reactor errors will be reported as
        errors. See L{test_reporter.DirtyReactorTests}.
        """
        self.parseOptions([])
        runner = self.getRunner()
        self.assertNotIsInstance(runner._makeResult(),
                                 reporter.UncleanWarningsReporterWrapper)


    def test_getsUncleanWarnings(self):
        """
        Specifying '--unclean-warnings' on the trial command line will cause
        reporters to be wrapped in a device which converts unclean errors to
        warnings.  See L{test_reporter.DirtyReactorTests} for implications.
        """
        self.parseOptions(['--unclean-warnings'])
        runner = self.getRunner()
        self.assertIsInstance(runner._makeResult(),
                              reporter.UncleanWarningsReporterWrapper)


    def test_runner_working_directory(self):
        self.parseOptions(['--temp-directory', 'some_path'])
        runner = self.getRunner()
        self.assertEqual(runner.workingDirectory, 'some_path')


    def test_concurrentImplicitWorkingDirectory(self):
        """
        If no working directory is explicitly specified and the default
        working directory is in use by another runner, L{TrialRunner.run}
        selects a different default working directory to use.
        """
        self.parseOptions([])

        # Make sure we end up with the same working directory after this test
        # as we had before it.
        self.addCleanup(os.chdir, os.getcwd())

        # Make a new directory and change into it.  This isolates us from state
        # that other tests might have dumped into this process's temp
        # directory.
        runDirectory = FilePath(self.mktemp())
        runDirectory.makedirs()
        os.chdir(runDirectory.path)

        firstRunner = self.getRunner()
        secondRunner = self.getRunner()

        where = {}

        class ConcurrentCase(unittest.SynchronousTestCase):
            def test_first(self):
                """
                Start a second test run which will have a default working
                directory which is the same as the working directory of the
                test run already in progress.
                """
                # Change the working directory to the value it had before this
                # test suite was started.
                where['concurrent'] = subsequentDirectory = os.getcwd()
                os.chdir(runDirectory.path)
                self.addCleanup(os.chdir, subsequentDirectory)

                secondRunner.run(ConcurrentCase('test_second'))

            def test_second(self):
                """
                Record the working directory for later analysis.
                """
                where['record'] = os.getcwd()

        result = firstRunner.run(ConcurrentCase('test_first'))
        bad = result.errors + result.failures
        if bad:
            self.fail(bad[0][1])
        self.assertEqual(
            where, {
                'concurrent': runDirectory.child('_trial_temp').path,
                'record': runDirectory.child('_trial_temp-1').path})


    def test_concurrentExplicitWorkingDirectory(self):
        """
        If a working directory which is already in use is explicitly specified,
        L{TrialRunner.run} raises L{_WorkingDirectoryBusy}.
        """
        self.parseOptions(['--temp-directory', os.path.abspath(self.mktemp())])

        initialDirectory = os.getcwd()
        self.addCleanup(os.chdir, initialDirectory)

        firstRunner = self.getRunner()
        secondRunner = self.getRunner()

        class ConcurrentCase(unittest.SynchronousTestCase):
            def test_concurrent(self):
                """
                Try to start another runner in the same working directory and
                assert that it raises L{_WorkingDirectoryBusy}.
                """
                self.assertRaises(
                    util._WorkingDirectoryBusy,
                    secondRunner.run, ConcurrentCase('test_failure'))

            def test_failure(self):
                """
                Should not be called, always fails.
                """
                self.fail("test_failure should never be called.")

        result = firstRunner.run(ConcurrentCase('test_concurrent'))
        bad = result.errors + result.failures
        if bad:
            self.fail(bad[0][1])


    def test_runner_normal(self):
        self.parseOptions(['--temp-directory', self.mktemp(),
                           '--reporter', 'capturing',
                           'twisted.trial.test.sample'])
        my_runner = self.getRunner()
        loader = runner.TestLoader()
        suite = loader.loadByName('twisted.trial.test.sample', True)
        result = my_runner.run(suite)
        self.assertEqual(self.standardReport, result._calls)


    def runSampleSuite(self, my_runner):
        loader = runner.TestLoader()
        suite = loader.loadByName('twisted.trial.test.sample', True)
        return my_runner.run(suite)


    def test_runnerDebug(self):
        """
        Trial uses its debugger if the `--debug` option is passed.
        """
        self.parseOptions(['--reporter', 'capturing',
                           '--debug', 'twisted.trial.test.sample'])
        my_runner = self.getRunner()
        debugger = my_runner.debugger = CapturingDebugger()
        result = self.runSampleSuite(my_runner)
        self.assertEqual(self.standardReport, result._calls)
        self.assertEqual(['runcall'], debugger._calls)


    def test_runnerDebuggerDefaultsToPdb(self):
        """
        Trial uses pdb if no debugger is specified by `--debugger`
        """
        self.parseOptions(['--debug', 'twisted.trial.test.sample'])
        pdbrcFile = FilePath("pdbrc")
        pdbrcFile.touch()

        self.runcall_called = False
        def runcall(pdb, suite, result):
            self.runcall_called = True
        self.patch(pdb.Pdb, "runcall", runcall)

        self.runSampleSuite(self.getRunner())

        self.assertTrue(self.runcall_called)


    def test_runnerDebuggerWithExplicitlyPassedPdb(self):
        """
        Trial uses pdb if pdb is passed explicitly to the `--debugger` arg.
        """
        self.parseOptions([
            '--reporter', 'capturing',
            '--debugger', 'pdb',
            '--debug', 'twisted.trial.test.sample',
        ])

        self.runcall_called = False
        def runcall(pdb, suite, result):
            self.runcall_called = True
        self.patch(pdb.Pdb, "runcall", runcall)

        self.runSampleSuite(self.getRunner())

        self.assertTrue(self.runcall_called)


    cdebugger = CapturingDebugger()


    def test_runnerDebugger(self):
        """
        Trial uses specified debugger if the debugger is available.
        """
        self.parseOptions([
            '--reporter', 'capturing',
            '--debugger',
            'twisted.trial.test.test_runner.RunnerTests.cdebugger',
            '--debug',
            'twisted.trial.test.sample',
        ])
        my_runner = self.getRunner()
        result = self.runSampleSuite(my_runner)
        self.assertEqual(self.standardReport, result._calls)
        self.assertEqual(['runcall'], my_runner.debugger._calls)


    def test_exitfirst(self):
        """
        If trial was passed the C{--exitfirst} option, the constructed test
        result object is wrapped with L{reporter._ExitWrapper}.
        """
        self.parseOptions(["--exitfirst"])
        runner = self.getRunner()
        result = runner._makeResult()
        self.assertIsInstance(result, reporter._ExitWrapper)



class TrialSuiteTests(unittest.SynchronousTestCase):

    def test_imports(self):
        # FIXME, HTF do you test the reactor can be cleaned up ?!!!
        namedAny('twisted.trial.runner.TrialSuite')



class UntilFailureTests(unittest.SynchronousTestCase):
    class FailAfter(pyunit.TestCase):
        """
        A test case that fails when run 3 times in a row.
        """
        count = []
        def test_foo(self):
            self.count.append(None)
            if len(self.count) == 3:
                self.fail('Count reached 3')


    def setUp(self):
        UntilFailureTests.FailAfter.count = []
        self.test = UntilFailureTests.FailAfter('test_foo')
        self.stream = NativeStringIO()
        self.runner = runner.TrialRunner(reporter.Reporter, stream=self.stream)


    def test_runUntilFailure(self):
        """
        Test that the runUntilFailure method of the runner actually fail after
        a few runs.
        """
        result = self.runner.runUntilFailure(self.test)
        self.assertEqual(result.testsRun, 1)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(self._getFailures(result), 1)


    def _getFailures(self, result):
        """
        Get the number of failures that were reported to a result.
        """
        return len(result.failures)


    def test_runUntilFailureDecorate(self):
        """
        C{runUntilFailure} doesn't decorate the tests uselessly: it does it one
        time when run starts, but not at each turn.
        """
        decorated = []
        def decorate(test, interface):
            decorated.append((test, interface))
            return test
        self.patch(unittest, "decorate", decorate)
        result = self.runner.runUntilFailure(self.test)
        self.assertEqual(result.testsRun, 1)

        self.assertEqual(len(decorated), 1)
        self.assertEqual(decorated, [(self.test, ITestCase)])


    def test_runUntilFailureForceGCDecorate(self):
        """
        C{runUntilFailure} applies the force-gc decoration after the standard
        L{ITestCase} decoration, but only one time.
        """
        decorated = []
        def decorate(test, interface):
            decorated.append((test, interface))
            return test
        self.patch(unittest, "decorate", decorate)
        self.runner._forceGarbageCollection = True
        result = self.runner.runUntilFailure(self.test)
        self.assertEqual(result.testsRun, 1)

        self.assertEqual(len(decorated), 2)
        self.assertEqual(decorated,
            [(self.test, ITestCase),
             (self.test, _ForceGarbageCollectionDecorator)])



class UncleanUntilFailureTests(UntilFailureTests):
    """
    Test that the run-until-failure feature works correctly with the unclean
    error suppressor.
    """

    def setUp(self):
        UntilFailureTests.setUp(self)
        self.runner = runner.TrialRunner(reporter.Reporter, stream=self.stream,
                                         uncleanWarnings=True)

    def _getFailures(self, result):
        """
        Get the number of failures that were reported to a result that
        is wrapped in an UncleanFailureWrapper.
        """
        return len(result._originalReporter.failures)



class BreakingSuite(runner.TestSuite):
    """
    A L{TestSuite} that logs an error when it is run.
    """

    def run(self, result):
        try:
            raise RuntimeError("error that occurs outside of a test")
        except RuntimeError:
            log.err(failure.Failure())



class LoggedErrorsTests(unittest.SynchronousTestCase):
    """
    It is possible for an error generated by a test to be logged I{outside} of
    any test. The log observers constructed by L{TestCase} won't catch these
    errors. Here we try to generate such errors and ensure they are reported to
    a L{TestResult} object.
    """

    def tearDown(self):
        self.flushLoggedErrors(RuntimeError)


    def test_construct(self):
        """
        Check that we can construct a L{runner.LoggedSuite} and that it
        starts empty.
        """
        suite = runner.LoggedSuite()
        self.assertEqual(suite.countTestCases(), 0)


    def test_capturesError(self):
        """
        Chek that a L{LoggedSuite} reports any logged errors to its result.
        """
        result = reporter.TestResult()
        suite = runner.LoggedSuite([BreakingSuite()])
        suite.run(result)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0][0].id(), runner.NOT_IN_TEST)
        self.assertTrue(result.errors[0][1].check(RuntimeError))



class TestHolderTests(unittest.SynchronousTestCase):

    def setUp(self):
        self.description = "description"
        self.holder = runner.TestHolder(self.description)


    def test_holder(self):
        """
        Check that L{runner.TestHolder} takes a description as a parameter
        and that this description is returned by the C{id} and
        C{shortDescription} methods.
        """
        self.assertEqual(self.holder.id(), self.description)
        self.assertEqual(self.holder.shortDescription(), self.description)


    def test_holderImplementsITestCase(self):
        """
        L{runner.TestHolder} implements L{ITestCase}.
        """
        self.assertIdentical(self.holder, ITestCase(self.holder))
        self.assertTrue(
            verifyObject(ITestCase, self.holder),
            "%r claims to provide %r but does not do so correctly."
            % (self.holder, ITestCase))


    def test_runsWithStandardResult(self):
        """
        A L{runner.TestHolder} can run against the standard Python
        C{TestResult}.
        """
        result = pyunit.TestResult()
        self.holder.run(result)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(1, result.testsRun)



class ErrorHolderTestsMixin(object):
    """
    This mixin defines test methods which can be applied to a
    L{runner.ErrorHolder} constructed with either a L{Failure} or a
    C{exc_info}-style tuple.

    Subclass this and implement C{setUp} to create C{self.holder} referring to a
    L{runner.ErrorHolder} instance and C{self.error} referring to a L{Failure}
    which the holder holds.
    """
    exceptionForTests = ZeroDivisionError('integer division or modulo by zero')

    class TestResultStub(object):
        """
        Stub for L{TestResult}.
        """
        def __init__(self):
            self.errors = []

        def startTest(self, test):
            pass

        def stopTest(self, test):
            pass

        def addError(self, test, error):
            self.errors.append((test, error))


    def test_runsWithStandardResult(self):
        """
        A L{runner.ErrorHolder} can run against the standard Python
        C{TestResult}.
        """
        result = pyunit.TestResult()
        self.holder.run(result)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(1, result.testsRun)


    def test_run(self):
        """
        L{runner.ErrorHolder} adds an error to the result when run.
        """
        self.holder.run(self.result)
        self.assertEqual(
            self.result.errors,
            [(self.holder, (self.error.type, self.error.value, self.error.tb))])


    def test_call(self):
        """
        L{runner.ErrorHolder} adds an error to the result when called.
        """
        self.holder(self.result)
        self.assertEqual(
            self.result.errors,
            [(self.holder, (self.error.type, self.error.value, self.error.tb))])


    def test_countTestCases(self):
        """
        L{runner.ErrorHolder.countTestCases} always returns 0.
        """
        self.assertEqual(self.holder.countTestCases(), 0)


    def test_repr(self):
        """
        L{runner.ErrorHolder.__repr__} returns a string describing the error it
        holds.
        """
        self.assertEqual(repr(self.holder),
            "<ErrorHolder description='description' "
            "error=ZeroDivisionError('integer division or modulo by zero',)>")



class FailureHoldingErrorHolderTests(ErrorHolderTestsMixin, TestHolderTests):
    """
    Tests for L{runner.ErrorHolder} behaving similarly to L{runner.TestHolder}
    when constructed with a L{Failure} representing its error.
    """
    def setUp(self):
        self.description = "description"
        # make a real Failure so we can construct ErrorHolder()
        try:
            raise self.exceptionForTests
        except ZeroDivisionError:
            self.error = failure.Failure()
        self.holder = runner.ErrorHolder(self.description, self.error)
        self.result = self.TestResultStub()



class ExcInfoHoldingErrorHolderTests(ErrorHolderTestsMixin, TestHolderTests):
    """
    Tests for L{runner.ErrorHolder} behaving similarly to L{runner.TestHolder}
    when constructed with a C{exc_info}-style tuple representing its error.
    """
    def setUp(self):
        self.description = "description"
        # make a real Failure so we can construct ErrorHolder()
        try:
            raise self.exceptionForTests
        except ZeroDivisionError:
            exceptionInfo = sys.exc_info()
            self.error = failure.Failure()
        self.holder = runner.ErrorHolder(self.description, exceptionInfo)
        self.result = self.TestResultStub()



class MalformedMethodTests(unittest.SynchronousTestCase):
    """
    Test that trial manages when test methods don't have correct signatures.
    """
    class ContainMalformed(pyunit.TestCase):
        """
        This TestCase holds malformed test methods that trial should handle.
        """
        def test_foo(self, blah):
            pass
        def test_bar():
            pass
        test_spam = defer.inlineCallbacks(test_bar)

    def _test(self, method):
        """
        Wrapper for one of the test method of L{ContainMalformed}.
        """
        stream = NativeStringIO()
        trialRunner = runner.TrialRunner(reporter.Reporter, stream=stream)
        test = MalformedMethodTests.ContainMalformed(method)
        result = trialRunner.run(test)
        self.assertEqual(result.testsRun, 1)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(len(result.errors), 1)

    def test_extraArg(self):
        """
        Test when the method has extra (useless) arguments.
        """
        self._test('test_foo')

    def test_noArg(self):
        """
        Test when the method doesn't have even self as argument.
        """
        self._test('test_bar')

    def test_decorated(self):
        """
        Test a decorated method also fails.
        """
        self._test('test_spam')



class DestructiveTestSuiteTests(unittest.SynchronousTestCase):
    """
    Test for L{runner.DestructiveTestSuite}.
    """

    def test_basic(self):
        """
        Thes destructive test suite should run the tests normally.
        """
        called = []
        class MockTest(pyunit.TestCase):
            def test_foo(test):
                called.append(True)
        test = MockTest('test_foo')
        result = reporter.TestResult()
        suite = runner.DestructiveTestSuite([test])
        self.assertEqual(called, [])
        suite.run(result)
        self.assertEqual(called, [True])
        self.assertEqual(suite.countTestCases(), 0)


    def test_shouldStop(self):
        """
        Test the C{shouldStop} management: raising a C{KeyboardInterrupt} must
        interrupt the suite.
        """
        called = []
        class MockTest(unittest.TestCase):
            def test_foo1(test):
                called.append(1)
            def test_foo2(test):
                raise KeyboardInterrupt()
            def test_foo3(test):
                called.append(2)
        result = reporter.TestResult()
        loader = runner.TestLoader()
        loader.suiteFactory = runner.DestructiveTestSuite
        suite = loader.loadClass(MockTest)
        self.assertEqual(called, [])
        suite.run(result)
        self.assertEqual(called, [1])
        # The last test shouldn't have been run
        self.assertEqual(suite.countTestCases(), 1)


    def test_cleanup(self):
        """
        Checks that the test suite cleanups its tests during the run, so that
        it ends empty.
        """
        class MockTest(pyunit.TestCase):
            def test_foo(test):
                pass
        test = MockTest('test_foo')
        result = reporter.TestResult()
        suite = runner.DestructiveTestSuite([test])
        self.assertEqual(suite.countTestCases(), 1)
        suite.run(result)
        self.assertEqual(suite.countTestCases(), 0)



class RunnerDeprecationTests(unittest.SynchronousTestCase):

    class FakeReporter(reporter.Reporter):
        """
        Fake reporter that does *not* implement done() but *does* implement
        printErrors, separator, printSummary, stream, write and writeln
        without deprecations.
        """

        done = None
        separator = None
        stream = None

        def printErrors(self, *args):
            pass

        def printSummary(self, *args):
            pass

        def write(self, *args):
            pass

        def writeln(self, *args):
            pass


    def test_reporterDeprecations(self):
        """
        The runner emits a warning if it is using a result that doesn't
        implement 'done'.
        """
        trialRunner = runner.TrialRunner(None)
        result = self.FakeReporter()
        trialRunner._makeResult = lambda: result
        def f():
            # We have to use a pyunit test, otherwise we'll get deprecation
            # warnings about using iterate() in a test.
            trialRunner.run(pyunit.TestCase('id'))
        self.assertWarns(
            DeprecationWarning,
            "%s should implement done() but doesn't. Falling back to "
            "printErrors() and friends." % reflect.qual(result.__class__),
            __file__, f)



class QualifiedNameWalkerTests(unittest.SynchronousTestCase):
    """
    Tests for L{twisted.trial.runner._qualNameWalker}.
    """

    def test_walksDownPath(self):
        """
        C{_qualNameWalker} is a generator that, when given a Python qualified
        name, yields that name, and then the parent of that name, and so forth,
        along with a list of the tried components, in a 2-tuple.
        """
        walkerResults = list(runner._qualNameWalker("walker.texas.ranger"))

        self.assertEqual(walkerResults,
                         [("walker.texas.ranger", []),
                          ("walker.texas", ["ranger"]),
                          ("walker", ["texas", "ranger"])])



class TrialMainDoesNothingTests(unittest.SynchronousTestCase):
    """
    Importing L{twisted.trial.__main__} will not run the script
    unless it is actually C{__main__}.
    """
    def test_importDoesNothing(self):
        """
        If we import L{twisted.trial.__main__}, it should do nothing.
        """
        # We shouldn't suddenly drop into a script when we import this!
        __import__('twisted.trial.__main__')
