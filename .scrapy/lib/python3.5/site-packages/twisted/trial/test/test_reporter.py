# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
#
# Maintainer: Jonathan Lange

"""
Tests for L{twisted.trial.reporter}.
"""
from __future__ import absolute_import, division

import errno
import os
import re
import sys

from inspect import getmro
from unittest import expectedFailure
from unittest import TestCase as StdlibTestCase

from twisted.python import log
from twisted.python.failure import Failure
from twisted.trial import itrial, unittest, runner, reporter, util
from twisted.trial.reporter import _ExitWrapper, UncleanWarningsReporterWrapper
from twisted.trial.test import erroneous
from twisted.trial.unittest import makeTodo, SkipTest, Todo
from twisted.trial.test import sample

from twisted.python.compat import NativeStringIO, _PY3

if _PY3:
    from io import BytesIO
else:
    # On Python 2, we want regular old StringIO, because otherwise subunit
    # complains
    from StringIO import StringIO as BytesIO



class BrokenStream(object):
    """
    Stream-ish object that raises a signal interrupt error. We use this to make
    sure that Trial still manages to write what it needs to write.
    """
    written = False
    flushed = False

    def __init__(self, fObj):
        self.fObj = fObj

    def write(self, s):
        if self.written:
            return self.fObj.write(s)
        self.written = True
        raise IOError(errno.EINTR, "Interrupted write")

    def flush(self):
        if self.flushed:
            return self.fObj.flush()
        self.flushed = True
        raise IOError(errno.EINTR, "Interrupted flush")


class StringTest(unittest.SynchronousTestCase):
    def stringComparison(self, expect, output):
        output = list(filter(None, output))
        self.assertTrue(len(expect) <= len(output),
                        "Must have more observed than expected"
                        "lines %d < %d" % (len(output), len(expect)))
        REGEX_PATTERN_TYPE = type(re.compile(''))
        for line_number, (exp, out) in enumerate(zip(expect, output)):
            if exp is None:
                continue
            elif isinstance(exp, str):
                self.assertSubstring(exp, out, "Line %d: %r not in %r"
                                     % (line_number, exp, out))
            elif isinstance(exp, REGEX_PATTERN_TYPE):
                self.assertTrue(exp.match(out),
                                "Line %d: %r did not match string %r"
                                % (line_number, exp.pattern, out))
            else:
                raise TypeError("don't know what to do with object %r"
                                % (exp,))


class TestResultTests(unittest.SynchronousTestCase):
    def setUp(self):
        self.result = reporter.TestResult()

    def test_pyunitAddError(self):
        # pyunit passes an exc_info tuple directly to addError
        try:
            raise RuntimeError('foo')
        except RuntimeError as e:
            excValue = e
            self.result.addError(self, sys.exc_info())
        failure = self.result.errors[0][1]
        self.assertEqual(excValue, failure.value)
        self.assertEqual(RuntimeError, failure.type)

    def test_pyunitAddFailure(self):
        # pyunit passes an exc_info tuple directly to addFailure
        try:
            raise self.failureException('foo')
        except self.failureException as e:
            excValue = e
            self.result.addFailure(self, sys.exc_info())
        failure = self.result.failures[0][1]
        self.assertEqual(excValue, failure.value)
        self.assertEqual(self.failureException, failure.type)


class ReporterRealtimeTests(TestResultTests):
    def setUp(self):
        output = NativeStringIO()
        self.result = reporter.Reporter(output, realtime=True)


class ErrorReportingTests(StringTest):
    doubleSeparator = re.compile(r'^=+$')

    def setUp(self):
        self.loader = runner.TestLoader()
        self.output = NativeStringIO()
        self.result = reporter.Reporter(self.output)

    def getOutput(self, suite):
        result = self.getResult(suite)
        result.done()
        return self.output.getvalue()

    def getResult(self, suite):
        suite.run(self.result)
        return self.result

    def test_formatErroredMethod(self):
        """
        A test method which runs and has an error recorded against it is
        reported in the output stream with the I{ERROR} tag along with a
        summary of what error was reported and the ID of the test.
        """
        cls = erroneous.SynchronousTestFailureInSetUp
        suite = self.loader.loadClass(cls)
        output = self.getOutput(suite).splitlines()
        match = [
            self.doubleSeparator,
            '[ERROR]',
            'Traceback (most recent call last):',
            re.compile(r'^\s+File .*erroneous\.py., line \d+, in setUp$'),
            re.compile(r'^\s+raise FoolishError.'
                       r'.I am a broken setUp method..$'),
            ('twisted.trial.test.erroneous.FoolishError: '
             'I am a broken setUp method'),
            '%s.%s.test_noop' % (cls.__module__, cls.__name__)]
        self.stringComparison(match, output)


    def test_formatFailedMethod(self):
        """
        A test method which runs and has a failure recorded against it is
        reported in the output stream with the I{FAIL} tag along with a summary
        of what failure was reported and the ID of the test.
        """
        suite = self.loader.loadByName(
            "twisted.trial.test.erroneous.TestRegularFail.test_fail")
        output = self.getOutput(suite).splitlines()
        match = [
            self.doubleSeparator,
            '[FAIL]',
            'Traceback (most recent call last):',
            re.compile(r'^\s+File .*erroneous\.py., line \d+, in test_fail$'),
            re.compile(r'^\s+self\.fail\("I fail"\)$'),
            'twisted.trial.unittest.FailTest: I fail',
            'twisted.trial.test.erroneous.TestRegularFail.test_fail',
            ]
        self.stringComparison(match, output)


    def test_doctestError(self):
        """
        A problem encountered while running a doctest is reported in the output
        stream with a I{FAIL} or I{ERROR} tag along with a summary of what
        problem was encountered and the ID of the test.
        """
        from twisted.trial.test import erroneous
        suite = unittest.decorate(
            self.loader.loadDoctests(erroneous), itrial.ITestCase)
        output = self.getOutput(suite)
        path = 'twisted.trial.test.erroneous.unexpectedException'
        for substring in ['1/0', 'ZeroDivisionError',
                          'Exception raised:', path]:
            self.assertSubstring(substring, output)
        self.assertTrue(re.search('Fail(ed|ure in) example:', output),
                        "Couldn't match 'Failure in example: ' "
                        "or 'Failed example: '")
        expect = [self.doubleSeparator,
                  re.compile(r'\[(ERROR|FAIL)\]')]
        self.stringComparison(expect, output.splitlines())


    def test_hiddenException(self):
        """
        Check that errors in C{DelayedCall}s get reported, even if the
        test already has a failure.

        Only really necessary for testing the deprecated style of tests that
        use iterate() directly. See
        L{erroneous.DelayedCall.testHiddenException} for more details.
        """
        test = erroneous.DelayedCall('testHiddenException')
        output = self.getOutput(test).splitlines()
        if _PY3:
            errorQual = RuntimeError.__qualname__
        else:
            errorQual = "exceptions.RuntimeError"
        match = [
            self.doubleSeparator,
            '[FAIL]',
            'Traceback (most recent call last):',
            re.compile(r'^\s+File .*erroneous\.py., line \d+, in '
                       'testHiddenException$'),
            re.compile(r'^\s+self\.fail\("Deliberate failure to mask the '
                       'hidden exception"\)$'),
            'twisted.trial.unittest.FailTest: '
            'Deliberate failure to mask the hidden exception',
            'twisted.trial.test.erroneous.DelayedCall.testHiddenException',
            self.doubleSeparator,
            '[ERROR]',
            'Traceback (most recent call last):',
            re.compile(r'^\s+File .* in runUntilCurrent'),
            re.compile(r'^\s+.*'),
            re.compile('^\s+File .*erroneous\.py", line \d+, in go'),
            re.compile('^\s+raise RuntimeError\(self.hiddenExceptionMsg\)'),
            errorQual + ': something blew up',
            'twisted.trial.test.erroneous.DelayedCall.testHiddenException']
        self.stringComparison(match, output)



