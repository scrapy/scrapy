# -*- test-case-name: twisted.trial.test.test_reporter -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
#
# Maintainer: Jonathan Lange

"""
Defines classes that handle the results of tests.
"""

from __future__ import division, absolute_import

import sys
import os
import time
import warnings
import unittest as pyunit

from collections import OrderedDict

from zope.interface import implementer

from twisted.python import reflect, log
from twisted.python.components import proxyForInterface
from twisted.python.failure import Failure
from twisted.python.util import untilConcludes
from twisted.python.compat import _PY3, items
from twisted.trial import itrial, util
from twisted.trial.unittest import makeTodo

try:
    from subunit import TestProtocolClient
except ImportError:
    TestProtocolClient = None


class BrokenTestCaseWarning(Warning):
    """
    Emitted as a warning when an exception occurs in one of setUp or tearDown.
    """


class SafeStream(object):
    """
    Wraps a stream object so that all C{write} calls are wrapped in
    L{untilConcludes<twisted.python.util.untilConcludes>}.
    """

    def __init__(self, original):
        self.original = original

    def __getattr__(self, name):
        return getattr(self.original, name)

    def write(self, *a, **kw):
        return untilConcludes(self.original.write, *a, **kw)



@implementer(itrial.IReporter)
class TestResult(pyunit.TestResult, object):
    """
    Accumulates the results of several L{twisted.trial.unittest.TestCase}s.

    @ivar successes: count the number of successes achieved by the test run.
    @type successes: C{int}
    """

    # Used when no todo provided to addExpectedFailure or addUnexpectedSuccess.
    _DEFAULT_TODO = 'Test expected to fail'

    def __init__(self):
        super(TestResult, self).__init__()
        self.skips = []
        self.expectedFailures = []
        self.unexpectedSuccesses = []
        self.successes = 0
        self._timings = []


    def __repr__(self):
        return ('<%s run=%d errors=%d failures=%d todos=%d dones=%d skips=%d>'
                % (reflect.qual(self.__class__), self.testsRun,
                   len(self.errors), len(self.failures),
                   len(self.expectedFailures), len(self.skips),
                   len(self.unexpectedSuccesses)))


    def _getTime(self):
        return time.time()


    def _getFailure(self, error):
        """
        Convert a C{sys.exc_info()}-style tuple to a L{Failure}, if necessary.
        """
        if isinstance(error, tuple):
            return Failure(error[1], error[0], error[2])
        return error


    def startTest(self, test):
        """
        This must be called before the given test is commenced.

        @type test: L{pyunit.TestCase}
        """
        super(TestResult, self).startTest(test)
        self._testStarted = self._getTime()


    def stopTest(self, test):
        """
        This must be called after the given test is completed.

        @type test: L{pyunit.TestCase}
        """
        super(TestResult, self).stopTest(test)
        self._lastTime = self._getTime() - self._testStarted


    def addFailure(self, test, fail):
        """
        Report a failed assertion for the given test.

        @type test: L{pyunit.TestCase}
        @type fail: L{Failure} or L{tuple}
        """
        self.failures.append((test, self._getFailure(fail)))


    def addError(self, test, error):
        """
        Report an error that occurred while running the given test.

        @type test: L{pyunit.TestCase}
        @type error: L{Failure} or L{tuple}
        """
        self.errors.append((test, self._getFailure(error)))


    def addSkip(self, test, reason):
        """
        Report that the given test was skipped.

        In Trial, tests can be 'skipped'. Tests are skipped mostly because
        there is some platform or configuration issue that prevents them from
        being run correctly.

        @type test: L{pyunit.TestCase}
        @type reason: L{str}
        """
        self.skips.append((test, reason))


    def addUnexpectedSuccess(self, test, todo=None):
        """
        Report that the given test succeeded against expectations.

        In Trial, tests can be marked 'todo'. That is, they are expected to
        fail.  When a test that is expected to fail instead succeeds, it should
        call this method to report the unexpected success.

        @type test: L{pyunit.TestCase}
        @type todo: L{unittest.Todo}, or L{None}, in which case a default todo
            message is provided.
        """
        if todo is None:
            todo = makeTodo(self._DEFAULT_TODO)
        self.unexpectedSuccesses.append((test, todo))


    def addExpectedFailure(self, test, error, todo=None):
        """
        Report that the given test failed, and was expected to do so.

        In Trial, tests can be marked 'todo'. That is, they are expected to
        fail.

        @type test: L{pyunit.TestCase}
        @type error: L{Failure}
        @type todo: L{unittest.Todo}, or L{None}, in which case a default todo
            message is provided.
        """
        if todo is None:
            todo = makeTodo(self._DEFAULT_TODO)
        self.expectedFailures.append((test, error, todo))


    def addSuccess(self, test):
        """
        Report that the given test succeeded.

        @type test: L{pyunit.TestCase}
        """
        self.successes += 1


    def wasSuccessful(self):
        """
        Report whether or not this test suite was successful or not.

        The behaviour of this method changed in L{pyunit} in Python 3.4 to
        fail if there are any errors, failures, or unexpected successes.
        Previous to 3.4, it was only if there were errors or failures. This
        method implements the old behaviour for backwards compatibility reasons,
        checking just for errors and failures.

        @rtype: L{bool}
        """
        return len(self.failures) == len(self.errors) == 0


    def done(self):
        """
        The test suite has finished running.
        """



