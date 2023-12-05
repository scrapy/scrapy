# -*- test-case-name: twisted.internet.test.test_inlinecb -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet.defer.inlineCallbacks}.

Some tests for inlineCallbacks are defined in L{twisted.test.test_defgen} as
well.
"""


from twisted.internet.defer import (
    CancelledError,
    Deferred,
    inlineCallbacks,
    returnValue,
)
from twisted.trial.unittest import SynchronousTestCase, TestCase


class StopIterationReturnTests(TestCase):
    """
    On Python 3.4 and newer generator functions may use the C{return} statement
    with a value, which is attached to the L{StopIteration} exception that is
    raised.

    L{inlineCallbacks} will use this value when it fires the C{callback}.
    """

    def test_returnWithValue(self):
        """
        If the C{return} statement has a value it is propagated back to the
        L{Deferred} that the C{inlineCallbacks} function returned.
        """
        environ = {"inlineCallbacks": inlineCallbacks}
        exec(
            """
@inlineCallbacks
def f(d):
    yield d
    return 14
        """,
            environ,
        )
        d1 = Deferred()
        d2 = environ["f"](d1)
        d1.callback(None)
        self.assertEqual(self.successResultOf(d2), 14)


class NonLocalExitTests(TestCase):
    """
    It's possible for L{returnValue} to be (accidentally) invoked at a stack
    level below the L{inlineCallbacks}-decorated function which it is exiting.
    If this happens, L{returnValue} should report useful errors.

    If L{returnValue} is invoked from a function not decorated by
    L{inlineCallbacks}, it will emit a warning if it causes an
    L{inlineCallbacks} function further up the stack to exit.
    """

    def mistakenMethod(self):
        """
        This method mistakenly invokes L{returnValue}, despite the fact that it
        is not decorated with L{inlineCallbacks}.
        """
        returnValue(1)

    def assertMistakenMethodWarning(self, resultList):
        """
        Flush the current warnings and assert that we have been told that
        C{mistakenMethod} was invoked, and that the result from the Deferred
        that was fired (appended to the given list) is C{mistakenMethod}'s
        result.  The warning should indicate that an inlineCallbacks function
        called 'inline' was made to exit.
        """
        self.assertEqual(resultList, [1])
        warnings = self.flushWarnings(offendingFunctions=[self.mistakenMethod])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["category"], DeprecationWarning)
        self.assertEqual(
            warnings[0]["message"],
            "returnValue() in 'mistakenMethod' causing 'inline' to exit: "
            "returnValue should only be invoked by functions decorated with "
            "inlineCallbacks",
        )

    def test_returnValueNonLocalWarning(self):
        """
        L{returnValue} will emit a non-local exit warning in the simplest case,
        where the offending function is invoked immediately.
        """

        @inlineCallbacks
        def inline():
            self.mistakenMethod()
            returnValue(2)
            yield 0

        d = inline()
        results = []
        d.addCallback(results.append)
        self.assertMistakenMethodWarning(results)

    def test_returnValueNonLocalDeferred(self):
        """
        L{returnValue} will emit a non-local warning in the case where the
        L{inlineCallbacks}-decorated function has already yielded a Deferred
        and therefore moved its generator function along.
        """
        cause = Deferred()

        @inlineCallbacks
        def inline():
            yield cause
            self.mistakenMethod()
            returnValue(2)

        effect = inline()
        results = []
        effect.addCallback(results.append)
        self.assertEqual(results, [])
        cause.callback(1)
        self.assertMistakenMethodWarning(results)


class ForwardTraceBackTests(SynchronousTestCase):
    def test_forwardTracebacks(self):
        """
        Chained inlineCallbacks are forwarding the traceback information
        from generator to generator.

        A first simple test with a couple of inline callbacks.
        """

        @inlineCallbacks
        def erroring():
            yield "forcing generator"
            raise Exception("Error Marker")

        @inlineCallbacks
        def calling():
            yield erroring()

        d = calling()
        f = self.failureResultOf(d)
        tb = f.getTraceback()
        self.assertIn("in erroring", tb)
        self.assertIn("in calling", tb)
        self.assertIn("Error Marker", tb)

    def test_forwardLotsOfTracebacks(self):
        """
        Several Chained inlineCallbacks gives information about all generators.

        A wider test with a 4 chained inline callbacks.

        Application stack-trace should be reported, and implementation details
        like "throwExceptionIntoGenerator" symbols are omitted from the stack.

        Note that the previous test is testing the simple case, and this one is
        testing the deep recursion case.

        That case needs specific code in failure.py to accomodate to stack
        breakage introduced by throwExceptionIntoGenerator.

        Hence we keep the two tests in order to sort out which code we
        might have regression in.
        """

        @inlineCallbacks
        def erroring():
            yield "forcing generator"
            raise Exception("Error Marker")

        @inlineCallbacks
        def calling3():
            yield erroring()

        @inlineCallbacks
        def calling2():
            yield calling3()

        @inlineCallbacks
        def calling():
            yield calling2()

        d = calling()
        f = self.failureResultOf(d)
        tb = f.getTraceback()
        self.assertIn("in erroring", tb)
        self.assertIn("in calling", tb)
        self.assertIn("in calling2", tb)
        self.assertIn("in calling3", tb)
        self.assertNotIn("throwExceptionIntoGenerator", tb)
        self.assertIn("Error Marker", tb)
        self.assertIn("in erroring", f.getTraceback())


class UntranslatedError(Exception):
    """
    Untranslated exception type when testing an exception translation.
    """


class TranslatedError(Exception):
    """
    Translated exception type when testing an exception translation.
    """


class DontFail(Exception):
    """
    Sample exception type.
    """

    def __init__(self, actual):
        Exception.__init__(self)
        self.actualValue = actual


class CancellationTests(SynchronousTestCase):
    """
    Tests for cancellation of L{Deferred}s returned by L{inlineCallbacks}.
    For each of these tests, let:
        - C{G} be a generator decorated with C{inlineCallbacks}
        - C{D} be a L{Deferred} returned by C{G}
        - C{C} be a L{Deferred} awaited by C{G} with C{yield}
    """

    def setUp(self):
        """
        Set up the list of outstanding L{Deferred}s.
        """
        self.deferredsOutstanding = []

    def tearDown(self):
        """
        If any L{Deferred}s are still outstanding, fire them.
        """
        while self.deferredsOutstanding:
            self.deferredGotten()

    @inlineCallbacks
    def sampleInlineCB(self, getChildDeferred=None):
        """
        Generator for testing cascade cancelling cases.

        @param getChildDeferred: Some callable returning L{Deferred} that we
            awaiting (with C{yield})
        """
        if getChildDeferred is None:
            getChildDeferred = self.getDeferred
        try:
            x = yield getChildDeferred()
        except UntranslatedError:
            raise TranslatedError()
        except DontFail as df:
            x = df.actualValue - 2
        returnValue(x + 1)

    def getDeferred(self):
        """
        A sample function that returns a L{Deferred} that can be fired on
        demand, by L{CancellationTests.deferredGotten}.

        @return: L{Deferred} that can be fired on demand.
        """
        self.deferredsOutstanding.append(Deferred())
        return self.deferredsOutstanding[-1]

    def deferredGotten(self, result=None):
        """
        Fire the L{Deferred} returned from the least-recent call to
        L{CancellationTests.getDeferred}.

        @param result: result object to be used when firing the L{Deferred}.
        """
        self.deferredsOutstanding.pop(0).callback(result)

    def test_cascadeCancellingOnCancel(self):
        """
        When C{D} cancelled, C{C} will be immediately cancelled too.
        """
        childResultHolder = ["FAILURE"]

        def getChildDeferred():
            d = Deferred()

            def _eb(result):
                childResultHolder[0] = result.check(CancelledError)
                return result

            d.addErrback(_eb)
            return d

        d = self.sampleInlineCB(getChildDeferred=getChildDeferred)
        d.addErrback(lambda result: None)
        d.cancel()
        self.assertEqual(
            childResultHolder[0],
            CancelledError,
            "no cascade cancelling occurs",
        )

    def test_errbackCancelledErrorOnCancel(self):
        """
        When C{D} cancelled, CancelledError from C{C} will be errbacked
        through C{D}.
        """
        d = self.sampleInlineCB()
        d.cancel()
        self.assertRaises(
            CancelledError,
            self.failureResultOf(d).raiseException,
        )

    def test_errorToErrorTranslation(self):
        """
        When C{D} is cancelled, and C raises a particular type of error, C{G}
        may catch that error at the point of yielding and translate it into
        a different error which may be received by application code.
        """

        def cancel(it):
            it.errback(UntranslatedError())

        a = Deferred(cancel)
        d = self.sampleInlineCB(lambda: a)
        d.cancel()
        self.assertRaises(
            TranslatedError,
            self.failureResultOf(d).raiseException,
        )

    def test_errorToSuccessTranslation(self):
        """
        When C{D} is cancelled, and C{C} raises a particular type of error,
        C{G} may catch that error at the point of yielding and translate it
        into a result value which may be received by application code.
        """

        def cancel(it):
            it.errback(DontFail(4321))

        a = Deferred(cancel)
        d = self.sampleInlineCB(lambda: a)
        results = []
        d.addCallback(results.append)
        d.cancel()
        self.assertEquals(results, [4320])

    def test_asynchronousCancellation(self):
        """
        When C{D} is cancelled, it won't reach the callbacks added to it by
        application code until C{C} reaches the point in its callback chain
        where C{G} awaits it.  Otherwise, application code won't be able to
        track resource usage that C{D} may be using.
        """
        moreDeferred = Deferred()

        def deferMeMore(result):
            result.trap(CancelledError)
            return moreDeferred

        def deferMe():
            d = Deferred()
            d.addErrback(deferMeMore)
            return d

        d = self.sampleInlineCB(getChildDeferred=deferMe)
        d.cancel()
        self.assertNoResult(d)
        moreDeferred.callback(6543)
        self.assertEqual(self.successResultOf(d), 6544)