class UncleanWarningWrapperErrorReportingTests(ErrorReportingTests):
    """
    Tests that the L{UncleanWarningsReporterWrapper} can sufficiently proxy
    IReporter failure and error reporting methods to a L{reporter.Reporter}.
    """
    def setUp(self):
        self.loader = runner.TestLoader()
        self.output = NativeStringIO()
        self.result = UncleanWarningsReporterWrapper(
            reporter.Reporter(self.output))



class TracebackHandlingTests(unittest.SynchronousTestCase):

    def getErrorFrames(self, test):
        """
        Run the given C{test}, make sure it fails and return the trimmed
        frames.

        @param test: The test case to run.

        @return: The C{list} of frames trimmed.
        """
        stream = NativeStringIO()
        result = reporter.Reporter(stream)
        test.run(result)
        bads = result.failures + result.errors
        self.assertEqual(len(bads), 1)
        self.assertEqual(bads[0][0], test)
        return result._trimFrames(bads[0][1].frames)

    def checkFrames(self, observedFrames, expectedFrames):
        for observed, expected in zip(observedFrames, expectedFrames):
            self.assertEqual(observed[0], expected[0])
            observedSegs = os.path.splitext(observed[1])[0].split(os.sep)
            expectedSegs = expected[1].split('/')
            self.assertEqual(observedSegs[-len(expectedSegs):],
                             expectedSegs)
        self.assertEqual(len(observedFrames), len(expectedFrames))

    def test_basic(self):
        test = erroneous.TestRegularFail('test_fail')
        frames = self.getErrorFrames(test)
        self.checkFrames(frames,
                         [('test_fail', 'twisted/trial/test/erroneous')])

    def test_subroutine(self):
        test = erroneous.TestRegularFail('test_subfail')
        frames = self.getErrorFrames(test)
        self.checkFrames(frames,
                         [('test_subfail', 'twisted/trial/test/erroneous'),
                          ('subroutine', 'twisted/trial/test/erroneous')])

    def test_deferred(self):
        """
        C{_trimFrames} removes traces of C{_runCallbacks} when getting an error
        in a callback returned by a C{TestCase} based test.
        """
        test = erroneous.TestAsynchronousFail('test_fail')
        frames = self.getErrorFrames(test)
        self.checkFrames(frames,
                         [('_later', 'twisted/trial/test/erroneous')])

    def test_noFrames(self):
        result = reporter.Reporter(None)
        self.assertEqual([], result._trimFrames([]))

    def test_oneFrame(self):
        result = reporter.Reporter(None)
        self.assertEqual(['fake frame'], result._trimFrames(['fake frame']))

    def test_exception(self):
        """
        C{_trimFrames} removes traces of C{runWithWarningsSuppressed} from
        C{utils} when a synchronous exception happens in a C{TestCase}
        based test.
        """
        test = erroneous.TestAsynchronousFail('test_exception')
        frames = self.getErrorFrames(test)
        self.checkFrames(frames,
                         [('test_exception', 'twisted/trial/test/erroneous')])


class FormatFailuresTests(StringTest):
    def setUp(self):
        try:
            raise RuntimeError('foo')
        except RuntimeError:
            self.f = Failure()
        self.f.frames = [
            ['foo', 'foo/bar.py', 5, [('x', 5)], [('y', 'orange')]],
            ['qux', 'foo/bar.py', 10, [('a', 'two')], [('b', 'MCMXCIX')]]
            ]
        self.stream = NativeStringIO()
        self.result = reporter.Reporter(self.stream)

    def test_formatDefault(self):
        tb = self.result._formatFailureTraceback(self.f)
        self.stringComparison([
            'Traceback (most recent call last):',
            '  File "foo/bar.py", line 5, in foo',
            re.compile(r'^\s*$'),
            '  File "foo/bar.py", line 10, in qux',
            re.compile(r'^\s*$'),
            'RuntimeError: foo'], tb.splitlines())

    def test_formatString(self):
        tb = '''
  File "twisted/trial/unittest.py", line 256, in failUnlessSubstring
    return self.failUnlessIn(substring, astring, msg)
exceptions.TypeError: iterable argument required

'''
        expected = '''
  File "twisted/trial/unittest.py", line 256, in failUnlessSubstring
    return self.failUnlessIn(substring, astring, msg)
exceptions.TypeError: iterable argument required
'''
        formatted = self.result._formatFailureTraceback(tb)
        self.assertEqual(expected, formatted)

    def test_mutation(self):
        frames = self.f.frames[:]
        # The call shouldn't mutate the frames.
        self.result._formatFailureTraceback(self.f)
        self.assertEqual(self.f.frames, frames)