@implementer(itrial.IReporter)
class TestResultDecorator(proxyForInterface(itrial.IReporter,
                                            "_originalReporter")):
    """
    Base class for TestResult decorators.

    @ivar _originalReporter: The wrapped instance of reporter.
    @type _originalReporter: A provider of L{itrial.IReporter}
    """



@implementer(itrial.IReporter)
class UncleanWarningsReporterWrapper(TestResultDecorator):
    """
    A wrapper for a reporter that converts L{util.DirtyReactorAggregateError}s
    to warnings.
    """

    def addError(self, test, error):
        """
        If the error is a L{util.DirtyReactorAggregateError}, instead of
        reporting it as a normal error, throw a warning.
        """

        if (isinstance(error, Failure)
            and error.check(util.DirtyReactorAggregateError)):
            warnings.warn(error.getErrorMessage())
        else:
            self._originalReporter.addError(test, error)



@implementer(itrial.IReporter)
class _ExitWrapper(TestResultDecorator):
    """
    A wrapper for a reporter that causes the reporter to stop after
    unsuccessful tests.
    """

    def addError(self, *args, **kwargs):
        self.shouldStop = True
        return self._originalReporter.addError(*args, **kwargs)


    def addFailure(self, *args, **kwargs):
        self.shouldStop = True
        return self._originalReporter.addFailure(*args, **kwargs)



class _AdaptedReporter(TestResultDecorator):
    """
    TestResult decorator that makes sure that addError only gets tests that
    have been adapted with a particular test adapter.
    """

    def __init__(self, original, testAdapter):
        """
        Construct an L{_AdaptedReporter}.

        @param original: An {itrial.IReporter}.
        @param testAdapter: A callable that returns an L{itrial.ITestCase}.
        """
        TestResultDecorator.__init__(self, original)
        self.testAdapter = testAdapter


    def addError(self, test, error):
        """
        See L{itrial.IReporter}.
        """
        test = self.testAdapter(test)
        return self._originalReporter.addError(test, error)


    def addExpectedFailure(self, test, failure, todo=None):
        """
        See L{itrial.IReporter}.

        @type test: A L{pyunit.TestCase}.
        @type failure: A L{failure.Failure} or L{exceptions.AssertionError}
        @type todo: A L{unittest.Todo} or None

        When C{todo} is L{None} a generic C{unittest.Todo} is built.

        L{pyunit.TestCase}'s C{run()} calls this with 3 positional arguments
        (without C{todo}).
        """
        return self._originalReporter.addExpectedFailure(
            self.testAdapter(test), failure, todo)


    def addFailure(self, test, failure):
        """
        See L{itrial.IReporter}.
        """
        test = self.testAdapter(test)
        return self._originalReporter.addFailure(test, failure)


    def addSkip(self, test, skip):
        """
        See L{itrial.IReporter}.
        """
        test = self.testAdapter(test)
        return self._originalReporter.addSkip(test, skip)


    def addUnexpectedSuccess(self, test, todo=None):
        """
        See L{itrial.IReporter}.

        @type test: A L{pyunit.TestCase}.
        @type todo: A L{unittest.Todo} or None

        When C{todo} is L{None} a generic C{unittest.Todo} is built.

        L{pyunit.TestCase}'s C{run()} calls this with 2 positional arguments
        (without C{todo}).
        """
        test = self.testAdapter(test)
        return self._originalReporter.addUnexpectedSuccess(test, todo)


    def startTest(self, test):
        """
        See L{itrial.IReporter}.
        """
        return self._originalReporter.startTest(self.testAdapter(test))


    def stopTest(self, test):
        """
        See L{itrial.IReporter}.
        """
        return self._originalReporter.stopTest(self.testAdapter(test))



