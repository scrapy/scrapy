# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.internet.defer}.
"""


import functools
import gc
import re
import traceback
import types
import warnings
from asyncio import AbstractEventLoop, CancelledError, Future, new_event_loop
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Dict,
    Generator,
    List,
    Mapping,
    NoReturn,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

from hamcrest import assert_that, equal_to, is_

from twisted.internet import defer, reactor
from twisted.internet.defer import (
    Deferred,
    DeferredFilesystemLock,
    DeferredList,
    DeferredLock,
    DeferredQueue,
    DeferredSemaphore,
    _DeferredListResultListT,
    _DeferredListSingleResultT,
    _DeferredResultT,
    ensureDeferred,
)
from twisted.internet.task import Clock
from twisted.python import log
from twisted.python.failure import Failure
from twisted.trial import unittest

if TYPE_CHECKING:
    import contextvars
else:
    try:
        import contextvars
    except ImportError:
        contextvars = None


def ensuringDeferred(
    f: Callable[..., Coroutine[Deferred[_DeferredResultT], Any, _DeferredResultT]]
) -> Callable[..., Deferred[_DeferredResultT]]:
    @functools.wraps(f)
    def wrapper(*args: object, **kwargs: object) -> Deferred[_DeferredResultT]:
        coro = f(*args, **kwargs)
        return Deferred.fromCoroutine(coro)

    return wrapper


class GenericError(Exception):
    pass


def getDivisionFailure(*args: object, **kwargs: object) -> Failure:
    """
    Make a L{Failure} of a divide-by-zero error.

    @param args: Any C{*args} are passed to Failure's constructor.
    @param kwargs: Any C{**kwargs} are passed to Failure's constructor.
    """
    try:
        1 / 0
    except BaseException:
        f = Failure(*args, **kwargs)
    return f


def fakeCallbackCanceller(deferred: Deferred[str]) -> None:
    """
    A fake L{Deferred} canceller which callbacks the L{Deferred}
    with C{str} "Callback Result" when cancelling it.

    @param deferred: The cancelled L{Deferred}.
    """
    deferred.callback("Callback Result")


_ExceptionT = TypeVar("_ExceptionT", bound=Exception)


class ImmediateFailureMixin:
    """
    Add additional assertion methods.
    """

    def assertImmediateFailure(
        self, deferred: Deferred[Any], exception: Type[_ExceptionT]
    ) -> _ExceptionT:
        """
        Assert that the given Deferred current result is a Failure with the
        given exception.

        @return: The exception instance in the Deferred.
        """
        testCase = cast(unittest.TestCase, self)
        failures: List[Failure] = []
        deferred.addErrback(failures.append)
        testCase.assertEqual(len(failures), 1)
        testCase.assertTrue(failures[0].check(exception))
        return cast(_ExceptionT, failures[0].value)


class UtilTests(unittest.TestCase):
    """
    Tests for utility functions.
    """

    def test_logErrorReturnsError(self) -> None:
        """
        L{defer.logError} returns the given error.
        """
        error = Failure(RuntimeError())
        result = defer.logError(error)
        self.flushLoggedErrors(RuntimeError)

        self.assertIs(error, result)

    def test_logErrorLogsError(self) -> None:
        """
        L{defer.logError} logs the given error.
        """
        error = Failure(RuntimeError())
        defer.logError(error)
        errors = self.flushLoggedErrors(RuntimeError)

        self.assertEqual(errors, [error])

    def test_logErrorLogsErrorNoRepr(self) -> None:
        """
        The text logged by L{defer.logError} has no repr of the failure.
        """
        output = []

        def emit(eventDict: Dict[str, Any]) -> None:
            text = log.textFromEventDict(eventDict)
            assert text is not None
            output.append(text)

        log.addObserver(emit)

        error = Failure(RuntimeError())
        defer.logError(error)
        self.flushLoggedErrors(RuntimeError)

        self.assertTrue(output[0].startswith("Unhandled Error\nTraceback "))


class DeferredTests(unittest.SynchronousTestCase, ImmediateFailureMixin):
    def setUp(self) -> None:
        self.callbackResults: Optional[
            Tuple[Tuple[object, ...], Dict[str, object]]
        ] = None
        self.callback2Results: Optional[
            Tuple[Tuple[object, ...], Dict[str, object]]
        ] = None
        self.errbackResults: Optional[
            Tuple[Tuple[Failure, ...], Dict[str, object]]
        ] = None

        # Restore the debug flag to its original state when done.
        self.addCleanup(defer.setDebugging, defer.getDebugging())

    def _callback(self, *args: object, **kwargs: object) -> Any:
        self.callbackResults = args, kwargs
        return args[0]

    def _callback2(self, *args: object, **kwargs: object) -> None:
        self.callback2Results = args, kwargs

    def _errback(self, *args: Failure, **kwargs: object) -> None:
        self.errbackResults = args, kwargs

    def testCallbackWithoutArgs(self) -> None:
        deferred: Deferred[str] = Deferred()
        deferred.addCallback(self._callback)
        deferred.callback("hello")
        self.assertIsNone(self.errbackResults)
        self.assertEqual(self.callbackResults, (("hello",), {}))

    def testCallbackWithArgs(self) -> None:
        deferred: Deferred[str] = Deferred()
        deferred.addCallback(self._callback, "world")
        deferred.callback("hello")
        self.assertIsNone(self.errbackResults)
        self.assertEqual(self.callbackResults, (("hello", "world"), {}))

    def testCallbackWithKwArgs(self) -> None:
        deferred: Deferred[str] = Deferred()
        deferred.addCallback(self._callback, world="world")
        deferred.callback("hello")
        self.assertIsNone(self.errbackResults)
        self.assertEqual(self.callbackResults, (("hello",), {"world": "world"}))

    def testTwoCallbacks(self) -> None:
        deferred: Deferred[str] = Deferred()
        deferred.addCallback(self._callback)
        deferred.addCallback(self._callback2)
        deferred.callback("hello")
        self.assertIsNone(self.errbackResults)
        self.assertEqual(self.callbackResults, (("hello",), {}))
        self.assertEqual(self.callback2Results, (("hello",), {}))

    def test_addCallbacksNoneErrback(self) -> None:
        """
        If given None for an errback, addCallbacks uses a pass-through.
        """
        error = GenericError("oopsie")
        deferred: Deferred[None] = Deferred()
        deferred.addCallbacks(self._callback, cast(Callable[..., object], None))
        deferred.errback(error)
        deferred.addErrback(self._errback)
        self.assertIsNone(self.callbackResults)
        assert self.errbackResults is not None
        self.assertEqual(len(self.errbackResults[0]), 1)
        self.assertEqual(self.errbackResults[0][0].value, error)
        self.assertEqual(self.errbackResults[1], {})

    def test_addCallbacksNoneCallbackArgs(self) -> None:
        """
        If given None as a callback args and kwargs, () and {} are used.
        """
        deferred: Deferred[str] = Deferred()
        deferred.addCallbacks(
            self._callback,
            self._errback,
            cast(Tuple[object], None),
            cast(Mapping[str, object], None),
            (),
            {},
        )
        deferred.callback("hello")
        self.assertIsNone(self.errbackResults)
        self.assertEqual(self.callbackResults, (("hello",), {}))

    def test_addCallbacksNoneErrbackArgs(self) -> None:
        """
        If given None as a errback args and kwargs, () and {} are used.
        """
        error = GenericError("oopsie")
        deferred: Deferred[None] = Deferred()
        deferred.addCallbacks(
            self._callback,
            self._errback,
            (),
            {},
            cast(Tuple[object], None),
            cast(Mapping[str, object], None),
        )
        deferred.errback(error)
        deferred.addErrback(self._errback)
        self.assertIsNone(self.callbackResults)
        assert self.errbackResults is not None
        self.assertEqual(len(self.errbackResults[0]), 1)
        self.assertEqual(self.errbackResults[0][0].value, error)
        self.assertEqual(self.errbackResults[1], {})

    def testDeferredList(self) -> None:
        ResultList = List[Tuple[bool, Union[str, Failure]]]

        defr1: Deferred[str] = Deferred()
        defr2: Deferred[str] = Deferred()
        defr3: Deferred[str] = Deferred()
        dl = DeferredList([defr1, defr2, defr3])
        result: ResultList = []

        def cb(resultList: ResultList, result: ResultList = result) -> None:
            result.extend(resultList)

        def catch(err: Failure) -> None:
            return None

        dl.addCallbacks(cb, cb)
        defr1.callback("1")
        defr2.addErrback(catch)
        # "catch" is added to eat the GenericError that will be passed on by
        # the DeferredList's callback on defr2. If left unhandled, the
        # Failure object would cause a log.err() warning about "Unhandled
        # error in Deferred". Twisted's pyunit watches for log.err calls and
        # treats them as failures. So "catch" must eat the error to prevent
        # it from flunking the test.
        defr2.errback(GenericError("2"))
        defr3.callback("3")
        self.assertEqual(
            [
                result[0],
                # result[1][1] is now a Failure instead of an Exception
                (result[1][0], str(cast(Failure, result[1][1]).value)),
                result[2],
            ],
            [(defer.SUCCESS, "1"), (defer.FAILURE, "2"), (defer.SUCCESS, "3")],
        )

    def testEmptyDeferredList(self) -> None:
        result: List[_DeferredListResultListT] = []

        def cb(
            resultList: _DeferredListResultListT,
            result: List[_DeferredListResultListT] = result,
        ) -> None:
            result.append(resultList)

        dl1: Deferred[_DeferredListResultListT] = DeferredList([])
        dl1.addCallbacks(cb)
        self.assertEqual(result, [[]])

        result[:] = []
        dl2: Deferred[_DeferredListSingleResultT] = DeferredList(
            [], fireOnOneCallback=True
        )
        dl2.addCallbacks(cb)
        self.assertEqual(result, [])

    def testDeferredListFireOnOneError(self) -> None:
        defr1: Deferred[str] = Deferred()
        defr2: Deferred[str] = Deferred()
        defr3: Deferred[str] = Deferred()
        dl = DeferredList([defr1, defr2, defr3], fireOnOneErrback=True)
        result: List[Failure] = []
        dl.addErrback(result.append)

        # consume errors after they pass through the DeferredList (to avoid
        # 'Unhandled error in Deferred'.
        def catch(err: Failure) -> None:
            return None

        defr2.addErrback(catch)

        # fire one Deferred's callback, no result yet
        defr1.callback("1")
        self.assertEqual(result, [])

        # fire one Deferred's errback -- now we have a result
        defr2.errback(GenericError("from def2"))
        self.assertEqual(len(result), 1)

        # extract the result from the list
        aFailure = result[0]

        # the type of the failure is a FirstError
        self.assertTrue(
            issubclass(aFailure.type, defer.FirstError),
            "issubclass(aFailure.type, defer.FirstError) failed: "
            "failure's type is %r" % (aFailure.type,),
        )

        firstError = aFailure.value

        # check that the GenericError("2") from the deferred at index 1
        # (defr2) is intact inside failure.value
        self.assertEqual(firstError.subFailure.type, GenericError)
        self.assertEqual(firstError.subFailure.value.args, ("from def2",))
        self.assertEqual(firstError.index, 1)

    def testDeferredListDontConsumeErrors(self) -> None:
        d1: Deferred[None] = Deferred()
        dl = DeferredList([d1])

        errorTrap: List[Failure] = []
        d1.addErrback(errorTrap.append)

        resultLists: List[_DeferredListResultListT] = []
        dl.addCallback(resultLists.append)

        d1.errback(GenericError("Bang"))
        self.assertEqual("Bang", errorTrap[0].value.args[0])
        self.assertEqual(1, len(resultLists))
        firstResult = resultLists[0][0]
        assert firstResult is not None
        self.assertEqual("Bang", firstResult[1].value.args[0])

    def testDeferredListConsumeErrors(self) -> None:
        d1: Deferred[None] = Deferred()
        dl = DeferredList([d1], consumeErrors=True)

        errorTrap: List[Failure] = []
        d1.addErrback(errorTrap.append)

        resultLists: List[_DeferredListResultListT] = []
        dl.addCallback(resultLists.append)

        d1.errback(GenericError("Bang"))
        self.assertEqual([], errorTrap)
        self.assertEqual(1, len(resultLists))
        firstResult = resultLists[0][0]
        assert firstResult is not None
        self.assertEqual("Bang", firstResult[1].value.args[0])

    def testDeferredListFireOnOneErrorWithAlreadyFiredDeferreds(self) -> None:
        # Create some deferreds, and errback one
        d1: Deferred[None] = Deferred()
        d2: Deferred[None] = Deferred()
        d1.errback(GenericError("Bang"))

        # *Then* build the DeferredList, with fireOnOneErrback=True
        dl = DeferredList([d1, d2], fireOnOneErrback=True)
        result: List[Failure] = []
        dl.addErrback(result.append)
        self.assertEqual(1, len(result))

        d1.addErrback(lambda e: None)  # Swallow error

    def testDeferredListWithAlreadyFiredDeferreds(self) -> None:
        # Create some deferreds, and err one, call the other
        d1: Deferred[int] = Deferred()
        d2: Deferred[int] = Deferred()
        d1.errback(GenericError("Bang"))
        d2.callback(2)

        # *Then* build the DeferredList
        dl = DeferredList([d1, d2])

        result: List[int] = []
        dl.addCallback(result.append)

        self.assertEqual(1, len(result))

        d1.addErrback(lambda e: None)  # Swallow error

    def test_cancelDeferredList(self) -> None:
        """
        When cancelling an unfired L{DeferredList}, cancel every
        L{Deferred} in the list.
        """
        deferredOne: Deferred[None] = Deferred()
        deferredTwo: Deferred[None] = Deferred()
        deferredList = DeferredList([deferredOne, deferredTwo])
        deferredList.cancel()
        self.failureResultOf(deferredOne, defer.CancelledError)
        self.failureResultOf(deferredTwo, defer.CancelledError)

    def test_cancelDeferredListCallback(self) -> None:
        """
        When cancelling an unfired L{DeferredList} without the
        C{fireOnOneCallback} and C{fireOnOneErrback} flags set, the
        L{DeferredList} will be callback with a C{list} of
        (success, result) C{tuple}s.
        """
        deferredOne: Deferred[str] = Deferred(fakeCallbackCanceller)
        deferredTwo: Deferred[str] = Deferred()
        deferredList = DeferredList([deferredOne, deferredTwo])
        deferredList.cancel()
        self.failureResultOf(deferredTwo, defer.CancelledError)
        result = self.successResultOf(deferredList)
        self.assertTrue(result[0][0])
        self.assertEqual(result[0][1], "Callback Result")
        self.assertFalse(result[1][0])
        self.assertTrue(result[1][1].check(defer.CancelledError))

    def test_cancelDeferredListWithFireOnOneCallback(self) -> None:
        """
        When cancelling an unfired L{DeferredList} with the flag
        C{fireOnOneCallback} set, cancel every L{Deferred} in the list.
        """
        deferredOne: Deferred[None] = Deferred()
        deferredTwo: Deferred[None] = Deferred()
        deferredList = DeferredList([deferredOne, deferredTwo], fireOnOneCallback=True)
        deferredList.cancel()
        self.failureResultOf(deferredOne, defer.CancelledError)
        self.failureResultOf(deferredTwo, defer.CancelledError)

    def test_cancelDeferredListWithFireOnOneCallbackAndDeferredCallback(self) -> None:
        """
        When cancelling an unfired L{DeferredList} with the flag
        C{fireOnOneCallback} set, if one of the L{Deferred} callbacks
        in its canceller, the L{DeferredList} will callback with the
        result and the index of the L{Deferred} in a C{tuple}.
        """
        deferredOne: Deferred[str] = Deferred(fakeCallbackCanceller)
        deferredTwo: Deferred[str] = Deferred()
        deferredList = DeferredList([deferredOne, deferredTwo], fireOnOneCallback=True)
        deferredList.cancel()
        self.failureResultOf(deferredTwo, defer.CancelledError)
        result = self.successResultOf(deferredList)
        self.assertEqual(result, ("Callback Result", 0))

    def test_cancelDeferredListWithFireOnOneErrback(self) -> None:
        """
        When cancelling an unfired L{DeferredList} with the flag
        C{fireOnOneErrback} set, cancel every L{Deferred} in the list.
        """
        deferredOne: Deferred[None] = Deferred()
        deferredTwo: Deferred[None] = Deferred()
        deferredList = DeferredList([deferredOne, deferredTwo], fireOnOneErrback=True)
        deferredList.cancel()
        self.failureResultOf(deferredOne, defer.CancelledError)
        self.failureResultOf(deferredTwo, defer.CancelledError)
        deferredListFailure = self.failureResultOf(deferredList, defer.FirstError)
        firstError = deferredListFailure.value
        self.assertTrue(firstError.subFailure.check(defer.CancelledError))

    def test_cancelDeferredListWithFireOnOneErrbackAllDeferredsCallback(self) -> None:
        """
        When cancelling an unfired L{DeferredList} with the flag
        C{fireOnOneErrback} set, if all the L{Deferred} callbacks
        in its canceller, the L{DeferredList} will callback with a
        C{list} of (success, result) C{tuple}s.
        """
        deferredOne: Deferred[str] = Deferred(fakeCallbackCanceller)
        deferredTwo: Deferred[str] = Deferred(fakeCallbackCanceller)
        deferredList = DeferredList([deferredOne, deferredTwo], fireOnOneErrback=True)
        deferredList.cancel()
        result = self.successResultOf(deferredList)
        self.assertTrue(result[0][0])
        self.assertEqual(result[0][1], "Callback Result")
        self.assertTrue(result[1][0])
        self.assertEqual(result[1][1], "Callback Result")

    def test_cancelDeferredListWithOriginalDeferreds(self) -> None:
        """
        Cancelling a L{DeferredList} will cancel the original
        L{Deferred}s passed in.
        """
        deferredOne: Deferred[None] = Deferred()
        deferredTwo: Deferred[None] = Deferred()
        argumentList = [deferredOne, deferredTwo]
        deferredList = DeferredList(argumentList)
        deferredThree: Deferred[None] = Deferred()
        argumentList.append(deferredThree)
        deferredList.cancel()
        self.failureResultOf(deferredOne, defer.CancelledError)
        self.failureResultOf(deferredTwo, defer.CancelledError)
        self.assertNoResult(deferredThree)

    def test_cancelDeferredListWithException(self) -> None:
        """
        Cancelling a L{DeferredList} will cancel every L{Deferred}
        in the list even exceptions raised from the C{cancel} method of the
        L{Deferred}s.
        """

        def cancellerRaisesException(deferred: Deferred[object]) -> None:
            """
            A L{Deferred} canceller that raises an exception.

            @param deferred: The cancelled L{Deferred}.
            """
            raise RuntimeError("test")

        deferredOne: Deferred[None] = Deferred(cancellerRaisesException)
        deferredTwo: Deferred[None] = Deferred()
        deferredList = DeferredList([deferredOne, deferredTwo])
        deferredList.cancel()
        self.failureResultOf(deferredTwo, defer.CancelledError)
        errors = self.flushLoggedErrors(RuntimeError)
        self.assertEqual(len(errors), 1)

    def test_cancelFiredOnOneCallbackDeferredList(self) -> None:
        """
        When a L{DeferredList} has fired because one L{Deferred} in
        the list fired with a non-failure result, the cancellation will do
        nothing instead of cancelling the rest of the L{Deferred}s.
        """
        deferredOne: Deferred[None] = Deferred()
        deferredTwo: Deferred[None] = Deferred()
        deferredList = DeferredList([deferredOne, deferredTwo], fireOnOneCallback=True)
        deferredOne.callback(None)
        deferredList.cancel()
        self.assertNoResult(deferredTwo)

    def test_cancelFiredOnOneErrbackDeferredList(self) -> None:
        """
        When a L{DeferredList} has fired because one L{Deferred} in
        the list fired with a failure result, the cancellation will do
        nothing instead of cancelling the rest of the L{Deferred}s.
        """
        deferredOne: Deferred[None] = Deferred()
        deferredTwo: Deferred[None] = Deferred()
        deferredList = DeferredList([deferredOne, deferredTwo], fireOnOneErrback=True)
        deferredOne.errback(GenericError("test"))
        deferredList.cancel()
        self.assertNoResult(deferredTwo)
        self.failureResultOf(deferredOne, GenericError)
        self.failureResultOf(deferredList, defer.FirstError)

    def testImmediateSuccess(self) -> None:
        l: List[str] = []
        d: Deferred[str] = defer.succeed("success")
        d.addCallback(l.append)
        self.assertEqual(l, ["success"])

    def testImmediateFailure(self) -> None:
        l: List[Failure] = []
        d: Deferred[None] = defer.fail(GenericError("fail"))
        d.addErrback(l.append)
        self.assertEqual(str(l[0].value), "fail")

    def testPausedFailure(self) -> None:
        l: List[Failure] = []
        d = defer.fail(GenericError("fail"))
        d.pause()
        d.addErrback(l.append)
        self.assertEqual(l, [])
        d.unpause()
        self.assertEqual(str(l[0].value), "fail")

    def testCallbackErrors(self) -> None:
        l: List[Failure] = []
        d = Deferred().addCallback(lambda _: 1 // 0).addErrback(l.append)
        d.callback(1)
        self.assertIsInstance(l[0].value, ZeroDivisionError)
        l = []
        d = (
            Deferred()
            .addCallback(lambda _: Failure(ZeroDivisionError()))
            .addErrback(l.append)
        )
        d.callback(1)
        self.assertIsInstance(l[0].value, ZeroDivisionError)

    def testUnpauseBeforeCallback(self) -> None:
        d: Deferred[None] = Deferred()
        d.pause()
        d.addCallback(self._callback)
        d.unpause()

    def testReturnDeferred(self) -> None:
        d1: Deferred[int] = Deferred()
        d2: Deferred[int] = Deferred()
        d2.pause()
        d1.addCallback(lambda r, d2=d2: cast(int, d2))
        d1.addCallback(self._callback)
        d1.callback(1)
        assert self.callbackResults is None, "Should not have been called yet."
        d2.callback(2)
        assert self.callbackResults is None, "Still should not have been called yet."
        d2.unpause()
        assert self.callbackResults is not None
        assert (  # type: ignore[unreachable]
            self.callbackResults[0][0] == 2
        ), "Result should have been from second deferred:{}".format(
            self.callbackResults
        )

    def test_chainedPausedDeferredWithResult(self) -> None:
        """
        When a paused Deferred with a result is returned from a callback on
        another Deferred, the other Deferred is chained to the first and waits
        for it to be unpaused.
        """
        expected = object()
        paused: Deferred[object] = Deferred()
        paused.callback(expected)
        paused.pause()
        chained: Deferred[None] = Deferred()
        chained.addCallback(lambda ignored: paused)
        chained.callback(None)

        result: List[object] = []
        chained.addCallback(result.append)
        self.assertEqual(result, [])
        paused.unpause()
        self.assertEqual(result, [expected])

    def test_pausedDeferredChained(self) -> None:
        """
        A paused Deferred encountered while pushing a result forward through a
        chain does not prevent earlier Deferreds from continuing to execute
        their callbacks.
        """
        first: Deferred[None] = Deferred()
        second: Deferred[None] = Deferred()
        first.addCallback(lambda ignored: second)
        first.callback(None)
        first.pause()
        second.callback(None)
        result: List[None] = []
        second.addCallback(result.append)
        self.assertEqual(result, [None])

    def test_gatherResults(self) -> None:
        # test successful list of deferreds
        results: List[List[int]] = []
        defer.gatherResults([defer.succeed(1), defer.succeed(2)]).addCallback(
            results.append
        )
        self.assertEqual(results, [[1, 2]])
        # test failing list of deferreds
        errors: List[Failure] = []
        dl = [defer.succeed(1), defer.fail(ValueError())]
        defer.gatherResults(dl).addErrback(errors.append)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], Failure)
        # get rid of error
        dl[1].addErrback(lambda e: 1)

    def test_gatherResultsWithConsumeErrors(self) -> None:
        """
        If a L{Deferred} in the list passed to L{gatherResults} fires with a
        failure and C{consumerErrors} is C{True}, the failure is converted to a
        L{None} result on that L{Deferred}.
        """
        # test successful list of deferreds
        dgood = defer.succeed(1)
        dbad = defer.fail(RuntimeError("oh noes"))
        d = defer.gatherResults([dgood, dbad], consumeErrors=True)
        unconsumedErrors: List[Failure] = []
        dbad.addErrback(unconsumedErrors.append)
        gatheredErrors: List[Failure] = []
        d.addErrback(gatheredErrors.append)

        self.assertEqual((len(unconsumedErrors), len(gatheredErrors)), (0, 1))
        self.assertIsInstance(gatheredErrors[0].value, defer.FirstError)
        firstError = gatheredErrors[0].value.subFailure
        self.assertIsInstance(firstError.value, RuntimeError)

    def test_cancelGatherResults(self) -> None:
        """
        When cancelling the L{defer.gatherResults} call, all the
        L{Deferred}s in the list will be cancelled.
        """
        deferredOne: Deferred[None] = Deferred()
        deferredTwo: Deferred[None] = Deferred()
        result = defer.gatherResults([deferredOne, deferredTwo])
        result.cancel()
        self.failureResultOf(deferredOne, defer.CancelledError)
        self.failureResultOf(deferredTwo, defer.CancelledError)
        gatherResultsFailure = self.failureResultOf(result, defer.FirstError)
        firstError = gatherResultsFailure.value
        self.assertTrue(firstError.subFailure.check(defer.CancelledError))

    def test_cancelGatherResultsWithAllDeferredsCallback(self) -> None:
        """
        When cancelling the L{defer.gatherResults} call, if all the
        L{Deferred}s callback in their canceller, the L{Deferred}
        returned by L{defer.gatherResults} will be callbacked with the C{list}
        of the results.
        """
        deferredOne: Deferred[str] = Deferred(fakeCallbackCanceller)
        deferredTwo: Deferred[str] = Deferred(fakeCallbackCanceller)
        result = defer.gatherResults([deferredOne, deferredTwo])
        result.cancel()
        callbackResult = self.successResultOf(result)
        self.assertEqual(callbackResult[0], "Callback Result")
        self.assertEqual(callbackResult[1], "Callback Result")

    def test_maybeDeferredSync(self) -> None:
        """
        L{defer.maybeDeferred} should retrieve the result of a synchronous
        function and pass it to its resulting L{Deferred}.
        """
        result = object()
        results: List[object] = []
        errors: List[Failure] = []
        d = defer.maybeDeferred(lambda: result)
        d.addCallbacks(results.append, errors.append)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 1)
        self.assertIdentical(results[0], result)

    def test_maybeDeferredSyncWithArgs(self) -> None:
        """
        L{defer.maybeDeferred} should pass arguments to the called function.
        """

        def plusFive(x: int) -> int:
            return x + 5

        results: List[int] = []
        errors: List[Failure] = []
        d = defer.maybeDeferred(plusFive, 10)
        d.addCallbacks(results.append, errors.append)
        self.assertEqual(errors, [])
        self.assertEqual(results, [15])

    def test_maybeDeferredSyncException(self) -> None:
        """
        L{defer.maybeDeferred} should catch an exception raised by a synchronous
        function and errback its resulting L{Deferred} with it.
        """
        expected = ValueError("that value is unacceptable")

        def raisesException() -> NoReturn:
            raise expected

        results: List[int] = []
        errors: List[Failure] = []
        d = defer.maybeDeferred(raisesException)
        d.addCallbacks(results.append, errors.append)
        self.assertEqual(results, [])
        self.assertEqual(len(errors), 1)
        self.assertEqual(str(errors[0].value), str(expected))

    def test_maybeDeferredSyncFailure(self) -> None:
        """
        L{defer.maybeDeferred} should handle a L{Failure} returned by a
        function and errback with it.
        """
        try:
            "10" + 5  # type: ignore[operator]
        except TypeError:
            expected = Failure()

        results: List[int] = []
        errors: List[Failure] = []
        d = defer.maybeDeferred(lambda: expected)
        d.addCallbacks(results.append, errors.append)
        self.assertEqual(results, [])
        self.assertEqual(len(errors), 1)
        self.assertIdentical(errors[0], expected)

    def test_maybeDeferredAsync(self) -> None:
        """
        L{defer.maybeDeferred} should let L{Deferred} instance pass by
        so that original result is the same.
        """
        d1: Deferred[str] = Deferred()
        d2 = defer.maybeDeferred(lambda: d1)
        d1.callback("Success")
        result: List[str] = []
        d2.addCallback(result.append)
        self.assertEqual(result, ["Success"])

    def test_maybeDeferredAsyncError(self) -> None:
        """
        L{defer.maybeDeferred} should let L{Deferred} instance pass by
        so that L{Failure} returned by the original instance is the
        same.
        """
        d1: Deferred[None] = Deferred()
        d2: Deferred[None] = defer.maybeDeferred(
            lambda: d1  # type: ignore[arg-type]  # because nested Deferred
        )
        d1.errback(Failure(RuntimeError()))
        self.assertImmediateFailure(d2, RuntimeError)

    def test_maybeDeferredCoroutineSuccess(self) -> None:
        """
        When called with a coroutine function L{defer.maybeDeferred} returns a
        L{defer.Deferred} which has the same result as the coroutine returned
        by the function.
        """
        result = object()

        async def f() -> object:
            return result

        # Demonstrate that the function itself does not need to be a coroutine
        # function to trigger the coroutine-handling behavior.
        def g() -> Coroutine:
            return f()

        assert_that(
            self.successResultOf(defer.maybeDeferred(g)),
            is_(result),
        )

    def test_maybeDeferredCoroutineFailure(self) -> None:
        """
        When called with a coroutine function L{defer.maybeDeferred} returns a
        L{defer.Deferred} which has a L{Failure} result wrapping the exception
        raised by the coroutine function.
        """

        class SomeException(Exception):
            pass

        async def f() -> None:
            raise SomeException()

        # Demonstrate that the function itself does not need to be a coroutine
        # function to trigger the coroutine-handling behavior.
        def g() -> Coroutine:
            return f()

        assert_that(
            self.failureResultOf(defer.maybeDeferred(g)).type,
            equal_to(SomeException),
        )

    def test_innerCallbacksPreserved(self) -> None:
        """
        When a L{Deferred} encounters a result which is another L{Deferred}
        which is waiting on a third L{Deferred}, the middle L{Deferred}'s
        callbacks are executed after the third L{Deferred} fires and before the
        first receives a result.
        """
        results: List[Tuple[str, str]] = []
        failures: List[Failure] = []
        inner: Deferred[str] = Deferred()

        def cb(result: str) -> Deferred[str]:
            results.append(("start-of-cb", result))
            d = defer.succeed("inner")

            def firstCallback(result: str) -> Deferred[str]:
                results.append(("firstCallback", "inner"))
                return inner

            def secondCallback(result: str) -> str:
                results.append(("secondCallback", result))
                return result * 2

            d.addCallback(firstCallback).addCallback(secondCallback)
            d.addErrback(failures.append)
            return d

        outer = defer.succeed("outer")
        outer.addCallback(cb)
        inner.callback("orange")
        outer.addCallback(results.append)
        inner.addErrback(failures.append)
        outer.addErrback(failures.append)
        self.assertEqual([], failures)
        self.assertEqual(
            results,
            [
                ("start-of-cb", "outer"),
                ("firstCallback", "inner"),
                ("secondCallback", "orange"),
                "orangeorange",
            ],
        )

    def test_continueCallbackNotFirst(self) -> None:
        """
        The continue callback of a L{Deferred} waiting for another L{Deferred}
        is not necessarily the first one. This is somewhat a whitebox test
        checking that we search for that callback among the whole list of
        callbacks.
        """
        results: List[Tuple[str, Optional[str]]] = []
        failures: List[Failure] = []
        a: Deferred[str] = Deferred()

        def cb(result: str) -> Deferred[Optional[str]]:
            results.append(("cb", result))
            d: Deferred[Optional[str]] = Deferred()

            def firstCallback(result: str) -> Deferred[List[str]]:
                results.append(("firstCallback", result))
                return defer.gatherResults([a])

            def secondCallback(result: str) -> None:
                results.append(("secondCallback", result))

            d.addCallback(firstCallback)
            d.addCallback(secondCallback)
            d.addErrback(failures.append)
            d.callback(None)
            return d

        outer = defer.succeed("outer")
        outer.addCallback(cb)
        outer.addErrback(failures.append)
        self.assertEqual([("cb", "outer"), ("firstCallback", None)], results)
        a.callback("withers")
        self.assertEqual([], failures)
        self.assertEqual(
            results,
            [("cb", "outer"), ("firstCallback", None), ("secondCallback", ["withers"])],
        )

    def test_callbackOrderPreserved(self) -> None:
        """
        A callback added to a L{Deferred} after a previous callback attached
        another L{Deferred} as a result is run after the callbacks of the other
        L{Deferred} are run.
        """
        results: List[Tuple[str, Optional[str]]] = []
        failures: List[Failure] = []
        a: Deferred[Optional[str]] = Deferred()

        def cb(result: str) -> Deferred[Optional[str]]:
            results.append(("cb", result))
            d: Deferred[Optional[str]] = Deferred()

            def firstCallback(result: str) -> Deferred[List[str]]:
                results.append(("firstCallback", result))
                return defer.gatherResults([a])

            def secondCallback(result: str) -> None:
                results.append(("secondCallback", result))

            d.addCallback(firstCallback)
            d.addCallback(secondCallback)
            d.addErrback(failures.append)
            d.callback(None)
            return d

        outer: Deferred[str] = Deferred()
        outer.addCallback(cb)
        outer.addCallback(lambda x: results.append(("final", None)))
        outer.addErrback(failures.append)
        outer.callback("outer")
        self.assertEqual([("cb", "outer"), ("firstCallback", None)], results)
        a.callback("withers")
        self.assertEqual([], failures)
        self.assertEqual(
            results,
            [
                ("cb", "outer"),
                ("firstCallback", None),
                ("secondCallback", ["withers"]),
                ("final", None),
            ],
        )

    def test_reentrantRunCallbacks(self) -> None:
        """
        A callback added to a L{Deferred} by a callback on that L{Deferred}
        should be added to the end of the callback chain.
        """
        deferred: Deferred[None] = Deferred()
        called = []

        def callback3(result: None) -> None:
            called.append(3)

        def callback2(result: None) -> None:
            called.append(2)

        def callback1(result: None) -> None:
            called.append(1)
            deferred.addCallback(callback3)

        deferred.addCallback(callback1)
        deferred.addCallback(callback2)
        deferred.callback(None)
        self.assertEqual(called, [1, 2, 3])

    def test_nonReentrantCallbacks(self) -> None:
        """
        A callback added to a L{Deferred} by a callback on that L{Deferred}
        should not be executed until the running callback returns.
        """
        deferred: Deferred[None] = Deferred()
        called = []

        def callback2(result: None) -> None:
            called.append(2)

        def callback1(result: None) -> None:
            called.append(1)
            deferred.addCallback(callback2)
            self.assertEqual(called, [1])

        deferred.addCallback(callback1)
        deferred.callback(None)
        self.assertEqual(called, [1, 2])

    def test_reentrantRunCallbacksWithFailure(self) -> None:
        """
        After an exception is raised by a callback which was added to a
        L{Deferred} by a callback on that L{Deferred}, the L{Deferred} should
        call the first errback with a L{Failure} wrapping that exception.
        """
        exceptionMessage = "callback raised exception"
        deferred: Deferred[None] = Deferred()

        def callback2(result: object) -> None:
            raise Exception(exceptionMessage)

        def callback1(result: object) -> None:
            deferred.addCallback(callback2)

        deferred.addCallback(callback1)
        deferred.callback(None)
        exception = self.assertImmediateFailure(deferred, Exception)
        self.assertEqual(exception.args, (exceptionMessage,))

    def test_synchronousImplicitChain(self) -> None:
        """
        If a first L{Deferred} with a result is returned from a callback on a
        second L{Deferred}, the result of the second L{Deferred} becomes the
        result of the first L{Deferred} and the result of the first L{Deferred}
        becomes L{None}.
        """
        result = object()
        first = defer.succeed(result)
        second: Deferred[None] = Deferred()
        second.addCallback(lambda ign: first)
        second.callback(None)

        results: List[Optional[object]] = []
        first.addCallback(results.append)
        self.assertIsNone(results[0])
        second.addCallback(results.append)
        self.assertIs(results[1], result)

    def test_asynchronousImplicitChain(self) -> None:
        """
        If a first L{Deferred} without a result is returned from a callback on
        a second L{Deferred}, the result of the second L{Deferred} becomes the
        result of the first L{Deferred} as soon as the first L{Deferred} has
        one and the result of the first L{Deferred} becomes L{None}.
        """
        first: Deferred[object] = Deferred()
        second: Deferred[object] = Deferred()
        second.addCallback(lambda ign: first)
        second.callback(None)

        firstResult: List[object] = []
        first.addCallback(firstResult.append)
        secondResult: List[object] = []
        second.addCallback(secondResult.append)

        self.assertEqual(firstResult, [])
        self.assertEqual(secondResult, [])

        result = object()
        first.callback(result)

        self.assertEqual(firstResult, [None])
        self.assertEqual(secondResult, [result])

    def test_synchronousImplicitErrorChain(self) -> None:
        """
        If a first L{Deferred} with a L{Failure} result is returned from a
        callback on a second L{Deferred}, the first L{Deferred}'s result is
        converted to L{None} and no unhandled error is logged when it is
        garbage collected.
        """
        first = defer.fail(RuntimeError("First Deferred's Failure"))

        def cb(_: None, first: Deferred[None] = first) -> Deferred[None]:
            return first

        second: Deferred[None] = Deferred()
        second.addCallback(cb)
        second.callback(None)
        firstResult: List[None] = []
        first.addCallback(firstResult.append)
        self.assertIsNone(firstResult[0])
        self.assertImmediateFailure(second, RuntimeError)

    def test_asynchronousImplicitErrorChain(self) -> None:
        """
        Let C{a} and C{b} be two L{Deferred}s.

        If C{a} has no result and is returned from a callback on C{b} then when
        C{a} fails, C{b}'s result becomes the L{Failure} that was C{a}'s result,
        the result of C{a} becomes L{None} so that no unhandled error is logged
        when it is garbage collected.
        """
        first: Deferred[None] = Deferred()
        second: Deferred[None] = Deferred()
        second.addCallback(lambda ign: first)
        second.callback(None)
        secondError: List[Failure] = []
        second.addErrback(secondError.append)

        firstResult: List[None] = []
        first.addCallback(firstResult.append)
        secondResult: List[None] = []
        second.addCallback(secondResult.append)

        self.assertEqual(firstResult, [])
        self.assertEqual(secondResult, [])

        first.errback(RuntimeError("First Deferred's Failure"))
        self.assertTrue(secondError[0].check(RuntimeError))
        self.assertEqual(firstResult, [None])
        self.assertEqual(len(secondResult), 1)

    def test_doubleAsynchronousImplicitChaining(self) -> None:
        """
        L{Deferred} chaining is transitive.

        In other words, let A, B, and C be Deferreds.  If C is returned from a
        callback on B and B is returned from a callback on A then when C fires,
        A fires.
        """
        first: Deferred[object] = Deferred()
        second: Deferred[object] = Deferred()
        second.addCallback(lambda ign: first)
        third: Deferred[object] = Deferred()
        third.addCallback(lambda ign: second)

        thirdResult: List[object] = []
        third.addCallback(thirdResult.append)

        result = object()
        # After this, second is waiting for first to tell it to continue.
        second.callback(None)
        # And after this, third is waiting for second to tell it to continue.
        third.callback(None)

        # Still waiting
        self.assertEqual(thirdResult, [])

        # This will tell second to continue which will tell third to continue.
        first.callback(result)

        self.assertEqual(thirdResult, [result])

    def test_nestedAsynchronousChainedDeferreds(self) -> None:
        """
        L{Deferred}s can have callbacks that themselves return L{Deferred}s.
        When these "inner" L{Deferred}s fire (even asynchronously), the
        callback chain continues.
        """
        results: List[Tuple[str, str]] = []
        failures: List[Failure] = []

        # A Deferred returned in the inner callback.
        inner: Deferred[str] = Deferred()

        def cb(result: str) -> Deferred[str]:
            results.append(("start-of-cb", result))
            d = defer.succeed("inner")

            def firstCallback(result: str) -> Deferred[str]:
                results.append(("firstCallback", "inner"))
                # Return a Deferred that definitely has not fired yet, so we
                # can fire the Deferreds out of order.
                return inner

            def secondCallback(result: str) -> str:
                results.append(("secondCallback", result))
                return result * 2

            d.addCallback(firstCallback).addCallback(secondCallback)
            d.addErrback(failures.append)
            return d

        # Create a synchronous Deferred that has a callback 'cb' that returns
        # a Deferred 'd' that has fired but is now waiting on an unfired
        # Deferred 'inner'.
        outer = defer.succeed("outer")
        outer.addCallback(cb)
        outer.addCallback(results.append)
        # At this point, the callback 'cb' has been entered, and the first
        # callback of 'd' has been called.
        self.assertEqual(
            results, [("start-of-cb", "outer"), ("firstCallback", "inner")]
        )

        # Once the inner Deferred is fired, processing of the outer Deferred's
        # callback chain continues.
        inner.callback("orange")

        # Make sure there are no errors.
        inner.addErrback(failures.append)
        outer.addErrback(failures.append)
        self.assertEqual([], failures, "Got errbacks but wasn't expecting any.")

        self.assertEqual(
            results,
            [
                ("start-of-cb", "outer"),
                ("firstCallback", "inner"),
                ("secondCallback", "orange"),
                "orangeorange",
            ],
        )

    def test_nestedAsynchronousChainedDeferredsWithExtraCallbacks(self) -> None:
        """
        L{Deferred}s can have callbacks that themselves return L{Deferred}s.
        These L{Deferred}s can have other callbacks added before they are
        returned, which subtly changes the callback chain. When these "inner"
        L{Deferred}s fire (even asynchronously), the outer callback chain
        continues.
        """
        results: List[Any] = []
        failures: List[Failure] = []

        # A Deferred returned in the inner callback after a callback is
        # added explicitly and directly to it.
        inner: Deferred[Union[str, List[str]]] = Deferred()

        def cb(result: str) -> Deferred[str]:
            results.append(("start-of-cb", result))
            d = defer.succeed("inner")

            def firstCallback(result: str) -> Deferred[List[str]]:
                results.append(("firstCallback", result))
                # Return a Deferred that definitely has not fired yet with a
                # result-transforming callback so we can fire the Deferreds
                # out of order and see how the callback affects the ultimate
                # results.

                def transform(result: str) -> List[str]:
                    return [result]

                return inner.addCallback(transform)

            def secondCallback(result: List[str]) -> List[str]:
                results.append(("secondCallback", result))
                return result * 2

            d.addCallback(firstCallback)
            d.addCallback(secondCallback)
            d.addErrback(failures.append)
            return d

        # Create a synchronous Deferred that has a callback 'cb' that returns
        # a Deferred 'd' that has fired but is now waiting on an unfired
        # Deferred 'inner'.
        outer = defer.succeed("outer")
        outer.addCallback(cb)
        outer.addCallback(results.append)
        # At this point, the callback 'cb' has been entered, and the first
        # callback of 'd' has been called.
        self.assertEqual(
            results, [("start-of-cb", "outer"), ("firstCallback", "inner")]
        )

        # Once the inner Deferred is fired, processing of the outer Deferred's
        # callback chain continues.
        inner.callback("withers")

        # Make sure there are no errors.
        outer.addErrback(failures.append)
        inner.addErrback(failures.append)
        self.assertEqual([], failures, "Got errbacks but wasn't expecting any.")

        self.assertEqual(
            results,
            [
                ("start-of-cb", "outer"),
                ("firstCallback", "inner"),
                ("secondCallback", ["withers"]),
                ["withers", "withers"],
            ],
        )

    def test_chainDeferredRecordsExplicitChain(self) -> None:
        """
        When we chain a L{Deferred}, that chaining is recorded explicitly.
        """
        a: Deferred[None] = Deferred()
        b: Deferred[None] = Deferred()
        b.chainDeferred(a)
        self.assertIs(a._chainedTo, b)

    def test_explicitChainClearedWhenResolved(self) -> None:
        """
        Any recorded chaining is cleared once the chaining is resolved, since
        it no longer exists.

        In other words, if one L{Deferred} is recorded as depending on the
        result of another, and I{that} L{Deferred} has fired, then the
        dependency is resolved and we no longer benefit from recording it.
        """
        a: Deferred[None] = Deferred()
        b: Deferred[None] = Deferred()
        b.chainDeferred(a)
        b.callback(None)
        self.assertIsNone(a._chainedTo)

    def test_chainDeferredRecordsImplicitChain(self) -> None:
        """
        We can chain L{Deferred}s implicitly by adding callbacks that return
        L{Deferred}s. When this chaining happens, we record it explicitly as
        soon as we can find out about it.
        """
        a: Deferred[None] = Deferred()
        b: Deferred[None] = Deferred()
        a.addCallback(lambda ignored: b)
        a.callback(None)
        self.assertIs(a._chainedTo, b)

    def test_circularChainWarning(self) -> None:
        """
        When a Deferred is returned from a callback directly attached to that
        same Deferred, a warning is emitted.
        """
        d: Deferred[str] = Deferred()

        def circularCallback(result: str) -> Deferred[str]:
            return d

        d.addCallback(circularCallback)
        d.callback("foo")

        circular_warnings = self.flushWarnings([circularCallback])
        self.assertEqual(len(circular_warnings), 1)
        warning = circular_warnings[0]
        self.assertEqual(warning["category"], DeprecationWarning)
        pattern = "Callback returned the Deferred it was attached to"
        self.assertTrue(
            re.search(pattern, warning["message"]),
            "\nExpected match: {!r}\nGot: {!r}".format(pattern, warning["message"]),
        )

    def test_circularChainException(self) -> None:
        """
        If the deprecation warning for circular deferred callbacks is
        configured to be an error, the exception will become the failure
        result of the Deferred.
        """
        self.addCleanup(
            setattr,
            warnings,
            "filters",
            warnings.filters,
        )
        warnings.filterwarnings("error", category=DeprecationWarning)
        d: Deferred[str] = Deferred()

        def circularCallback(result: str) -> Deferred[str]:
            return d

        d.addCallback(circularCallback)
        d.callback("foo")
        failure = self.failureResultOf(d)
        failure.trap(DeprecationWarning)

    def test_repr(self) -> None:
        """
        The C{repr()} of a L{Deferred} contains the class name and a
        representation of the internal Python ID.
        """
        d: Deferred[None] = Deferred()
        address = id(d)
        self.assertEqual(repr(d), f"<Deferred at 0x{address:x}>")

    def test_reprWithResult(self) -> None:
        """
        If a L{Deferred} has been fired, then its C{repr()} contains its
        result.
        """
        d: Deferred[str] = Deferred()
        d.callback("orange")
        self.assertEqual(repr(d), f"<Deferred at 0x{id(d):x} current result: 'orange'>")

    def test_reprWithChaining(self) -> None:
        """
        If a L{Deferred} C{a} has been fired, but is waiting on another
        L{Deferred} C{b} that appears in its callback chain, then C{repr(a)}
        says that it is waiting on C{b}.
        """
        a: Deferred[None] = Deferred()
        b: Deferred[None] = Deferred()
        b.chainDeferred(a)
        self.assertEqual(
            repr(a),
            f"<Deferred at 0x{id(a):x} waiting on Deferred at 0x{id(b):x}>",
        )

    def test_boundedStackDepth(self) -> None:
        """
        The depth of the call stack does not grow as more L{Deferred} instances
        are chained together.
        """

        def chainDeferreds(howMany: int) -> int:
            stack = []

            def recordStackDepth(ignored: object) -> None:
                stack.append(len(traceback.extract_stack()))

            top: Deferred[None] = Deferred()
            innerDeferreds: List[Deferred[None]] = [
                Deferred() for ignored in range(howMany)
            ]
            originalInners = innerDeferreds[:]
            last: Deferred[None] = Deferred()

            inner = innerDeferreds.pop()

            def cbInner(
                ignored: object, inner: Deferred[None] = inner
            ) -> Deferred[None]:
                return inner

            top.addCallback(cbInner)
            top.addCallback(recordStackDepth)

            while innerDeferreds:
                newInner = innerDeferreds.pop()

                def cbNewInner(
                    ignored: object, inner: Deferred[None] = newInner
                ) -> Deferred[None]:
                    return inner

                inner.addCallback(cbNewInner)
                inner = newInner

            inner.addCallback(lambda ign: last)

            top.callback(None)
            for inner in originalInners:
                inner.callback(None)

            # Sanity check - the record callback is not intended to have
            # fired yet.
            self.assertEqual(stack, [])

            # Now fire the last thing and return the stack depth at which the
            # callback was invoked.
            last.callback(None)
            return stack[0]

        # Callbacks should be invoked at the same stack depth regardless of
        # how many Deferreds are chained.
        self.assertEqual(chainDeferreds(1), chainDeferreds(2))

    def test_resultOfDeferredResultOfDeferredOfFiredDeferredCalled(self) -> None:
        """
        Given three Deferreds, one chained to the next chained to the next,
        callbacks on the middle Deferred which are added after the chain is
        created are called once the last Deferred fires.

        This is more of a regression-style test.  It doesn't exercise any
        particular code path through the current implementation of Deferred, but
        it does exercise a broken codepath through one of the variations of the
        implementation proposed as a resolution to ticket #411.
        """
        first: Deferred[None] = Deferred()
        second: Deferred[None] = Deferred()
        third: Deferred[None] = Deferred()
        first.addCallback(lambda ignored: second)
        second.addCallback(lambda ignored: third)
        second.callback(None)
        first.callback(None)
        third.callback(None)
        results: List[None] = []
        second.addCallback(results.append)
        self.assertEqual(results, [None])

    def test_errbackWithNoArgsNoDebug(self) -> None:
        """
        C{Deferred.errback()} creates a failure from the current Python
        exception.  When Deferred.debug is not set no globals or locals are
        captured in that failure.
        """
        defer.setDebugging(False)
        d: Deferred[None] = Deferred()
        l: List[Failure] = []
        exc = GenericError("Bang")
        try:
            raise exc
        except BaseException:
            d.errback()
        d.addErrback(l.append)
        fail = l[0]
        self.assertEqual(fail.value, exc)
        localz, globalz = fail.frames[0][-2:]
        self.assertEqual([], localz)
        self.assertEqual([], globalz)

    def test_errbackWithNoArgs(self) -> None:
        """
        C{Deferred.errback()} creates a failure from the current Python
        exception.  When Deferred.debug is set globals and locals are captured
        in that failure.
        """
        defer.setDebugging(True)
        d: Deferred[None] = Deferred()
        l: List[Failure] = []
        exc = GenericError("Bang")
        try:
            raise exc
        except BaseException:
            d.errback()
        d.addErrback(l.append)
        fail = l[0]
        self.assertEqual(fail.value, exc)
        localz, globalz = fail.frames[0][-2:]
        self.assertNotEqual([], localz)
        self.assertNotEqual([], globalz)

    def test_errorInCallbackDoesNotCaptureVars(self) -> None:
        """
        An error raised by a callback creates a Failure.  The Failure captures
        locals and globals if and only if C{Deferred.debug} is set.
        """
        d: Deferred[None] = Deferred()
        d.callback(None)
        defer.setDebugging(False)

        def raiseError(ignored: object) -> None:
            raise GenericError("Bang")

        d.addCallback(raiseError)
        l: List[Failure] = []
        d.addErrback(l.append)
        fail = l[0]
        localz, globalz = fail.frames[0][-2:]
        self.assertEqual([], localz)
        self.assertEqual([], globalz)

    def test_errorInCallbackCapturesVarsWhenDebugging(self) -> None:
        """
        An error raised by a callback creates a Failure.  The Failure captures
        locals and globals if and only if C{Deferred.debug} is set.
        """
        d: Deferred[None] = Deferred()
        d.callback(None)
        defer.setDebugging(True)

        def raiseError(ignored: object) -> None:
            raise GenericError("Bang")

        d.addCallback(raiseError)
        l: List[Failure] = []
        d.addErrback(l.append)
        fail = l[0]
        localz, globalz = fail.frames[0][-2:]
        self.assertNotEqual([], localz)
        self.assertNotEqual([], globalz)

    def test_inlineCallbacksTracebacks(self) -> None:
        """
        L{defer.inlineCallbacks} that re-raise tracebacks into their deferred
        should not lose their tracebacks.
        """
        f = getDivisionFailure()
        d: Deferred[None] = Deferred()
        try:
            f.raiseException()
        except BaseException:
            d.errback()

        def ic(d: object) -> Generator[Any, Any, None]:
            yield d

        defer.inlineCallbacks(ic)
        newFailure = self.failureResultOf(d)
        tb = traceback.extract_tb(newFailure.getTracebackObject())

        self.assertEqual(len(tb), 3)
        self.assertIn("test_defer", tb[2][0])
        self.assertEqual("getDivisionFailure", tb[2][2])
        self.assertEqual("1 / 0", tb[2][3])

        self.assertIn("test_defer", tb[0][0])
        self.assertEqual("test_inlineCallbacksTracebacks", tb[0][2])
        self.assertEqual("f.raiseException()", tb[0][3])

    def test_fromCoroutineRequiresCoroutine(self) -> None:
        """
        L{Deferred.fromCoroutine} requires a coroutine object or a generator,
        and will reject things that are not that.
        """
        thingsThatAreNotCoroutines = [
            # Lambda
            lambda x: x,
            # Int
            1,
            # Boolean
            True,
            # Function
            self.test_fromCoroutineRequiresCoroutine,
            # None
            None,
            # Module
            defer,
        ]

        for thing in thingsThatAreNotCoroutines:
            self.assertRaises(defer.NotACoroutineError, Deferred.fromCoroutine, thing)


class FirstErrorTests(unittest.SynchronousTestCase):
    """
    Tests for L{FirstError}.
    """

    def test_repr(self) -> None:
        """
        The repr of a L{FirstError} instance includes the repr of the value of
        the sub-failure and the index which corresponds to the L{FirstError}.
        """
        exc = ValueError("some text")
        try:
            raise exc
        except BaseException:
            f = Failure()

        error = defer.FirstError(f, 3)
        self.assertEqual(repr(error), f"FirstError[#3, {repr(exc)}]")

    def test_str(self) -> None:
        """
        The str of a L{FirstError} instance includes the str of the
        sub-failure and the index which corresponds to the L{FirstError}.
        """
        exc = ValueError("some text")
        try:
            raise exc
        except BaseException:
            f = Failure()

        error = defer.FirstError(f, 5)
        self.assertEqual(str(error), f"FirstError[#5, {str(f)}]")

    def test_comparison(self) -> None:
        """
        L{FirstError} instances compare equal to each other if and only if
        their failure and index compare equal.  L{FirstError} instances do not
        compare equal to instances of other types.
        """
        try:
            1 // 0
        except BaseException:
            firstFailure = Failure()

        one = defer.FirstError(firstFailure, 13)
        anotherOne = defer.FirstError(firstFailure, 13)

        try:
            raise ValueError("bar")
        except BaseException:
            secondFailure = Failure()

        another = defer.FirstError(secondFailure, 9)

        self.assertTrue(one == anotherOne)
        self.assertFalse(one == another)
        self.assertTrue(one != another)
        self.assertFalse(one != anotherOne)

        self.assertFalse(one == 10)


class AlreadyCalledTests(unittest.SynchronousTestCase):
    def setUp(self) -> None:
        self._deferredWasDebugging = defer.getDebugging()
        defer.setDebugging(True)

    def tearDown(self) -> None:
        defer.setDebugging(self._deferredWasDebugging)

    def _callback(self, *args: object, **kwargs: object) -> None:
        pass

    def _errback(self, *args: object, **kwargs: object) -> None:
        pass

    def _call_1(self, d: Deferred[str]) -> None:
        d.callback("hello")

    def _call_2(self, d: Deferred[str]) -> None:
        d.callback("twice")

    def _err_1(self, d: Deferred[str]) -> None:
        d.errback(Failure(RuntimeError()))

    def _err_2(self, d: Deferred[str]) -> None:
        d.errback(Failure(RuntimeError()))

    def testAlreadyCalled_CC(self) -> None:
        d: Deferred[str] = Deferred()
        d.addCallbacks(self._callback, self._errback)
        self._call_1(d)
        self.assertRaises(defer.AlreadyCalledError, self._call_2, d)

    def testAlreadyCalled_CE(self) -> None:
        d: Deferred[str] = Deferred()
        d.addCallbacks(self._callback, self._errback)
        self._call_1(d)
        self.assertRaises(defer.AlreadyCalledError, self._err_2, d)

    def testAlreadyCalled_EE(self) -> None:
        d: Deferred[str] = Deferred()
        d.addCallbacks(self._callback, self._errback)
        self._err_1(d)
        self.assertRaises(defer.AlreadyCalledError, self._err_2, d)

    def testAlreadyCalled_EC(self) -> None:
        d: Deferred[str] = Deferred()
        d.addCallbacks(self._callback, self._errback)
        self._err_1(d)
        self.assertRaises(defer.AlreadyCalledError, self._call_2, d)

    def _count(self, linetype: str, func: str, lines: List[str], expected: int) -> None:
        count = 0
        for line in lines:
            if line.startswith(" %s:" % linetype) and line.endswith(" %s" % func):
                count += 1
        self.assertTrue(count == expected)

    def _check(self, e: Exception, caller: str, invoker1: str, invoker2: str) -> None:
        # make sure the debugging information is vaguely correct
        lines = e.args[0].split("\n")
        # the creator should list the creator (testAlreadyCalledDebug) but not
        # _call_1 or _call_2 or other invokers
        self._count("C", caller, lines, 1)
        self._count("C", "_call_1", lines, 0)
        self._count("C", "_call_2", lines, 0)
        self._count("C", "_err_1", lines, 0)
        self._count("C", "_err_2", lines, 0)
        # invoker should list the first invoker but not the second
        self._count("I", invoker1, lines, 1)
        self._count("I", invoker2, lines, 0)

    def testAlreadyCalledDebug_CC(self) -> None:
        d: Deferred[str] = Deferred()
        d.addCallbacks(self._callback, self._errback)
        self._call_1(d)
        try:
            self._call_2(d)
        except defer.AlreadyCalledError as e:
            self._check(e, "testAlreadyCalledDebug_CC", "_call_1", "_call_2")
        else:
            self.fail("second callback failed to raise AlreadyCalledError")

    def testAlreadyCalledDebug_CE(self) -> None:
        d: Deferred[str] = Deferred()
        d.addCallbacks(self._callback, self._errback)
        self._call_1(d)
        try:
            self._err_2(d)
        except defer.AlreadyCalledError as e:
            self._check(e, "testAlreadyCalledDebug_CE", "_call_1", "_err_2")
        else:
            self.fail("second errback failed to raise AlreadyCalledError")

    def testAlreadyCalledDebug_EC(self) -> None:
        d: Deferred[str] = Deferred()
        d.addCallbacks(self._callback, self._errback)
        self._err_1(d)
        try:
            self._call_2(d)
        except defer.AlreadyCalledError as e:
            self._check(e, "testAlreadyCalledDebug_EC", "_err_1", "_call_2")
        else:
            self.fail("second callback failed to raise AlreadyCalledError")

    def testAlreadyCalledDebug_EE(self) -> None:
        d: Deferred[str] = Deferred()
        d.addCallbacks(self._callback, self._errback)
        self._err_1(d)
        try:
            self._err_2(d)
        except defer.AlreadyCalledError as e:
            self._check(e, "testAlreadyCalledDebug_EE", "_err_1", "_err_2")
        else:
            self.fail("second errback failed to raise AlreadyCalledError")

    def testNoDebugging(self) -> None:
        defer.setDebugging(False)
        d: Deferred[str] = Deferred()
        d.addCallbacks(self._callback, self._errback)
        self._call_1(d)
        try:
            self._call_2(d)
        except defer.AlreadyCalledError as e:
            self.assertFalse(e.args)
        else:
            self.fail("second callback failed to raise AlreadyCalledError")

    def testSwitchDebugging(self) -> None:
        # Make sure Deferreds can deal with debug state flipping
        # around randomly.  This is covering a particular fixed bug.
        defer.setDebugging(False)
        d: Deferred[None] = Deferred()
        d.addBoth(lambda ign: None)
        defer.setDebugging(True)
        d.callback(None)

        defer.setDebugging(False)
        d = Deferred()
        d.callback(None)
        defer.setDebugging(True)
        d.addBoth(lambda ign: None)


class DeferredCancellerTests(unittest.SynchronousTestCase):
    def setUp(self) -> None:
        self.callbackResults: Optional[str] = None
        self.errbackResults: Optional[Failure] = None
        self.callback2Results: Optional[str] = None
        self.cancellerCallCount = 0

    def tearDown(self) -> None:
        # Sanity check that the canceller was called at most once.
        self.assertIn(self.cancellerCallCount, (0, 1))

    def _callback(self, data: str) -> str:
        self.callbackResults = data
        return data

    def _callback2(self, data: str) -> None:
        self.callback2Results = data

    def _errback(self, error: Failure) -> None:
        self.errbackResults = error

    def test_noCanceller(self) -> None:
        """
        A L{Deferred} without a canceller must errback with a
        L{defer.CancelledError} and not callback.
        """
        d: Deferred[None] = Deferred()
        d.addCallbacks(self._callback, self._errback)
        d.cancel()
        assert self.errbackResults is not None
        self.assertEqual(self.errbackResults.type, defer.CancelledError)
        self.assertIsNone(self.callbackResults)

    def test_raisesAfterCancelAndCallback(self) -> None:
        """
        A L{Deferred} without a canceller, when cancelled must allow
        a single extra call to callback, and raise
        L{defer.AlreadyCalledError} if callbacked or errbacked thereafter.
        """
        d: Deferred[None] = Deferred()
        d.addCallbacks(self._callback, self._errback)
        d.cancel()

        # A single extra callback should be swallowed.
        d.callback(None)

        # But a second call to callback or errback is not.
        self.assertRaises(defer.AlreadyCalledError, d.callback, None)
        self.assertRaises(defer.AlreadyCalledError, d.errback, Exception())

    def test_raisesAfterCancelAndErrback(self) -> None:
        """
        A L{Deferred} without a canceller, when cancelled must allow
        a single extra call to errback, and raise
        L{defer.AlreadyCalledError} if callbacked or errbacked thereafter.
        """
        d: Deferred[None] = Deferred()
        d.addCallbacks(self._callback, self._errback)
        d.cancel()

        # A single extra errback should be swallowed.
        d.errback(Exception())

        # But a second call to callback or errback is not.
        self.assertRaises(defer.AlreadyCalledError, d.callback, None)
        self.assertRaises(defer.AlreadyCalledError, d.errback, Exception())

    def test_noCancellerMultipleCancelsAfterCancelAndCallback(self) -> None:
        """
        A L{Deferred} without a canceller, when cancelled and then
        callbacked, ignores multiple cancels thereafter.
        """
        d: Deferred[None] = Deferred()
        d.addCallbacks(self._callback, self._errback)
        d.cancel()
        currentFailure = self.errbackResults
        # One callback will be ignored
        d.callback(None)
        # Cancel should have no effect.
        d.cancel()
        self.assertIs(currentFailure, self.errbackResults)

    def test_noCancellerMultipleCancelsAfterCancelAndErrback(self) -> None:
        """
        A L{Deferred} without a canceller, when cancelled and then
        errbacked, ignores multiple cancels thereafter.
        """
        d: Deferred[None] = Deferred()
        d.addCallbacks(self._callback, self._errback)
        d.cancel()
        assert self.errbackResults is not None
        self.assertEqual(self.errbackResults.type, defer.CancelledError)
        currentFailure = self.errbackResults
        # One errback will be ignored
        d.errback(GenericError())
        # I.e., we should still have a CancelledError.
        self.assertEqual(self.errbackResults.type, defer.CancelledError)
        d.cancel()
        self.assertIs(currentFailure, self.errbackResults)

    def test_noCancellerMultipleCancel(self) -> None:
        """
        Calling cancel multiple times on a deferred with no canceller
        results in a L{defer.CancelledError}. Subsequent calls to cancel
        do not cause an error.
        """
        d: Deferred[None] = Deferred()
        d.addCallbacks(self._callback, self._errback)
        d.cancel()
        assert self.errbackResults is not None
        self.assertEqual(self.errbackResults.type, defer.CancelledError)
        currentFailure = self.errbackResults
        d.cancel()
        self.assertIs(currentFailure, self.errbackResults)

    def test_cancellerMultipleCancel(self) -> None:
        """
        Verify that calling cancel multiple times on a deferred with a
        canceller that does not errback results in a
        L{defer.CancelledError} and that subsequent calls to cancel do not
        cause an error and that after all that, the canceller was only
        called once.
        """

        def cancel(d: Deferred[object]) -> None:
            self.cancellerCallCount += 1

        d: Deferred[None] = Deferred(canceller=cancel)
        d.addCallbacks(self._callback, self._errback)
        d.cancel()
        assert self.errbackResults is not None
        self.assertEqual(self.errbackResults.type, defer.CancelledError)
        currentFailure = self.errbackResults
        d.cancel()
        self.assertIs(currentFailure, self.errbackResults)
        self.assertEqual(self.cancellerCallCount, 1)

    def test_simpleCanceller(self) -> None:
        """
        Verify that a L{Deferred} calls its specified canceller when
        it is cancelled, and that further call/errbacks raise
        L{defer.AlreadyCalledError}.
        """

        def cancel(d: Deferred[object]) -> None:
            self.cancellerCallCount += 1

        d: Deferred[None] = Deferred(canceller=cancel)
        d.addCallbacks(self._callback, self._errback)
        d.cancel()
        self.assertEqual(self.cancellerCallCount, 1)
        assert self.errbackResults is not None
        self.assertEqual(self.errbackResults.type, defer.CancelledError)

        # Test that further call/errbacks are *not* swallowed
        self.assertRaises(defer.AlreadyCalledError, d.callback, None)
        self.assertRaises(defer.AlreadyCalledError, d.errback, Exception())

    def test_cancellerArg(self) -> None:
        """
        Verify that a canceller is given the correct deferred argument.
        """

        def cancel(d1: Deferred[object]) -> None:
            self.assertIs(d1, d)

        d: Deferred[None] = Deferred(canceller=cancel)
        d.addCallbacks(self._callback, self._errback)
        d.cancel()

    def test_cancelAfterCallback(self) -> None:
        """
        Test that cancelling a deferred after it has been callbacked does
        not cause an error.
        """

        def cancel(d: Deferred[object]) -> None:
            self.cancellerCallCount += 1
            d.errback(GenericError())

        d: Deferred[str] = Deferred(canceller=cancel)
        d.addCallbacks(self._callback, self._errback)
        d.callback("biff!")
        d.cancel()
        self.assertEqual(self.cancellerCallCount, 0)
        self.assertIsNone(self.errbackResults)
        self.assertEqual(self.callbackResults, "biff!")

    def test_cancelAfterErrback(self) -> None:
        """
        Test that cancelling a L{Deferred} after it has been errbacked does
        not result in a L{defer.CancelledError}.
        """

        def cancel(d: Deferred[object]) -> None:
            self.cancellerCallCount += 1
            d.errback(GenericError())

        d: Deferred[None] = Deferred(canceller=cancel)
        d.addCallbacks(self._callback, self._errback)
        d.errback(GenericError())
        d.cancel()
        self.assertEqual(self.cancellerCallCount, 0)
        assert self.errbackResults is not None
        self.assertEqual(self.errbackResults.type, GenericError)
        self.assertIsNone(self.callbackResults)

    def test_cancellerThatErrbacks(self) -> None:
        """
        Test a canceller which errbacks its deferred.
        """

        def cancel(d: Deferred[object]) -> None:
            self.cancellerCallCount += 1
            d.errback(GenericError())

        d: Deferred[None] = Deferred(canceller=cancel)
        d.addCallbacks(self._callback, self._errback)
        d.cancel()
        self.assertEqual(self.cancellerCallCount, 1)
        assert self.errbackResults is not None
        self.assertEqual(self.errbackResults.type, GenericError)

    def test_cancellerThatCallbacks(self) -> None:
        """
        Test a canceller which calls its deferred.
        """

        def cancel(d: Deferred[object]) -> None:
            self.cancellerCallCount += 1
            d.callback("hello!")

        d: Deferred[None] = Deferred(canceller=cancel)
        d.addCallbacks(self._callback, self._errback)
        d.cancel()
        self.assertEqual(self.cancellerCallCount, 1)
        self.assertEqual(self.callbackResults, "hello!")
        self.assertIsNone(self.errbackResults)

    def test_cancelNestedDeferred(self) -> None:
        """
        Verify that a Deferred, a, which is waiting on another Deferred, b,
        returned from one of its callbacks, will propagate
        L{defer.CancelledError} when a is cancelled.
        """

        def innerCancel(d: Deferred[object]) -> None:
            self.cancellerCallCount += 1

        def cancel(d: Deferred[object]) -> None:
            self.assertTrue(False)

        b: Deferred[None] = Deferred(canceller=innerCancel)
        a: Deferred[None] = Deferred(canceller=cancel)
        a.callback(None)
        a.addCallback(lambda data: b)
        a.cancel()
        a.addCallbacks(self._callback, self._errback)
        # The cancel count should be one (the cancellation done by B)
        self.assertEqual(self.cancellerCallCount, 1)
        # B's canceller didn't errback, so defer.py will have called errback
        # with a CancelledError.
        assert self.errbackResults is not None
        self.assertEqual(self.errbackResults.type, defer.CancelledError)


class LogTests(unittest.SynchronousTestCase):
    """
    Test logging of unhandled errors.
    """

    def setUp(self) -> None:
        """
        Add a custom observer to observer logging.
        """
        self.c: List[Dict[str, Any]] = []
        log.addObserver(self.c.append)

    def tearDown(self) -> None:
        """
        Remove the observer.
        """
        log.removeObserver(self.c.append)

    def _loggedErrors(self) -> List[Dict[str, Any]]:
        return [e for e in self.c if e["isError"]]

    def _check(self) -> None:
        """
        Check the output of the log observer to see if the error is present.
        """
        c2 = self._loggedErrors()
        self.assertEqual(len(c2), 2)
        c2[1]["failure"].trap(ZeroDivisionError)
        self.flushLoggedErrors(ZeroDivisionError)

    def test_errorLog(self) -> None:
        """
        Verify that when a L{Deferred} with no references to it is fired,
        and its final result (the one not handled by any callback) is an
        exception, that exception will be logged immediately.
        """
        Deferred().addCallback(lambda x: 1 // 0).callback(1)
        gc.collect()
        self._check()

    def test_errorLogWithInnerFrameRef(self) -> None:
        """
        Same as L{test_errorLog}, but with an inner frame.
        """

        def _subErrorLogWithInnerFrameRef() -> None:
            d: Deferred[int] = Deferred()
            d.addCallback(lambda x: 1 // 0)
            d.callback(1)

        _subErrorLogWithInnerFrameRef()
        gc.collect()
        self._check()

    def test_errorLogWithInnerFrameCycle(self) -> None:
        """
        Same as L{test_errorLogWithInnerFrameRef}, plus create a cycle.
        """

        def _subErrorLogWithInnerFrameCycle() -> None:
            d: Deferred[int] = Deferred()
            d.addCallback(lambda x, d=d: 1 // 0)
            # Set a self deference on to create a cycle
            d._d = d  # type: ignore[attr-defined]
            d.callback(1)

        _subErrorLogWithInnerFrameCycle()
        gc.collect()
        self._check()

    def test_errorLogNoRepr(self) -> None:
        """
        Verify that when a L{Deferred} with no references to it is fired,
        the logged message does not contain a repr of the failure object.
        """
        Deferred().addCallback(lambda x: 1 // 0).callback(1)

        gc.collect()
        self._check()

        self.assertEqual(2, len(self.c))
        msg = log.textFromEventDict(self.c[-1])
        assert msg is not None
        expected = "Unhandled Error\nTraceback "
        self.assertTrue(
            msg.startswith(expected),
            f"Expected message starting with: {expected!r}",
        )

    def test_errorLogDebugInfo(self) -> None:
        """
        Verify that when a L{Deferred} with no references to it is fired,
        the logged message includes debug info if debugging on the deferred
        is enabled.
        """

        def doit() -> None:
            d: Deferred[int] = Deferred()
            d.debug = True
            d.addCallback(lambda x: 1 // 0)
            d.callback(1)

        doit()
        gc.collect()
        self._check()

        self.assertEqual(2, len(self.c))
        msg = log.textFromEventDict(self.c[-1])
        assert msg is not None
        expected = "(debug:  I"
        self.assertTrue(
            msg.startswith(expected),
            f"Expected message starting with: {expected!r}",
        )

    def test_chainedErrorCleanup(self) -> None:
        """
        If one Deferred with an error result is returned from a callback on
        another Deferred, when the first Deferred is garbage collected it does
        not log its error.
        """
        d: Deferred[None] = Deferred()
        d.addCallback(lambda ign: defer.fail(RuntimeError("zoop")))
        d.callback(None)

        # Sanity check - this isn't too interesting, but we do want the original
        # Deferred to have gotten the failure.
        results: List[None] = []
        errors: List[Failure] = []
        d.addCallbacks(results.append, errors.append)
        self.assertEqual(results, [])
        self.assertEqual(len(errors), 1)
        errors[0].trap(Exception)

        # Get rid of any references we might have to the inner Deferred (none of
        # these should really refer to it, but we're just being safe).
        del results, errors, d
        # Force a collection cycle so that there's a chance for an error to be
        # logged, if it's going to be logged.
        gc.collect()
        # And make sure it is not.
        self.assertEqual(self._loggedErrors(), [])

    def test_errorClearedByChaining(self) -> None:
        """
        If a Deferred with a failure result has an errback which chains it to
        another Deferred, the initial failure is cleared by the errback so it is
        not logged.
        """
        # Start off with a Deferred with a failure for a result
        bad: Optional[Deferred[None]] = defer.fail(Exception("oh no"))
        good: Optional[Deferred[None]] = Deferred()
        # Give it a callback that chains it to another Deferred
        assert bad is not None
        bad.addErrback(lambda ignored: good)
        # That's all, clean it up.  No Deferred here still has a failure result,
        # so nothing should be logged.
        good = bad = None
        gc.collect()
        self.assertEqual(self._loggedErrors(), [])


class DeferredListEmptyTests(unittest.SynchronousTestCase):
    def setUp(self) -> None:
        self.callbackRan = 0

    def testDeferredListEmpty(self) -> None:
        """Testing empty DeferredList."""
        dl = DeferredList([])
        dl.addCallback(self.cb_empty)

    def cb_empty(self, res: List[object]) -> None:
        self.callbackRan = 1
        self.assertEqual([], res)

    def tearDown(self) -> None:
        self.assertTrue(self.callbackRan, "Callback was never run.")


class OtherPrimitivesTests(unittest.SynchronousTestCase, ImmediateFailureMixin):
    def _incr(self, result: object) -> None:
        self.counter += 1

    def setUp(self) -> None:
        self.counter = 0

    def testLock(self) -> None:
        lock = DeferredLock()
        lock.acquire().addCallback(self._incr)
        self.assertTrue(lock.locked)
        self.assertEqual(self.counter, 1)

        lock.acquire().addCallback(self._incr)
        self.assertTrue(lock.locked)
        self.assertEqual(self.counter, 1)

        lock.release()
        self.assertTrue(lock.locked)
        self.assertEqual(self.counter, 2)

        lock.release()
        self.assertFalse(lock.locked)
        self.assertEqual(self.counter, 2)

        self.assertRaises(TypeError, lock.run)

        firstUnique = object()
        secondUnique = object()

        controlDeferred: Deferred[object] = Deferred()

        result: Optional[object] = None

        def helper(resultValue: object, returnValue: object = None) -> object:
            nonlocal result
            result = resultValue
            return returnValue

        resultDeferred = lock.run(
            helper, resultValue=firstUnique, returnValue=controlDeferred
        )
        self.assertTrue(lock.locked)
        self.assertEqual(result, firstUnique)

        resultDeferred.addCallback(helper)

        lock.acquire().addCallback(self._incr)
        self.assertTrue(lock.locked)
        self.assertEqual(self.counter, 2)

        controlDeferred.callback(secondUnique)
        self.assertEqual(result, secondUnique)
        self.assertTrue(lock.locked)
        self.assertEqual(self.counter, 3)

        d = lock.acquire().addBoth(helper)
        d.cancel()
        self.assertIsInstance(result, Failure)
        self.assertEqual(cast(Failure, result).type, defer.CancelledError)

        lock.release()
        self.assertFalse(lock.locked)

    def test_cancelLockAfterAcquired(self) -> None:
        """
        When canceling a L{Deferred} from a L{DeferredLock} that already
        has the lock, the cancel should have no effect.
        """

        def failOnErrback(f: Failure) -> None:
            self.fail("Unexpected errback call!")

        lock = DeferredLock()
        d = lock.acquire()
        d.addErrback(failOnErrback)
        d.cancel()

    def test_cancelLockBeforeAcquired(self) -> None:
        """
        When canceling a L{Deferred} from a L{DeferredLock} that does not
        yet have the lock (i.e., the L{Deferred} has not fired), the cancel
        should cause a L{defer.CancelledError} failure.
        """
        lock = DeferredLock()
        lock.acquire()
        d = lock.acquire()
        d.cancel()
        self.assertImmediateFailure(d, defer.CancelledError)

    def testSemaphore(self) -> None:
        N = 13
        sem = DeferredSemaphore(N)

        controlDeferred: Deferred[None] = Deferred()

        helperArg: object = None

        def helper(arg: object) -> Deferred[None]:
            nonlocal helperArg
            helperArg = arg
            return controlDeferred

        results: List[object] = []
        uniqueObject = object()
        resultDeferred = sem.run(helper, arg=uniqueObject)
        resultDeferred.addCallback(results.append)
        resultDeferred.addCallback(self._incr)
        self.assertEqual(results, [])
        self.assertEqual(helperArg, uniqueObject)
        controlDeferred.callback(None)
        self.assertIsNone(results.pop())
        self.assertEqual(self.counter, 1)

        self.counter = 0
        for i in range(1, 1 + N):
            sem.acquire().addCallback(self._incr)
            self.assertEqual(self.counter, i)

        success = []

        def fail(r: object) -> None:
            success.append(False)

        def succeed(r: object) -> None:
            success.append(True)

        d = sem.acquire().addCallbacks(fail, succeed)
        d.cancel()
        self.assertEqual(success, [True])

        sem.acquire().addCallback(self._incr)
        self.assertEqual(self.counter, N)

        sem.release()
        self.assertEqual(self.counter, N + 1)

        for i in range(1, 1 + N):
            sem.release()
            self.assertEqual(self.counter, N + 1)

    def test_semaphoreInvalidTokens(self) -> None:
        """
        If the token count passed to L{DeferredSemaphore} is less than one
        then L{ValueError} is raised.
        """
        self.assertRaises(ValueError, DeferredSemaphore, 0)
        self.assertRaises(ValueError, DeferredSemaphore, -1)

    def test_cancelSemaphoreAfterAcquired(self) -> None:
        """
        When canceling a L{Deferred} from a L{DeferredSemaphore} that
        already has the semaphore, the cancel should have no effect.
        """

        def failOnErrback(f: Failure) -> None:
            self.fail("Unexpected errback call!")

        sem = DeferredSemaphore(1)
        d = sem.acquire()
        d.addErrback(failOnErrback)
        d.cancel()

    def test_cancelSemaphoreBeforeAcquired(self) -> None:
        """
        When canceling a L{Deferred} from a L{DeferredSemaphore} that does
        not yet have the semaphore (i.e., the L{Deferred} has not fired),
        the cancel should cause a L{defer.CancelledError} failure.
        """
        sem = DeferredSemaphore(1)
        sem.acquire()
        d = sem.acquire()
        d.cancel()
        self.assertImmediateFailure(d, defer.CancelledError)

    def testQueue(self) -> None:
        N, M = 2, 2
        queue: DeferredQueue[int] = DeferredQueue(N, M)

        gotten: List[int] = []

        for i in range(M):
            queue.get().addCallback(gotten.append)
        self.assertRaises(defer.QueueUnderflow, queue.get)

        for i in range(M):
            queue.put(i)
            self.assertEqual(gotten, list(range(i + 1)))
        for i in range(N):
            queue.put(N + i)
            self.assertEqual(gotten, list(range(M)))
        self.assertRaises(defer.QueueOverflow, queue.put, None)

        gotten = []
        for i in range(N):
            queue.get().addCallback(gotten.append)
            self.assertEqual(gotten, list(range(N, N + i + 1)))

        queue = DeferredQueue()
        gotten = []
        for i in range(N):
            queue.get().addCallback(gotten.append)
        for i in range(N):
            queue.put(i)
        self.assertEqual(gotten, list(range(N)))

        queue = DeferredQueue(size=0)
        self.assertRaises(defer.QueueOverflow, queue.put, None)

        queue = DeferredQueue(backlog=0)
        self.assertRaises(defer.QueueUnderflow, queue.get)

    def test_cancelQueueAfterSynchronousGet(self) -> None:
        """
        When canceling a L{Deferred} from a L{DeferredQueue} that already has
        a result, the cancel should have no effect.
        """

        def failOnErrback(f: Failure) -> None:
            self.fail("Unexpected errback call!")

        queue: DeferredQueue[None] = DeferredQueue()
        d = queue.get()
        d.addErrback(failOnErrback)
        queue.put(None)
        d.cancel()

    def test_cancelQueueAfterGet(self) -> None:
        """
        When canceling a L{Deferred} from a L{DeferredQueue} that does not
        have a result (i.e., the L{Deferred} has not fired), the cancel
        causes a L{defer.CancelledError} failure. If the queue has a result
        later on, it doesn't try to fire the deferred.
        """
        queue: DeferredQueue[None] = DeferredQueue()
        d = queue.get()
        d.cancel()
        self.assertImmediateFailure(d, defer.CancelledError)

        def cb(ignore: object) -> Deferred[None]:
            # If the deferred is still linked with the deferred queue, it will
            # fail with an AlreadyCalledError
            queue.put(None)
            return queue.get().addCallback(self.assertIs, None)

        d.addCallback(cb)
        done: List[None] = []
        d.addCallback(done.append)
        self.assertEqual(len(done), 1)


class DeferredFilesystemLockTests(unittest.TestCase):
    """
    Test the behavior of L{DeferredFilesystemLock}
    """

    def setUp(self) -> None:
        self.clock = Clock()
        self.lock = DeferredFilesystemLock(self.mktemp(), scheduler=self.clock)

    def test_waitUntilLockedWithNoLock(self) -> Deferred[None]:
        """
        Test that the lock can be acquired when no lock is held
        """
        return self.lock.deferUntilLocked(timeout=1)

    def test_waitUntilLockedWithTimeoutLocked(self) -> Deferred[None]:
        """
        Test that the lock can not be acquired when the lock is held
        for longer than the timeout.
        """
        self.assertTrue(self.lock.lock())

        d = self.lock.deferUntilLocked(timeout=5.5)
        self.assertFailure(d, defer.TimeoutError)

        self.clock.pump([1] * 10)

        return d

    def test_waitUntilLockedWithTimeoutUnlocked(self) -> Deferred[None]:
        """
        Test that a lock can be acquired while a lock is held
        but the lock is unlocked before our timeout.
        """

        def onTimeout(f: Failure) -> None:
            f.trap(defer.TimeoutError)
            self.fail("Should not have timed out")

        self.assertTrue(self.lock.lock())

        self.clock.callLater(1, self.lock.unlock)
        d = self.lock.deferUntilLocked(timeout=10)
        d.addErrback(onTimeout)

        self.clock.pump([1] * 10)

        return d

    def test_defaultScheduler(self) -> None:
        """
        Test that the default scheduler is set up properly.
        """
        lock = DeferredFilesystemLock(self.mktemp())

        self.assertEqual(lock._scheduler, reactor)

    def test_concurrentUsage(self) -> Deferred[None]:
        """
        Test that an appropriate exception is raised when attempting
        to use deferUntilLocked concurrently.
        """
        self.lock.lock()
        self.clock.callLater(1, self.lock.unlock)

        d1 = self.lock.deferUntilLocked()
        d2 = self.lock.deferUntilLocked()

        self.assertFailure(d2, defer.AlreadyTryingToLockError)

        self.clock.advance(1)

        return d1

    def test_multipleUsages(self) -> Deferred[None]:
        """
        Test that a DeferredFilesystemLock can be used multiple times
        """

        def lockAquired(ign: object) -> Deferred[None]:
            self.lock.unlock()
            d = self.lock.deferUntilLocked()
            return d

        self.lock.lock()
        self.clock.callLater(1, self.lock.unlock)

        d = self.lock.deferUntilLocked()
        d.addCallback(lockAquired)

        self.clock.advance(1)

        return d

    def test_cancelDeferUntilLocked(self) -> None:
        """
        When cancelling a L{Deferred} returned by
        L{DeferredFilesystemLock.deferUntilLocked}, the
        L{DeferredFilesystemLock._tryLockCall} is cancelled.
        """
        self.lock.lock()
        deferred = self.lock.deferUntilLocked()
        tryLockCall = self.lock._tryLockCall
        assert tryLockCall is not None
        deferred.cancel()
        self.assertFalse(tryLockCall.active())
        self.assertIsNone(self.lock._tryLockCall)
        self.failureResultOf(deferred, defer.CancelledError)

    def test_cancelDeferUntilLockedWithTimeout(self) -> None:
        """
        When cancel a L{Deferred} returned by
        L{DeferredFilesystemLock.deferUntilLocked}, if the timeout is
        set, the timeout call will be cancelled.
        """
        self.lock.lock()
        deferred = self.lock.deferUntilLocked(timeout=1)
        timeoutCall = self.lock._timeoutCall
        assert timeoutCall is not None
        deferred.cancel()
        self.assertFalse(timeoutCall.active())
        self.assertIsNone(self.lock._timeoutCall)
        self.failureResultOf(deferred, defer.CancelledError)


def _overrideFunc(v: object, t: float) -> str:
    """
    Private function to be used to pass as an alternate onTimeoutCancel value
    to timeoutDeferred
    """
    return "OVERRIDDEN"


class DeferredAddTimeoutTests(unittest.SynchronousTestCase):
    """
    Tests for the function L{Deferred.addTimeout}
    """

    def test_timeoutChainable(self) -> None:
        """
        L{Deferred.addTimeout} returns its own L{Deferred} so it
        can be called in a callback chain.
        """
        d: Deferred[None] = Deferred()
        d.addTimeout(5, Clock())
        d.addCallback(lambda _: "done")
        d.callback(None)
        self.assertEqual("done", self.successResultOf(d))

    def test_successResultBeforeTimeout(self) -> None:
        """
        The L{Deferred} callbacks with the result if it succeeds before
        the timeout. No cancellation happens after the callback either,
        which could also cancel inner deferreds.
        """
        clock = Clock()
        d: Deferred[str] = Deferred()
        d.addTimeout(10, clock)

        # addTimeout is added first so that if d is timed out, d would be
        # canceled before innerDeferred gets returned from an callback on d
        innerDeferred: Deferred[None] = Deferred()
        dCallbacked: Optional[str] = None

        def onCallback(results: str) -> Deferred[None]:
            nonlocal dCallbacked
            dCallbacked = results
            return innerDeferred

        d.addCallback(onCallback)
        d.callback("results")

        # d is callbacked immediately, before innerDeferred is returned from
        # the callback on d
        self.assertIsNot(None, dCallbacked)
        self.assertEqual(dCallbacked, "results")

        # The timeout never happens - if it did, d would have been cancelled,
        # which would cancel innerDeferred too.
        clock.advance(15)
        self.assertNoResult(innerDeferred)

    def test_successResultBeforeTimeoutCustom(self) -> None:
        """
        The L{Deferred} callbacks with the result if it succeeds before
        the timeout, even if a custom C{onTimeoutCancel} function is provided.
        No cancellation happens after the callback either, which could also
        cancel inner deferreds.
        """
        clock = Clock()
        d: Deferred[str] = Deferred()
        d.addTimeout(10, clock, onTimeoutCancel=_overrideFunc)

        # addTimeout is added first so that if d is timed out, d would be
        # canceled before innerDeferred gets returned from an callback on d
        innerDeferred: Deferred[None] = Deferred()
        dCallbacked: Optional[str] = None

        def onCallback(results: str) -> Deferred[None]:
            nonlocal dCallbacked
            dCallbacked = results
            return innerDeferred

        d.addCallback(onCallback)
        d.callback("results")

        # d is callbacked immediately, before innerDeferred is returned from
        # the callback on d
        self.assertIsNot(None, dCallbacked)
        self.assertEqual(dCallbacked, "results")

        # The timeout never happens - if it did, d would have been cancelled,
        # which would cancel innerDeferred too
        clock.advance(15)
        self.assertNoResult(innerDeferred)

    def test_failureBeforeTimeout(self) -> None:
        """
        The L{Deferred} errbacks with the failure if it fails before the
        timeout. No cancellation happens after the errback either, which
        could also cancel inner deferreds.
        """
        clock = Clock()
        d: Deferred[None] = Deferred()
        d.addTimeout(10, clock)

        # addTimeout is added first so that if d is timed out, d would be
        # canceled before innerDeferred gets returned from an errback on d
        innerDeferred: Deferred[None] = Deferred()
        dErrbacked: Optional[Failure] = None
        error = ValueError("fail")

        def onErrback(f: Failure) -> Deferred[None]:
            nonlocal dErrbacked
            dErrbacked = f
            return innerDeferred

        d.addErrback(onErrback)
        d.errback(error)

        # d is errbacked immediately, before innerDeferred is returned from the
        # errback on d
        assert dErrbacked is not None
        self.assertIsInstance(dErrbacked, Failure)
        self.assertIs(dErrbacked.value, error)

        # The timeout never happens - if it did, d would have been cancelled,
        # which would cancel innerDeferred too
        clock.advance(15)
        self.assertNoResult(innerDeferred)

    def test_failureBeforeTimeoutCustom(self) -> None:
        """
        The L{Deferred} errbacks with the failure if it fails before the
        timeout, even if using a custom C{onTimeoutCancel} function.
        No cancellation happens after the errback either, which could also
        cancel inner deferreds.
        """
        clock = Clock()
        d: Deferred[None] = Deferred()
        d.addTimeout(10, clock, onTimeoutCancel=_overrideFunc)

        # addTimeout is added first so that if d is timed out, d would be
        # canceled before innerDeferred gets returned from an errback on d
        innerDeferred: Deferred[None] = Deferred()
        dErrbacked: Optional[Failure] = None
        error = ValueError("fail")

        def onErrback(f: Failure) -> Deferred[None]:
            nonlocal dErrbacked
            dErrbacked = f
            return innerDeferred

        d.addErrback(onErrback)
        d.errback(error)

        # d is errbacked immediately, before innerDeferred is returned from the
        # errback on d
        assert dErrbacked is not None
        self.assertIsInstance(dErrbacked, Failure)
        self.assertIs(dErrbacked.value, error)

        # The timeout never happens - if it did, d would have been cancelled,
        # which would cancel innerDeferred too
        clock.advance(15)
        self.assertNoResult(innerDeferred)

    def test_timedOut(self) -> None:
        """
        The L{Deferred} by default errbacks with a L{defer.TimeoutError}
        if it times out before callbacking or errbacking.
        """
        clock = Clock()
        d: Deferred[None] = Deferred()
        d.addTimeout(10, clock)
        self.assertNoResult(d)

        clock.advance(15)

        self.failureResultOf(d, defer.TimeoutError)

    def test_timedOutCustom(self) -> None:
        """
        If a custom C{onTimeoutCancel] function is provided, the
        L{Deferred} returns the custom function's return value if the
        L{Deferred} times out before callbacking or errbacking.
        The custom C{onTimeoutCancel} function can return a result instead of
        a failure.
        """
        clock = Clock()
        d: Deferred[None] = Deferred()
        d.addTimeout(10, clock, onTimeoutCancel=_overrideFunc)
        self.assertNoResult(d)

        clock.advance(15)

        self.assertEqual("OVERRIDDEN", self.successResultOf(d))

    def test_timedOutProvidedCancelSuccess(self) -> None:
        """
        If a cancellation function is provided when the L{Deferred} is
        initialized, the L{Deferred} returns the cancellation value's
        non-failure return value when the L{Deferred} times out.
        """
        clock = Clock()
        d: Deferred[str] = Deferred(lambda c: c.callback("I was cancelled!"))
        d.addTimeout(10, clock)
        self.assertNoResult(d)

        clock.advance(15)

        self.assertEqual(self.successResultOf(d), "I was cancelled!")

    def test_timedOutProvidedCancelFailure(self) -> None:
        """
        If a cancellation function is provided when the L{Deferred} is
        initialized, the L{Deferred} returns the cancellation value's
        non-L{CanceledError} failure when the L{Deferred} times out.
        """
        clock = Clock()
        error = ValueError("what!")
        d: Deferred[None] = Deferred(lambda c: c.errback(error))
        d.addTimeout(10, clock)
        self.assertNoResult(d)

        clock.advance(15)

        f = self.failureResultOf(d, ValueError)
        self.assertIs(f.value, error)

    def test_cancelBeforeTimeout(self) -> None:
        """
        If the L{Deferred} is manually cancelled before the timeout, it
        is not re-cancelled (no L{AlreadyCancelled} error, and also no
        canceling of inner deferreds), and the default C{onTimeoutCancel}
        function is not called, preserving the original L{CancelledError}.
        """
        clock = Clock()
        d: Deferred[None] = Deferred()
        d.addTimeout(10, clock)

        # addTimeout is added first so that if d is timed out, d would be
        # canceled before innerDeferred gets returned from an errback on d
        innerDeferred: Deferred[None] = Deferred()
        dCanceled = None

        def onErrback(f: Failure) -> Deferred[None]:
            nonlocal dCanceled
            dCanceled = f
            return innerDeferred

        d.addErrback(onErrback)
        d.cancel()

        # d is cancelled immediately, before innerDeferred is returned from the
        # errback on d
        assert dCanceled is not None
        self.assertIsInstance(dCanceled, Failure)
        self.assertIs(dCanceled.type, defer.CancelledError)

        # The timeout never happens - if it did, d would have been cancelled
        # again, which would cancel innerDeferred too
        clock.advance(15)
        self.assertNoResult(innerDeferred)

    def test_cancelBeforeTimeoutCustom(self) -> None:
        """
        If the L{Deferred} is manually cancelled before the timeout, it
        is not re-cancelled (no L{AlreadyCancelled} error, and also no
        canceling of inner deferreds), and the custom C{onTimeoutCancel}
        function is not called, preserving the original L{CancelledError}.
        """
        clock = Clock()
        d: Deferred[None] = Deferred()
        d.addTimeout(10, clock, onTimeoutCancel=_overrideFunc)

        # addTimeout is added first so that if d is timed out, d would be
        # canceled before innerDeferred gets returned from an errback on d
        innerDeferred: Deferred[None] = Deferred()
        dCanceled = None

        def onErrback(f: Failure) -> Deferred[None]:
            nonlocal dCanceled
            dCanceled = f
            return innerDeferred

        d.addErrback(onErrback)
        d.cancel()

        # d is cancelled immediately, before innerDeferred is returned from the
        # errback on d
        assert dCanceled is not None
        self.assertIsInstance(dCanceled, Failure)
        self.assertIs(dCanceled.type, defer.CancelledError)

        # The timeout never happens - if it did, d would have been cancelled
        # again, which would cancel innerDeferred too
        clock.advance(15)
        self.assertNoResult(innerDeferred)

    def test_providedCancelCalledBeforeTimeoutCustom(self) -> None:
        """
        A custom translation function can handle a L{Deferred} with a
        custom cancellation function.
        """
        clock = Clock()
        d: Deferred[None] = Deferred(lambda c: c.errback(ValueError("what!")))
        d.addTimeout(10, clock, onTimeoutCancel=_overrideFunc)
        self.assertNoResult(d)

        clock.advance(15)

        self.assertEqual("OVERRIDDEN", self.successResultOf(d))

    def test_errbackAddedBeforeTimeout(self) -> None:
        """
        An errback added before a timeout is added errbacks with a
        L{defer.CancelledError} when the timeout fires.  If the
        errback returns the L{defer.CancelledError}, it is translated
        to a L{defer.TimeoutError} by the timeout implementation.
        """
        clock = Clock()
        d: Deferred[None] = Deferred()

        dErrbacked = None

        def errback(f: Failure) -> Failure:
            nonlocal dErrbacked
            dErrbacked = f
            return f

        d.addErrback(errback)
        d.addTimeout(10, clock)

        clock.advance(15)

        assert dErrbacked is not None
        self.assertIsInstance(dErrbacked, Failure)
        self.assertIsInstance(dErrbacked.value, defer.CancelledError)

        self.failureResultOf(d, defer.TimeoutError)

    def test_errbackAddedBeforeTimeoutSuppressesCancellation(self) -> None:
        """
        An errback added before a timeout is added errbacks with a
        L{defer.CancelledError} when the timeout fires.  If the
        errback suppresses the L{defer.CancelledError}, the deferred
        successfully completes.
        """
        clock = Clock()
        d: Deferred[None] = Deferred()

        dErrbacked = None

        def errback(f: Failure) -> None:
            nonlocal dErrbacked
            dErrbacked = f
            f.trap(defer.CancelledError)

        d.addErrback(errback)
        d.addTimeout(10, clock)

        clock.advance(15)

        assert dErrbacked is not None
        self.assertIsInstance(dErrbacked, Failure)
        self.assertIsInstance(dErrbacked.value, defer.CancelledError)

        self.successResultOf(d)

    def test_errbackAddedBeforeTimeoutCustom(self) -> None:
        """
        An errback added before a timeout is added with a custom
        timeout function errbacks with a L{defer.CancelledError} when
        the timeout fires.  The timeout function runs if the errback
        returns the L{defer.CancelledError}.
        """
        clock = Clock()
        d: Deferred[None] = Deferred()

        dErrbacked = None

        def errback(f: Failure) -> Failure:
            nonlocal dErrbacked
            dErrbacked = f
            return f

        d.addErrback(errback)
        d.addTimeout(10, clock, _overrideFunc)

        clock.advance(15)

        assert dErrbacked is not None
        self.assertIsInstance(dErrbacked, Failure)
        self.assertIsInstance(dErrbacked.value, defer.CancelledError)

        self.assertEqual("OVERRIDDEN", self.successResultOf(d))

    def test_errbackAddedBeforeTimeoutSuppressesCancellationCustom(self) -> None:
        """
        An errback added before a timeout is added with a custom
        timeout function errbacks with a L{defer.CancelledError} when
        the timeout fires.  The timeout function runs if the errback
        suppresses the L{defer.CancelledError}.
        """
        clock = Clock()
        d: Deferred[None] = Deferred()

        dErrbacked = None

        def errback(f: Failure) -> None:
            nonlocal dErrbacked
            dErrbacked = f

        d.addErrback(errback)
        d.addTimeout(10, clock, _overrideFunc)

        clock.advance(15)

        assert dErrbacked is not None
        self.assertIsInstance(dErrbacked, Failure)
        self.assertIsInstance(dErrbacked.value, defer.CancelledError)

        self.assertEqual("OVERRIDDEN", self.successResultOf(d))

    def test_callbackAddedToCancelerBeforeTimeout(self) -> None:
        """
        Given a deferred with a cancellation function that resumes the
        callback chain, a callback that is added to the deferred
        before a timeout is added to runs when the timeout fires.  The
        deferred completes successfully, without a
        L{defer.TimeoutError}.
        """
        clock = Clock()
        success = "success"
        d: Deferred[str] = Deferred(lambda d: d.callback(success))

        dCallbacked = None

        def callback(value: str) -> str:
            nonlocal dCallbacked
            dCallbacked = value
            return value

        d.addCallback(callback)
        d.addTimeout(10, clock)

        clock.advance(15)

        self.assertEqual(dCallbacked, success)

        self.assertIs(success, self.successResultOf(d))

    def test_callbackAddedToCancelerBeforeTimeoutCustom(self) -> None:
        """
        Given a deferred with a cancellation function that resumes the
        callback chain, a callback that is added to the deferred
        before a timeout is added to runs when the timeout fires.  The
        deferred completes successfully, without a
        L{defer.TimeoutError}.  The timeout's custom timeout function
        also runs.
        """
        clock = Clock()
        success = "success"
        d: Deferred[str] = Deferred(lambda d: d.callback(success))

        dCallbacked = None

        def callback(value: str) -> str:
            nonlocal dCallbacked
            dCallbacked = value
            return value

        d.addCallback(callback)
        d.addTimeout(10, clock, onTimeoutCancel=_overrideFunc)

        clock.advance(15)

        self.assertEqual(dCallbacked, success)

        self.assertEqual("OVERRIDDEN", self.successResultOf(d))


class EnsureDeferredTests(unittest.TestCase):
    """
    Tests for L{ensureDeferred}.
    """

    def test_passesThroughDeferreds(self) -> None:
        """
        L{ensureDeferred} will pass through a Deferred unchanged.
        """
        d1: Deferred[None] = Deferred()
        d2 = ensureDeferred(d1)
        self.assertIs(d1, d2)

    def test_willNotAllowNonDeferredOrCoroutine(self) -> None:
        """
        Passing L{ensureDeferred} a non-coroutine and a non-Deferred will
        raise a L{ValueError}.
        """
        with self.assertRaises(defer.NotACoroutineError):
            ensureDeferred("something")  # type: ignore[arg-type]

    def test_ensureDeferredCoroutine(self) -> None:
        """
        L{ensureDeferred} will turn a coroutine into a L{Deferred}.
        """

        async def run() -> str:
            d = defer.succeed("foo")
            res = await d
            return res

        # It's a coroutine...
        r = run()
        self.assertIsInstance(r, types.CoroutineType)

        # Now it's a Deferred.
        d = ensureDeferred(r)
        self.assertIsInstance(d, Deferred)

        # The Deferred has the result we want.
        res = self.successResultOf(d)
        self.assertEqual(res, "foo")

    def test_ensureDeferredGenerator(self) -> None:
        """
        L{ensureDeferred} will turn a yield-from coroutine into a L{Deferred}.
        """

        def run() -> Generator[Deferred[str], None, str]:
            d = defer.succeed("foo")
            res = cast(str, (yield from d))
            return res

        # It's a generator...
        r = run()
        self.assertIsInstance(r, types.GeneratorType)

        # Now it's a Deferred.
        d: Deferred[str] = ensureDeferred(r)
        self.assertIsInstance(d, Deferred)

        # The Deferred has the result we want.
        res = self.successResultOf(d)
        self.assertEqual(res, "foo")


class TimeoutErrorTests(unittest.TestCase, ImmediateFailureMixin):
    """
    L{twisted.internet.defer} timeout code.
    """

    def test_deprecatedTimeout(self) -> None:
        """
        L{twisted.internet.defer.timeout} is deprecated.
        """
        deferred: Deferred[None] = Deferred()
        defer.timeout(deferred)
        self.assertFailure(deferred, defer.TimeoutError)
        warningsShown = self.flushWarnings([self.test_deprecatedTimeout])
        self.assertEqual(len(warningsShown), 1)
        self.assertIs(warningsShown[0]["category"], DeprecationWarning)
        self.assertEqual(
            warningsShown[0]["message"],
            "twisted.internet.defer.timeout was deprecated in Twisted 17.1.0;"
            " please use twisted.internet.defer.Deferred.addTimeout instead",
        )


def callAllSoonCalls(loop: AbstractEventLoop) -> None:
    """
    Tickle an asyncio event loop to call all of the things scheduled with
    call_soon, inasmuch as this can be done via the public API.

    @param loop: The asyncio event loop to flush the previously-called
        C{call_soon} entries from.
    """
    loop.call_soon(loop.stop)
    loop.run_forever()


class DeferredFutureAdapterTests(unittest.TestCase):
    def test_asFuture(self) -> None:
        """
        L{Deferred.asFuture} returns a L{asyncio.Future} which fires when
        the given L{Deferred} does.
        """
        d: Deferred[int] = Deferred()
        loop = new_event_loop()
        aFuture = d.asFuture(loop)
        self.assertEqual(aFuture.done(), False)
        d.callback(13)
        callAllSoonCalls(loop)
        self.assertEqual(self.successResultOf(d), None)
        self.assertEqual(aFuture.result(), 13)

    def test_asFutureCancelFuture(self) -> None:
        """
        L{Deferred.asFuture} returns a L{asyncio.Future} which, when
        cancelled, will cancel the original L{Deferred}.
        """

        called = False

        def canceler(dprime: Deferred[object]) -> None:
            nonlocal called
            called = True

        d: Deferred[None] = Deferred(canceler)
        loop = new_event_loop()
        aFuture = d.asFuture(loop)
        aFuture.cancel()
        callAllSoonCalls(loop)
        self.assertTrue(called)
        self.assertEqual(self.successResultOf(d), None)
        self.assertRaises(CancelledError, aFuture.result)

    def test_asFutureSuccessCancel(self) -> None:
        """
        While Futures don't support succeeding in response to cancellation,
        Deferreds do; if a Deferred is coerced into a success by a Future
        cancellation, that should just be ignored.
        """

        def canceler(dprime: Deferred[object]) -> None:
            dprime.callback(9)

        d: Deferred[None] = Deferred(canceler)
        loop = new_event_loop()
        aFuture = d.asFuture(loop)
        aFuture.cancel()
        callAllSoonCalls(loop)
        self.assertEqual(self.successResultOf(d), None)
        self.assertRaises(CancelledError, aFuture.result)

    def test_asFutureFailure(self) -> None:
        """
        L{Deferred.asFuture} makes a L{asyncio.Future} fire with an
        exception when the given L{Deferred} does.
        """
        d: Deferred[None] = Deferred()
        theFailure = Failure(ZeroDivisionError())
        loop = new_event_loop()
        future = d.asFuture(loop)
        callAllSoonCalls(loop)
        d.errback(theFailure)
        callAllSoonCalls(loop)
        self.assertRaises(ZeroDivisionError, future.result)

    def test_fromFuture(self) -> None:
        """
        L{Deferred.fromFuture} returns a L{Deferred} that fires
        when the given L{asyncio.Future} does.
        """
        loop = new_event_loop()
        aFuture: Future[int] = Future(loop=loop)
        d = Deferred.fromFuture(aFuture)
        self.assertNoResult(d)
        aFuture.set_result(7)
        callAllSoonCalls(loop)
        self.assertEqual(self.successResultOf(d), 7)

    def test_fromFutureFutureCancelled(self) -> None:
        """
        L{Deferred.fromFuture} makes a L{Deferred} fire with
        an L{asyncio.CancelledError} when the given
        L{asyncio.Future} is cancelled.
        """
        loop = new_event_loop()
        cancelled: Future[None] = Future(loop=loop)
        d = Deferred.fromFuture(cancelled)
        cancelled.cancel()
        callAllSoonCalls(loop)
        self.assertRaises(CancelledError, cancelled.result)
        self.failureResultOf(d).trap(CancelledError)

    def test_fromFutureDeferredCancelled(self) -> None:
        """
        L{Deferred.fromFuture} makes a L{Deferred} which, when
        cancelled, cancels the L{asyncio.Future} it was created from.
        """
        loop = new_event_loop()
        cancelled: Future[None] = Future(loop=loop)
        d = Deferred.fromFuture(cancelled)
        d.cancel()
        callAllSoonCalls(loop)
        self.assertEqual(cancelled.cancelled(), True)
        self.assertRaises(CancelledError, cancelled.result)
        self.failureResultOf(d).trap(CancelledError)


class CoroutineContextVarsTests(unittest.TestCase):

    if contextvars is None:
        skip = "contextvars is not available"  # type: ignore[unreachable]

    def test_withInlineCallbacks(self) -> None:
        """
        When an inlineCallbacks function is called, the context is taken from
        when it was first called. When it resumes, the same context is applied.
        """
        clock = Clock()

        var: contextvars.ContextVar[int] = contextvars.ContextVar("testvar")
        var.set(1)

        # This Deferred will set its own context to 3 when it is called
        mutatingDeferred: Deferred[bool] = Deferred()
        mutatingDeferred.addCallback(lambda _: var.set(3))

        mutatingDeferredThatFails: Deferred[int] = Deferred()
        mutatingDeferredThatFails.addCallback(lambda _: var.set(4))
        mutatingDeferredThatFails.addCallback(lambda _: 1 / 0)

        @defer.inlineCallbacks
        def yieldingDeferred() -> Generator[Deferred[Any], Any, None]:
            d: Deferred[int] = Deferred()
            clock.callLater(1, d.callback, True)
            yield d
            var.set(3)

        # context is 1 when the function is defined
        @defer.inlineCallbacks
        def testFunction() -> Generator[Deferred[Any], Any, None]:

            # Expected to be 2
            self.assertEqual(var.get(), 2)

            # Does not mutate the context
            yield defer.succeed(1)

            # Expected to be 2
            self.assertEqual(var.get(), 2)

            # mutatingDeferred mutates it to 3, but only in its Deferred chain
            clock.callLater(1, mutatingDeferred.callback, True)
            yield mutatingDeferred

            # When it resumes, it should still be 2
            self.assertEqual(var.get(), 2)

            # mutatingDeferredThatFails mutates it to 3, but only in its
            # Deferred chain
            clock.callLater(1, mutatingDeferredThatFails.callback, True)
            try:
                yield mutatingDeferredThatFails
            except Exception:
                self.assertEqual(var.get(), 2)
            else:
                raise Exception("???? should have failed")

            # IMPLEMENTATION DETAIL: Because inlineCallbacks must be at every
            # level, an inlineCallbacks function yielding another
            # inlineCallbacks function will NOT mutate the outer one's context,
            # as it is copied when the inner one is ran and mutated there.
            yield yieldingDeferred()
            self.assertEqual(var.get(), 2)

            defer.returnValue(True)

        # The inlineCallbacks context is 2 when it's called
        var.set(2)
        d = testFunction()

        # Advance the clock so mutatingDeferred triggers
        clock.advance(1)

        # Advance the clock so that mutatingDeferredThatFails triggers
        clock.advance(1)

        # Advance the clock so that yieldingDeferred triggers
        clock.advance(1)

        self.assertEqual(self.successResultOf(d), True)

    def test_resetWithInlineCallbacks(self) -> None:
        """
        When an inlineCallbacks function resumes, we should be able to reset() a
        contextvar that was set when it was first called.
        """
        clock = Clock()

        var: contextvars.ContextVar[int] = contextvars.ContextVar("testvar")

        @defer.inlineCallbacks
        def yieldingDeferred() -> Generator[Deferred[Any], Any, None]:
            # first try setting the var
            token = var.set(3)

            # after a sleep, try resetting it
            d: Deferred[int] = Deferred()
            clock.callLater(1, d.callback, True)
            yield d
            self.assertEqual(var.get(), 3)

            var.reset(token)
            # it should have gone back to what we started with (2)
            self.assertEqual(var.get(), 2)

        # we start off with the var set to 2
        var.set(2)
        d = yieldingDeferred()

        # Advance the clock so that yieldingDeferred triggers
        clock.advance(1)
        self.successResultOf(d)

    @ensuringDeferred
    async def test_asyncWithLock(self) -> None:
        """
        L{DeferredLock} can be used as an asynchronous context manager.
        """
        lock = DeferredLock()
        async with lock:
            self.assertTrue(lock.locked)
            d = lock.acquire()
            d.addCallback(lambda _: lock.release())
            self.assertTrue(lock.locked)
            self.assertFalse(d.called)
        self.assertTrue(d.called)
        await d
        self.assertFalse(lock.locked)

    @ensuringDeferred
    async def test_asyncWithSemaphore(self) -> None:
        """
        L{DeferredSemaphore} can be used as an asynchronous context
        manager.
        """
        sem = DeferredSemaphore(3)

        async with sem:
            self.assertEqual(sem.tokens, 2)
            async with sem:
                self.assertEqual(sem.tokens, 1)
                d1 = sem.acquire()
                d2 = sem.acquire()
                self.assertEqual(sem.tokens, 0)
                self.assertTrue(d1.called)
                self.assertFalse(d2.called)
            self.assertEqual(sem.tokens, 0)
            self.assertTrue(d2.called)
            d1.addCallback(lambda _: sem.release())
            d2.addCallback(lambda _: sem.release())
            await d1
            await d2
            self.assertEqual(sem.tokens, 2)
        self.assertEqual(sem.tokens, 3)

    @ensuringDeferred
    async def test_asyncWithLockException(self) -> None:
        """
        C{DeferredLock} correctly propagates exceptions when
        used as an asynchronous context manager.
        """
        lock = DeferredLock()
        with self.assertRaisesRegexp(Exception, "some specific exception"):
            async with lock:
                self.assertTrue(lock.locked)
                raise Exception("some specific exception")
        self.assertFalse(lock.locked)

    def test_contextvarsWithAsyncAwait(self) -> None:
        """
        When a coroutine is called, the context is taken from when it was first
        called. When it resumes, the same context is applied.
        """
        clock = Clock()

        var: contextvars.ContextVar[int] = contextvars.ContextVar("testvar")
        var.set(1)

        # This Deferred will set its own context to 3 when it is called
        mutatingDeferred: Deferred[bool] = Deferred()
        mutatingDeferred.addCallback(lambda _: var.set(3))

        mutatingDeferredThatFails: Deferred[bool] = Deferred()
        mutatingDeferredThatFails.addCallback(lambda _: var.set(4))
        mutatingDeferredThatFails.addCallback(lambda _: 1 / 0)

        async def asyncFuncAwaitingDeferred() -> None:
            d: Deferred[bool] = Deferred()
            clock.callLater(1, d.callback, True)
            await d
            var.set(3)

        # context is 1 when the function is defined
        async def testFunction() -> bool:

            # Expected to be 2
            self.assertEqual(var.get(), 2)

            # Does not mutate the context
            await defer.succeed(1)

            # Expected to be 2
            self.assertEqual(var.get(), 2)

            # mutatingDeferred mutates it to 3, but only in its Deferred chain
            clock.callLater(0, mutatingDeferred.callback, True)
            await mutatingDeferred

            # When it resumes, it should still be 2
            self.assertEqual(var.get(), 2)

            # mutatingDeferredThatFails mutates it to 3, but only in its
            # Deferred chain
            clock.callLater(1, mutatingDeferredThatFails.callback, True)
            try:
                await mutatingDeferredThatFails
            except Exception:
                self.assertEqual(var.get(), 2)
            else:
                raise Exception("???? should have failed")

            # If we await another async def-defined function, it will be able
            # to mutate the outer function's context, it is *not* frozen and
            # restored inside the function call.
            await asyncFuncAwaitingDeferred()
            self.assertEqual(var.get(), 3)

            return True

        # The inlineCallbacks context is 2 when it's called
        var.set(2)
        d = ensureDeferred(testFunction())

        # Advance the clock so mutatingDeferred triggers
        clock.advance(1)

        # Advance the clock so that mutatingDeferredThatFails triggers
        clock.advance(1)

        # Advance the clock so that asyncFuncAwaitingDeferred triggers
        clock.advance(1)

        self.assertEqual(self.successResultOf(d), True)