class PyunitNamesTests(unittest.SynchronousTestCase):
    def setUp(self):
        self.stream = NativeStringIO()
        self.test = sample.PyunitTest('test_foo')

    def test_verboseReporter(self):
        result = reporter.VerboseTextReporter(self.stream)
        result.startTest(self.test)
        output = self.stream.getvalue()
        self.assertEqual(
            output, 'twisted.trial.test.sample.PyunitTest.test_foo ... ')

    def test_treeReporter(self):
        result = reporter.TreeReporter(self.stream)
        result.startTest(self.test)
        output = self.stream.getvalue()
        output = output.splitlines()[-1].strip()
        self.assertEqual(output, result.getDescription(self.test) + ' ...')

    def test_getDescription(self):
        result = reporter.TreeReporter(self.stream)
        output = result.getDescription(self.test)
        self.assertEqual(output, 'test_foo')


    def test_minimalReporter(self):
        """
        The summary of L{reporter.MinimalReporter} is a simple list of numbers,
        indicating how many tests ran, how many failed etc.

        The numbers represents:
         * the run time of the tests
         * the number of tests run, printed 2 times for legacy reasons
         * the number of errors
         * the number of failures
         * the number of skips
        """
        result = reporter.MinimalReporter(self.stream)
        self.test.run(result)
        result._printSummary()
        output = self.stream.getvalue().strip().split(' ')
        self.assertEqual(output[1:], ['1', '1', '0', '0', '0'])


    def test_minimalReporterTime(self):
        """
        L{reporter.MinimalReporter} reports the time to run the tests as first
        data in its output.
        """
        times = [1.0, 1.2, 1.5, 1.9]
        result = reporter.MinimalReporter(self.stream)
        result._getTime = lambda: times.pop(0)
        self.test.run(result)
        result._printSummary()
        output = self.stream.getvalue().strip().split(' ')
        timer = output[0]
        self.assertEqual(timer, "0.7")


    def test_emptyMinimalReporter(self):
        """
        The summary of L{reporter.MinimalReporter} is a list of zeroes when no
        test is actually run.
        """
        result = reporter.MinimalReporter(self.stream)
        result._printSummary()
        output = self.stream.getvalue().strip().split(' ')
        self.assertEqual(output, ['0', '0', '0', '0', '0', '0'])



class DirtyReactorTests(unittest.SynchronousTestCase):
    """
    The trial script has an option to treat L{DirtyReactorAggregateError}s as
    warnings, as a migration tool for test authors. It causes a wrapper to be
    placed around reporters that replaces L{DirtyReactorAggregatErrors} with
    warnings.
    """

    def setUp(self):
        self.dirtyError = Failure(
            util.DirtyReactorAggregateError(['foo'], ['bar']))
        self.output = NativeStringIO()
        self.test = DirtyReactorTests('test_errorByDefault')


    def test_errorByDefault(self):
        """
        L{DirtyReactorAggregateError}s are reported as errors with the default
        Reporter.
        """
        result = reporter.Reporter(stream=self.output)
        result.addError(self.test, self.dirtyError)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0][1], self.dirtyError)


    def test_warningsEnabled(self):
        """
        L{DirtyReactorAggregateError}s are reported as warnings when using
        the L{UncleanWarningsReporterWrapper}.
        """
        result = UncleanWarningsReporterWrapper(
            reporter.Reporter(stream=self.output))
        self.assertWarns(UserWarning, self.dirtyError.getErrorMessage(),
                         reporter.__file__,
                         result.addError, self.test, self.dirtyError)


    def test_warningsMaskErrors(self):
        """
        L{DirtyReactorAggregateError}s are I{not} reported as errors if the
        L{UncleanWarningsReporterWrapper} is used.
        """
        result = UncleanWarningsReporterWrapper(
            reporter.Reporter(stream=self.output))
        self.assertWarns(UserWarning, self.dirtyError.getErrorMessage(),
                         reporter.__file__,
                         result.addError, self.test, self.dirtyError)
        self.assertEqual(result._originalReporter.errors, [])


    def test_dealsWithThreeTuples(self):
        """
        Some annoying stuff can pass three-tuples to addError instead of
        Failures (like PyUnit). The wrapper, of course, handles this case,
        since it is a part of L{twisted.trial.itrial.IReporter}! But it does
        not convert L{DirtyReactorAggregateError} to warnings in this case,
        because nobody should be passing those in the form of three-tuples.
        """
        result = UncleanWarningsReporterWrapper(
            reporter.Reporter(stream=self.output))
        result.addError(self.test,
                        (self.dirtyError.type, self.dirtyError.value, None))
        self.assertEqual(len(result._originalReporter.errors), 1)
        self.assertEqual(result._originalReporter.errors[0][1].type,
                          self.dirtyError.type)
        self.assertEqual(result._originalReporter.errors[0][1].value,
                          self.dirtyError.value)



class TrialNamesTests(unittest.SynchronousTestCase):

    def setUp(self):
        self.stream = NativeStringIO()
        self.test = sample.FooTest('test_foo')

    def test_verboseReporter(self):
        result = reporter.VerboseTextReporter(self.stream)
        result.startTest(self.test)
        output = self.stream.getvalue()
        self.assertEqual(output, self.test.id() + ' ... ')

    def test_treeReporter(self):
        result = reporter.TreeReporter(self.stream)
        result.startTest(self.test)
        output = self.stream.getvalue()
        output = output.splitlines()[-1].strip()
        self.assertEqual(output, result.getDescription(self.test) + ' ...')

    def test_treeReporterWithDocstrings(self):
        """A docstring"""
        result = reporter.TreeReporter(self.stream)
        self.assertEqual(result.getDescription(self),
                         'test_treeReporterWithDocstrings')

    def test_getDescription(self):
        result = reporter.TreeReporter(self.stream)
        output = result.getDescription(self.test)
        self.assertEqual(output, "test_foo")


class SkipTests(unittest.SynchronousTestCase):
    """
    Tests for L{reporter.Reporter}'s handling of skips.
    """
    def setUp(self):
        self.stream = NativeStringIO()
        self.result = reporter.Reporter(self.stream)
        self.test = sample.FooTest('test_foo')

    def _getSkips(self, result):
        """
        Get the number of skips that happened to a reporter.
        """
        return len(result.skips)

    def test_accumulation(self):
        self.result.addSkip(self.test, 'some reason')
        self.assertEqual(self._getSkips(self.result), 1)

    def test_success(self):
        self.result.addSkip(self.test, 'some reason')
        self.assertEqual(True, self.result.wasSuccessful())


    def test_summary(self):
        """
        The summary of a successful run with skips indicates that the test
        suite passed and includes the number of skips.
        """
        self.result.addSkip(self.test, 'some reason')
        self.result.done()
        output = self.stream.getvalue().splitlines()[-1]
        prefix = 'PASSED '
        self.assertTrue(output.startswith(prefix))
        self.assertEqual(output[len(prefix):].strip(), '(skips=1)')


    def test_basicErrors(self):
        """
        The output at the end of a test run with skips includes the reasons
        for skipping those tests.
        """
        self.result.addSkip(self.test, 'some reason')
        self.result.done()
        output = self.stream.getvalue().splitlines()[3]
        self.assertEqual(output.strip(), 'some reason')


    def test_booleanSkip(self):
        """
        Tests can be skipped without specifying a reason by setting the 'skip'
        attribute to True. When this happens, the test output includes 'True'
        as the reason.
        """
        self.result.addSkip(self.test, True)
        self.result.done()
        output = self.stream.getvalue().splitlines()[3]
        self.assertEqual(output, 'True')


    def test_exceptionSkip(self):
        """
        Skips can be raised as errors. When this happens, the error is
        included in the summary at the end of the test suite.
        """
        try:
            1/0
        except Exception as e:
            error = e
        self.result.addSkip(self.test, error)
        self.result.done()
        output = '\n'.join(self.stream.getvalue().splitlines()[3:5]).strip()
        self.assertEqual(output, str(error))