@implementer(itrial.IReporter)
class Reporter(TestResult):
    """
    A basic L{TestResult} with support for writing to a stream.

    @ivar _startTime: The time when the first test was started. It defaults to
        L{None}, which means that no test was actually launched.
    @type _startTime: C{float} or L{None}

    @ivar _warningCache: A C{set} of tuples of warning message (file, line,
        text, category) which have already been written to the output stream
        during the currently executing test.  This is used to avoid writing
        duplicates of the same warning to the output stream.
    @type _warningCache: C{set}

    @ivar _publisher: The log publisher which will be observed for warning
        events.
    @type _publisher: L{twisted.python.log.LogPublisher}
    """

    _separator = '-' * 79
    _doubleSeparator = '=' * 79

    def __init__(self, stream=sys.stdout, tbformat='default', realtime=False,
                 publisher=None):
        super(Reporter, self).__init__()
        self._stream = SafeStream(stream)
        self.tbformat = tbformat
        self.realtime = realtime
        self._startTime = None
        self._warningCache = set()

        # Start observing log events so as to be able to report warnings.
        self._publisher = publisher
        if publisher is not None:
            publisher.addObserver(self._observeWarnings)


    def _observeWarnings(self, event):
        """
        Observe warning events and write them to C{self._stream}.

        This method is a log observer which will be registered with
        C{self._publisher.addObserver}.

        @param event: A C{dict} from the logging system.  If it has a
            C{'warning'} key, a logged warning will be extracted from it and
            possibly written to C{self.stream}.
        """
        if 'warning' in event:
            key = (event['filename'], event['lineno'],
                   event['category'].split('.')[-1],
                   str(event['warning']))
            if key not in self._warningCache:
                self._warningCache.add(key)
                self._stream.write('%s:%s: %s: %s\n' % key)


    def startTest(self, test):
        """
        Called when a test begins to run. Records the time when it was first
        called and resets the warning cache.

        @param test: L{ITestCase}
        """
        super(Reporter, self).startTest(test)
        if self._startTime is None:
            self._startTime = self._getTime()
        self._warningCache = set()


    def addFailure(self, test, fail):
        """
        Called when a test fails. If C{realtime} is set, then it prints the
        error to the stream.

        @param test: L{ITestCase} that failed.
        @param fail: L{failure.Failure} containing the error.
        """
        super(Reporter, self).addFailure(test, fail)
        if self.realtime:
            fail = self.failures[-1][1] # guarantee it's a Failure
            self._write(self._formatFailureTraceback(fail))


    def addError(self, test, error):
        """
        Called when a test raises an error. If C{realtime} is set, then it
        prints the error to the stream.

        @param test: L{ITestCase} that raised the error.
        @param error: L{failure.Failure} containing the error.
        """
        error = self._getFailure(error)
        super(Reporter, self).addError(test, error)
        if self.realtime:
            error = self.errors[-1][1] # guarantee it's a Failure
            self._write(self._formatFailureTraceback(error))


    def _write(self, format, *args):
        """
        Safely write to the reporter's stream.

        @param format: A format string to write.
        @param *args: The arguments for the format string.
        """
        s = str(format)
        assert isinstance(s, type(''))
        if args:
            self._stream.write(s % args)
        else:
            self._stream.write(s)
        untilConcludes(self._stream.flush)


    def _writeln(self, format, *args):
        """
        Safely write a line to the reporter's stream. Newline is appended to
        the format string.

        @param format: A format string to write.
        @param *args: The arguments for the format string.
        """
        self._write(format, *args)
        self._write('\n')


    def upDownError(self, method, error, warn, printStatus):
        super(Reporter, self).upDownError(method, error, warn, printStatus)
        if warn:
            tbStr = self._formatFailureTraceback(error)
            log.msg(tbStr)
            msg = ("caught exception in %s, your TestCase is broken\n\n%s"
                   % (method, tbStr))
            warnings.warn(msg, BrokenTestCaseWarning, stacklevel=2)


    def cleanupErrors(self, errs):
        super(Reporter, self).cleanupErrors(errs)
        warnings.warn("%s\n%s" % ("REACTOR UNCLEAN! traceback(s) follow: ",
                                  self._formatFailureTraceback(errs)),
                      BrokenTestCaseWarning)


    def _trimFrames(self, frames):
        """
        Trim frames to remove internal paths.

        When a C{SynchronousTestCase} method fails synchronously, the stack
        looks like this:
         - [0]: C{SynchronousTestCase._run}
         - [1]: C{util.runWithWarningsSuppressed}
         - [2:-2]: code in the test method which failed
         - [-1]: C{_synctest.fail}

        When a C{TestCase} method fails synchronously, the stack looks like
        this:
         - [0]: C{defer.maybeDeferred}
         - [1]: C{utils.runWithWarningsSuppressed}
         - [2]: C{utils.runWithWarningsSuppressed}
         - [3:-2]: code in the test method which failed
         - [-1]: C{_synctest.fail}

        When a method fails inside a C{Deferred} (i.e., when the test method
        returns a C{Deferred}, and that C{Deferred}'s errback fires), the stack
        captured inside the resulting C{Failure} looks like this:
         - [0]: C{defer.Deferred._runCallbacks}
         - [1:-2]: code in the testmethod which failed
         - [-1]: C{_synctest.fail}

        As a result, we want to trim either [maybeDeferred, runWWS, runWWS] or
        [Deferred._runCallbacks] or [SynchronousTestCase._run, runWWS] from the
        front, and trim the [unittest.fail] from the end.

        There is also another case, when the test method is badly defined and
        contains extra arguments.

        If it doesn't recognize one of these cases, it just returns the
        original frames.

        @param frames: The C{list} of frames from the test failure.

        @return: The C{list} of frames to display.
        """
        newFrames = list(frames)

        if len(frames) < 2:
            return newFrames

        firstMethod = newFrames[0][0]
        firstFile = os.path.splitext(os.path.basename(newFrames[0][1]))[0]

        secondMethod = newFrames[1][0]
        secondFile = os.path.splitext(os.path.basename(newFrames[1][1]))[0]

        syncCase = (("_run", "_synctest"),
                    ("runWithWarningsSuppressed", "util"))
        asyncCase = (("maybeDeferred", "defer"),
                     ("runWithWarningsSuppressed", "utils"))

        twoFrames = ((firstMethod, firstFile), (secondMethod, secondFile))

        if _PY3:
            # On PY3, we have an extra frame which is reraising the exception
            for frame in newFrames:
                frameFile = os.path.splitext(os.path.basename(frame[1]))[0]
                if frameFile == "compat" and frame[0] == "reraise":
                    # If it's in the compat module and is reraise, BLAM IT
                    newFrames.pop(newFrames.index(frame))

        if twoFrames == syncCase:
            newFrames = newFrames[2:]
        elif twoFrames == asyncCase:
            newFrames = newFrames[3:]
        elif (firstMethod, firstFile) == ("_runCallbacks", "defer"):
            newFrames = newFrames[1:]

        if not newFrames:
            # The method fails before getting called, probably an argument
            # problem
            return newFrames

        last = newFrames[-1]
        if (last[0].startswith('fail')
            and os.path.splitext(os.path.basename(last[1]))[0] == '_synctest'):
            newFrames = newFrames[:-1]

        return newFrames


    def _formatFailureTraceback(self, fail):
        if isinstance(fail, str):
            return fail.rstrip() + '\n'
        fail.frames, frames = self._trimFrames(fail.frames), fail.frames
        result = fail.getTraceback(detail=self.tbformat,
                                   elideFrameworkCode=True)
        fail.frames = frames
        return result


    def _groupResults(self, results, formatter):
        """
        Group tests together based on their results.

        @param results: An iterable of tuples of two or more elements.  The
            first element of each tuple is a test case.  The remaining
            elements describe the outcome of that test case.

        @param formatter: A callable which turns a test case result into a
            string.  The elements after the first of the tuples in
            C{results} will be passed as positional arguments to
            C{formatter}.

        @return: A C{list} of two-tuples.  The first element of each tuple
            is a unique string describing one result from at least one of
            the test cases in C{results}.  The second element is a list of
            the test cases which had that result.
        """
        groups = OrderedDict()
        for content in results:
            case = content[0]
            outcome = content[1:]
            key = formatter(*outcome)
            groups.setdefault(key, []).append(case)
        return items(groups)


    def _printResults(self, flavor, errors, formatter):
        """
        Print a group of errors to the stream.

        @param flavor: A string indicating the kind of error (e.g. 'TODO').
        @param errors: A list of errors, often L{failure.Failure}s, but
            sometimes 'todo' errors.
        @param formatter: A callable that knows how to format the errors.
        """
        for reason, cases in self._groupResults(errors, formatter):
            self._writeln(self._doubleSeparator)
            self._writeln(flavor)
            self._write(reason)
            self._writeln('')
            for case in cases:
                self._writeln(case.id())


    def _printExpectedFailure(self, error, todo):
        return 'Reason: %r\n%s' % (todo.reason,
                                   self._formatFailureTraceback(error))


    def _printUnexpectedSuccess(self, todo):
        ret = 'Reason: %r\n' % (todo.reason,)
        if todo.errors:
            ret += 'Expected errors: %s\n' % (', '.join(todo.errors),)
        return ret


    def _printErrors(self):
        """
        Print all of the non-success results to the stream in full.
        """
        self._write('\n')
        self._printResults('[SKIPPED]', self.skips, lambda x: '%s\n' % x)
        self._printResults('[TODO]', self.expectedFailures,
                           self._printExpectedFailure)
        self._printResults('[FAIL]', self.failures,
                           self._formatFailureTraceback)
        self._printResults('[ERROR]', self.errors,
                           self._formatFailureTraceback)
        self._printResults('[SUCCESS!?!]', self.unexpectedSuccesses,
                           self._printUnexpectedSuccess)


    def _getSummary(self):
        """
        Return a formatted count of tests status results.
        """
        summaries = []
        for stat in ("skips", "expectedFailures", "failures", "errors",
                     "unexpectedSuccesses"):
            num = len(getattr(self, stat))
            if num:
                summaries.append('%s=%d' % (stat, num))
        if self.successes:
            summaries.append('successes=%d' % (self.successes,))
        summary = (summaries and ' (' + ', '.join(summaries) + ')') or ''
        return summary


    def _printSummary(self):
        """
        Print a line summarising the test results to the stream.
        """
        summary = self._getSummary()
        if self.wasSuccessful():
            status = "PASSED"
        else:
            status = "FAILED"
        self._write("%s%s\n", status, summary)


    def done(self):
        """
        Summarize the result of the test run.

        The summary includes a report of all of the errors, todos, skips and
        so forth that occurred during the run. It also includes the number of
        tests that were run and how long it took to run them (not including
        load time).

        Expects that C{_printErrors}, C{_writeln}, C{_write}, C{_printSummary}
        and C{_separator} are all implemented.
        """
        if self._publisher is not None:
            self._publisher.removeObserver(self._observeWarnings)
        self._printErrors()
        self._writeln(self._separator)
        if self._startTime is not None:
            self._writeln('Ran %d tests in %.3fs', self.testsRun,
                          time.time() - self._startTime)
        self._write('\n')
        self._printSummary()



