# -*- test-case-name: twisted.test.test_task,twisted.test.test_cooperator -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Scheduling utility methods and classes.
"""


import sys
import time
import warnings
from typing import (
    Callable,
    Coroutine,
    Iterable,
    Iterator,
    List,
    NoReturn,
    Optional,
    Sequence,
    TypeVar,
    Union,
    cast,
)

from zope.interface import implementer

from incremental import Version

from twisted.internet.base import DelayedCall
from twisted.internet.defer import Deferred, ensureDeferred, maybeDeferred
from twisted.internet.error import ReactorNotRunning
from twisted.internet.interfaces import IDelayedCall, IReactorCore, IReactorTime
from twisted.python import log, reflect
from twisted.python.deprecate import _getDeprecationWarningString
from twisted.python.failure import Failure

_T = TypeVar("_T")


class LoopingCall:
    """Call a function repeatedly.

    If C{f} returns a deferred, rescheduling will not take place until the
    deferred has fired. The result value is ignored.

    @ivar f: The function to call.
    @ivar a: A tuple of arguments to pass the function.
    @ivar kw: A dictionary of keyword arguments to pass to the function.
    @ivar clock: A provider of
        L{twisted.internet.interfaces.IReactorTime}.  The default is
        L{twisted.internet.reactor}. Feel free to set this to
        something else, but it probably ought to be set *before*
        calling L{start}.

    @ivar running: A flag which is C{True} while C{f} is scheduled to be called
        (or is currently being called). It is set to C{True} when L{start} is
        called and set to C{False} when L{stop} is called or if C{f} raises an
        exception. In either case, it will be C{False} by the time the
        C{Deferred} returned by L{start} fires its callback or errback.

    @ivar _realLastTime: When counting skips, the time at which the skip
        counter was last invoked.

    @ivar _runAtStart: A flag indicating whether the 'now' argument was passed
        to L{LoopingCall.start}.
    """

    call: Optional[IDelayedCall] = None
    running = False
    _deferred: Optional[Deferred["LoopingCall"]] = None
    interval: Optional[float] = None
    _runAtStart = False
    starttime: Optional[float] = None
    _realLastTime: Optional[float] = None

    def __init__(self, f: Callable[..., object], *a: object, **kw: object) -> None:
        self.f = f
        self.a = a
        self.kw = kw
        from twisted.internet import reactor

        self.clock = cast(IReactorTime, reactor)

    @property
    def deferred(self) -> Optional[Deferred["LoopingCall"]]:
        """
        DEPRECATED. L{Deferred} fired when loop stops or fails.

        Use the L{Deferred} returned by L{LoopingCall.start}.
        """
        warningString = _getDeprecationWarningString(
            "twisted.internet.task.LoopingCall.deferred",
            Version("Twisted", 16, 0, 0),
            replacement="the deferred returned by start()",
        )
        warnings.warn(warningString, DeprecationWarning, stacklevel=2)

        return self._deferred

    @classmethod
    def withCount(cls, countCallable: Callable[[int], object]) -> "LoopingCall":
        """
        An alternate constructor for L{LoopingCall} that makes available the
        number of calls which should have occurred since it was last invoked.

        Note that this number is an C{int} value; It represents the discrete
        number of calls that should have been made.  For example, if you are
        using a looping call to display an animation with discrete frames, this
        number would be the number of frames to advance.

        The count is normally 1, but can be higher. For example, if the reactor
        is blocked and takes too long to invoke the L{LoopingCall}, a Deferred
        returned from a previous call is not fired before an interval has
        elapsed, or if the callable itself blocks for longer than an interval,
        preventing I{itself} from being called.

        When running with an interval of 0, count will be always 1.

        @param countCallable: A callable that will be invoked each time the
            resulting LoopingCall is run, with an integer specifying the number
            of calls that should have been invoked.

        @return: An instance of L{LoopingCall} with call counting enabled,
            which provides the count as the first positional argument.

        @since: 9.0
        """

        def counter() -> object:
            now = self.clock.seconds()

            if self.interval == 0:
                self._realLastTime = now
                return countCallable(1)

            lastTime = self._realLastTime
            if lastTime is None:
                assert (
                    self.starttime is not None
                ), "LoopingCall called before it was started"
                lastTime = self.starttime
                if self._runAtStart:
                    assert (
                        self.interval is not None
                    ), "Looping call called with None interval"
                    lastTime -= self.interval
            lastInterval = self._intervalOf(lastTime)
            thisInterval = self._intervalOf(now)
            count = thisInterval - lastInterval
            if count > 0:
                self._realLastTime = now
                return countCallable(count)

            return None

        self = cls(counter)

        return self

    def _intervalOf(self, t: float) -> int:
        """
        Determine the number of intervals passed as of the given point in
        time.

        @param t: The specified time (from the start of the L{LoopingCall}) to
            be measured in intervals

        @return: The C{int} number of intervals which have passed as of the
            given point in time.
        """
        assert self.starttime is not None
        assert self.interval is not None
        elapsedTime = t - self.starttime
        intervalNum = int(elapsedTime / self.interval)
        return intervalNum

    def start(self, interval: float, now: bool = True) -> Deferred["LoopingCall"]:
        """
        Start running function every interval seconds.

        @param interval: The number of seconds between calls.  May be
        less than one.  Precision will depend on the underlying
        platform, the available hardware, and the load on the system.

        @param now: If True, run this call right now.  Otherwise, wait
        until the interval has elapsed before beginning.

        @return: A Deferred whose callback will be invoked with
        C{self} when C{self.stop} is called, or whose errback will be
        invoked when the function raises an exception or returned a
        deferred that has its errback invoked.
        """
        assert not self.running, "Tried to start an already running " "LoopingCall."
        if interval < 0:
            raise ValueError("interval must be >= 0")
        self.running = True
        # Loop might fail to start and then self._deferred will be cleared.
        # This why the local C{deferred} variable is used.
        deferred = self._deferred = Deferred()
        self.starttime = self.clock.seconds()
        self.interval = interval
        self._runAtStart = now
        if now:
            self()
        else:
            self._scheduleFrom(self.starttime)
        return deferred

    def stop(self) -> None:
        """Stop running function."""
        assert self.running, "Tried to stop a LoopingCall that was " "not running."
        self.running = False
        if self.call is not None:
            self.call.cancel()
            self.call = None
            d, self._deferred = self._deferred, None
            assert d is not None
            d.callback(self)

    def reset(self) -> None:
        """
        Skip the next iteration and reset the timer.

        @since: 11.1
        """
        assert self.running, "Tried to reset a LoopingCall that was " "not running."
        if self.call is not None:
            self.call.cancel()
            self.call = None
            self.starttime = self.clock.seconds()
            self._scheduleFrom(self.starttime)

    def __call__(self) -> None:
        def cb(result: object) -> None:
            if self.running:
                self._scheduleFrom(self.clock.seconds())
            else:
                d, self._deferred = self._deferred, None
                assert d is not None
                d.callback(self)

        def eb(failure: Failure) -> None:
            self.running = False
            d, self._deferred = self._deferred, None
            assert d is not None
            d.errback(failure)

        self.call = None
        d = maybeDeferred(self.f, *self.a, **self.kw)
        d.addCallback(cb)
        d.addErrback(eb)

    def _scheduleFrom(self, when: float) -> None:
        """
        Schedule the next iteration of this looping call.

        @param when: The present time from whence the call is scheduled.
        """

        def howLong() -> float:
            # How long should it take until the next invocation of our
            # callable?  Split out into a function because there are multiple
            # places we want to 'return' out of this.
            if self.interval == 0:
                # If the interval is 0, just go as fast as possible, always
                # return zero, call ourselves ASAP.
                return 0
            # Compute the time until the next interval; how long has this call
            # been running for?
            assert self.starttime is not None
            runningFor = when - self.starttime
            # And based on that start time, when does the current interval end?
            assert self.interval is not None
            untilNextInterval = self.interval - (runningFor % self.interval)
            # Now that we know how long it would be, we have to tell if the
            # number is effectively zero.  However, we can't just test against
            # zero.  If a number with a small exponent is added to a number
            # with a large exponent, it may be so small that the digits just
            # fall off the end, which means that adding the increment makes no
            # difference; it's time to tick over into the next interval.
            if when == when + untilNextInterval:
                # If it's effectively zero, then we need to add another
                # interval.
                return self.interval
            # Finally, if everything else is normal, we just return the
            # computed delay.
            return untilNextInterval

        self.call = self.clock.callLater(howLong(), self)

    def __repr__(self) -> str:
        # This code should be replaced by a utility function in reflect;
        # see ticket #6066:
        func = getattr(self.f, "__qualname__", None)
        if func is None:
            func = getattr(self.f, "__name__", None)
            if func is not None:
                imClass = getattr(self.f, "im_class", None)
                if imClass is not None:
                    func = f"{imClass}.{func}"
        if func is None:
            func = reflect.safe_repr(self.f)

        return "LoopingCall<{!r}>({}, *{}, **{})".format(
            self.interval,
            func,
            reflect.safe_repr(self.a),
            reflect.safe_repr(self.kw),
        )


class SchedulerError(Exception):
    """
    The operation could not be completed because the scheduler or one of its
    tasks was in an invalid state.  This exception should not be raised
    directly, but is a superclass of various scheduler-state-related
    exceptions.
    """


class SchedulerStopped(SchedulerError):
    """
    The operation could not complete because the scheduler was stopped in
    progress or was already stopped.
    """


class TaskFinished(SchedulerError):
    """
    The operation could not complete because the task was already completed,
    stopped, encountered an error or otherwise permanently stopped running.
    """


class TaskDone(TaskFinished):
    """
    The operation could not complete because the task was already completed.
    """


class TaskStopped(TaskFinished):
    """
    The operation could not complete because the task was stopped.
    """


class TaskFailed(TaskFinished):
    """
    The operation could not complete because the task died with an unhandled
    error.
    """


class NotPaused(SchedulerError):
    """
    This exception is raised when a task is resumed which was not previously
    paused.
    """


class _Timer:
    MAX_SLICE = 0.01

    def __init__(self) -> None:
        self.end = time.time() + self.MAX_SLICE

    def __call__(self) -> bool:
        return time.time() >= self.end


_EPSILON = 0.00000001


def _defaultScheduler(callable: Callable[[], None]) -> IDelayedCall:
    from twisted.internet import reactor

    return cast(IReactorTime, reactor).callLater(_EPSILON, callable)


_TaskResultT = TypeVar("_TaskResultT")


class CooperativeTask:
    """
    A L{CooperativeTask} is a task object inside a L{Cooperator}, which can be
    paused, resumed, and stopped.  It can also have its completion (or
    termination) monitored.

    @see: L{Cooperator.cooperate}

    @ivar _iterator: the iterator to iterate when this L{CooperativeTask} is
        asked to do work.

    @ivar _cooperator: the L{Cooperator} that this L{CooperativeTask}
        participates in, which is used to re-insert it upon resume.

    @ivar _deferreds: the list of L{Deferred}s to fire when this task
        completes, fails, or finishes.

    @ivar _pauseCount: the number of times that this L{CooperativeTask} has
        been paused; if 0, it is running.

    @ivar _completionState: The completion-state of this L{CooperativeTask}.
        L{None} if the task is not yet completed, an instance of L{TaskStopped}
        if C{stop} was called to stop this task early, of L{TaskFailed} if the
        application code in the iterator raised an exception which caused it to
        terminate, and of L{TaskDone} if it terminated normally via raising
        C{StopIteration}.
    """

    def __init__(
        self, iterator: Iterator[_TaskResultT], cooperator: "Cooperator"
    ) -> None:
        """
        A private constructor: to create a new L{CooperativeTask}, see
        L{Cooperator.cooperate}.
        """
        self._iterator = iterator
        self._cooperator = cooperator
        self._deferreds: List[Deferred[Iterator[_TaskResultT]]] = []
        self._pauseCount = 0
        self._completionState: Optional[SchedulerError] = None
        self._completionResult: Optional[Union[Iterator[_TaskResultT], Failure]] = None
        cooperator._addTask(self)

    def whenDone(self) -> Deferred[Iterator[_TaskResultT]]:
        """
        Get a L{Deferred} notification of when this task is complete.

        @return: a L{Deferred} that fires with the C{iterator} that this
            L{CooperativeTask} was created with when the iterator has been
            exhausted (i.e. its C{next} method has raised C{StopIteration}), or
            fails with the exception raised by C{next} if it raises some other
            exception.

        @rtype: L{Deferred}
        """
        d: Deferred[Iterator[_TaskResultT]] = Deferred()
        if self._completionState is None:
            self._deferreds.append(d)
        else:
            assert self._completionResult is not None
            d.callback(self._completionResult)
        return d

    def pause(self) -> None:
        """
        Pause this L{CooperativeTask}.  Stop doing work until
        L{CooperativeTask.resume} is called.  If C{pause} is called more than
        once, C{resume} must be called an equal number of times to resume this
        task.

        @raise TaskFinished: if this task has already finished or completed.
        """
        self._checkFinish()
        self._pauseCount += 1
        if self._pauseCount == 1:
            self._cooperator._removeTask(self)

    def resume(self) -> None:
        """
        Resume processing of a paused L{CooperativeTask}.

        @raise NotPaused: if this L{CooperativeTask} is not paused.
        """
        if self._pauseCount == 0:
            raise NotPaused()
        self._pauseCount -= 1
        if self._pauseCount == 0 and self._completionState is None:
            self._cooperator._addTask(self)

    def _completeWith(
        self,
        completionState: SchedulerError,
        deferredResult: Union[Iterator[_TaskResultT], Failure],
    ) -> None:
        """
        @param completionState: a L{SchedulerError} exception or a subclass
            thereof, indicating what exception should be raised when subsequent
            operations are performed.

        @param deferredResult: the result to fire all the deferreds with.
        """
        self._completionState = completionState
        self._completionResult = deferredResult
        if not self._pauseCount:
            self._cooperator._removeTask(self)

        # The Deferreds need to be invoked after all this is completed, because
        # a Deferred may want to manipulate other tasks in a Cooperator.  For
        # example, if you call "stop()" on a cooperator in a callback on a
        # Deferred returned from whenDone(), this CooperativeTask must be gone
        # from the Cooperator by that point so that _completeWith is not
        # invoked reentrantly; that would cause these Deferreds to blow up with
        # an AlreadyCalledError, or the _removeTask to fail with a ValueError.
        for d in self._deferreds:
            d.callback(deferredResult)

    def stop(self) -> None:
        """
        Stop further processing of this task.

        @raise TaskFinished: if this L{CooperativeTask} has previously
            completed, via C{stop}, completion, or failure.
        """
        self._checkFinish()
        self._completeWith(TaskStopped(), Failure(TaskStopped()))

    def _checkFinish(self) -> None:
        """
        If this task has been stopped, raise the appropriate subclass of
        L{TaskFinished}.
        """
        if self._completionState is not None:
            raise self._completionState

    def _oneWorkUnit(self) -> None:
        """
        Perform one unit of work for this task, retrieving one item from its
        iterator, stopping if there are no further items in the iterator, and
        pausing if the result was a L{Deferred}.
        """
        try:
            result = next(self._iterator)
        except StopIteration:
            self._completeWith(TaskDone(), self._iterator)
        except BaseException:
            self._completeWith(TaskFailed(), Failure())
        else:
            if isinstance(result, Deferred):
                self.pause()

                def failLater(failure: Failure) -> None:
                    self._completeWith(TaskFailed(), failure)

                result.addCallbacks(lambda result: self.resume(), failLater)


class Cooperator:
    """
    Cooperative task scheduler.

    A cooperative task is an iterator where each iteration represents an
    atomic unit of work.  When the iterator yields, it allows the
    L{Cooperator} to decide which of its tasks to execute next.  If the
    iterator yields a L{Deferred} then work will pause until the
    L{Deferred} fires and completes its callback chain.

    When a L{Cooperator} has more than one task, it distributes work between
    all tasks.

    There are two ways to add tasks to a L{Cooperator}, L{cooperate} and
    L{coiterate}.  L{cooperate} is the more useful of the two, as it returns a
    L{CooperativeTask}, which can be L{paused<CooperativeTask.pause>},
    L{resumed<CooperativeTask.resume>} and L{waited
    on<CooperativeTask.whenDone>}.  L{coiterate} has the same effect, but
    returns only a L{Deferred} that fires when the task is done.

    L{Cooperator} can be used for many things, including but not limited to:

      - running one or more computationally intensive tasks without blocking
      - limiting parallelism by running a subset of the total tasks
        simultaneously
      - doing one thing, waiting for a L{Deferred} to fire,
        doing the next thing, repeat (i.e. serializing a sequence of
        asynchronous tasks)

    Multiple L{Cooperator}s do not cooperate with each other, so for most
    cases you should use the L{global cooperator<task.cooperate>}.
    """

    def __init__(
        self,
        terminationPredicateFactory: Callable[[], Callable[[], bool]] = _Timer,
        scheduler: Callable[[Callable[[], None]], IDelayedCall] = _defaultScheduler,
        started: bool = True,
    ):
        """
        Create a scheduler-like object to which iterators may be added.

        @param terminationPredicateFactory: A no-argument callable which will
        be invoked at the beginning of each step and should return a
        no-argument callable which will return True when the step should be
        terminated.  The default factory is time-based and allows iterators to
        run for 1/100th of a second at a time.

        @param scheduler: A one-argument callable which takes a no-argument
        callable and should invoke it at some future point.  This will be used
        to schedule each step of this Cooperator.

        @param started: A boolean which indicates whether iterators should be
        stepped as soon as they are added, or if they will be queued up until
        L{Cooperator.start} is called.
        """
        self._tasks: List[CooperativeTask] = []
        self._metarator: Iterator[CooperativeTask] = iter(())
        self._terminationPredicateFactory = terminationPredicateFactory
        self._scheduler = scheduler
        self._delayedCall: Optional[IDelayedCall] = None
        self._stopped = False
        self._started = started

    def coiterate(
        self,
        iterator: Iterator[_TaskResultT],
        doneDeferred: Optional[Deferred[Iterator[_TaskResultT]]] = None,
    ) -> Deferred[Iterator[_TaskResultT]]:
        """
        Add an iterator to the list of iterators this L{Cooperator} is
        currently running.

        Equivalent to L{cooperate}, but returns a L{Deferred} that will
        be fired when the task is done.

        @param doneDeferred: If specified, this will be the Deferred used as
            the completion deferred.  It is suggested that you use the default,
            which creates a new Deferred for you.

        @return: a Deferred that will fire when the iterator finishes.
        """
        if doneDeferred is None:
            doneDeferred = Deferred()
        CooperativeTask(iterator, self).whenDone().chainDeferred(doneDeferred)
        return doneDeferred

    def cooperate(self, iterator: Iterator[_TaskResultT]) -> CooperativeTask:
        """
        Start running the given iterator as a long-running cooperative task, by
        calling next() on it as a periodic timed event.

        @param iterator: the iterator to invoke.

        @return: a L{CooperativeTask} object representing this task.
        """
        return CooperativeTask(iterator, self)

    def _addTask(self, task: CooperativeTask) -> None:
        """
        Add a L{CooperativeTask} object to this L{Cooperator}.
        """
        if self._stopped:
            self._tasks.append(task)  # XXX silly, I know, but _completeWith
            # does the inverse
            task._completeWith(SchedulerStopped(), Failure(SchedulerStopped()))
        else:
            self._tasks.append(task)
            self._reschedule()

    def _removeTask(self, task: CooperativeTask) -> None:
        """
        Remove a L{CooperativeTask} from this L{Cooperator}.
        """
        self._tasks.remove(task)
        # If no work left to do, cancel the delayed call:
        if not self._tasks and self._delayedCall:
            self._delayedCall.cancel()
            self._delayedCall = None

    def _tasksWhileNotStopped(self) -> Iterable[CooperativeTask]:
        """
        Yield all L{CooperativeTask} objects in a loop as long as this
        L{Cooperator}'s termination condition has not been met.
        """
        terminator = self._terminationPredicateFactory()
        while self._tasks:
            for t in self._metarator:
                yield t
                if terminator():
                    return
            self._metarator = iter(self._tasks)

    def _tick(self) -> None:
        """
        Run one scheduler tick.
        """
        self._delayedCall = None
        for taskObj in self._tasksWhileNotStopped():
            taskObj._oneWorkUnit()
        self._reschedule()

    _mustScheduleOnStart = False

    def _reschedule(self) -> None:
        if not self._started:
            self._mustScheduleOnStart = True
            return
        if self._delayedCall is None and self._tasks:
            self._delayedCall = self._scheduler(self._tick)

    def start(self) -> None:
        """
        Begin scheduling steps.
        """
        self._stopped = False
        self._started = True
        if self._mustScheduleOnStart:
            del self._mustScheduleOnStart
            self._reschedule()

    def stop(self) -> None:
        """
        Stop scheduling steps.  Errback the completion Deferreds of all
        iterators which have been added and forget about them.
        """
        self._stopped = True
        for taskObj in self._tasks:
            taskObj._completeWith(SchedulerStopped(), Failure(SchedulerStopped()))
        self._tasks = []
        if self._delayedCall is not None:
            self._delayedCall.cancel()
            self._delayedCall = None

    @property
    def running(self) -> bool:
        """
        Is this L{Cooperator} is currently running?

        @return: C{True} if the L{Cooperator} is running, C{False} otherwise.
        @rtype: C{bool}
        """
        return self._started and not self._stopped


_theCooperator = Cooperator()


def coiterate(iterator: Iterator[_T]) -> Deferred[Iterator[_T]]:
    """
    Cooperatively iterate over the given iterator, dividing runtime between it
    and all other iterators which have been passed to this function and not yet
    exhausted.

    @param iterator: the iterator to invoke.

    @return: a Deferred that will fire when the iterator finishes.
    """
    return _theCooperator.coiterate(iterator)


def cooperate(iterator: Iterator[_T]) -> CooperativeTask:
    """
    Start running the given iterator as a long-running cooperative task, by
    calling next() on it as a periodic timed event.

    This is very useful if you have computationally expensive tasks that you
    want to run without blocking the reactor.  Just break each task up so that
    it yields frequently, pass it in here and the global L{Cooperator} will
    make sure work is distributed between them without blocking longer than a
    single iteration of a single task.

    @param iterator: the iterator to invoke.

    @return: a L{CooperativeTask} object representing this task.
    """
    return _theCooperator.cooperate(iterator)


@implementer(IReactorTime)
class Clock:
    """
    Provide a deterministic, easily-controlled implementation of
    L{IReactorTime.callLater}.  This is commonly useful for writing
    deterministic unit tests for code which schedules events using this API.
    """

    rightNow = 0.0

    def __init__(self) -> None:
        self.calls: List[DelayedCall] = []

    def seconds(self) -> float:
        """
        Pretend to be time.time().  This is used internally when an operation
        such as L{IDelayedCall.reset} needs to determine a time value
        relative to the current time.

        @return: The time which should be considered the current time.
        """
        return self.rightNow

    def _sortCalls(self) -> None:
        """
        Sort the pending calls according to the time they are scheduled.
        """
        self.calls.sort(key=lambda a: a.getTime())

    def callLater(
        self, delay: float, callable: Callable[..., object], *args: object, **kw: object
    ) -> IDelayedCall:
        """
        See L{twisted.internet.interfaces.IReactorTime.callLater}.
        """
        dc = DelayedCall(
            self.seconds() + delay,
            callable,
            args,
            kw,
            self.calls.remove,
            lambda c: None,
            self.seconds,
        )
        self.calls.append(dc)
        self._sortCalls()
        return dc

    def getDelayedCalls(self) -> Sequence[IDelayedCall]:
        """
        See L{twisted.internet.interfaces.IReactorTime.getDelayedCalls}
        """
        return self.calls

    def advance(self, amount: float) -> None:
        """
        Move time on this clock forward by the given amount and run whatever
        pending calls should be run.

        @param amount: The number of seconds which to advance this clock's
        time.
        """
        self.rightNow += amount
        self._sortCalls()
        while self.calls and self.calls[0].getTime() <= self.seconds():
            call = self.calls.pop(0)
            call.called = 1
            call.func(*call.args, **call.kw)
            self._sortCalls()

    def pump(self, timings: Iterable[float]) -> None:
        """
        Advance incrementally by the given set of times.
        """
        for amount in timings:
            self.advance(amount)


def deferLater(
    clock: IReactorTime,
    delay: float,
    callable: Optional[Callable[..., _T]] = None,
    *args: object,
    **kw: object,
) -> Deferred[_T]:
    """
    Call the given function after a certain period of time has passed.

    @param clock: The object which will be used to schedule the delayed
        call.

    @param delay: The number of seconds to wait before calling the function.

    @param callable: The callable to call after the delay, or C{None}.

    @param args: The positional arguments to pass to C{callable}.

    @param kw: The keyword arguments to pass to C{callable}.

    @return: A deferred that fires with the result of the callable when the
        specified time has elapsed.
    """

    def deferLaterCancel(deferred: Deferred[object]) -> None:
        delayedCall.cancel()

    def cb(result: object) -> _T:
        if callable is None:
            return None  # type: ignore[return-value]
        return callable(*args, **kw)

    d: Deferred[_T] = Deferred(deferLaterCancel)
    d.addCallback(cb)
    delayedCall = clock.callLater(delay, d.callback, None)
    return d


def react(
    main: Callable[
        ...,
        Union[Deferred[_T], Coroutine["Deferred[_T]", object, _T]],
    ],
    argv: Iterable[object] = (),
    _reactor: Optional[IReactorCore] = None,
) -> NoReturn:
    """
    Call C{main} and run the reactor until the L{Deferred} it returns fires or
    the coroutine it returns completes.

    This is intended as the way to start up an application with a well-defined
    completion condition.  Use it to write clients or one-off asynchronous
    operations.  Prefer this to calling C{reactor.run} directly, as this
    function will also:

      - Take care to call C{reactor.stop} once and only once, and at the right
        time.
      - Log any failures from the C{Deferred} returned by C{main}.
      - Exit the application when done, with exit code 0 in case of success and
        1 in case of failure. If C{main} fails with a C{SystemExit} error, the
        code returned is used.

    The following demonstrates the signature of a C{main} function which can be
    used with L{react}::

      async def main(reactor, username, password):
          return "ok"

      task.react(main, ("alice", "secret"))

    @param main: A callable which returns a L{Deferred} or
        coroutine. It should take the reactor as its first
        parameter, followed by the elements of C{argv}.

    @param argv: A list of arguments to pass to C{main}. If omitted the
        callable will be invoked with no additional arguments.

    @param _reactor: An implementation detail to allow easier unit testing.  Do
        not supply this parameter.

    @since: 12.3
    """
    if _reactor is None:
        from twisted.internet import reactor

        _reactor = cast(IReactorCore, reactor)

    finished = ensureDeferred(main(_reactor, *argv))
    code = 0

    stopping = False

    def onShutdown() -> None:
        nonlocal stopping
        stopping = True

    _reactor.addSystemEventTrigger("before", "shutdown", onShutdown)

    def stop(result: object, stopReactor: bool) -> None:
        if stopReactor:
            assert _reactor is not None
            try:
                _reactor.stop()
            except ReactorNotRunning:
                pass

        if isinstance(result, Failure):
            nonlocal code
            if result.check(SystemExit) is not None:
                code = result.value.code
            else:
                log.err(result, "main function encountered error")
                code = 1

    def cbFinish(result: object) -> None:
        if stopping:
            stop(result, False)
        else:
            assert _reactor is not None
            _reactor.callWhenRunning(stop, result, True)

    finished.addBoth(cbFinish)
    _reactor.run()
    sys.exit(code)


__all__ = [
    "LoopingCall",
    "Clock",
    "SchedulerStopped",
    "Cooperator",
    "coiterate",
    "deferLater",
    "react",
]