class UncleanWarningSkipTests(SkipTests):
    """
    Tests for skips on a L{reporter.Reporter} wrapped by an
    L{UncleanWarningsReporterWrapper}.
    """
    def setUp(self):
        SkipTests.setUp(self)
        self.result = UncleanWarningsReporterWrapper(self.result)

    def _getSkips(self, result):
        """
        Get the number of skips that happened to a reporter inside of an
        unclean warnings reporter wrapper.
        """
        return len(result._originalReporter.skips)



class TodoTests(unittest.SynchronousTestCase):
    """
    Tests for L{reporter.Reporter}'s handling of todos.
    """

    def setUp(self):
        self.stream = NativeStringIO()
        self.result = reporter.Reporter(self.stream)
        self.test = sample.FooTest('test_foo')


    def _getTodos(self, result):
        """
        Get the expected failures that happened to a reporter.
        """
        return result.expectedFailures


    def _getUnexpectedSuccesses(self, result):
        """
        Get the unexpected successes that happened to a reporter.
        """
        return result.unexpectedSuccesses


    def test_accumulation(self):
        """
        L{reporter.Reporter} accumulates the expected failures that it
        is notified of.
        """
        self.result.addExpectedFailure(self.test, Failure(Exception()),
                                       makeTodo('todo!'))
        self.assertEqual(len(self._getTodos(self.result)), 1)


    def test_noTodoProvided(self):
        """
        If no C{Todo} is provided to C{addExpectedFailure}, then
        L{reporter.Reporter} makes up a sensible default.

        This allows standard Python unittests to use Twisted reporters.
        """
        failure = Failure(Exception())
        self.result.addExpectedFailure(self.test, failure)
        [(test, error, todo)] = self._getTodos(self.result)
        self.assertEqual(test, self.test)
        self.assertEqual(error, failure)
        self.assertEqual(repr(todo), repr(makeTodo('Test expected to fail')))


    def test_success(self):
        """
        A test run is still successful even if there are expected failures.
        """
        self.result.addExpectedFailure(self.test, Failure(Exception()),
                                       makeTodo('todo!'))
        self.assertEqual(True, self.result.wasSuccessful())


    def test_unexpectedSuccess(self):
        """
        A test which is marked as todo but succeeds will have an unexpected
        success reported to its result. A test run is still successful even
        when this happens.
        """
        self.result.addUnexpectedSuccess(self.test, makeTodo("Heya!"))
        self.assertEqual(True, self.result.wasSuccessful())
        self.assertEqual(len(self._getUnexpectedSuccesses(self.result)), 1)


    def test_unexpectedSuccessNoTodo(self):
        """
        A test which is marked as todo but succeeds will have an unexpected
        success reported to its result. A test run is still successful even
        when this happens.

        If no C{Todo} is provided, then we make up a sensible default. This
        allows standard Python unittests to use Twisted reporters.
        """
        self.result.addUnexpectedSuccess(self.test)
        [(test, todo)] = self._getUnexpectedSuccesses(self.result)
        self.assertEqual(test, self.test)
        self.assertEqual(repr(todo), repr(makeTodo('Test expected to fail')))


    def test_summary(self):
        """
        The reporter's C{printSummary} method should print the number of
        expected failures that occurred.
        """
        self.result.addExpectedFailure(self.test, Failure(Exception()),
                                       makeTodo('some reason'))
        self.result.done()
        output = self.stream.getvalue().splitlines()[-1]
        prefix = 'PASSED '
        self.assertTrue(output.startswith(prefix))
        self.assertEqual(output[len(prefix):].strip(),
                         '(expectedFailures=1)')


    def test_basicErrors(self):
        """
        The reporter's L{printErrors} method should include the value of the
        Todo.
        """
        self.result.addExpectedFailure(self.test, Failure(Exception()),
                                       makeTodo('some reason'))
        self.result.done()
        output = self.stream.getvalue().splitlines()[3].strip()
        self.assertEqual(output, "Reason: 'some reason'")


    def test_booleanTodo(self):
        """
        Booleans CAN'T be used as the value of a todo. Maybe this sucks. This
        is a test for current behavior, not a requirement.
        """
        self.result.addExpectedFailure(self.test, Failure(Exception()), True)
        self.assertRaises(Exception, self.result.done)


    def test_exceptionTodo(self):
        """
        The exception for expected failures should be shown in the
        C{printErrors} output.
        """
        try:
            1/0
        except Exception as e:
            error = e
        self.result.addExpectedFailure(self.test, Failure(error),
                                       makeTodo("todo!"))
        self.result.done()
        output = '\n'.join(self.stream.getvalue().splitlines()[3:]).strip()
        self.assertTrue(str(error) in output)


    def test_standardLibraryCompatibilityFailure(self):
        """
        Tests that use the standard library C{expectedFailure} feature worth
        with Trial reporters.
        """
        class Test(StdlibTestCase):
            @expectedFailure
            def test_fail(self):
                self.fail('failure')

        test = Test('test_fail')
        test.run(self.result)
        self.assertEqual(len(self._getTodos(self.result)), 1)


    def test_standardLibraryCompatibilitySuccess(self):
        """
        Tests that use the standard library C{expectedFailure} feature worth
        with Trial reporters.
        """
        class Test(StdlibTestCase):
            @expectedFailure
            def test_success(self):
                pass

        test = Test('test_success')
        test.run(self.result)
        self.assertEqual(len(self._getUnexpectedSuccesses(self.result)), 1)