class MinimalReporter(Reporter):
    """
    A minimalist reporter that prints only a summary of the test result, in
    the form of (timeTaken, #tests, #tests, #errors, #failures, #skips).
    """

    def _printErrors(self):
        """
        Don't print a detailed summary of errors. We only care about the
        counts.
        """


    def _printSummary(self):
        """
        Print out a one-line summary of the form:
        '%(runtime) %(number_of_tests) %(number_of_tests) %(num_errors)
        %(num_failures) %(num_skips)'
        """
        numTests = self.testsRun
        if self._startTime is not None:
            timing = self._getTime() - self._startTime
        else:
            timing = 0
        t = (timing, numTests, numTests,
             len(self.errors), len(self.failures), len(self.skips))
        self._writeln(' '.join(map(str, t)))



class TextReporter(Reporter):
    """
    Simple reporter that prints a single character for each test as it runs,
    along with the standard Trial summary text.
    """

    def addSuccess(self, test):
        super(TextReporter, self).addSuccess(test)
        self._write('.')


    def addError(self, *args):
        super(TextReporter, self).addError(*args)
        self._write('E')


    def addFailure(self, *args):
        super(TextReporter, self).addFailure(*args)
        self._write('F')


    def addSkip(self, *args):
        super(TextReporter, self).addSkip(*args)
        self._write('S')


    def addExpectedFailure(self, *args):
        super(TextReporter, self).addExpectedFailure(*args)
        self._write('T')


    def addUnexpectedSuccess(self, *args):
        super(TextReporter, self).addUnexpectedSuccess(*args)
        self._write('!')



