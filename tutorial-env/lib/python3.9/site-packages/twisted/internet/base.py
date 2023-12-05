# -*- test-case-name: twisted.test.test_internet,twisted.internet.test.test_core -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Very basic functionality for a Reactor implementation.
"""


import builtins
import socket  # needed only for sync-dns
import warnings
from abc import ABC, abstractmethod
from heapq import heapify, heappop, heappush
from traceback import format_stack
from types import FrameType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    NewType,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
    cast,
)

from zope.interface import classImplements, implementer

from twisted.internet import abstract, defer, error, fdesc, main, threads
from twisted.internet._resolver import (
    ComplexResolverSimplifier as _ComplexResolverSimplifier,
    GAIResolver as _GAIResolver,
    SimpleResolverComplexifier as _SimpleResolverComplexifier,
)
from twisted.internet.defer import Deferred, DeferredList
from twisted.internet.interfaces import (
    IAddress,
    IConnector,
    IDelayedCall,
    IHostnameResolver,
    IProtocol,
    IReactorCore,
    IReactorPluggableNameResolver,
    IReactorPluggableResolver,
    IReactorThreads,
    IReactorTime,
    IReadDescriptor,
    IResolverSimple,
    IWriteDescriptor,
    _ISupportsExitSignalCapturing,
)
from twisted.internet.protocol import ClientFactory
from twisted.python import log, reflect
from twisted.python.failure import Failure
from twisted.python.runtime import platform, seconds as runtimeSeconds

if TYPE_CHECKING:
    from twisted.internet.tcp import Client

# This import is for side-effects!  Even if you don't see any code using it
# in this module, don't delete it.
from twisted.python import threadable

if platform.supportsThreads():
    from twisted.python.threadpool import ThreadPool
else:
    ThreadPool = None  # type: ignore[misc, assignment]


@implementer(IDelayedCall)
class DelayedCall:

    # enable .debug to record creator call stack, and it will be logged if
    # an exception occurs while the function is being run
    debug = False
    _repr: Optional[str] = None

    # In debug mode, the call stack at the time of instantiation.
    creator: Optional[Sequence[str]] = None

    def __init__(
        self,
        time: float,
        func: Callable[..., Any],
        args: Sequence[object],
        kw: Dict[str, object],
        cancel: Callable[["DelayedCall"], None],
        reset: Callable[["DelayedCall"], None],
        seconds: Callable[[], float] = runtimeSeconds,
    ) -> None:
        """
        @param time: Seconds from the epoch at which to call C{func}.
        @param func: The callable to call.
        @param args: The positional arguments to pass to the callable.
        @param kw: The keyword arguments to pass to the callable.
        @param cancel: A callable which will be called with this
            DelayedCall before cancellation.
        @param reset: A callable which will be called with this
            DelayedCall after changing this DelayedCall's scheduled
            execution time. The callable should adjust any necessary
            scheduling details to ensure this DelayedCall is invoked
            at the new appropriate time.
        @param seconds: If provided, a no-argument callable which will be
            used to determine the current time any time that information is
            needed.
        """
        self.time, self.func, self.args, self.kw = time, func, args, kw
        self.resetter = reset
        self.canceller = cancel
        self.seconds = seconds
        self.cancelled = self.called = 0
        self.delayed_time = 0.0
        if self.debug:
            self.creator = format_stack()[:-2]

    def getTime(self) -> float:
        """
        Return the time at which this call will fire

        @return: The number of seconds after the epoch at which this call is
            scheduled to be made.
        """
        return self.time + self.delayed_time

    def cancel(self) -> None:
        """
        Unschedule this call

        @raise AlreadyCancelled: Raised if this call has already been
            unscheduled.

        @raise AlreadyCalled: Raised if this call has already been made.
        """
        if self.cancelled:
            raise error.AlreadyCancelled
        elif self.called:
            raise error.AlreadyCalled
        else:
            self.canceller(self)
            self.cancelled = 1
            if self.debug:
                self._repr = repr(self)
            del self.func, self.args, self.kw

    def reset(self, secondsFromNow: float) -> None:
        """
        Reschedule this call for a different time

        @param secondsFromNow: The number of seconds from the time of the
            C{reset} call at which this call will be scheduled.

        @raise AlreadyCancelled: Raised if this call has been cancelled.
        @raise AlreadyCalled: Raised if this call has already been made.
        """
        if self.cancelled:
            raise error.AlreadyCancelled
        elif self.called:
            raise error.AlreadyCalled
        else:
            newTime = self.seconds() + secondsFromNow
            if newTime < self.time:
                self.delayed_time = 0.0
                self.time = newTime
                self.resetter(self)
            else:
                self.delayed_time = newTime - self.time

    def delay(self, secondsLater: float) -> None:
        """
        Reschedule this call for a later time

        @param secondsLater: The number of seconds after the originally
            scheduled time for which to reschedule this call.

        @raise AlreadyCancelled: Raised if this call has been cancelled.
        @raise AlreadyCalled: Raised if this call has already been made.
        """
        if self.cancelled:
            raise error.AlreadyCancelled
        elif self.called:
            raise error.AlreadyCalled
        else:
            self.delayed_time += secondsLater
            if self.delayed_time < 0.0:
                self.activate_delay()
                self.resetter(self)

    def activate_delay(self) -> None:
        self.time += self.delayed_time
        self.delayed_time = 0.0

    def active(self) -> bool:
        """Determine whether this call is still pending

        @return: True if this call has not yet been made or cancelled,
            False otherwise.
        """
        return not (self.cancelled or self.called)

    def __le__(self, other: object) -> bool:
        """
        Implement C{<=} operator between two L{DelayedCall} instances.

        Comparison is based on the C{time} attribute (unadjusted by the
        delayed time).
        """
        if isinstance(other, DelayedCall):
            return self.time <= other.time
        else:
            return NotImplemented

    def __lt__(self, other: object) -> bool:
        """
        Implement C{<} operator between two L{DelayedCall} instances.

        Comparison is based on the C{time} attribute (unadjusted by the
        delayed time).
        """
        if isinstance(other, DelayedCall):
            return self.time < other.time
        else:
            return NotImplemented

    def __repr__(self) -> str:
        """
        Implement C{repr()} for L{DelayedCall} instances.

        @returns: String containing details of the L{DelayedCall}.
        """
        if self._repr is not None:
            return self._repr
        if hasattr(self, "func"):
            # This code should be replaced by a utility function in reflect;
            # see ticket #6066:
            func = getattr(self.func, "__qualname__", None)
            if func is None:
                func = getattr(self.func, "__name__", None)
                if func is not None:
                    imClass = getattr(self.func, "im_class", None)
                    if imClass is not None:
                        func = f"{imClass}.{func}"
            if func is None:
                func = reflect.safe_repr(self.func)
        else:
            func = None

        now = self.seconds()
        L = [
            "<DelayedCall 0x%x [%ss] called=%s cancelled=%s"
            % (id(self), self.time - now, self.called, self.cancelled)
        ]
        if func is not None:
            L.extend((" ", func, "("))
            if self.args:
                L.append(", ".join([reflect.safe_repr(e) for e in self.args]))
                if self.kw:
                    L.append(", ")
            if self.kw:
                L.append(
                    ", ".join(
                        [f"{k}={reflect.safe_repr(v)}" for (k, v) in self.kw.items()]
                    )
                )
            L.append(")")

        if self.creator is not None:
            L.append("\n\ntraceback at creation: \n\n%s" % ("    ".join(self.creator)))
        L.append(">")

        return "".join(L)


@implementer(IResolverSimple)
class ThreadedResolver:
    """
    L{ThreadedResolver} uses a reactor, a threadpool, and
    L{socket.gethostbyname} to perform name lookups without blocking the
    reactor thread.  It also supports timeouts indepedently from whatever
    timeout logic L{socket.gethostbyname} might have.

    @ivar reactor: The reactor the threadpool of which will be used to call
        L{socket.gethostbyname} and the I/O thread of which the result will be
        delivered.
    """

    def __init__(self, reactor: "ReactorBase") -> None:
        self.reactor = reactor
        self._runningQueries: Dict[
            Deferred[str], Tuple[Deferred[str], IDelayedCall]
        ] = {}

    def _fail(self, name: str, err: str) -> Failure:
        lookupError = error.DNSLookupError(f"address {name!r} not found: {err}")
        return Failure(lookupError)

    def _cleanup(self, name: str, lookupDeferred: Deferred[str]) -> None:
        userDeferred, cancelCall = self._runningQueries[lookupDeferred]
        del self._runningQueries[lookupDeferred]
        userDeferred.errback(self._fail(name, "timeout error"))

    def _checkTimeout(
        self, result: str, name: str, lookupDeferred: Deferred[str]
    ) -> None:
        try:
            userDeferred, cancelCall = self._runningQueries[lookupDeferred]
        except KeyError:
            pass
        else:
            del self._runningQueries[lookupDeferred]
            cancelCall.cancel()

            if isinstance(result, Failure):
                userDeferred.errback(self._fail(name, result.getErrorMessage()))
            else:
                userDeferred.callback(result)

    def getHostByName(
        self, name: str, timeout: Sequence[int] = (1, 3, 11, 45)
    ) -> Deferred[str]:
        """
        See L{twisted.internet.interfaces.IResolverSimple.getHostByName}.

        Note that the elements of C{timeout} are summed and the result is used
        as a timeout for the lookup.  Any intermediate timeout or retry logic
        is left up to the platform via L{socket.gethostbyname}.
        """
        if timeout:
            timeoutDelay = sum(timeout)
        else:
            timeoutDelay = 60
        userDeferred: Deferred[str] = Deferred()
        lookupDeferred = threads.deferToThreadPool(
            self.reactor,
            cast(IReactorThreads, self.reactor).getThreadPool(),
            socket.gethostbyname,
            name,
        )
        cancelCall = cast(IReactorTime, self.reactor).callLater(
            timeoutDelay, self._cleanup, name, lookupDeferred
        )
        self._runningQueries[lookupDeferred] = (userDeferred, cancelCall)
        lookupDeferred.addBoth(self._checkTimeout, name, lookupDeferred)
        return userDeferred


@implementer(IResolverSimple)
class BlockingResolver:
    def getHostByName(
        self, name: str, timeout: Sequence[int] = (1, 3, 11, 45)
    ) -> Deferred[str]:
        try:
            address = socket.gethostbyname(name)
        except OSError:
            msg = f"address {name!r} not found"
            err = error.DNSLookupError(msg)
            return defer.fail(err)
        else:
            return defer.succeed(address)


_ThreePhaseEventTriggerCallable = Callable[..., Any]
_ThreePhaseEventTrigger = Tuple[
    _ThreePhaseEventTriggerCallable, Tuple[object, ...], Dict[str, object]
]
_ThreePhaseEventTriggerHandle = NewType(
    "_ThreePhaseEventTriggerHandle",
    Tuple[str, _ThreePhaseEventTriggerCallable, Tuple[object, ...], Dict[str, object]],
)


class _ThreePhaseEvent:
    """
    Collection of callables (with arguments) which can be invoked as a group in
    a particular order.

    This provides the underlying implementation for the reactor's system event
    triggers.  An instance of this class tracks triggers for all phases of a
    single type of event.

    @ivar before: A list of the before-phase triggers containing three-tuples
        of a callable, a tuple of positional arguments, and a dict of keyword
        arguments

    @ivar finishedBefore: A list of the before-phase triggers which have
        already been executed.  This is only populated in the C{'BEFORE'} state.

    @ivar during: A list of the during-phase triggers containing three-tuples
        of a callable, a tuple of positional arguments, and a dict of keyword
        arguments

    @ivar after: A list of the after-phase triggers containing three-tuples
        of a callable, a tuple of positional arguments, and a dict of keyword
        arguments

    @ivar state: A string indicating what is currently going on with this
        object.  One of C{'BASE'} (for when nothing in particular is happening;
        this is the initial value), C{'BEFORE'} (when the before-phase triggers
        are in the process of being executed).
    """

    def __init__(self) -> None:
        self.before: List[_ThreePhaseEventTrigger] = []
        self.during: List[_ThreePhaseEventTrigger] = []
        self.after: List[_ThreePhaseEventTrigger] = []
        self.state = "BASE"

    def addTrigger(
        self,
        phase: str,
        callable: _ThreePhaseEventTriggerCallable,
        *args: object,
        **kwargs: object,
    ) -> _ThreePhaseEventTriggerHandle:
        """
        Add a trigger to the indicate phase.

        @param phase: One of C{'before'}, C{'during'}, or C{'after'}.

        @param callable: An object to be called when this event is triggered.
        @param args: Positional arguments to pass to C{callable}.
        @param kwargs: Keyword arguments to pass to C{callable}.

        @return: An opaque handle which may be passed to L{removeTrigger} to
            reverse the effects of calling this method.
        """
        if phase not in ("before", "during", "after"):
            raise KeyError("invalid phase")
        getattr(self, phase).append((callable, args, kwargs))
        return _ThreePhaseEventTriggerHandle((phase, callable, args, kwargs))

    def removeTrigger(self, handle: _ThreePhaseEventTriggerHandle) -> None:
        """
        Remove a previously added trigger callable.

        @param handle: An object previously returned by L{addTrigger}.  The
            trigger added by that call will be removed.

        @raise ValueError: If the trigger associated with C{handle} has already
            been removed or if C{handle} is not a valid handle.
        """
        getattr(self, "removeTrigger_" + self.state)(handle)

    def removeTrigger_BASE(self, handle: _ThreePhaseEventTriggerHandle) -> None:
        """
        Just try to remove the trigger.

        @see: removeTrigger
        """
        try:
            phase, callable, args, kwargs = handle
        except (TypeError, ValueError):
            raise ValueError("invalid trigger handle")
        else:
            if phase not in ("before", "during", "after"):
                raise KeyError("invalid phase")
            getattr(self, phase).remove((callable, args, kwargs))

    def removeTrigger_BEFORE(self, handle: _ThreePhaseEventTriggerHandle) -> None:
        """
        Remove the trigger if it has yet to be executed, otherwise emit a
        warning that in the future an exception will be raised when removing an
        already-executed trigger.

        @see: removeTrigger
        """
        phase, callable, args, kwargs = handle
        if phase != "before":
            return self.removeTrigger_BASE(handle)
        if (callable, args, kwargs) in self.finishedBefore:
            warnings.warn(
                "Removing already-fired system event triggers will raise an "
                "exception in a future version of Twisted.",
                category=DeprecationWarning,
                stacklevel=3,
            )
        else:
            self.removeTrigger_BASE(handle)

    def fireEvent(self) -> None:
        """
        Call the triggers added to this event.
        """
        self.state = "BEFORE"
        self.finishedBefore = []
        beforeResults: List[Deferred[object]] = []
        while self.before:
            callable, args, kwargs = self.before.pop(0)
            self.finishedBefore.append((callable, args, kwargs))
            try:
                result = callable(*args, **kwargs)
            except BaseException:
                log.err()
            else:
                if isinstance(result, Deferred):
                    beforeResults.append(result)
        DeferredList(beforeResults).addCallback(self._continueFiring)

    def _continueFiring(self, ignored: object) -> None:
        """
        Call the during and after phase triggers for this event.
        """
        self.state = "BASE"
        self.finishedBefore = []
        for phase in self.during, self.after:
            while phase:
                callable, args, kwargs = phase.pop(0)
                try:
                    callable(*args, **kwargs)
                except BaseException:
                    log.err()


@implementer(IReactorPluggableNameResolver, IReactorPluggableResolver)
class PluggableResolverMixin:
    """
    A mixin which implements the pluggable resolver reactor interfaces.

    @ivar resolver: The installed L{IResolverSimple}.
    @ivar _nameResolver: The installed L{IHostnameResolver}.
    """

    resolver: IResolverSimple = BlockingResolver()
    _nameResolver: IHostnameResolver = _SimpleResolverComplexifier(resolver)

    # IReactorPluggableResolver
    def installResolver(self, resolver: IResolverSimple) -> IResolverSimple:
        """
        See L{IReactorPluggableResolver}.

        @param resolver: see L{IReactorPluggableResolver}.

        @return: see L{IReactorPluggableResolver}.
        """
        assert IResolverSimple.providedBy(resolver)
        oldResolver = self.resolver
        self.resolver = resolver
        self._nameResolver = _SimpleResolverComplexifier(resolver)
        return oldResolver

    # IReactorPluggableNameResolver
    def installNameResolver(self, resolver: IHostnameResolver) -> IHostnameResolver:
        """
        See L{IReactorPluggableNameResolver}.

        @param resolver: See L{IReactorPluggableNameResolver}.

        @return: see L{IReactorPluggableNameResolver}.
        """
        previousNameResolver = self._nameResolver
        self._nameResolver = resolver
        self.resolver = _ComplexResolverSimplifier(resolver)
        return previousNameResolver

    @property
    def nameResolver(self) -> IHostnameResolver:
        """
        Implementation of read-only
        L{IReactorPluggableNameResolver.nameResolver}.
        """
        return self._nameResolver


_SystemEventID = NewType("_SystemEventID", Tuple[str, _ThreePhaseEventTriggerHandle])
_ThreadCall = Tuple[Callable[..., Any], Tuple[object, ...], Dict[str, object]]


@implementer(IReactorCore, IReactorTime, _ISupportsExitSignalCapturing)
class ReactorBase(PluggableResolverMixin):
    """
    Default base class for Reactors.

    @ivar _stopped: A flag which is true between paired calls to C{reactor.run}
        and C{reactor.stop}.  This should be replaced with an explicit state
        machine.
    @ivar _justStopped: A flag which is true between the time C{reactor.stop}
        is called and the time the shutdown system event is fired.  This is
        used to determine whether that event should be fired after each
        iteration through the mainloop.  This should be replaced with an
        explicit state machine.
    @ivar _started: A flag which is true from the time C{reactor.run} is called
        until the time C{reactor.run} returns.  This is used to prevent calls
        to C{reactor.run} on a running reactor.  This should be replaced with
        an explicit state machine.
    @ivar running: See L{IReactorCore.running}
    @ivar _registerAsIOThread: A flag controlling whether the reactor will
        register the thread it is running in as the I/O thread when it starts.
        If C{True}, registration will be done, otherwise it will not be.
    @ivar _exitSignal: See L{_ISupportsExitSignalCapturing._exitSignal}
    """

    _registerAsIOThread = True

    _stopped = True
    installed = False
    usingThreads = False
    _exitSignal = None

    __name__ = "twisted.internet.reactor"

    def __init__(self) -> None:
        super().__init__()
        self.threadCallQueue: List[_ThreadCall] = []
        self._eventTriggers: Dict[str, _ThreePhaseEvent] = {}
        self._pendingTimedCalls: List[DelayedCall] = []
        self._newTimedCalls: List[DelayedCall] = []
        self._cancellations = 0
        self.running = False
        self._started = False
        self._justStopped = False
        self._startedBefore = False
        # reactor internal readers, e.g. the waker.
        # Using Any as the type here… unable to find a suitable defined interface
        self._internalReaders: Set[Any] = set()
        self.waker: Any = None

        # Arrange for the running attribute to change to True at the right time
        # and let a subclass possibly do other things at that time (eg install
        # signal handlers).
        self.addSystemEventTrigger("during", "startup", self._reallyStartRunning)
        self.addSystemEventTrigger("during", "shutdown", self.crash)
        self.addSystemEventTrigger("during", "shutdown", self.disconnectAll)

        if platform.supportsThreads():
            self._initThreads()
        self.installWaker()

    # override in subclasses

    _lock = None

    def installWaker(self) -> None:
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement installWaker"
        )

    def wakeUp(self) -> None:
        """
        Wake up the event loop.
        """
        if self.waker:
            self.waker.wakeUp()
        # if the waker isn't installed, the reactor isn't running, and
        # therefore doesn't need to be woken up

    def doIteration(self, delay: Optional[float]) -> None:
        """
        Do one iteration over the readers and writers which have been added.
        """
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement doIteration"
        )

    def addReader(self, reader: IReadDescriptor) -> None:
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement addReader"
        )

    def addWriter(self, writer: IWriteDescriptor) -> None:
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement addWriter"
        )

    def removeReader(self, reader: IReadDescriptor) -> None:
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement removeReader"
        )

    def removeWriter(self, writer: IWriteDescriptor) -> None:
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement removeWriter"
        )

    def removeAll(self) -> List[Union[IReadDescriptor, IWriteDescriptor]]:
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement removeAll"
        )

    def getReaders(self) -> List[IReadDescriptor]:
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement getReaders"
        )

    def getWriters(self) -> List[IWriteDescriptor]:
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement getWriters"
        )

    # IReactorCore
    def resolve(
        self, name: str, timeout: Sequence[int] = (1, 3, 11, 45)
    ) -> Deferred[str]:
        """
        Return a Deferred that will resolve a hostname."""
        if not name:
            # XXX - This is *less than* '::', and will screw up IPv6 servers
            return defer.succeed("0.0.0.0")
        if abstract.isIPAddress(name):
            return defer.succeed(name)
        return self.resolver.getHostByName(name, timeout)

    def stop(self) -> None:
        """
        See twisted.internet.interfaces.IReactorCore.stop.
        """
        if self._stopped:
            raise error.ReactorNotRunning("Can't stop reactor that isn't running.")
        self._stopped = True
        self._justStopped = True
        self._startedBefore = True

    def crash(self) -> None:
        """
        See twisted.internet.interfaces.IReactorCore.crash.

        Reset reactor state tracking attributes and re-initialize certain
        state-transition helpers which were set up in C{__init__} but later
        destroyed (through use).
        """
        self._started = False
        self.running = False
        self.addSystemEventTrigger("during", "startup", self._reallyStartRunning)

    def sigInt(self, number: int, frame: Optional[FrameType] = None) -> None:
        """
        Handle a SIGINT interrupt.

        @param number: See handler specification in L{signal.signal}
        @param frame: See handler specification in L{signal.signal}
        """
        log.msg("Received SIGINT, shutting down.")
        self.callFromThread(self.stop)
        self._exitSignal = number

    def sigBreak(self, number: int, frame: Optional[FrameType] = None) -> None:
        """
        Handle a SIGBREAK interrupt.

        @param number: See handler specification in L{signal.signal}
        @param frame: See handler specification in L{signal.signal}
        """
        log.msg("Received SIGBREAK, shutting down.")
        self.callFromThread(self.stop)
        self._exitSignal = number

    def sigTerm(self, number: int, frame: Optional[FrameType] = None) -> None:
        """
        Handle a SIGTERM interrupt.

        @param number: See handler specification in L{signal.signal}
        @param frame: See handler specification in L{signal.signal}
        """
        log.msg("Received SIGTERM, shutting down.")
        self.callFromThread(self.stop)
        self._exitSignal = number

    def disconnectAll(self) -> None:
        """Disconnect every reader, and writer in the system."""
        selectables = self.removeAll()
        for reader in selectables:
            log.callWithLogger(
                reader, reader.connectionLost, Failure(main.CONNECTION_LOST)
            )

    def iterate(self, delay: float = 0.0) -> None:
        """
        See twisted.internet.interfaces.IReactorCore.iterate.
        """
        self.runUntilCurrent()
        self.doIteration(delay)

    def fireSystemEvent(self, eventType: str) -> None:
        """
        See twisted.internet.interfaces.IReactorCore.fireSystemEvent.
        """
        event = self._eventTriggers.get(eventType)
        if event is not None:
            event.fireEvent()

    def addSystemEventTrigger(
        self,
        phase: str,
        eventType: str,
        callable: Callable[..., Any],
        *args: object,
        **kwargs: object,
    ) -> _SystemEventID:
        """
        See twisted.internet.interfaces.IReactorCore.addSystemEventTrigger.
        """
        assert builtins.callable(callable), f"{callable} is not callable"
        if eventType not in self._eventTriggers:
            self._eventTriggers[eventType] = _ThreePhaseEvent()
        return _SystemEventID(
            (
                eventType,
                self._eventTriggers[eventType].addTrigger(
                    phase, callable, *args, **kwargs
                ),
            )
        )

    def removeSystemEventTrigger(self, triggerID: _SystemEventID) -> None:
        """
        See twisted.internet.interfaces.IReactorCore.removeSystemEventTrigger.
        """
        eventType, handle = triggerID
        self._eventTriggers[eventType].removeTrigger(handle)

    def callWhenRunning(
        self, callable: Callable[..., Any], *args: object, **kwargs: object
    ) -> Optional[_SystemEventID]:
        """
        See twisted.internet.interfaces.IReactorCore.callWhenRunning.
        """
        if self.running:
            callable(*args, **kwargs)
            return None
        else:
            return self.addSystemEventTrigger(
                "after", "startup", callable, *args, **kwargs
            )

    def startRunning(self) -> None:
        """
        Method called when reactor starts: do some initialization and fire
        startup events.

        Don't call this directly, call reactor.run() instead: it should take
        care of calling this.

        This method is somewhat misnamed.  The reactor will not necessarily be
        in the running state by the time this method returns.  The only
        guarantee is that it will be on its way to the running state.
        """
        if self._started:
            raise error.ReactorAlreadyRunning()
        if self._startedBefore:
            raise error.ReactorNotRestartable()
        self._started = True
        self._stopped = False
        if self._registerAsIOThread:
            threadable.registerAsIOThread()
        self.fireSystemEvent("startup")

    def _reallyStartRunning(self) -> None:
        """
        Method called to transition to the running state.  This should happen
        in the I{during startup} event trigger phase.
        """
        self.running = True

    def run(self) -> None:
        # IReactorCore.run
        raise NotImplementedError()

    # IReactorTime

    seconds = staticmethod(runtimeSeconds)

    def callLater(
        self, delay: float, callable: Callable[..., Any], *args: object, **kw: object
    ) -> DelayedCall:
        """
        See twisted.internet.interfaces.IReactorTime.callLater.
        """
        assert builtins.callable(callable), f"{callable} is not callable"
        assert delay >= 0, f"{delay} is not greater than or equal to 0 seconds"
        delayedCall = DelayedCall(
            self.seconds() + delay,
            callable,
            args,
            kw,
            self._cancelCallLater,
            self._moveCallLaterSooner,
            seconds=self.seconds,
        )
        self._newTimedCalls.append(delayedCall)
        return delayedCall

    def _moveCallLaterSooner(self, delayedCall: DelayedCall) -> None:
        # Linear time find: slow.
        heap = self._pendingTimedCalls
        try:
            pos = heap.index(delayedCall)

            # Move elt up the heap until it rests at the right place.
            elt = heap[pos]
            while pos != 0:
                parent = (pos - 1) // 2
                if heap[parent] <= elt:
                    break
                # move parent down
                heap[pos] = heap[parent]
                pos = parent
            heap[pos] = elt
        except ValueError:
            # element was not found in heap - oh well...
            pass

    def _cancelCallLater(self, delayedCall: DelayedCall) -> None:
        self._cancellations += 1

    def getDelayedCalls(self) -> Sequence[IDelayedCall]:
        """
        See L{twisted.internet.interfaces.IReactorTime.getDelayedCalls}
        """
        return [
            x
            for x in (self._pendingTimedCalls + self._newTimedCalls)
            if not x.cancelled
        ]

    def _insertNewDelayedCalls(self) -> None:
        for call in self._newTimedCalls:
            if call.cancelled:
                self._cancellations -= 1
            else:
                call.activate_delay()
                heappush(self._pendingTimedCalls, call)
        self._newTimedCalls = []

    def timeout(self) -> Optional[float]:
        """
        Determine the longest time the reactor may sleep (waiting on I/O
        notification, perhaps) before it must wake up to service a time-related
        event.

        @return: The maximum number of seconds the reactor may sleep.
        """
        # insert new delayed calls to make sure to include them in timeout value
        self._insertNewDelayedCalls()

        if not self._pendingTimedCalls:
            return None

        delay = self._pendingTimedCalls[0].time - self.seconds()

        # Pick a somewhat arbitrary maximum possible value for the timeout.
        # This value is 2 ** 31 / 1000, which is the number of seconds which can
        # be represented as an integer number of milliseconds in a signed 32 bit
        # integer.  This particular limit is imposed by the epoll_wait(3)
        # interface which accepts a timeout as a C "int" type and treats it as
        # representing a number of milliseconds.
        longest = 2147483

        # Don't let the delay be in the past (negative) or exceed a plausible
        # maximum (platform-imposed) interval.
        return max(0, min(longest, delay))

    def runUntilCurrent(self) -> None:
        """
        Run all pending timed calls.
        """
        if self.threadCallQueue:
            # Keep track of how many calls we actually make, as we're
            # making them, in case another call is added to the queue
            # while we're in this loop.
            count = 0
            total = len(self.threadCallQueue)
            for (f, a, kw) in self.threadCallQueue:
                try:
                    f(*a, **kw)
                except BaseException:
                    log.err()
                count += 1
                if count == total:
                    break
            del self.threadCallQueue[:count]
            if self.threadCallQueue:
                self.wakeUp()

        # insert new delayed calls now
        self._insertNewDelayedCalls()

        now = self.seconds()
        while self._pendingTimedCalls and (self._pendingTimedCalls[0].time <= now):
            call = heappop(self._pendingTimedCalls)
            if call.cancelled:
                self._cancellations -= 1
                continue

            if call.delayed_time > 0.0:
                call.activate_delay()
                heappush(self._pendingTimedCalls, call)
                continue

            try:
                call.called = 1
                call.func(*call.args, **call.kw)
            except BaseException:
                log.err()
                if call.creator is not None:
                    e = "\n"
                    e += (
                        " C: previous exception occurred in "
                        + "a DelayedCall created here:\n"
                    )
                    e += " C:"
                    e += "".join(call.creator).rstrip().replace("\n", "\n C:")
                    e += "\n"
                    log.msg(e)

        if (
            self._cancellations > 50
            and self._cancellations > len(self._pendingTimedCalls) >> 1
        ):
            self._cancellations = 0
            self._pendingTimedCalls = [
                x for x in self._pendingTimedCalls if not x.cancelled
            ]
            heapify(self._pendingTimedCalls)

        if self._justStopped:
            self._justStopped = False
            self.fireSystemEvent("shutdown")

    # IReactorThreads
    if platform.supportsThreads():
        assert ThreadPool is not None

        threadpool = None
        # ID of the trigger starting the threadpool
        _threadpoolStartupID = None
        # ID of the trigger stopping the threadpool
        threadpoolShutdownID = None

        def _initThreads(self) -> None:
            self.installNameResolver(_GAIResolver(self, self.getThreadPool))
            self.usingThreads = True

        # `IReactorFromThreads` defines the first named argument as
        # `callable: Callable[..., Any]` but this defines it as `f`
        # really both should be defined using py3.8 positional only
        def callFromThread(  # type: ignore[override]
            self, f: Callable[..., Any], *args: object, **kwargs: object
        ) -> None:
            """
            See
            L{twisted.internet.interfaces.IReactorFromThreads.callFromThread}.
            """
            assert callable(f), f"{f} is not callable"
            # lists are thread-safe in CPython, but not in Jython
            # this is probably a bug in Jython, but until fixed this code
            # won't work in Jython.
            self.threadCallQueue.append((f, args, kwargs))
            self.wakeUp()

        def _initThreadPool(self) -> None:
            """
            Create the threadpool accessible with callFromThread.
            """
            self.threadpool = ThreadPool(0, 10, "twisted.internet.reactor")
            self._threadpoolStartupID = self.callWhenRunning(self.threadpool.start)
            self.threadpoolShutdownID = self.addSystemEventTrigger(
                "during", "shutdown", self._stopThreadPool
            )

        def _uninstallHandler(self) -> None:
            pass

        def _stopThreadPool(self) -> None:
            """
            Stop the reactor threadpool.  This method is only valid if there
            is currently a threadpool (created by L{_initThreadPool}).  It
            is not intended to be called directly; instead, it will be
            called by a shutdown trigger created in L{_initThreadPool}.
            """
            triggers = [self._threadpoolStartupID, self.threadpoolShutdownID]
            for trigger in filter(None, triggers):
                try:
                    self.removeSystemEventTrigger(trigger)
                except ValueError:
                    pass
            self._threadpoolStartupID = None
            self.threadpoolShutdownID = None
            assert self.threadpool is not None
            self.threadpool.stop()
            self.threadpool = None

        def getThreadPool(self) -> ThreadPool:
            """
            See L{twisted.internet.interfaces.IReactorThreads.getThreadPool}.
            """
            if self.threadpool is None:
                self._initThreadPool()
                assert self.threadpool is not None
            return self.threadpool

        # `IReactorInThreads` defines the first named argument as
        # `callable: Callable[..., Any]` but this defines it as `_callable`
        # really both should be defined using py3.8 positional only
        def callInThread(  # type: ignore[override]
            self, _callable: Callable[..., Any], *args: object, **kwargs: object
        ) -> None:
            """
            See L{twisted.internet.interfaces.IReactorInThreads.callInThread}.
            """
            self.getThreadPool().callInThread(_callable, *args, **kwargs)

        def suggestThreadPoolSize(self, size: int) -> None:
            """
            See L{twisted.internet.interfaces.IReactorThreads.suggestThreadPoolSize}.
            """
            self.getThreadPool().adjustPoolsize(maxthreads=size)

    else:
        # This is for signal handlers.
        def callFromThread(
            self, f: Callable[..., Any], *args: object, **kwargs: object
        ) -> None:
            assert callable(f), f"{f} is not callable"
            # See comment in the other callFromThread implementation.
            self.threadCallQueue.append((f, args, kwargs))


if platform.supportsThreads():
    classImplements(ReactorBase, IReactorThreads)


@implementer(IConnector)
class BaseConnector(ABC):
    """
    Basic implementation of L{IConnector}.

    State can be: "connecting", "connected", "disconnected"
    """

    timeoutID = None
    factoryStarted = 0

    def __init__(
        self, factory: ClientFactory, timeout: float, reactor: ReactorBase
    ) -> None:
        self.state = "disconnected"
        self.reactor = reactor
        self.factory = factory
        self.timeout = timeout

    def disconnect(self) -> None:
        """Disconnect whatever our state is."""
        if self.state == "connecting":
            self.stopConnecting()
        elif self.state == "connected":
            assert self.transport is not None
            self.transport.loseConnection()

    @abstractmethod
    def _makeTransport(self) -> "Client":
        pass

    def connect(self) -> None:
        """Start connection to remote server."""
        if self.state != "disconnected":
            raise RuntimeError("can't connect in this state")

        self.state = "connecting"
        if not self.factoryStarted:
            self.factory.doStart()
            self.factoryStarted = 1
        self.transport: Optional[Client] = self._makeTransport()
        if self.timeout is not None:
            self.timeoutID = self.reactor.callLater(
                self.timeout, self.transport.failIfNotConnected, error.TimeoutError()
            )
        self.factory.startedConnecting(self)

    def stopConnecting(self) -> None:
        """Stop attempting to connect."""
        if self.state != "connecting":
            raise error.NotConnectingError("we're not trying to connect")

        assert self.transport is not None
        self.state = "disconnected"
        self.transport.failIfNotConnected(error.UserError())
        del self.transport

    def cancelTimeout(self) -> None:
        if self.timeoutID is not None:
            try:
                self.timeoutID.cancel()
            except ValueError:
                pass
            del self.timeoutID

    def buildProtocol(self, addr: IAddress) -> Optional[IProtocol]:
        self.state = "connected"
        self.cancelTimeout()
        return self.factory.buildProtocol(addr)

    def connectionFailed(self, reason: Failure) -> None:
        self.cancelTimeout()
        self.transport = None
        self.state = "disconnected"
        self.factory.clientConnectionFailed(self, reason)
        if self.state == "disconnected":
            # factory hasn't called our connect() method
            self.factory.doStop()
            self.factoryStarted = 0

    def connectionLost(self, reason: Failure) -> None:
        self.state = "disconnected"
        self.factory.clientConnectionLost(self, reason)
        if self.state == "disconnected":
            # factory hasn't called our connect() method
            self.factory.doStop()
            self.factoryStarted = 0

    def getDestination(self) -> IAddress:
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement " "getDestination"
        )

    def __repr__(self) -> str:
        return "<{} instance at 0x{:x} {} {}>".format(
            reflect.qual(self.__class__),
            id(self),
            self.state,
            self.getDestination(),
        )


class BasePort(abstract.FileDescriptor):
    """Basic implementation of a ListeningPort.

    Note: This does not actually implement IListeningPort.
    """

    addressFamily: socket.AddressFamily = None  # type: ignore[assignment]
    socketType: socket.SocketKind = None  # type: ignore[assignment]

    def createInternetSocket(self) -> socket.socket:
        s = socket.socket(self.addressFamily, self.socketType)
        s.setblocking(False)
        fdesc._setCloseOnExec(s.fileno())
        return s

    def doWrite(self) -> Optional[Failure]:
        """Raises a RuntimeError"""
        raise RuntimeError("doWrite called on a %s" % reflect.qual(self.__class__))


class _SignalReactorMixin:
    """
    Private mixin to manage signals: it installs signal handlers at start time,
    and define run method.

    It can only be used mixed in with L{ReactorBase}, and has to be defined
    first in the inheritance (so that method resolution order finds
    startRunning first).

    @ivar _installSignalHandlers: A flag which indicates whether any signal
        handlers will be installed during startup.  This includes handlers for
        SIGCHLD to monitor child processes, and SIGINT, SIGTERM, and SIGBREAK
        to stop the reactor.
    """

    _installSignalHandlers = False

    def _handleSignals(self) -> None:
        """
        Install the signal handlers for the Twisted event loop.
        """
        try:
            import signal
        except ImportError:
            log.msg(
                "Warning: signal module unavailable -- "
                "not installing signal handlers."
            )
            return

        reactorBaseSelf = cast(ReactorBase, self)

        if signal.getsignal(signal.SIGINT) == signal.default_int_handler:
            # only handle if there isn't already a handler, e.g. for Pdb.
            signal.signal(signal.SIGINT, reactorBaseSelf.sigInt)
        signal.signal(signal.SIGTERM, reactorBaseSelf.sigTerm)

        # Catch Ctrl-Break in windows
        SIGBREAK = getattr(signal, "SIGBREAK", None)
        if SIGBREAK is not None:
            signal.signal(SIGBREAK, reactorBaseSelf.sigBreak)

    def startRunning(self, installSignalHandlers: bool = True) -> None:
        """
        Extend the base implementation in order to remember whether signal
        handlers should be installed later.

        @param installSignalHandlers: A flag which, if set, indicates that
            handlers for a number of (implementation-defined) signals should be
            installed during startup.
        """
        self._installSignalHandlers = installSignalHandlers
        ReactorBase.startRunning(cast(ReactorBase, self))

    def _reallyStartRunning(self) -> None:
        """
        Extend the base implementation by also installing signal handlers, if
        C{self._installSignalHandlers} is true.
        """
        ReactorBase._reallyStartRunning(cast(ReactorBase, self))
        if self._installSignalHandlers:
            # Make sure this happens before after-startup events, since the
            # expectation of after-startup is that the reactor is fully
            # initialized.  Don't do it right away for historical reasons
            # (perhaps some before-startup triggers don't want there to be a
            # custom SIGCHLD handler so that they can run child processes with
            # some blocking api).
            self._handleSignals()

    def run(self, installSignalHandlers: bool = True) -> None:
        self.startRunning(installSignalHandlers=installSignalHandlers)
        self.mainLoop()

    def mainLoop(self) -> None:
        reactorBaseSelf = cast(ReactorBase, self)

        while reactorBaseSelf._started:
            try:
                while reactorBaseSelf._started:
                    # Advance simulation time in delayed event
                    # processors.
                    reactorBaseSelf.runUntilCurrent()
                    t2 = reactorBaseSelf.timeout()
                    t = reactorBaseSelf.running and t2
                    reactorBaseSelf.doIteration(t)
            except BaseException:
                log.msg("Unexpected error in main loop.")
                log.err()
            else:
                log.msg("Main loop terminated.")  # type:ignore[unreachable]


__all__: List[str] = []