class UncleanWarningTodoTests(TodoTests):
    """
    Tests for L{UncleanWarningsReporterWrapper}'s handling of todos.
    """

    def setUp(self):
        TodoTests.setUp(self)
        self.result = UncleanWarningsReporterWrapper(self.result)


    def _getTodos(self, result):
        """
        Get the  todos that happened to a reporter inside of an unclean
        warnings reporter wrapper.
        """
        return result._originalReporter.expectedFailures


    def _getUnexpectedSuccesses(self, result):
        """
        Get the number of unexpected successes that happened to a reporter
        inside of an unclean warnings reporter wrapper.
        """
        return result._originalReporter.unexpectedSuccesses



class MockColorizer:
    """
    Used by TreeReporterTests to make sure that output is colored correctly.
    """

    def __init__(self, stream):
        self.log = []


    def write(self, text, color):
        self.log.append((color, text))



class TreeReporterTests(unittest.SynchronousTestCase):
    def setUp(self):
        self.test = sample.FooTest('test_foo')
        self.stream = NativeStringIO()
        self.result = reporter.TreeReporter(self.stream)
        self.result._colorizer = MockColorizer(self.stream)
        self.log = self.result._colorizer.log

    def makeError(self):
        try:
            1/0
        except ZeroDivisionError:
            f = Failure()
        return f


    def test_summaryColoredSuccess(self):
        """
        The summary in case of success should have a good count of successes
        and be colored properly.
        """
        self.result.addSuccess(self.test)
        self.result.done()
        self.assertEqual(self.log[1], (self.result.SUCCESS, 'PASSED'))
        self.assertEqual(
            self.stream.getvalue().splitlines()[-1].strip(), "(successes=1)")


    def test_summaryColoredFailure(self):
        """
        The summary in case of failure should have a good count of errors
        and be colored properly.
        """
        try:
            raise RuntimeError('foo')
        except RuntimeError:
            self.result.addError(self, sys.exc_info())
        self.result.done()
        self.assertEqual(self.log[1], (self.result.FAILURE, 'FAILED'))
        self.assertEqual(
            self.stream.getvalue().splitlines()[-1].strip(), "(errors=1)")


    def test_getPrelude(self):
        """
        The tree needs to get the segments of the test ID that correspond
        to the module and class that it belongs to.
        """
        self.assertEqual(
            ['foo.bar', 'baz'],
            self.result._getPreludeSegments('foo.bar.baz.qux'))
        self.assertEqual(
            ['foo', 'bar'],
            self.result._getPreludeSegments('foo.bar.baz'))
        self.assertEqual(
            ['foo'],
            self.result._getPreludeSegments('foo.bar'))
        self.assertEqual([], self.result._getPreludeSegments('foo'))


    def test_groupResults(self):
        """
        If two different tests have the same error, L{Reporter._groupResults}
        includes them together in one of the tuples in the list it returns.
        """
        try:
            raise RuntimeError('foo')
        except RuntimeError:
            self.result.addError(self, sys.exc_info())
            self.result.addError(self.test, sys.exc_info())
        try:
            raise RuntimeError('bar')
        except RuntimeError:
            extra = sample.FooTest('test_bar')
            self.result.addError(extra, sys.exc_info())
        self.result.done()
        grouped = self.result._groupResults(
            self.result.errors, self.result._formatFailureTraceback)
        self.assertEqual(grouped[0][1], [self, self.test])
        self.assertEqual(grouped[1][1], [extra])


    def test_printResults(self):
        """
        L{Reporter._printResults} uses the results list and formatter callable
        passed to it to produce groups of results to write to its output
        stream.
        """
        def formatter(n):
            return str(n) + '\n'
        first = sample.FooTest('test_foo')
        second = sample.FooTest('test_bar')
        third = sample.PyunitTest('test_foo')
        self.result._printResults(
            'FOO', [(first, 1), (second, 1), (third, 2)], formatter)
        self.assertEqual(
            self.stream.getvalue(),
            "%(double separator)s\n"
            "FOO\n"
            "1\n"
            "\n"
            "%(first)s\n"
            "%(second)s\n"
            "%(double separator)s\n"
            "FOO\n"
            "2\n"
            "\n"
            "%(third)s\n" % {
                'double separator': self.result._doubleSeparator,
                'first': first.id(),
                'second': second.id(),
                'third': third.id(),
                })



class ReporterInterfaceTests(unittest.SynchronousTestCase):
    """
    Tests for the bare interface of a trial reporter.

    Subclass this test case and provide a different 'resultFactory' to test
    that a particular reporter implementation will work with the rest of
    Trial.

    @cvar resultFactory: A callable that returns a reporter to be tested. The
        callable must take the same parameters as L{reporter.Reporter}.
    """

    resultFactory = reporter.Reporter

    def setUp(self):
        self.test = sample.FooTest('test_foo')
        self.stream = NativeStringIO()
        self.publisher = log.LogPublisher()
        self.result = self.resultFactory(self.stream, publisher=self.publisher)


    def test_shouldStopInitiallyFalse(self):
        """
        shouldStop is False to begin with.
        """
        self.assertEqual(False, self.result.shouldStop)


    def test_shouldStopTrueAfterStop(self):
        """
        shouldStop becomes True soon as someone calls stop().
        """
        self.result.stop()
        self.assertEqual(True, self.result.shouldStop)


    def test_wasSuccessfulInitiallyTrue(self):
        """
        wasSuccessful() is True when there have been no results reported.
        """
        self.assertEqual(True, self.result.wasSuccessful())


    def test_wasSuccessfulTrueAfterSuccesses(self):
        """
        wasSuccessful() is True when there have been only successes, False
        otherwise.
        """
        self.result.addSuccess(self.test)
        self.assertEqual(True, self.result.wasSuccessful())


    def test_wasSuccessfulFalseAfterErrors(self):
        """
        wasSuccessful() becomes False after errors have been reported.
        """
        try:
            1 / 0
        except ZeroDivisionError:
            self.result.addError(self.test, sys.exc_info())
        self.assertEqual(False, self.result.wasSuccessful())


    def test_wasSuccessfulFalseAfterFailures(self):
        """
        wasSuccessful() becomes False after failures have been reported.
        """
        try:
            self.fail("foo")
        except self.failureException:
            self.result.addFailure(self.test, sys.exc_info())
        self.assertEqual(False, self.result.wasSuccessful())