class VerboseTextReporter(Reporter):
    """
    A verbose reporter that prints the name of each test as it is running.

    Each line is printed with the name of the test, followed by the result of
    that test.
    """

    # This is actually the bwverbose option

    def startTest(self, tm):
        self._write('%s ... ', tm.id())
        super(VerboseTextReporter, self).startTest(tm)


    def addSuccess(self, test):
        super(VerboseTextReporter, self).addSuccess(test)
        self._write('[OK]')


    def addError(self, *args):
        super(VerboseTextReporter, self).addError(*args)
        self._write('[ERROR]')


    def addFailure(self, *args):
        super(VerboseTextReporter, self).addFailure(*args)
        self._write('[FAILURE]')


    def addSkip(self, *args):
        super(VerboseTextReporter, self).addSkip(*args)
        self._write('[SKIPPED]')


    def addExpectedFailure(self, *args):
        super(VerboseTextReporter, self).addExpectedFailure(*args)
        self._write('[TODO]')


    def addUnexpectedSuccess(self, *args):
        super(VerboseTextReporter, self).addUnexpectedSuccess(*args)
        self._write('[SUCCESS!?!]')


    def stopTest(self, test):
        super(VerboseTextReporter, self).stopTest(test)
        self._write('\n')



class TimingTextReporter(VerboseTextReporter):
    """
    Prints out each test as it is running, followed by the time taken for each
    test to run.
    """

    def stopTest(self, method):
        """
        Mark the test as stopped, and write the time it took to run the test
        to the stream.
        """
        super(TimingTextReporter, self).stopTest(method)
        self._write("(%.03f secs)\n" % self._lastTime)



