# -*- test-case-name: twisted.trial.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Things likely to be used by writers of unit tests.

Maintainer: Jonathan Lange
"""

from __future__ import division, absolute_import

import inspect
import os, warnings, sys, tempfile, types
from dis import findlinestarts as _findlinestarts

from twisted.python import failure, log, monkey
from twisted.python.reflect import fullyQualifiedName
from twisted.python.util import runWithWarningsSuppressed
from twisted.python.deprecate import (
    getDeprecationWarningString, warnAboutFunction)

from twisted.trial import itrial, util

import unittest as pyunit

# Python 2.7 and higher has skip support built-in
SkipTest = pyunit.SkipTest



class FailTest(AssertionError):
    """Raised to indicate the current test has failed to pass."""



class Todo(object):
    """
    Internal object used to mark a L{TestCase} as 'todo'. Tests marked 'todo'
    are reported differently in Trial L{TestResult}s. If todo'd tests fail,
    they do not fail the suite and the errors are reported in a separate
    category. If todo'd tests succeed, Trial L{TestResult}s will report an
    unexpected success.
    """

    def __init__(self, reason, errors=None):
        """
        @param reason: A string explaining why the test is marked 'todo'

        @param errors: An iterable of exception types that the test is
        expected to raise. If one of these errors is raised by the test, it
        will be trapped. Raising any other kind of error will fail the test.
        If L{None} is passed, then all errors will be trapped.
        """
        self.reason = reason
        self.errors = errors

    def __repr__(self):
        return "<Todo reason=%r errors=%r>" % (self.reason, self.errors)

    def expected(self, failure):
        """
        @param failure: A L{twisted.python.failure.Failure}.

        @return: C{True} if C{failure} is expected, C{False} otherwise.
        """
        if self.errors is None:
            return True
        for error in self.errors:
            if failure.check(error):
                return True
        return False


def makeTodo(value):
    """
    Return a L{Todo} object built from C{value}.

    If C{value} is a string, return a Todo that expects any exception with
    C{value} as a reason. If C{value} is a tuple, the second element is used
    as the reason and the first element as the excepted error(s).

    @param value: A string or a tuple of C{(errors, reason)}, where C{errors}
    is either a single exception class or an iterable of exception classes.

    @return: A L{Todo} object.
    """
    if isinstance(value, str):
        return Todo(reason=value)
    if isinstance(value, tuple):
        errors, reason = value
        try:
            errors = list(errors)
        except TypeError:
            errors = [errors]
        return Todo(reason=reason, errors=errors)



class _Warning(object):
    """
    A L{_Warning} instance represents one warning emitted through the Python
    warning system (L{warnings}).  This is used to insulate callers of
    L{_collectWarnings} from changes to the Python warnings system which might
    otherwise require changes to the warning objects that function passes to
    the observer object it accepts.

    @ivar message: The string which was passed as the message parameter to
        L{warnings.warn}.

    @ivar category: The L{Warning} subclass which was passed as the category
        parameter to L{warnings.warn}.

    @ivar filename: The name of the file containing the definition of the code
        object which was C{stacklevel} frames above the call to
        L{warnings.warn}, where C{stacklevel} is the value of the C{stacklevel}
        parameter passed to L{warnings.warn}.

    @ivar lineno: The source line associated with the active instruction of the
        code object object which was C{stacklevel} frames above the call to
        L{warnings.warn}, where C{stacklevel} is the value of the C{stacklevel}
        parameter passed to L{warnings.warn}.
    """
    def __init__(self, message, category, filename, lineno):
        self.message = message
        self.category = category
        self.filename = filename
        self.lineno = lineno


def _setWarningRegistryToNone(modules):
    """
    Disable the per-module cache for every module found in C{modules}, typically
    C{sys.modules}.

    @param modules: Dictionary of modules, typically sys.module dict
    """
    for v in list(modules.values()):
        if v is not None:
            try:
                v.__warningregistry__ = None
            except:
                # Don't specify a particular exception type to handle in case
                # some wacky object raises some wacky exception in response to
                # the setattr attempt.
                pass


def _collectWarnings(observeWarning, f, *args, **kwargs):
    """
    Call C{f} with C{args} positional arguments and C{kwargs} keyword arguments
    and collect all warnings which are emitted as a result in a list.

    @param observeWarning: A callable which will be invoked with a L{_Warning}
        instance each time a warning is emitted.

    @return: The return value of C{f(*args, **kwargs)}.
    """
    def showWarning(message, category, filename, lineno, file=None, line=None):
        assert isinstance(message, Warning)
        observeWarning(_Warning(
                message.args[0], category, filename, lineno))

    # Disable the per-module cache for every module otherwise if the warning
    # which the caller is expecting us to collect was already emitted it won't
    # be re-emitted by the call to f which happens below.
    _setWarningRegistryToNone(sys.modules)

    origFilters = warnings.filters[:]
    origShow = warnings.showwarning
    warnings.simplefilter('always')
    try:
        warnings.showwarning = showWarning
        result = f(*args, **kwargs)
    finally:
        warnings.filters[:] = origFilters
        warnings.showwarning = origShow
    return result



class UnsupportedTrialFeature(Exception):
    """A feature of twisted.trial was used that pyunit cannot support."""



class PyUnitResultAdapter(object):
    """
    Wrap a C{TestResult} from the standard library's C{unittest} so that it
    supports the extended result types from Trial, and also supports
    L{twisted.python.failure.Failure}s being passed to L{addError} and
    L{addFailure}.
    """

    def __init__(self, original):
        """
        @param original: A C{TestResult} instance from C{unittest}.
        """
        self.original = original


    def _exc_info(self, err):
        return util.excInfoOrFailureToExcInfo(err)


    def startTest(self, method):
        self.original.startTest(method)


    def stopTest(self, method):
        self.original.stopTest(method)


    def addFailure(self, test, fail):
        self.original.addFailure(test, self._exc_info(fail))


    def addError(self, test, error):
        self.original.addError(test, self._exc_info(error))


    def _unsupported(self, test, feature, info):
        self.original.addFailure(
            test,
            (UnsupportedTrialFeature,
             UnsupportedTrialFeature(feature, info),
             None))


    def addSkip(self, test, reason):
        """
        Report the skip as a failure.
        """
        self.original.addSkip(test, reason)


    def addUnexpectedSuccess(self, test, todo=None):
        """
        Report the unexpected success as a failure.
        """
        self._unsupported(test, 'unexpected success', todo)


    def addExpectedFailure(self, test, error):
        """
        Report the expected failure (i.e. todo) as a failure.
        """
        self._unsupported(test, 'expected failure', error)


    def addSuccess(self, test):
        self.original.addSuccess(test)


    def upDownError(self, method, error, warn, printStatus):
        pass



class _AssertRaisesContext(object):
    """
    A helper for implementing C{assertRaises}.  This is a context manager and a
    helper method to support the non-context manager version of
    C{assertRaises}.

    @ivar _testCase: See C{testCase} parameter of C{__init__}

    @ivar _expected: See C{expected} parameter of C{__init__}

    @ivar _returnValue: The value returned by the callable being tested (only
        when not being used as a context manager).

    @ivar _expectedName: A short string describing the expected exception
        (usually the name of the exception class).

    @ivar exception: The exception which was raised by the function being
        tested (if it raised one).
    """

    def __init__(self, testCase, expected):
        """
        @param testCase: The L{TestCase} instance which is used to raise a
            test-failing exception when that is necessary.

        @param expected: The exception type expected to be raised.
        """
        self._testCase = testCase
        self._expected = expected
        self._returnValue = None
        try:
            self._expectedName = self._expected.__name__
        except AttributeError:
            self._expectedName = str(self._expected)


    def _handle(self, obj):
        """
        Call the given object using this object as a context manager.

        @param obj: The object to call and which is expected to raise some
            exception.
        @type obj: L{object}

        @return: Whatever exception is raised by C{obj()}.
        @rtype: L{BaseException}
        """
        with self as context:
            self._returnValue = obj()
        return context.exception


    def __enter__(self):
        return self


    def __exit__(self, exceptionType, exceptionValue, traceback):
        """
        Check exit exception against expected exception.
        """
        # No exception raised.
        if exceptionType is None:
            self._testCase.fail(
                "{0} not raised ({1} returned)".format(
                    self._expectedName, self._returnValue)
                )

        if not isinstance(exceptionValue, exceptionType):
            # Support some Python 2.6 ridiculousness.  Exceptions raised using
            # the C API appear here as the arguments you might pass to the
            # exception class to create an exception instance.  So... do that
            # to turn them into the instances.
            if isinstance(exceptionValue, tuple):
                exceptionValue = exceptionType(*exceptionValue)
            else:
                exceptionValue = exceptionType(exceptionValue)

        # Store exception so that it can be access from context.
        self.exception = exceptionValue

        # Wrong exception raised.
        if not issubclass(exceptionType, self._expected):
            reason = failure.Failure(exceptionValue, exceptionType, traceback)
            self._testCase.fail(
                "{0} raised instead of {1}:\n {2}".format(
                    fullyQualifiedName(exceptionType),
                    self._expectedName, reason.getTraceback()),
                )

        # All good.
        return True



class _Assertions(pyunit.TestCase, object):
    """
    Replaces many of the built-in TestCase assertions. In general, these
    assertions provide better error messages and are easier to use in
    callbacks.
    """

    def fail(self, msg=None):
        """
        Absolutely fail the test.  Do not pass go, do not collect $200.

        @param msg: the message that will be displayed as the reason for the
        failure
        """
        raise self.failureException(msg)


    def assertFalse(self, condition, msg=None):
        """
        Fail the test if C{condition} evaluates to True.

        @param condition: any object that defines __nonzero__
        """
        super(_Assertions, self).assertFalse(condition, msg)
        return condition
    assertNot = failUnlessFalse = failIf = assertFalse


    def assertTrue(self, condition, msg=None):
        """
        Fail the test if C{condition} evaluates to False.

        @param condition: any object that defines __nonzero__
        """
        super(_Assertions, self).assertTrue(condition, msg)
        return condition
    assert_ = failUnlessTrue = failUnless = assertTrue


    def assertRaises(self, exception, f=None, *args, **kwargs):
        """
        Fail the test unless calling the function C{f} with the given
        C{args} and C{kwargs} raises C{exception}. The failure will report
        the traceback and call stack of the unexpected exception.

        @param exception: exception type that is to be expected
        @param f: the function to call

        @return: If C{f} is L{None}, a context manager which will make an
            assertion about the exception raised from the suite it manages.  If
            C{f} is not L{None}, the exception raised by C{f}.

        @raise self.failureException: Raised if the function call does
            not raise an exception or if it raises an exception of a
            different type.
        """
        context = _AssertRaisesContext(self, exception)
        if f is None:
            return context

        return context._handle(lambda: f(*args, **kwargs))
    failUnlessRaises = assertRaises


    def assertEqual(self, first, second, msg=None):
        """
        Fail the test if C{first} and C{second} are not equal.

        @param msg: A string describing the failure that's included in the
            exception.
        """
        super(_Assertions, self).assertEqual(first, second, msg)
        return first
    failUnlessEqual = failUnlessEquals = assertEquals = assertEqual


    def assertIs(self, first, second, msg=None):
        """
        Fail the test if C{first} is not C{second}.  This is an
        obect-identity-equality test, not an object equality
        (i.e. C{__eq__}) test.

        @param msg: if msg is None, then the failure message will be
        '%r is not %r' % (first, second)
        """
        if first is not second:
            raise self.failureException(msg or '%r is not %r' % (first, second))
        return first
    failUnlessIdentical = assertIdentical = assertIs


    def assertIsNot(self, first, second, msg=None):
        """
        Fail the test if C{first} is C{second}.  This is an
        obect-identity-equality test, not an object equality
        (i.e. C{__eq__}) test.

        @param msg: if msg is None, then the failure message will be
        '%r is %r' % (first, second)
        """
        if first is second:
            raise self.failureException(msg or '%r is %r' % (first, second))
        return first
    failIfIdentical = assertNotIdentical = assertIsNot


    def assertNotEqual(self, first, second, msg=None):
        """
        Fail the test if C{first} == C{second}.

        @param msg: if msg is None, then the failure message will be
        '%r == %r' % (first, second)
        """
        if not first != second:
            raise self.failureException(msg or '%r == %r' % (first, second))
        return first
    assertNotEquals = failIfEquals = failIfEqual = assertNotEqual


    def assertIn(self, containee, container, msg=None):
        """
        Fail the test if C{containee} is not found in C{container}.

        @param containee: the value that should be in C{container}
        @param container: a sequence type, or in the case of a mapping type,
                          will follow semantics of 'if key in dict.keys()'
        @param msg: if msg is None, then the failure message will be
                    '%r not in %r' % (first, second)
        """
        if containee not in container:
            raise self.failureException(msg or "%r not in %r"
                                        % (containee, container))
        return containee
    failUnlessIn = assertIn


    def assertNotIn(self, containee, container, msg=None):
        """
        Fail the test if C{containee} is found in C{container}.

        @param containee: the value that should not be in C{container}
        @param container: a sequence type, or in the case of a mapping type,
                          will follow semantics of 'if key in dict.keys()'
        @param msg: if msg is None, then the failure message will be
                    '%r in %r' % (first, second)
        """
        if containee in container:
            raise self.failureException(msg or "%r in %r"
                                        % (containee, container))
        return containee
    failIfIn = assertNotIn


    def assertNotAlmostEqual(self, first, second, places=7, msg=None):
        """
        Fail if the two objects are equal as determined by their
        difference rounded to the given number of decimal places
        (default 7) and comparing to zero.

        @note: decimal places (from zero) is usually not the same
               as significant digits (measured from the most
               significant digit).

        @note: included for compatibility with PyUnit test cases
        """
        if round(second-first, places) == 0:
            raise self.failureException(msg or '%r == %r within %r places'
                                        % (first, second, places))
        return first
    assertNotAlmostEquals = failIfAlmostEqual = assertNotAlmostEqual
    failIfAlmostEquals = assertNotAlmostEqual


    def assertAlmostEqual(self, first, second, places=7, msg=None):
        """
        Fail if the two objects are unequal as determined by their
        difference rounded to the given number of decimal places
        (default 7) and comparing to zero.

        @note: decimal places (from zero) is usually not the same
               as significant digits (measured from the most
               significant digit).

        @note: included for compatibility with PyUnit test cases
        """
        if round(second-first, places) != 0:
            raise self.failureException(msg or '%r != %r within %r places'
                                        % (first, second, places))
        return first
    assertAlmostEquals = failUnlessAlmostEqual = assertAlmostEqual
    failUnlessAlmostEquals = assertAlmostEqual


    def assertApproximates(self, first, second, tolerance, msg=None):
        """
        Fail if C{first} - C{second} > C{tolerance}

        @param msg: if msg is None, then the failure message will be
                    '%r ~== %r' % (first, second)
        """
        if abs(first - second) > tolerance:
            raise self.failureException(msg or "%s ~== %s" % (first, second))
        return first
    failUnlessApproximates = assertApproximates


    def assertSubstring(self, substring, astring, msg=None):
        """
        Fail if C{substring} does not exist within C{astring}.
        """
        return self.failUnlessIn(substring, astring, msg)
    failUnlessSubstring = assertSubstring


    def assertNotSubstring(self, substring, astring, msg=None):
        """
        Fail if C{astring} contains C{substring}.
        """
        return self.failIfIn(substring, astring, msg)
    failIfSubstring = assertNotSubstring


    def assertWarns(self, category, message, filename, f,
                    *args, **kwargs):
        """
        Fail if the given function doesn't generate the specified warning when
        called. It calls the function, checks the warning, and forwards the
        result of the function if everything is fine.

        @param category: the category of the warning to check.
        @param message: the output message of the warning to check.
        @param filename: the filename where the warning should come from.
        @param f: the function which is supposed to generate the warning.
        @type f: any callable.
        @param args: the arguments to C{f}.
        @param kwargs: the keywords arguments to C{f}.

        @return: the result of the original function C{f}.
        """
        warningsShown = []
        result = _collectWarnings(warningsShown.append, f, *args, **kwargs)

        if not warningsShown:
            self.fail("No warnings emitted")
        first = warningsShown[0]
        for other in warningsShown[1:]:
            if ((other.message, other.category)
                != (first.message, first.category)):
                self.fail("Can't handle different warnings")
        self.assertEqual(first.message, message)
        self.assertIdentical(first.category, category)

        # Use starts with because of .pyc/.pyo issues.
        self.assertTrue(
            filename.startswith(first.filename),
            'Warning in %r, expected %r' % (first.filename, filename))

        # It would be nice to be able to check the line number as well, but
        # different configurations actually end up reporting different line
        # numbers (generally the variation is only 1 line, but that's enough
        # to fail the test erroneously...).
        # self.assertEqual(lineno, xxx)

        return result
    failUnlessWarns = assertWarns


    def assertIsInstance(self, instance, classOrTuple, message=None):
        """
        Fail if C{instance} is not an instance of the given class or of
        one of the given classes.

        @param instance: the object to test the type (first argument of the
            C{isinstance} call).
        @type instance: any.
        @param classOrTuple: the class or classes to test against (second
            argument of the C{isinstance} call).
        @type classOrTuple: class, type, or tuple.

        @param message: Custom text to include in the exception text if the
            assertion fails.
        """
        if not isinstance(instance, classOrTuple):
            if message is None:
                suffix = ""
            else:
                suffix = ": " + message
            self.fail("%r is not an instance of %s%s" % (
                    instance, classOrTuple, suffix))
    failUnlessIsInstance = assertIsInstance


    def assertNotIsInstance(self, instance, classOrTuple):
        """
        Fail if C{instance} is an instance of the given class or of one of the
        given classes.

        @param instance: the object to test the type (first argument of the
            C{isinstance} call).
        @type instance: any.
        @param classOrTuple: the class or classes to test against (second
            argument of the C{isinstance} call).
        @type classOrTuple: class, type, or tuple.
        """
        if isinstance(instance, classOrTuple):
            self.fail("%r is an instance of %s" % (instance, classOrTuple))
    failIfIsInstance = assertNotIsInstance


    def successResultOf(self, deferred):
        """
        Return the current success result of C{deferred} or raise
        C{self.failureException}.

        @param deferred: A L{Deferred<twisted.internet.defer.Deferred>} which
            has a success result.  This means
            L{Deferred.callback<twisted.internet.defer.Deferred.callback>} or
            L{Deferred.errback<twisted.internet.defer.Deferred.errback>} has
            been called on it and it has reached the end of its callback chain
            and the last callback or errback returned a non-L{failure.Failure}.
        @type deferred: L{Deferred<twisted.internet.defer.Deferred>}

        @raise SynchronousTestCase.failureException: If the
            L{Deferred<twisted.internet.defer.Deferred>} has no result or has a
            failure result.

        @return: The result of C{deferred}.
        """
        result = []
        deferred.addBoth(result.append)
        if not result:
            self.fail(
                "Success result expected on %r, found no result instead" % (
                    deferred,))
        elif isinstance(result[0], failure.Failure):
            self.fail(
                "Success result expected on %r, "
                "found failure result instead:\n%s" % (
                    deferred, result[0].getTraceback()))
        else:
            return result[0]



    def failureResultOf(self, deferred, *expectedExceptionTypes):
        """
        Return the current failure result of C{deferred} or raise
        C{self.failureException}.

        @param deferred: A L{Deferred<twisted.internet.defer.Deferred>} which
            has a failure result.  This means
            L{Deferred.callback<twisted.internet.defer.Deferred.callback>} or
            L{Deferred.errback<twisted.internet.defer.Deferred.errback>} has
            been called on it and it has reached the end of its callback chain
            and the last callback or errback raised an exception or returned a
            L{failure.Failure}.
        @type deferred: L{Deferred<twisted.internet.defer.Deferred>}

        @param expectedExceptionTypes: Exception types to expect - if
            provided, and the exception wrapped by the failure result is
            not one of the types provided, then this test will fail.

        @raise SynchronousTestCase.failureException: If the
            L{Deferred<twisted.internet.defer.Deferred>} has no result, has a
            success result, or has an unexpected failure result.

        @return: The failure result of C{deferred}.
        @rtype: L{failure.Failure}
        """
        result = []
        deferred.addBoth(result.append)
        if not result:
            self.fail(
                "Failure result expected on %r, found no result instead" % (
                    deferred,))
        elif not isinstance(result[0], failure.Failure):
            self.fail(
                "Failure result expected on %r, "
                "found success result (%r) instead" % (deferred, result[0]))
        elif (expectedExceptionTypes and
              not result[0].check(*expectedExceptionTypes)):
            expectedString = " or ".join([
                '.'.join((t.__module__, t.__name__)) for t in
                expectedExceptionTypes])

            self.fail(
                "Failure of type (%s) expected on %r, "
                "found type %r instead: %s" % (
                    expectedString, deferred, result[0].type,
                    result[0].getTraceback()))
        else:
            return result[0]



    def assertNoResult(self, deferred):
        """
        Assert that C{deferred} does not have a result at this point.

        If the assertion succeeds, then the result of C{deferred} is left
        unchanged. Otherwise, any L{failure.Failure} result is swallowed.

        @param deferred: A L{Deferred<twisted.internet.defer.Deferred>} without
            a result.  This means that neither
            L{Deferred.callback<twisted.internet.defer.Deferred.callback>} nor
            L{Deferred.errback<twisted.internet.defer.Deferred.errback>} has
            been called, or that the
            L{Deferred<twisted.internet.defer.Deferred>} is waiting on another
            L{Deferred<twisted.internet.defer.Deferred>} for a result.
        @type deferred: L{Deferred<twisted.internet.defer.Deferred>}

        @raise SynchronousTestCase.failureException: If the
            L{Deferred<twisted.internet.defer.Deferred>} has a result.
        """
        result = []
        def cb(res):
            result.append(res)
            return res
        deferred.addBoth(cb)
        if result:
            # If there is already a failure, the self.fail below will
            # report it, so swallow it in the deferred
            deferred.addErrback(lambda _: None)
            self.fail(
                "No result expected on %r, found %r instead" % (
                    deferred, result[0]))



    def assertRegex(self, text, regex, msg=None):
        """
        Fail the test if a C{regexp} search of C{text} fails.

        @param text: Text which is under test.
        @type text: L{str}

        @param regex: A regular expression object or a string containing a
            regular expression suitable for use by re.search().
        @type regex: L{str} or L{re.RegexObject}

        @param msg: Text used as the error message on failure.
        @type msg: L{str}
        """
        if sys.version_info[:2] > (2, 7):
            super(_Assertions, self).assertRegex(text, regex, msg)
        else:
            # Python 2.7 has unittest.assertRegexpMatches() which was
            # renamed to unittest.assertRegex() in Python 3.2
            super(_Assertions, self).assertRegexpMatches(text, regex, msg)



class _LogObserver(object):
    """
    Observes the Twisted logs and catches any errors.

    @ivar _errors: A C{list} of L{Failure} instances which were received as
        error events from the Twisted logging system.

    @ivar _added: A C{int} giving the number of times C{_add} has been called
        less the number of times C{_remove} has been called; used to only add
        this observer to the Twisted logging since once, regardless of the
        number of calls to the add method.

    @ivar _ignored: A C{list} of exception types which will not be recorded.
    """

    def __init__(self):
        self._errors = []
        self._added = 0
        self._ignored = []


    def _add(self):
        if self._added == 0:
            log.addObserver(self.gotEvent)
        self._added += 1


    def _remove(self):
        self._added -= 1
        if self._added == 0:
            log.removeObserver(self.gotEvent)


    def _ignoreErrors(self, *errorTypes):
        """
        Do not store any errors with any of the given types.
        """
        self._ignored.extend(errorTypes)


    def _clearIgnores(self):
        """
        Stop ignoring any errors we might currently be ignoring.
        """
        self._ignored = []


    def flushErrors(self, *errorTypes):
        """
        Flush errors from the list of caught errors. If no arguments are
        specified, remove all errors. If arguments are specified, only remove
        errors of those types from the stored list.
        """
        if errorTypes:
            flushed = []
            remainder = []
            for f in self._errors:
                if f.check(*errorTypes):
                    flushed.append(f)
                else:
                    remainder.append(f)
            self._errors = remainder
        else:
            flushed = self._errors
            self._errors = []
        return flushed


    def getErrors(self):
        """
        Return a list of errors caught by this observer.
        """
        return self._errors


    def gotEvent(self, event):
        """
        The actual observer method. Called whenever a message is logged.

        @param event: A dictionary containing the log message. Actual
        structure undocumented (see source for L{twisted.python.log}).
        """
        if event.get('isError', False) and 'failure' in event:
            f = event['failure']
            if len(self._ignored) == 0 or not f.check(*self._ignored):
                self._errors.append(f)



_logObserver = _LogObserver()


class SynchronousTestCase(_Assertions):
    """
    A unit test. The atom of the unit testing universe.

    This class extends C{unittest.TestCase} from the standard library.  A number
    of convenient testing helpers are added, including logging and warning
    integration, monkey-patching support, and more.

    To write a unit test, subclass C{SynchronousTestCase} and define a method
    (say, 'test_foo') on the subclass. To run the test, instantiate your
    subclass with the name of the method, and call L{run} on the instance,
    passing a L{TestResult} object.

    The C{trial} script will automatically find any C{SynchronousTestCase}
    subclasses defined in modules beginning with 'test_' and construct test
    cases for all methods beginning with 'test'.

    If an error is logged during the test run, the test will fail with an
    error. See L{log.err}.

    @ivar failureException: An exception class, defaulting to C{FailTest}. If
    the test method raises this exception, it will be reported as a failure,
    rather than an exception. All of the assertion methods raise this if the
    assertion fails.

    @ivar skip: L{None} or a string explaining why this test is to be
    skipped. If defined, the test will not be run. Instead, it will be
    reported to the result object as 'skipped' (if the C{TestResult} supports
    skipping).

    @ivar todo: L{None}, a string or a tuple of C{(errors, reason)} where
    C{errors} is either an exception class or an iterable of exception
    classes, and C{reason} is a string. See L{Todo} or L{makeTodo} for more
    information.

    @ivar suppress: L{None} or a list of tuples of C{(args, kwargs)} to be
    passed to C{warnings.filterwarnings}. Use these to suppress warnings
    raised in a test. Useful for testing deprecated code. See also
    L{util.suppress}.
    """
    failureException = FailTest

    def __init__(self, methodName='runTest'):
        super(SynchronousTestCase, self).__init__(methodName)
        self._passed = False
        self._cleanups = []
        self._testMethodName = methodName
        testMethod = getattr(self, methodName)
        self._parents = [
            testMethod, self, sys.modules.get(self.__class__.__module__)]


    # Override the comparison defined by the base TestCase which considers
    # instances of the same class with the same _testMethodName to be
    # equal.  Since trial puts TestCase instances into a set, that
    # definition of comparison makes it impossible to run the same test
    # method twice.  Most likely, trial should stop using a set to hold
    # tests, but until it does, this is necessary on Python 2.6. -exarkun
    def __eq__(self, other):
        return self is other

    def __ne__(self, other):
        return self is not other

    def __hash__(self):
        return hash((self.__class__, self._testMethodName))


    def shortDescription(self):
        desc = super(SynchronousTestCase, self).shortDescription()
        if desc is None:
            return self._testMethodName
        return desc


    def getSkip(self):
        """
        Return the skip reason set on this test, if any is set. Checks on the
        instance first, then the class, then the module, then packages. As
        soon as it finds something with a C{skip} attribute, returns that.
        Returns L{None} if it cannot find anything. See L{TestCase} docstring
        for more details.
        """
        return util.acquireAttribute(self._parents, 'skip', None)


    def getTodo(self):
        """
        Return a L{Todo} object if the test is marked todo. Checks on the
        instance first, then the class, then the module, then packages. As
        soon as it finds something with a C{todo} attribute, returns that.
        Returns L{None} if it cannot find anything. See L{TestCase} docstring
        for more details.
        """
        todo = util.acquireAttribute(self._parents, 'todo', None)
        if todo is None:
            return None
        return makeTodo(todo)


    def runTest(self):
        """
        If no C{methodName} argument is passed to the constructor, L{run} will
        treat this method as the thing with the actual test inside.
        """


    def run(self, result):
        """
        Run the test case, storing the results in C{result}.

        First runs C{setUp} on self, then runs the test method (defined in the
        constructor), then runs C{tearDown}.  As with the standard library
        L{unittest.TestCase}, the return value of these methods is disregarded.
        In particular, returning a L{Deferred<twisted.internet.defer.Deferred>}
        has no special additional consequences.

        @param result: A L{TestResult} object.
        """
        log.msg("--> %s <--" % (self.id()))
        new_result = itrial.IReporter(result, None)
        if new_result is None:
            result = PyUnitResultAdapter(result)
        else:
            result = new_result
        result.startTest(self)
        if self.getSkip(): # don't run test methods that are marked as .skip
            result.addSkip(self, self.getSkip())
            result.stopTest(self)
            return

        self._passed = False
        self._warnings = []

        self._installObserver()
        # All the code inside _runFixturesAndTest will be run such that warnings
        # emitted by it will be collected and retrievable by flushWarnings.
        _collectWarnings(self._warnings.append, self._runFixturesAndTest, result)

        # Any collected warnings which the test method didn't flush get
        # re-emitted so they'll be logged or show up on stdout or whatever.
        for w in self.flushWarnings():
            try:
                warnings.warn_explicit(**w)
            except:
                result.addError(self, failure.Failure())

        result.stopTest(self)


    def addCleanup(self, f, *args, **kwargs):
        """
        Add the given function to a list of functions to be called after the
        test has run, but before C{tearDown}.

        Functions will be run in reverse order of being added. This helps
        ensure that tear down complements set up.

        As with all aspects of L{SynchronousTestCase}, Deferreds are not
        supported in cleanup functions.
        """
        self._cleanups.append((f, args, kwargs))


    def patch(self, obj, attribute, value):
        """
        Monkey patch an object for the duration of the test.

        The monkey patch will be reverted at the end of the test using the
        L{addCleanup} mechanism.

        The L{monkey.MonkeyPatcher} is returned so that users can restore and
        re-apply the monkey patch within their tests.

        @param obj: The object to monkey patch.
        @param attribute: The name of the attribute to change.
        @param value: The value to set the attribute to.
        @return: A L{monkey.MonkeyPatcher} object.
        """
        monkeyPatch = monkey.MonkeyPatcher((obj, attribute, value))
        monkeyPatch.patch()
        self.addCleanup(monkeyPatch.restore)
        return monkeyPatch


    def flushLoggedErrors(self, *errorTypes):
        """
        Remove stored errors received from the log.

        C{TestCase} stores each error logged during the run of the test and
        reports them as errors during the cleanup phase (after C{tearDown}).

        @param *errorTypes: If unspecified, flush all errors. Otherwise, only
        flush errors that match the given types.

        @return: A list of failures that have been removed.
        """
        return self._observer.flushErrors(*errorTypes)


    def flushWarnings(self, offendingFunctions=None):
        """
        Remove stored warnings from the list of captured warnings and return
        them.

        @param offendingFunctions: If L{None}, all warnings issued during the
            currently running test will be flushed.  Otherwise, only warnings
            which I{point} to a function included in this list will be flushed.
            All warnings include a filename and source line number; if these
            parts of a warning point to a source line which is part of a
            function, then the warning I{points} to that function.
        @type offendingFunctions: L{None} or L{list} of functions or methods.

        @raise ValueError: If C{offendingFunctions} is not L{None} and includes
            an object which is not a L{types.FunctionType} or
            L{types.MethodType} instance.

        @return: A C{list}, each element of which is a C{dict} giving
            information about one warning which was flushed by this call.  The
            keys of each C{dict} are:

                - C{'message'}: The string which was passed as the I{message}
                  parameter to L{warnings.warn}.

                - C{'category'}: The warning subclass which was passed as the
                  I{category} parameter to L{warnings.warn}.

                - C{'filename'}: The name of the file containing the definition
                  of the code object which was C{stacklevel} frames above the
                  call to L{warnings.warn}, where C{stacklevel} is the value of
                  the C{stacklevel} parameter passed to L{warnings.warn}.

                - C{'lineno'}: The source line associated with the active
                  instruction of the code object object which was C{stacklevel}
                  frames above the call to L{warnings.warn}, where
                  C{stacklevel} is the value of the C{stacklevel} parameter
                  passed to L{warnings.warn}.
        """
        if offendingFunctions is None:
            toFlush = self._warnings[:]
            self._warnings[:] = []
        else:
            toFlush = []
            for aWarning in self._warnings:
                for aFunction in offendingFunctions:
                    if not isinstance(aFunction, (
                            types.FunctionType, types.MethodType)):
                        raise ValueError("%r is not a function or method" % (
                                aFunction,))

                    # inspect.getabsfile(aFunction) sometimes returns a
                    # filename which disagrees with the filename the warning
                    # system generates.  This seems to be because a
                    # function's code object doesn't deal with source files
                    # being renamed.  inspect.getabsfile(module) seems
                    # better (or at least agrees with the warning system
                    # more often), and does some normalization for us which
                    # is desirable.  inspect.getmodule() is attractive, but
                    # somewhat broken in Python < 2.6.  See Python bug 4845.
                    aModule = sys.modules[aFunction.__module__]
                    filename = inspect.getabsfile(aModule)

                    if filename != os.path.normcase(aWarning.filename):
                        continue
                    lineStarts = list(_findlinestarts(aFunction.__code__))
                    first = lineStarts[0][1]
                    last = lineStarts[-1][1]
                    if not (first <= aWarning.lineno <= last):
                        continue
                    # The warning points to this function, flush it and move on
                    # to the next warning.
                    toFlush.append(aWarning)
                    break
            # Remove everything which is being flushed.
            list(map(self._warnings.remove, toFlush))

        return [
            {'message': w.message, 'category': w.category,
             'filename': w.filename, 'lineno': w.lineno}
            for w in toFlush]


    def callDeprecated(self, version, f, *args, **kwargs):
        """
        Call a function that should have been deprecated at a specific version
        and in favor of a specific alternative, and assert that it was thusly
        deprecated.

        @param version: A 2-sequence of (since, replacement), where C{since} is
            a the first L{version<twisted.python.versions.Version>} that C{f}
            should have been deprecated since, and C{replacement} is a suggested
            replacement for the deprecated functionality, as described by
            L{twisted.python.deprecate.deprecated}.  If there is no suggested
            replacement, this parameter may also be simply a
            L{version<twisted.python.versions.Version>} by itself.

        @param f: The deprecated function to call.

        @param args: The arguments to pass to C{f}.

        @param kwargs: The keyword arguments to pass to C{f}.

        @return: Whatever C{f} returns.

        @raise: Whatever C{f} raises.  If any exception is
            raised by C{f}, though, no assertions will be made about emitted
            deprecations.

        @raise FailTest: if no warnings were emitted by C{f}, or if the
            L{DeprecationWarning} emitted did not produce the canonical
            please-use-something-else message that is standard for Twisted
            deprecations according to the given version and replacement.
        """
        result = f(*args, **kwargs)
        warningsShown = self.flushWarnings([self.callDeprecated])
        try:
            info = list(version)
        except TypeError:
            since = version
            replacement = None
        else:
            [since, replacement] = info

        if len(warningsShown) == 0:
            self.fail('%r is not deprecated.' % (f,))

        observedWarning = warningsShown[0]['message']
        expectedWarning = getDeprecationWarningString(
            f, since, replacement=replacement)
        self.assertEqual(expectedWarning, observedWarning)

        return result


    def mktemp(self):
        """
        Create a new path name which can be used for a new file or directory.

        The result is a relative path that is guaranteed to be unique within the
        current working directory.  The parent of the path will exist, but the
        path will not.

        For a temporary directory call os.mkdir on the path.  For a temporary
        file just create the file (e.g. by opening the path for writing and then
        closing it).

        @return: The newly created path
        @rtype: C{str}
        """
        MAX_FILENAME = 32 # some platforms limit lengths of filenames
        base = os.path.join(self.__class__.__module__[:MAX_FILENAME],
                            self.__class__.__name__[:MAX_FILENAME],
                            self._testMethodName[:MAX_FILENAME])
        if not os.path.exists(base):
            os.makedirs(base)
        dirname = tempfile.mkdtemp('', '', base)
        return os.path.join(dirname, 'temp')


    def _getSuppress(self):
        """
        Returns any warning suppressions set for this test. Checks on the
        instance first, then the class, then the module, then packages. As
        soon as it finds something with a C{suppress} attribute, returns that.
        Returns any empty list (i.e. suppress no warnings) if it cannot find
        anything. See L{TestCase} docstring for more details.
        """
        return util.acquireAttribute(self._parents, 'suppress', [])


    def _getSkipReason(self, method, skip):
        """
        Return the reason to use for skipping a test method.

        @param method: The method which produced the skip.
        @param skip: A L{unittest.SkipTest} instance raised by C{method}.
        """
        if len(skip.args) > 0:
            return skip.args[0]

        warnAboutFunction(
            method,
            "Do not raise unittest.SkipTest with no arguments! Give a reason "
            "for skipping tests!")
        return skip


    def _run(self, suppress, todo, method, result):
        """
        Run a single method, either a test method or fixture.

        @param suppress: Any warnings to suppress, as defined by the C{suppress}
            attribute on this method, test case, or the module it is defined in.

        @param todo: Any expected failure or failures, as defined by the C{todo}
            attribute on this method, test case, or the module it is defined in.

        @param method: The method to run.

        @param result: The TestResult instance to which to report results.

        @return: C{True} if the method fails and no further method/fixture calls
            should be made, C{False} otherwise.
        """
        if inspect.isgeneratorfunction(method):
            exc = TypeError(
                '%r is a generator function and therefore will never run' % (
                    method,))
            result.addError(self, failure.Failure(exc))
            return True
        try:
            runWithWarningsSuppressed(suppress, method)
        except SkipTest as e:
            result.addSkip(self, self._getSkipReason(method, e))
        except:
            reason = failure.Failure()
            if todo is None or not todo.expected(reason):
                if reason.check(self.failureException):
                    addResult = result.addFailure
                else:
                    addResult = result.addError
                addResult(self, reason)
            else:
                result.addExpectedFailure(self, reason, todo)
        else:
            return False
        return True


    def _runFixturesAndTest(self, result):
        """
        Run C{setUp}, a test method, test cleanups, and C{tearDown}.

        @param result: The TestResult instance to which to report results.
        """
        suppress = self._getSuppress()
        try:
            if self._run(suppress, None, self.setUp, result):
                return

            todo = self.getTodo()
            method = getattr(self, self._testMethodName)
            if self._run(suppress, todo, method, result):
                return
        finally:
            self._runCleanups(result)

        if todo:
            result.addUnexpectedSuccess(self, todo)

        if self._run(suppress, None, self.tearDown, result):
            return

        passed = True
        for error in self._observer.getErrors():
            result.addError(self, error)
            passed = False
        self._observer.flushErrors()
        self._removeObserver()

        if passed and not todo:
            result.addSuccess(self)


    def _runCleanups(self, result):
        """
        Synchronously run any cleanups which have been added.
        """
        while len(self._cleanups) > 0:
            f, args, kwargs = self._cleanups.pop()
            try:
                f(*args, **kwargs)
            except:
                f = failure.Failure()
                result.addError(self, f)


    def _installObserver(self):
        self._observer = _logObserver
        self._observer._add()


    def _removeObserver(self):
        self._observer._remove()