class ReporterTests(ReporterInterfaceTests):
    """
    Tests for the base L{reporter.Reporter} class.
    """

    def setUp(self):
        ReporterInterfaceTests.setUp(self)
        self._timer = 0
        self.result._getTime = self._getTime


    def _getTime(self):
        self._timer += 1
        return self._timer


    def test_startStop(self):
        self.result.startTest(self.test)
        self.result.stopTest(self.test)
        self.assertTrue(self.result._lastTime > 0)
        self.assertEqual(self.result.testsRun, 1)
        self.assertEqual(self.result.wasSuccessful(), True)


    def test_brokenStream(self):
        """
        Test that the reporter safely writes to its stream.
        """
        result = self.resultFactory(stream=BrokenStream(self.stream))
        result._writeln("Hello")
        self.assertEqual(self.stream.getvalue(), 'Hello\n')
        self.stream.truncate(0)
        self.stream.seek(0)
        result._writeln("Hello %s!", 'World')
        self.assertEqual(self.stream.getvalue(), 'Hello World!\n')


    def test_warning(self):
        """
        L{reporter.Reporter} observes warnings emitted by the Twisted log
        system and writes them to its output stream.
        """
        message = RuntimeWarning("some warning text")
        category = 'exceptions.RuntimeWarning'
        filename = "path/to/some/file.py"
        lineno = 71
        self.publisher.msg(
            warning=message, category=category,
            filename=filename, lineno=lineno)
        self.assertEqual(
            self.stream.getvalue(),
            "%s:%d: %s: %s\n" % (
                filename, lineno, category.split('.')[-1], message))


    def test_duplicateWarningSuppressed(self):
        """
        A warning emitted twice within a single test is only written to the
        stream once.
        """
        # Emit the warning and assert that it shows up
        self.test_warning()
        # Emit the warning again and assert that the stream still only has one
        # warning on it.
        self.test_warning()


    def test_warningEmittedForNewTest(self):
        """
        A warning emitted again after a new test has started is written to the
        stream again.
        """
        test = self.__class__('test_warningEmittedForNewTest')
        self.result.startTest(test)

        # Clear whatever startTest wrote to the stream
        self.stream.seek(0)
        self.stream.truncate()

        # Emit a warning (and incidentally, assert that it was emitted)
        self.test_warning()

        # Clean up from the first warning to simplify the rest of the
        # assertions.
        self.stream.seek(0)
        self.stream.truncate()

        # Stop the first test and start another one (it just happens to be the
        # same one, but that doesn't matter)
        self.result.stopTest(test)
        self.result.startTest(test)

        # Clean up the stopTest/startTest output
        self.stream.seek(0)
        self.stream.truncate()

        # Emit the warning again and make sure it shows up
        self.test_warning()


    def test_stopObserving(self):
        """
        L{reporter.Reporter} stops observing log events when its C{done} method
        is called.
        """
        self.result.done()
        self.stream.seek(0)
        self.stream.truncate()
        self.publisher.msg(
            warning=RuntimeWarning("some message"),
            category='exceptions.RuntimeWarning',
            filename="file/name.py", lineno=17)
        self.assertEqual(self.stream.getvalue(), "")



class SafeStreamTests(unittest.SynchronousTestCase):
    def test_safe(self):
        """
        Test that L{reporter.SafeStream} successfully write to its original
        stream even if an interrupt happens during the write.
        """
        stream = NativeStringIO()
        broken = BrokenStream(stream)
        safe = reporter.SafeStream(broken)
        safe.write("Hello")
        self.assertEqual(stream.getvalue(), "Hello")