class _AnsiColorizer(object):
    """
    A colorizer is an object that loosely wraps around a stream, allowing
    callers to write text to the stream in a particular color.

    Colorizer classes must implement C{supported()} and C{write(text, color)}.
    """
    _colors = dict(black=30, red=31, green=32, yellow=33,
                   blue=34, magenta=35, cyan=36, white=37)

    def __init__(self, stream):
        self.stream = stream

    def supported(cls, stream=sys.stdout):
        """
        A class method that returns True if the current platform supports
        coloring terminal output using this method. Returns False otherwise.
        """
        if not stream.isatty():
            return False # auto color only on TTYs
        try:
            import curses
        except ImportError:
            return False
        else:
            try:
                try:
                    return curses.tigetnum("colors") > 2
                except curses.error:
                    curses.setupterm()
                    return curses.tigetnum("colors") > 2
            except:
                # guess false in case of error
                return False
    supported = classmethod(supported)

    def write(self, text, color):
        """
        Write the given text to the stream in the given color.

        @param text: Text to be written to the stream.

        @param color: A string label for a color. e.g. 'red', 'white'.
        """
        color = self._colors[color]
        self.stream.write('\x1b[%s;1m%s\x1b[0m' % (color, text))


class _Win32Colorizer(object):
    """
    See _AnsiColorizer docstring.
    """
    def __init__(self, stream):
        from win32console import GetStdHandle, STD_OUTPUT_HANDLE, \
             FOREGROUND_RED, FOREGROUND_BLUE, FOREGROUND_GREEN, \
             FOREGROUND_INTENSITY
        red, green, blue, bold = (FOREGROUND_RED, FOREGROUND_GREEN,
                                  FOREGROUND_BLUE, FOREGROUND_INTENSITY)
        self.stream = stream
        self.screenBuffer = GetStdHandle(STD_OUTPUT_HANDLE)
        self._colors = {
            'normal': red | green | blue,
            'red': red | bold,
            'green': green | bold,
            'blue': blue | bold,
            'yellow': red | green | bold,
            'magenta': red | blue | bold,
            'cyan': green | blue | bold,
            'white': red | green | blue | bold
            }

    def supported(cls, stream=sys.stdout):
        try:
            import win32console
            screenBuffer = win32console.GetStdHandle(
                win32console.STD_OUTPUT_HANDLE)
        except ImportError:
            return False
        import pywintypes
        try:
            screenBuffer.SetConsoleTextAttribute(
                win32console.FOREGROUND_RED |
                win32console.FOREGROUND_GREEN |
                win32console.FOREGROUND_BLUE)
        except pywintypes.error:
            return False
        else:
            return True
    supported = classmethod(supported)

    def write(self, text, color):
        color = self._colors[color]
        self.screenBuffer.SetConsoleTextAttribute(color)
        self.stream.write(text)
        self.screenBuffer.SetConsoleTextAttribute(self._colors['normal'])


