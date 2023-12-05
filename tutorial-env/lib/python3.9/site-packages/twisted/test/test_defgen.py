# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet.defer.deferredGenerator} and related APIs.
"""

import traceback

from twisted.internet import defer, reactor, task
from twisted.internet.defer import (
    Deferred,
    deferredGenerator,
    inlineCallbacks,
    returnValue,
    waitForDeferred,
)
from twisted.python.util import runWithWarningsSuppressed
from twisted.trial import unittest
from twisted.trial.util import suppress as SUPPRESS


def getThing():
    d = Deferred()
    reactor.callLater(0, d.callback, "hi")
    return d


def getOwie():
    d = Deferred()

    def CRAP():
        d.errback(ZeroDivisionError("OMG"))

    reactor.callLater(0, CRAP)
    return d


# NOTE: most of the tests in DeferredGeneratorTests are duplicated
# with slightly different syntax for the InlineCallbacksTests below.


class TerminalException(Exception):
    pass


class BaseDefgenTests:
    """
    This class sets up a bunch of test cases which will test both
    deferredGenerator and inlineCallbacks based generators. The subclasses
    DeferredGeneratorTests and InlineCallbacksTests each provide the actual
    generator implementations tested.
    """

    def testBasics(self):
        """
        Test that a normal deferredGenerator works.  Tests yielding a
        deferred which callbacks, as well as a deferred errbacks. Also
        ensures returning a final value works.
        """

        return self._genBasics().addCallback(self.assertEqual, "WOOSH")

    def testBuggy(self):
        """
        Ensure that a buggy generator properly signals a Failure
        condition on result deferred.
        """
        return self.assertFailure(self._genBuggy(), ZeroDivisionError)

    def testNothing(self):
        """Test that a generator which never yields results in None."""

        return self._genNothing().addCallback(self.assertEqual, None)

    def testHandledTerminalFailure(self):
        """
        Create a Deferred Generator which yields a Deferred which fails and
        handles the exception which results.  Assert that the Deferred
        Generator does not errback its Deferred.
        """
        return self._genHandledTerminalFailure().addCallback(self.assertEqual, None)

    def testHandledTerminalAsyncFailure(self):
        """
        Just like testHandledTerminalFailure, only with a Deferred which fires
        asynchronously with an error.
        """
        d = defer.Deferred()
        deferredGeneratorResultDeferred = self._genHandledTerminalAsyncFailure(d)
        d.errback(TerminalException("Handled Terminal Failure"))
        return deferredGeneratorResultDeferred.addCallback(self.assertEqual, None)

    def testStackUsage(self):
        """
        Make sure we don't blow the stack when yielding immediately
        available deferreds.
        """
        return self._genStackUsage().addCallback(self.assertEqual, 0)

    def testStackUsage2(self):
        """
        Make sure we don't blow the stack when yielding immediately
        available values.
        """
        return self._genStackUsage2().addCallback(self.assertEqual, 0)


def deprecatedDeferredGenerator(f):
    """
    Calls L{deferredGenerator} while suppressing the deprecation warning.

    @param f: Function to call
    @return: Return value of function.
    """
    return runWithWarningsSuppressed(
        [
            SUPPRESS(
                message="twisted.internet.defer.deferredGenerator was " "deprecated"
            )
        ],
        deferredGenerator,
        f,
    )


class DeferredGeneratorTests(BaseDefgenTests, unittest.TestCase):

    # First provide all the generator impls necessary for BaseDefgenTests
    @deprecatedDeferredGenerator
    def _genBasics(self):

        x = waitForDeferred(getThing())
        yield x
        x = x.getResult()

        self.assertEqual(x, "hi")

        ow = waitForDeferred(getOwie())
        yield ow
        try:
            ow.getResult()
        except ZeroDivisionError as e:
            self.assertEqual(str(e), "OMG")
        yield "WOOSH"
        return

    @deprecatedDeferredGenerator
    def _genBuggy(self):
        yield waitForDeferred(getThing())
        1 // 0

    @deprecatedDeferredGenerator
    def _genNothing(self):
        if False:
            yield 1

    @deprecatedDeferredGenerator
    def _genHandledTerminalFailure(self):
        x = waitForDeferred(defer.fail(TerminalException("Handled Terminal Failure")))
        yield x
        try:
            x.getResult()
        except TerminalException:
            pass

    @deprecatedDeferredGenerator
    def _genHandledTerminalAsyncFailure(self, d):
        x = waitForDeferred(d)
        yield x
        try:
            x.getResult()
        except TerminalException:
            pass

    def _genStackUsage(self):
        for x in range(5000):
            # Test with yielding a deferred
            x = waitForDeferred(defer.succeed(1))
            yield x
            x = x.getResult()
        yield 0

    _genStackUsage = deprecatedDeferredGenerator(_genStackUsage)

    def _genStackUsage2(self):
        for x in range(5000):
            # Test with yielding a random value
            yield 1
        yield 0

    _genStackUsage2 = deprecatedDeferredGenerator(_genStackUsage2)

    # Tests unique to deferredGenerator

    def testDeferredYielding(self):
        """
        Ensure that yielding a Deferred directly is trapped as an
        error.
        """
        # See the comment _deferGenerator about d.callback(Deferred).
        def _genDeferred():
            yield getThing()

        _genDeferred = deprecatedDeferredGenerator(_genDeferred)

        return self.assertFailure(_genDeferred(), TypeError)

    suppress = [
        SUPPRESS(message="twisted.internet.defer.waitForDeferred was " "deprecated")
    ]


class InlineCallbacksTests(BaseDefgenTests, unittest.TestCase):
    # First provide all the generator impls necessary for BaseDefgenTests

    def _genBasics(self):

        x = yield getThing()

        self.assertEqual(x, "hi")

        try:
            yield getOwie()
        except ZeroDivisionError as e:
            self.assertEqual(str(e), "OMG")
        returnValue("WOOSH")

    _genBasics = inlineCallbacks(_genBasics)

    def _genBuggy(self):
        yield getThing()
        1 / 0

    _genBuggy = inlineCallbacks(_genBuggy)

    def _genNothing(self):
        if False:
            yield 1

    _genNothing = inlineCallbacks(_genNothing)

    def _genHandledTerminalFailure(self):
        try:
            yield defer.fail(TerminalException("Handled Terminal Failure"))
        except TerminalException:
            pass

    _genHandledTerminalFailure = inlineCallbacks(_genHandledTerminalFailure)

    def _genHandledTerminalAsyncFailure(self, d):
        try:
            yield d
        except TerminalException:
            pass

    _genHandledTerminalAsyncFailure = inlineCallbacks(_genHandledTerminalAsyncFailure)

    def _genStackUsage(self):
        for x in range(5000):
            # Test with yielding a deferred
            yield defer.succeed(1)
        returnValue(0)

    _genStackUsage = inlineCallbacks(_genStackUsage)

    def _genStackUsage2(self):
        for x in range(5000):
            # Test with yielding a random value
            yield 1
        returnValue(0)

    _genStackUsage2 = inlineCallbacks(_genStackUsage2)

    # Tests unique to inlineCallbacks

    def testYieldNonDeferred(self):
        """
        Ensure that yielding a non-deferred passes it back as the
        result of the yield expression.

        @return: A L{twisted.internet.defer.Deferred}
        @rtype: L{twisted.internet.defer.Deferred}
        """

        def _test():
            yield 5
            returnValue(5)

        _test = inlineCallbacks(_test)

        return _test().addCallback(self.assertEqual, 5)

    def testReturnNoValue(self):
        """Ensure a standard python return results in a None result."""

        def _noReturn():
            yield 5
            return

        _noReturn = inlineCallbacks(_noReturn)

        return _noReturn().addCallback(self.assertEqual, None)

    def testReturnValue(self):
        """Ensure that returnValue works."""

        def _return():
            yield 5
            returnValue(6)

        _return = inlineCallbacks(_return)

        return _return().addCallback(self.assertEqual, 6)

    def test_nonGeneratorReturn(self):
        """
        Ensure that C{TypeError} with a message about L{inlineCallbacks} is
        raised when a non-generator returns something other than a generator.
        """

        def _noYield():
            return 5

        _noYield = inlineCallbacks(_noYield)

        self.assertIn("inlineCallbacks", str(self.assertRaises(TypeError, _noYield)))

    def test_nonGeneratorReturnValue(self):
        """
        Ensure that C{TypeError} with a message about L{inlineCallbacks} is
        raised when a non-generator calls L{returnValue}.
        """

        def _noYield():
            returnValue(5)

        _noYield = inlineCallbacks(_noYield)

        self.assertIn("inlineCallbacks", str(self.assertRaises(TypeError, _noYield)))

    def test_internalDefGenReturnValueDoesntLeak(self):
        """
        When one inlineCallbacks calls another, the internal L{_DefGen_Return}
        flow control exception raised by calling L{defer.returnValue} doesn't
        leak into tracebacks captured in the caller.
        """
        clock = task.Clock()

        @inlineCallbacks
        def _returns():
            """
            This is the inner function using returnValue.
            """
            yield task.deferLater(clock, 0)
            returnValue("actual-value-not-used-for-the-test")

        @inlineCallbacks
        def _raises():
            try:
                yield _returns()
                raise TerminalException("boom returnValue")
            except TerminalException:
                return traceback.format_exc()

        d = _raises()
        clock.advance(0)
        tb = self.successResultOf(d)

        # The internal exception is not in the traceback.
        self.assertNotIn("_DefGen_Return", tb)
        # No other extra exception is in the traceback.
        self.assertNotIn(
            "During handling of the above exception, another exception occurred", tb
        )
        # Our targeted exception is in the traceback
        self.assertIn("test_defgen.TerminalException: boom returnValue", tb)

    def test_internalStopIterationDoesntLeak(self):
        """
        When one inlineCallbacks calls another, the internal L{StopIteration}
        flow control exception generated when the inner generator returns
        doesn't leak into tracebacks captured in the caller.

        This is similar to C{test_internalDefGenReturnValueDoesntLeak} but the
        inner function uses the "normal" return statemement rather than the
        C{returnValue} helper.
        """
        clock = task.Clock()

        @inlineCallbacks
        def _returns():
            yield task.deferLater(clock, 0)
            return 6

        @inlineCallbacks
        def _raises():
            try:
                yield _returns()
                raise TerminalException("boom normal return")
            except TerminalException:
                return traceback.format_exc()

        d = _raises()
        clock.advance(0)
        tb = self.successResultOf(d)

        # The internal exception is not in the traceback.
        self.assertNotIn("StopIteration", tb)
        # No other extra exception is in the traceback.
        self.assertNotIn(
            "During handling of the above exception, another exception occurred", tb
        )
        # Our targeted exception is in the traceback
        self.assertIn("test_defgen.TerminalException: boom normal return", tb)


class DeprecateDeferredGeneratorTests(unittest.SynchronousTestCase):
    """
    Tests that L{DeferredGeneratorTests} and L{waitForDeferred} are
    deprecated.
    """

    def test_deferredGeneratorDeprecated(self):
        """
        L{deferredGenerator} is deprecated.
        """

        @deferredGenerator
        def decoratedFunction():
            yield None

        warnings = self.flushWarnings([self.test_deferredGeneratorDeprecated])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["category"], DeprecationWarning)
        self.assertEqual(
            warnings[0]["message"],
            "twisted.internet.defer.deferredGenerator was deprecated in "
            "Twisted 15.0.0; please use "
            "twisted.internet.defer.inlineCallbacks instead",
        )

    def test_waitForDeferredDeprecated(self):
        """
        L{waitForDeferred} is deprecated.
        """
        d = Deferred()
        waitForDeferred(d)

        warnings = self.flushWarnings([self.test_waitForDeferredDeprecated])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["category"], DeprecationWarning)
        self.assertEqual(
            warnings[0]["message"],
            "twisted.internet.defer.waitForDeferred was deprecated in "
            "Twisted 15.0.0; please use "
            "twisted.internet.defer.inlineCallbacks instead",
        )