class SubunitReporterTests(ReporterInterfaceTests):
    """
    Tests for the subunit reporter.

    This just tests that the subunit reporter implements the basic interface.
    """

    resultFactory = reporter.SubunitReporter


    def setUp(self):
        if reporter.TestProtocolClient is None:
            raise SkipTest(
                "Subunit not installed, cannot test SubunitReporter")

        self.test = sample.FooTest('test_foo')
        self.stream = BytesIO()
        self.publisher = log.LogPublisher()
        self.result = self.resultFactory(self.stream, publisher=self.publisher)


    def assertForwardsToSubunit(self, methodName, *args, **kwargs):
        """
        Assert that 'methodName' on L{SubunitReporter} forwards to the
        equivalent method on subunit.

        Checks that the return value from subunit is returned from the
        L{SubunitReporter} and that the reporter writes the same data to its
        stream as subunit does to its own.

        Assumes that the method on subunit has the same name as the method on
        L{SubunitReporter}.
        """
        stream = BytesIO()

        subunitClient = reporter.TestProtocolClient(stream)
        subunitReturn = getattr(subunitClient, methodName)(*args, **kwargs)
        subunitOutput = stream.getvalue()
        reporterReturn = getattr(self.result, methodName)(*args, **kwargs)
        self.assertEqual(subunitReturn, reporterReturn)
        self.assertEqual(subunitOutput, self.stream.getvalue())


    def removeMethod(self, klass, methodName):
        """
        Remove 'methodName' from 'klass'.

        If 'klass' does not have a method named 'methodName', then
        'removeMethod' succeeds silently.

        If 'klass' does have a method named 'methodName', then it is removed
        using delattr. Also, methods of the same name are removed from all
        base classes of 'klass', thus removing the method entirely.

        @param klass: The class to remove the method from.
        @param methodName: The name of the method to remove.
        """
        method = getattr(klass, methodName, None)
        if method is None:
            return
        for base in getmro(klass):
            try:
                delattr(base, methodName)
            except (AttributeError, TypeError):
                break
            else:
                self.addCleanup(setattr, base, methodName, method)


    def test_subunitWithoutAddExpectedFailureInstalled(self):
        """
        Some versions of subunit don't have "addExpectedFailure". For these
        versions, we report expected failures as successes.
        """
        self.removeMethod(reporter.TestProtocolClient, 'addExpectedFailure')
        try:
            1 / 0
        except ZeroDivisionError:
            self.result.addExpectedFailure(self.test, sys.exc_info(), "todo")
        expectedFailureOutput = self.stream.getvalue()
        self.stream.truncate(0)
        self.stream.seek(0)
        self.result.addSuccess(self.test)
        successOutput = self.stream.getvalue()
        self.assertEqual(successOutput, expectedFailureOutput)


    def test_subunitWithoutAddSkipInstalled(self):
        """
        Some versions of subunit don't have "addSkip". For these versions, we
        report skips as successes.
        """
        self.removeMethod(reporter.TestProtocolClient, 'addSkip')
        self.result.addSkip(self.test, "reason")
        skipOutput = self.stream.getvalue()
        self.stream.truncate(0)
        self.stream.seek(0)
        self.result.addSuccess(self.test)
        successOutput = self.stream.getvalue()
        self.assertEqual(successOutput, skipOutput)


    def test_addExpectedFailurePassedThrough(self):
        """
        Some versions of subunit have "addExpectedFailure". For these
        versions, when we call 'addExpectedFailure' on the test result, we
        pass the error and test through to the subunit client.
        """
        addExpectedFailureCalls = []
        def addExpectedFailure(test, error):
            addExpectedFailureCalls.append((test, error))

        # Provide our own addExpectedFailure, whether or not the locally
        # installed subunit has addExpectedFailure.
        self.result._subunit.addExpectedFailure = addExpectedFailure
        try:
            1 / 0
        except ZeroDivisionError:
            exc_info = sys.exc_info()
            self.result.addExpectedFailure(self.test, exc_info, 'todo')
        self.assertEqual(addExpectedFailureCalls, [(self.test, exc_info)])


    def test_addSkipSendsSubunitAddSkip(self):
        """
        Some versions of subunit have "addSkip". For these versions, when we
        call 'addSkip' on the test result, we pass the test and reason through
        to the subunit client.
        """
        addSkipCalls = []
        def addSkip(test, reason):
            addSkipCalls.append((test, reason))

        # Provide our own addSkip, whether or not the locally-installed
        # subunit has addSkip.
        self.result._subunit.addSkip = addSkip
        self.result.addSkip(self.test, 'reason')
        self.assertEqual(addSkipCalls, [(self.test, 'reason')])


    def test_doneDoesNothing(self):
        """
        The subunit reporter doesn't need to print out a summary -- the stream
        of results is everything. Thus, done() does nothing.
        """
        self.result.done()
        self.assertEqual(b'', self.stream.getvalue())


    def test_startTestSendsSubunitStartTest(self):
        """
        SubunitReporter.startTest() sends the subunit 'startTest' message.
        """
        self.assertForwardsToSubunit('startTest', self.test)


    def test_stopTestSendsSubunitStopTest(self):
        """
        SubunitReporter.stopTest() sends the subunit 'stopTest' message.
        """
        self.assertForwardsToSubunit('stopTest', self.test)


    def test_addSuccessSendsSubunitAddSuccess(self):
        """
        SubunitReporter.addSuccess() sends the subunit 'addSuccess' message.
        """
        self.assertForwardsToSubunit('addSuccess', self.test)


    def test_addErrorSendsSubunitAddError(self):
        """
        SubunitReporter.addError() sends the subunit 'addError' message.
        """
        try:
            1 / 0
        except ZeroDivisionError:
            error = sys.exc_info()
        self.assertForwardsToSubunit('addError', self.test, error)


    def test_addFailureSendsSubunitAddFailure(self):
        """
        SubunitReporter.addFailure() sends the subunit 'addFailure' message.
        """
        try:
            self.fail('hello')
        except self.failureException:
            failure = sys.exc_info()
        self.assertForwardsToSubunit('addFailure', self.test, failure)


    def test_addUnexpectedSuccessSendsSubunitAddSuccess(self):
        """
        SubunitReporter.addFailure() sends the subunit 'addSuccess' message,
        since subunit doesn't model unexpected success.
        """
        stream = BytesIO()
        subunitClient = reporter.TestProtocolClient(stream)
        subunitClient.addSuccess(self.test)
        subunitOutput = stream.getvalue()
        self.result.addUnexpectedSuccess(self.test)
        self.assertEqual(subunitOutput, self.stream.getvalue())


    def test_loadTimeErrors(self):
        """
        Load-time errors are reported like normal errors.
        """
        test = runner.TestLoader().loadByName('doesntexist')
        test.run(self.result)
        output = self.stream.getvalue()
        # Just check that 'doesntexist' is in the output, rather than
        # assembling the expected stack trace.
        self.assertIn(b'doesntexist', output)



class SubunitReporterNotInstalledTests(unittest.SynchronousTestCase):
    """
    Test behaviour when the subunit reporter is not installed.
    """

    def test_subunitNotInstalled(self):
        """
        If subunit is not installed, TestProtocolClient will be None, and
        SubunitReporter will raise an error when you try to construct it.
        """
        stream = NativeStringIO()
        self.patch(reporter, 'TestProtocolClient', None)
        e = self.assertRaises(Exception, reporter.SubunitReporter, stream)
        self.assertEqual("Subunit not available", str(e))



class TimingReporterTests(ReporterTests):
    resultFactory = reporter.TimingTextReporter



class LoggingReporter(reporter.Reporter):
    """
    Simple reporter that stores the last test that was passed to it.
    """

    def __init__(self, *args, **kwargs):
        reporter.Reporter.__init__(self, *args, **kwargs)
        self.test = None

    def addError(self, test, error):
        self.test = test

    def addExpectedFailure(self, test, failure, todo=None):
        self.test = test

    def addFailure(self, test, failure):
        self.test = test

    def addSkip(self, test, skip):
        self.test = test

    def addUnexpectedSuccess(self, test, todo=None):
        self.test = test

    def startTest(self, test):
        self.test = test

    def stopTest(self, test):
        self.test = test