class _NullColorizer(object):
    """
    See _AnsiColorizer docstring.
    """
    def __init__(self, stream):
        self.stream = stream

    def supported(cls, stream=sys.stdout):
        return True
    supported = classmethod(supported)

    def write(self, text, color):
        self.stream.write(text)



@implementer(itrial.IReporter)
class SubunitReporter(object):
    """
    Reports test output via Subunit.

    @ivar _subunit: The subunit protocol client that we are wrapping.

    @ivar _successful: An internal variable, used to track whether we have
        received only successful results.

    @since: 10.0
    """

    def __init__(self, stream=sys.stdout, tbformat='default',
                 realtime=False, publisher=None):
        """
        Construct a L{SubunitReporter}.

        @param stream: A file-like object representing the stream to print
            output to. Defaults to stdout.
        @param tbformat: The format for tracebacks. Ignored, since subunit
            always uses Python's standard format.
        @param realtime: Whether or not to print exceptions in the middle
            of the test results. Ignored, since subunit always does this.
        @param publisher: The log publisher which will be preserved for
            reporting events. Ignored, as it's not relevant to subunit.
        """
        if TestProtocolClient is None:
            raise Exception("Subunit not available")
        self._subunit = TestProtocolClient(stream)
        self._successful = True


    def done(self):
        """
        Record that the entire test suite run is finished.

        We do nothing, since a summary clause is irrelevant to the subunit
        protocol.
        """
        pass


    def shouldStop(self):
        """
        Whether or not the test runner should stop running tests.
        """
        return self._subunit.shouldStop
    shouldStop = property(shouldStop)


    def stop(self):
        """
        Signal that the test runner should stop running tests.
        """
        return self._subunit.stop()


    def wasSuccessful(self):
        """
        Has the test run been successful so far?

        @return: C{True} if we have received no reports of errors or failures,
            C{False} otherwise.
        """
        # Subunit has a bug in its implementation of wasSuccessful, see
        # https://bugs.edge.launchpad.net/subunit/+bug/491090, so we can't
        # simply forward it on.
        return self._successful


    def startTest(self, test):
        """
        Record that C{test} has started.
        """
        return self._subunit.startTest(test)


    def stopTest(self, test):
        """
        Record that C{test} has completed.
        """
        return self._subunit.stopTest(test)


    def addSuccess(self, test):
        """
        Record that C{test} was successful.
        """
        return self._subunit.addSuccess(test)


    def addSkip(self, test, reason):
        """
        Record that C{test} was skipped for C{reason}.

        Some versions of subunit don't have support for addSkip. In those
        cases, the skip is reported as a success.

        @param test: A unittest-compatible C{TestCase}.
        @param reason: The reason for it being skipped. The C{str()} of this
            object will be included in the subunit output stream.
        """
        addSkip = getattr(self._subunit, 'addSkip', None)
        if addSkip is None:
            self.addSuccess(test)
        else:
            self._subunit.addSkip(test, reason)


    def addError(self, test, err):
        """
        Record that C{test} failed with an unexpected error C{err}.

        Also marks the run as being unsuccessful, causing
        L{SubunitReporter.wasSuccessful} to return C{False}.
        """
        self._successful = False
        return self._subunit.addError(
            test, util.excInfoOrFailureToExcInfo(err))


    def addFailure(self, test, err):
        """
        Record that C{test} failed an assertion with the error C{err}.

        Also marks the run as being unsuccessful, causing
        L{SubunitReporter.wasSuccessful} to return C{False}.
        """
        self._successful = False
        return self._subunit.addFailure(
            test, util.excInfoOrFailureToExcInfo(err))


    def addExpectedFailure(self, test, failure, todo):
        """
        Record an expected failure from a test.

        Some versions of subunit do not implement this. For those versions, we
        record a success.
        """
        failure = util.excInfoOrFailureToExcInfo(failure)
        addExpectedFailure = getattr(self._subunit, 'addExpectedFailure', None)
        if addExpectedFailure is None:
            self.addSuccess(test)
        else:
            addExpectedFailure(test, failure)


    def addUnexpectedSuccess(self, test, todo=None):
        """
        Record an unexpected success.

        Since subunit has no way of expressing this concept, we record a
        success on the subunit stream.
        """
        # Not represented in pyunit/subunit.
        self.addSuccess(test)