class AdaptedReporterTests(unittest.SynchronousTestCase):
    """
    L{reporter._AdaptedReporter} is a reporter wrapper that wraps all of the
    tests it receives before passing them on to the original reporter.
    """

    def setUp(self):
        self.wrappedResult = self.getWrappedResult()


    def _testAdapter(self, test):
        return test.id()


    def assertWrapped(self, wrappedResult, test):
        self.assertEqual(wrappedResult._originalReporter.test,
                         self._testAdapter(test))


    def getFailure(self, exceptionInstance):
        """
        Return a L{Failure} from raising the given exception.

        @param exceptionInstance: The exception to raise.
        @return: L{Failure}
        """
        try:
            raise exceptionInstance
        except:
            return Failure()


    def getWrappedResult(self):
        result = LoggingReporter()
        return reporter._AdaptedReporter(result, self._testAdapter)


    def test_addError(self):
        """
        C{addError} wraps its test with the provided adapter.
        """
        self.wrappedResult.addError(self, self.getFailure(RuntimeError()))
        self.assertWrapped(self.wrappedResult, self)


    def test_addFailure(self):
        """
        C{addFailure} wraps its test with the provided adapter.
        """
        self.wrappedResult.addFailure(self, self.getFailure(AssertionError()))
        self.assertWrapped(self.wrappedResult, self)


    def test_addSkip(self):
        """
        C{addSkip} wraps its test with the provided adapter.
        """
        self.wrappedResult.addSkip(
            self, self.getFailure(SkipTest('no reason')))
        self.assertWrapped(self.wrappedResult, self)


    def test_startTest(self):
        """
        C{startTest} wraps its test with the provided adapter.
        """
        self.wrappedResult.startTest(self)
        self.assertWrapped(self.wrappedResult, self)


    def test_stopTest(self):
        """
        C{stopTest} wraps its test with the provided adapter.
        """
        self.wrappedResult.stopTest(self)
        self.assertWrapped(self.wrappedResult, self)


    def test_addExpectedFailure(self):
        """
        C{addExpectedFailure} wraps its test with the provided adapter.
        """
        self.wrappedResult.addExpectedFailure(
            self, self.getFailure(RuntimeError()), Todo("no reason"))
        self.assertWrapped(self.wrappedResult, self)


    def test_expectedFailureWithoutTodo(self):
        """
        C{addExpectedFailure} works without a C{Todo}.
        """
        self.wrappedResult.addExpectedFailure(
            self, self.getFailure(RuntimeError()))
        self.assertWrapped(self.wrappedResult, self)


    def test_addUnexpectedSuccess(self):
        """
        C{addUnexpectedSuccess} wraps its test with the provided adapter.
        """
        self.wrappedResult.addUnexpectedSuccess(self, Todo("no reason"))
        self.assertWrapped(self.wrappedResult, self)


    def test_unexpectedSuccessWithoutTodo(self):
        """
        C{addUnexpectedSuccess} works without a C{Todo}.
        """
        self.wrappedResult.addUnexpectedSuccess(self)
        self.assertWrapped(self.wrappedResult, self)



class FakeStream(object):
    """
    A fake stream which C{isatty} method returns some predictable.

    @ivar tty: returned value of C{isatty}.
    @type tty: C{bool}
    """

    def __init__(self, tty=True):
        self.tty = tty


    def isatty(self):
        return self.tty



class AnsiColorizerTests(unittest.SynchronousTestCase):
    """
    Tests for L{reporter._AnsiColorizer}.
    """

    def setUp(self):
        self.savedModules = sys.modules.copy()


    def tearDown(self):
        sys.modules.clear()
        sys.modules.update(self.savedModules)


    def test_supportedStdOutTTY(self):
        """
        L{reporter._AnsiColorizer.supported} returns C{False} if the given
        stream is not a TTY.
        """
        self.assertFalse(reporter._AnsiColorizer.supported(FakeStream(False)))


    def test_supportedNoCurses(self):
        """
        L{reporter._AnsiColorizer.supported} returns C{False} if the curses
        module can't be imported.
        """
        sys.modules['curses'] = None
        self.assertFalse(reporter._AnsiColorizer.supported(FakeStream()))


    def test_supportedSetupTerm(self):
        """
        L{reporter._AnsiColorizer.supported} returns C{True} if
        C{curses.tigetnum} returns more than 2 supported colors. It only tries
        to call C{curses.setupterm} if C{curses.tigetnum} previously failed
        with a C{curses.error}.
        """
        class fakecurses(object):
            error = RuntimeError
            setUp = 0

            def setupterm(self):
                self.setUp += 1

            def tigetnum(self, value):
                if self.setUp:
                    return 3
                else:
                    raise self.error()

        sys.modules['curses'] = fakecurses()
        self.assertTrue(reporter._AnsiColorizer.supported(FakeStream()))
        self.assertTrue(reporter._AnsiColorizer.supported(FakeStream()))

        self.assertEqual(sys.modules['curses'].setUp, 1)


    def test_supportedTigetNumWrongError(self):
        """
        L{reporter._AnsiColorizer.supported} returns C{False} and doesn't try
        to call C{curses.setupterm} if C{curses.tigetnum} returns something
        different than C{curses.error}.
        """
        class fakecurses(object):
            error = RuntimeError

            def tigetnum(self, value):
                raise ValueError()

        sys.modules['curses'] = fakecurses()
        self.assertFalse(reporter._AnsiColorizer.supported(FakeStream()))


    def test_supportedTigetNumNotEnoughColor(self):
        """
        L{reporter._AnsiColorizer.supported} returns C{False} if
        C{curses.tigetnum} returns less than 2 supported colors.
        """
        class fakecurses(object):
            error = RuntimeError

            def tigetnum(self, value):
                return 1

        sys.modules['curses'] = fakecurses()
        self.assertFalse(reporter._AnsiColorizer.supported(FakeStream()))


    def test_supportedTigetNumErrors(self):
        """
        L{reporter._AnsiColorizer.supported} returns C{False} if
        C{curses.tigetnum} raises an error, and calls C{curses.setupterm} once.
        """
        class fakecurses(object):
            error = RuntimeError
            setUp = 0

            def setupterm(self):
                self.setUp += 1

            def tigetnum(self, value):
                raise self.error()

        sys.modules['curses'] = fakecurses()
        self.assertFalse(reporter._AnsiColorizer.supported(FakeStream()))
        self.assertEqual(sys.modules['curses'].setUp, 1)



class ExitWrapperTests(unittest.SynchronousTestCase):
    """
    Tests for L{reporter._ExitWrapper}.
    """

    def setUp(self):
        self.failure = Failure(Exception("I am a Failure"))
        self.test = sample.FooTest('test_foo')
        self.result = reporter.TestResult()
        self.wrapped = _ExitWrapper(self.result)
        self.assertFalse(self.wrapped.shouldStop)


    def test_stopOnFailure(self):
        """
        L{reporter._ExitWrapper} causes a wrapped reporter to stop after its
        first failure.
        """
        self.wrapped.addFailure(self.test, self.failure)
        self.assertTrue(self.wrapped.shouldStop)
        self.assertEqual(self.result.failures, [(self.test, self.failure)])


    def test_stopOnError(self):
        """
        L{reporter._ExitWrapper} causes a wrapped reporter to stop after its
        first error.
        """
        self.wrapped.addError(self.test, self.failure)
        self.assertTrue(self.wrapped.shouldStop)
        self.assertEqual(self.result.errors, [(self.test, self.failure)])


    def test_doesNotStopOnUnexpectedSuccess(self):
        """
        L{reporter._ExitWrapper} does not cause a wrapped reporter to stop
        after an unexpected success.
        """
        self.wrapped.addUnexpectedSuccess(self.test, self.failure)
        self.assertFalse(self.wrapped.shouldStop)
        self.assertEqual(
            self.result.unexpectedSuccesses, [(self.test, self.failure)])