class TreeReporter(Reporter):
    """
    Print out the tests in the form a tree.

    Tests are indented according to which class and module they belong.
    Results are printed in ANSI color.
    """

    currentLine = ''
    indent = '  '
    columns = 79

    FAILURE = 'red'
    ERROR = 'red'
    TODO = 'blue'
    SKIP = 'blue'
    TODONE = 'red'
    SUCCESS = 'green'

    def __init__(self, stream=sys.stdout, *args, **kwargs):
        super(TreeReporter, self).__init__(stream, *args, **kwargs)
        self._lastTest = []
        for colorizer in [_Win32Colorizer, _AnsiColorizer, _NullColorizer]:
            if colorizer.supported(stream):
                self._colorizer = colorizer(stream)
                break

    def getDescription(self, test):
        """
        Return the name of the method which 'test' represents.  This is
        what gets displayed in the leaves of the tree.

        e.g. getDescription(TestCase('test_foo')) ==> test_foo
        """
        return test.id().split('.')[-1]

    def addSuccess(self, test):
        super(TreeReporter, self).addSuccess(test)
        self.endLine('[OK]', self.SUCCESS)

    def addError(self, *args):
        super(TreeReporter, self).addError(*args)
        self.endLine('[ERROR]', self.ERROR)

    def addFailure(self, *args):
        super(TreeReporter, self).addFailure(*args)
        self.endLine('[FAIL]', self.FAILURE)

    def addSkip(self, *args):
        super(TreeReporter, self).addSkip(*args)
        self.endLine('[SKIPPED]', self.SKIP)

    def addExpectedFailure(self, *args):
        super(TreeReporter, self).addExpectedFailure(*args)
        self.endLine('[TODO]', self.TODO)

    def addUnexpectedSuccess(self, *args):
        super(TreeReporter, self).addUnexpectedSuccess(*args)
        self.endLine('[SUCCESS!?!]', self.TODONE)

    def _write(self, format, *args):
        if args:
            format = format % args
        self.currentLine = format
        super(TreeReporter, self)._write(self.currentLine)


    def _getPreludeSegments(self, testID):
        """
        Return a list of all non-leaf segments to display in the tree.

        Normally this is the module and class name.
        """
        segments = testID.split('.')[:-1]
        if len(segments) == 0:
            return segments
        segments = [
            seg for seg in ('.'.join(segments[:-1]), segments[-1])
            if len(seg) > 0]
        return segments


    def _testPrelude(self, testID):
        """
        Write the name of the test to the stream, indenting it appropriately.

        If the test is the first test in a new 'branch' of the tree, also
        write all of the parents in that branch.
        """
        segments = self._getPreludeSegments(testID)
        indentLevel = 0
        for seg in segments:
            if indentLevel < len(self._lastTest):
                if seg != self._lastTest[indentLevel]:
                    self._write('%s%s\n' % (self.indent * indentLevel, seg))
            else:
                self._write('%s%s\n' % (self.indent * indentLevel, seg))
            indentLevel += 1
        self._lastTest = segments


    def cleanupErrors(self, errs):
        self._colorizer.write('    cleanup errors', self.ERROR)
        self.endLine('[ERROR]', self.ERROR)
        super(TreeReporter, self).cleanupErrors(errs)

    def upDownError(self, method, error, warn, printStatus):
        self._colorizer.write("  %s" % method, self.ERROR)
        if printStatus:
            self.endLine('[ERROR]', self.ERROR)
        super(TreeReporter, self).upDownError(method, error, warn, printStatus)

    def startTest(self, test):
        """
        Called when C{test} starts. Writes the tests name to the stream using
        a tree format.
        """
        self._testPrelude(test.id())
        self._write('%s%s ... ' % (self.indent * (len(self._lastTest)),
                                   self.getDescription(test)))
        super(TreeReporter, self).startTest(test)


    def endLine(self, message, color):
        """
        Print 'message' in the given color.

        @param message: A string message, usually '[OK]' or something similar.
        @param color: A string color, 'red', 'green' and so forth.
        """
        spaces = ' ' * (self.columns - len(self.currentLine) - len(message))
        super(TreeReporter, self)._write(spaces)
        self._colorizer.write(message, color)
        super(TreeReporter, self)._write("\n")


    def _printSummary(self):
        """
        Print a line summarising the test results to the stream, and color the
        status result.
        """
        summary = self._getSummary()
        if self.wasSuccessful():
            status = "PASSED"
            color = self.SUCCESS
        else:
            status = "FAILED"
            color = self.FAILURE
        self._colorizer.write(status, color)
        self._write("%s\n", summary)
