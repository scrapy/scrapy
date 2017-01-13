# -*- test-case-name: twisted.test.test_internet,twisted.internet.test.test_core -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Very basic functionality for a Reactor implementation.
"""

from __future__ import division, absolute_import

import socket # needed only for sync-dns
from zope.interface import implementer, classImplements

import sys
import warnings
from heapq import heappush, heappop, heapify

import traceback

from twisted.internet.interfaces import IReactorCore, IReactorTime, IReactorThreads
from twisted.internet.interfaces import IResolverSimple, IReactorPluggableResolver
from twisted.internet.interfaces import IConnector, IDelayedCall
from twisted.internet import fdesc, main, error, abstract, defer, threads
from twisted.python import log, failure, reflect
from twisted.python.compat import unicode, iteritems
from twisted.python.runtime import seconds as runtimeSeconds, platform
from twisted.internet.defer import Deferred, DeferredList

# This import is for side-effects!  Even if you don't see any code using it
# in this module, don't delete it.
from twisted.python import threadable


@implementer(IDelayedCall)
class DelayedCall:

    # enable .debug to record creator call stack, and it will be logged if
    # an exception occurs while the function is being run
    debug = False
    _str = None

    def __init__(self, time, func, args, kw, cancel, reset,
                 seconds=runtimeSeconds):
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
        self.delayed_time = 0
        if self.debug:
            self.creator = traceback.format_stack()[:-2]

    def getTime(self):
        """Return the time at which this call will fire

        @rtype: C{float}
        @return: The number of seconds after the epoch at which this call is
        scheduled to be made.
        """
        return self.time + self.delayed_time

    def cancel(self):
        """Unschedule this call

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
                self._str = bytes(self)
            del self.func, self.args, self.kw

    def reset(self, secondsFromNow):
        """Reschedule this call for a different time

        @type secondsFromNow: C{float}
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
                self.delayed_time = 0
                self.time = newTime
                self.resetter(self)
            else:
                self.delayed_time = newTime - self.time

    def delay(self, secondsLater):
        """Reschedule this call for a later time

        @type secondsLater: C{float}
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
            if self.delayed_time < 0:
                self.activate_delay()
                self.resetter(self)

    def activate_delay(self):
        self.time += self.delayed_time
        self.delayed_time = 0

    def active(self):
        """Determine whether this call is still pending

        @rtype: C{bool}
        @return: True if this call has not yet been made or cancelled,
        False otherwise.
        """
        return not (self.cancelled or self.called)


    def __le__(self, other):
        """
        Implement C{<=} operator between two L{DelayedCall} instances.

        Comparison is based on the C{time} attribute (unadjusted by the
        delayed time).
        """
        return self.time <= other.time


    def __lt__(self, other):
        """
        Implement C{<} operator between two L{DelayedCall} instances.

        Comparison is based on the C{time} attribute (unadjusted by the
        delayed time).
        """
        return self.time < other.time


    def __str__(self):
        if self._str is not None:
            return self._str
        if hasattr(self, 'func'):
            # This code should be replaced by a utility function in reflect;
            # see ticket #6066:
            if hasattr(self.func, '__qualname__'):
                func = self.func.__qualname__
            elif hasattr(self.func, '__name__'):
                func = self.func.func_name
                if hasattr(self.func, 'im_class'):
                    func = self.func.im_class.__name__ + '.' + func
            else:
                func = reflect.safe_repr(self.func)
        else:
            func = None

        now = self.seconds()
        L = ["<DelayedCall 0x%x [%ss] called=%s cancelled=%s" % (
                id(self), self.time - now, self.called,
                self.cancelled)]
        if func is not None:
            L.extend((" ", func, "("))
            if self.args:
                L.append(", ".join([reflect.safe_repr(e) for e in self.args]))
                if self.kw:
                    L.append(", ")
            if self.kw:
                L.append(", ".join(['%s=%s' % (k, reflect.safe_repr(v)) for (k, v) in self.kw.items()]))
            L.append(")")

        if self.debug:
            L.append("\n\ntraceback at creation: \n\n%s" % ('    '.join(self.creator)))
        L.append('>')

        return "".join(L)



@implementer(IResolverSimple)
class ThreadedResolver(object):
    """
    L{ThreadedResolver} uses a reactor, a threadpool, and
    L{socket.gethostbyname} to perform name lookups without blocking the
    reactor thread.  It also supports timeouts indepedently from whatever
    timeout logic L{socket.gethostbyname} might have.

    @ivar reactor: The reactor the threadpool of which will be used to call
        L{socket.gethostbyname} and the I/O thread of which the result will be
        delivered.
    """

    def __init__(self, reactor):
        self.reactor = reactor
        self._runningQueries = {}


    def _fail(self, name, err):
        err = error.DNSLookupError("address %r not found: %s" % (name, err))
        return failure.Failure(err)


    def _cleanup(self, name, lookupDeferred):
        userDeferred, cancelCall = self._runningQueries[lookupDeferred]
        del self._runningQueries[lookupDeferred]
        userDeferred.errback(self._fail(name, "timeout error"))


    def _checkTimeout(self, result, name, lookupDeferred):
        try:
            userDeferred, cancelCall = self._runningQueries[lookupDeferred]
        except KeyError:
            pass
        else:
            del self._runningQueries[lookupDeferred]
            cancelCall.cancel()

            if isinstance(result, failure.Failure):
                userDeferred.errback(self._fail(name, result.getErrorMessage()))
            else:
                userDeferred.callback(result)


    def getHostByName(self, name, timeout = (1, 3, 11, 45)):
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
        userDeferred = defer.Deferred()
        lookupDeferred = threads.deferToThreadPool(
            self.reactor, self.reactor.getThreadPool(),
            socket.gethostbyname, name)
        cancelCall = self.reactor.callLater(
            timeoutDelay, self._cleanup, name, lookupDeferred)
        self._runningQueries[lookupDeferred] = (userDeferred, cancelCall)
        lookupDeferred.addBoth(self._checkTimeout, name, lookupDeferred)
        return userDeferred



@implementer(IResolverSimple)
class BlockingResolver:

    def getHostByName(self, name, timeout = (1, 3, 11, 45)):
        try:
            address = socket.gethostbyname(name)
        except socket.error:
            msg = "address %r not found" % (name,)
            err = error.DNSLookupError(msg)
            return defer.fail(err)
        else:
            return defer.succeed(address)


class _ThreePhaseEvent(object):
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
    def __init__(self):
        self.before = []
        self.during = []
        self.after = []
        self.state = 'BASE'


    def addTrigger(self, phase, callable, *args, **kwargs):
        """
        Add a trigger to the indicate phase.

        @param phase: One of C{'before'}, C{'during'}, or C{'after'}.

        @param callable: An object to be called when this event is triggered.
        @param *args: Positional arguments to pass to C{callable}.
        @param **kwargs: Keyword arguments to pass to C{callable}.

        @return: An opaque handle which may be passed to L{removeTrigger} to
            reverse the effects of calling this method.
        """
        if phase not in ('before', 'during', 'after'):
            raise KeyError("invalid phase")
        getattr(self, phase).append((callable, args, kwargs))
        return phase, callable, args, kwargs


    def removeTrigger(self, handle):
        """
        Remove a previously added trigger callable.

        @param handle: An object previously returned by L{addTrigger}.  The
            trigger added by that call will be removed.

        @raise ValueError: If the trigger associated with C{handle} has already
            been removed or if C{handle} is not a valid handle.
        """
        return getattr(self, 'removeTrigger_' + self.state)(handle)


    def removeTrigger_BASE(self, handle):
        """
        Just try to remove the trigger.

        @see: removeTrigger
        """
        try:
            phase, callable, args, kwargs = handle
        except (TypeError, ValueError):
            raise ValueError("invalid trigger handle")
        else:
            if phase not in ('before', 'during', 'after'):
                raise KeyError("invalid phase")
            getattr(self, phase).remove((callable, args, kwargs))


    def removeTrigger_BEFORE(self, handle):
        """
        Remove the trigger if it has yet to be executed, otherwise emit a
        warning that in the future an exception will be raised when removing an
        already-executed trigger.

        @see: removeTrigger
        """
        phase, callable, args, kwargs = handle
        if phase != 'before':
            return self.removeTrigger_BASE(handle)
        if (callable, args, kwargs) in self.finishedBefore:
            warnings.warn(
                "Removing already-fired system event triggers will raise an "
                "exception in a future version of Twisted.",
                category=DeprecationWarning,
                stacklevel=3)
        else:
            self.removeTrigger_BASE(handle)


    def fireEvent(self):
        """
        Call the triggers added to this event.
        """
        self.state = 'BEFORE'
        self.finishedBefore = []
        beforeResults = []
        while self.before:
            callable, args, kwargs = self.before.pop(0)
            self.finishedBefore.append((callable, args, kwargs))
            try:
                result = callable(*args, **kwargs)
            except:
                log.err()
            else:
                if isinstance(result, Deferred):
                    beforeResults.append(result)
        DeferredList(beforeResults).addCallback(self._continueFiring)


    def _continueFiring(self, ignored):
        """
        Call the during and after phase triggers for this event.
        """
        self.state = 'BASE'
        self.finishedBefore = []
        for phase in self.during, self.after:
            while phase:
                callable, args, kwargs = phase.pop(0)
                try:
                    callable(*args, **kwargs)
                except:
                    log.err()



@implementer(IReactorCore, IReactorTime, IReactorPluggableResolver)
class ReactorBase(object):
    """
    Default base class for Reactors.

    @type _stopped: C{bool}
    @ivar _stopped: A flag which is true between paired calls to C{reactor.run}
        and C{reactor.stop}.  This should be replaced with an explicit state
        machine.

    @type _justStopped: C{bool}
    @ivar _justStopped: A flag which is true between the time C{reactor.stop}
        is called and the time the shutdown system event is fired.  This is
        used to determine whether that event should be fired after each
        iteration through the mainloop.  This should be replaced with an
        explicit state machine.

    @type _started: C{bool}
    @ivar _started: A flag which is true from the time C{reactor.run} is called
        until the time C{reactor.run} returns.  This is used to prevent calls
        to C{reactor.run} on a running reactor.  This should be replaced with
        an explicit state machine.

    @ivar running: See L{IReactorCore.running}

    @ivar _registerAsIOThread: A flag controlling whether the reactor will
        register the thread it is running in as the I/O thread when it starts.
        If C{True}, registration will be done, otherwise it will not be.
    """

    _registerAsIOThread = True

    _stopped = True
    installed = False
    usingThreads = False
    resolver = BlockingResolver()

    __name__ = "twisted.internet.reactor"

    def __init__(self):
        self.threadCallQueue = []
        self._eventTriggers = {}
        self._pendingTimedCalls = []
        self._newTimedCalls = []
        self._cancellations = 0
        self.running = False
        self._started = False
        self._justStopped = False
        self._startedBefore = False
        # reactor internal readers, e.g. the waker.
        self._internalReaders = set()
        self.waker = None

        # Arrange for the running attribute to change to True at the right time
        # and let a subclass possibly do other things at that time (eg install
        # signal handlers).
        self.addSystemEventTrigger(
            'during', 'startup', self._reallyStartRunning)
        self.addSystemEventTrigger('during', 'shutdown', self.crash)
        self.addSystemEventTrigger('during', 'shutdown', self.disconnectAll)

        if platform.supportsThreads():
            self._initThreads()
        self.installWaker()

    # override in subclasses

    _lock = None

    def installWaker(self):
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement installWaker")

    def installResolver(self, resolver):
        assert IResolverSimple.providedBy(resolver)
        oldResolver = self.resolver
        self.resolver = resolver
        return oldResolver

    def wakeUp(self):
        """
        Wake up the event loop.
        """
        if self.waker:
            self.waker.wakeUp()
        # if the waker isn't installed, the reactor isn't running, and
        # therefore doesn't need to be woken up

    def doIteration(self, delay):
        """
        Do one iteration over the readers and writers which have been added.
        """
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement doIteration")

    def addReader(self, reader):
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement addReader")

    def addWriter(self, writer):
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement addWriter")

    def removeReader(self, reader):
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement removeReader")

    def removeWriter(self, writer):
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement removeWriter")

    def removeAll(self):
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement removeAll")


    def getReaders(self):
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement getReaders")


    def getWriters(self):
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement getWriters")


    def resolve(self, name, timeout = (1, 3, 11, 45)):
        """Return a Deferred that will resolve a hostname.
        """
        if not name:
            # XXX - This is *less than* '::', and will screw up IPv6 servers
            return defer.succeed('0.0.0.0')
        if abstract.isIPAddress(name):
            return defer.succeed(name)
        return self.resolver.getHostByName(name, timeout)

    # Installation.

    # IReactorCore
    def stop(self):
        """
        See twisted.internet.interfaces.IReactorCore.stop.
        """
        if self._stopped:
            raise error.ReactorNotRunning(
                "Can't stop reactor that isn't running.")
        self._stopped = True
        self._justStopped = True
        self._startedBefore = True


    def crash(self):
        """
        See twisted.internet.interfaces.IReactorCore.crash.

        Reset reactor state tracking attributes and re-initialize certain
        state-transition helpers which were set up in C{__init__} but later
        destroyed (through use).
        """
        self._started = False
        self.running = False
        self.addSystemEventTrigger(
            'during', 'startup', self._reallyStartRunning)

    def sigInt(self, *args):
        """Handle a SIGINT interrupt.
        """
        log.msg("Received SIGINT, shutting down.")
        self.callFromThread(self.stop)

    def sigBreak(self, *args):
        """Handle a SIGBREAK interrupt.
        """
        log.msg("Received SIGBREAK, shutting down.")
        self.callFromThread(self.stop)

    def sigTerm(self, *args):
        """Handle a SIGTERM interrupt.
        """
        log.msg("Received SIGTERM, shutting down.")
        self.callFromThread(self.stop)

    def disconnectAll(self):
        """Disconnect every reader, and writer in the system.
        """
        selectables = self.removeAll()
        for reader in selectables:
            log.callWithLogger(reader,
                               reader.connectionLost,
                               failure.Failure(main.CONNECTION_LOST))


    def iterate(self, delay=0):
        """See twisted.internet.interfaces.IReactorCore.iterate.
        """
        self.runUntilCurrent()
        self.doIteration(delay)


    def fireSystemEvent(self, eventType):
        """See twisted.internet.interfaces.IReactorCore.fireSystemEvent.
        """
        event = self._eventTriggers.get(eventType)
        if event is not None:
            event.fireEvent()


    def addSystemEventTrigger(self, _phase, _eventType, _f, *args, **kw):
        """See twisted.internet.interfaces.IReactorCore.addSystemEventTrigger.
        """
        assert callable(_f), "%s is not callable" % _f
        if _eventType not in self._eventTriggers:
            self._eventTriggers[_eventType] = _ThreePhaseEvent()
        return (_eventType, self._eventTriggers[_eventType].addTrigger(
            _phase, _f, *args, **kw))


    def removeSystemEventTrigger(self, triggerID):
        """See twisted.internet.interfaces.IReactorCore.removeSystemEventTrigger.
        """
        eventType, handle = triggerID
        self._eventTriggers[eventType].removeTrigger(handle)


    def callWhenRunning(self, _callable, *args, **kw):
        """See twisted.internet.interfaces.IReactorCore.callWhenRunning.
        """
        if self.running:
            _callable(*args, **kw)
        else:
            return self.addSystemEventTrigger('after', 'startup',
                                              _callable, *args, **kw)

    def startRunning(self):
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
        self.fireSystemEvent('startup')


    def _reallyStartRunning(self):
        """
        Method called to transition to the running state.  This should happen
        in the I{during startup} event trigger phase.
        """
        self.running = True

    # IReactorTime

    seconds = staticmethod(runtimeSeconds)

    def callLater(self, _seconds, _f, *args, **kw):
        """See twisted.internet.interfaces.IReactorTime.callLater.
        """
        assert callable(_f), "%s is not callable" % _f
        assert _seconds >= 0, \
               "%s is not greater than or equal to 0 seconds" % (_seconds,)
        tple = DelayedCall(self.seconds() + _seconds, _f, args, kw,
                           self._cancelCallLater,
                           self._moveCallLaterSooner,
                           seconds=self.seconds)
        self._newTimedCalls.append(tple)
        return tple

    def _moveCallLaterSooner(self, tple):
        # Linear time find: slow.
        heap = self._pendingTimedCalls
        try:
            pos = heap.index(tple)

            # Move elt up the heap until it rests at the right place.
            elt = heap[pos]
            while pos != 0:
                parent = (pos-1) // 2
                if heap[parent] <= elt:
                    break
                # move parent down
                heap[pos] = heap[parent]
                pos = parent
            heap[pos] = elt
        except ValueError:
            # element was not found in heap - oh well...
            pass

    def _cancelCallLater(self, tple):
        self._cancellations+=1


    def getDelayedCalls(self):
        """Return all the outstanding delayed calls in the system.
        They are returned in no particular order.
        This method is not efficient -- it is really only meant for
        test cases."""
        return [x for x in (self._pendingTimedCalls + self._newTimedCalls) if not x.cancelled]

    def _insertNewDelayedCalls(self):
        for call in self._newTimedCalls:
            if call.cancelled:
                self._cancellations-=1
            else:
                call.activate_delay()
                heappush(self._pendingTimedCalls, call)
        self._newTimedCalls = []


    def timeout(self):
        """
        Determine the longest time the reactor may sleep (waiting on I/O
        notification, perhaps) before it must wake up to service a time-related
        event.

        @return: The maximum number of seconds the reactor may sleep.
        @rtype: L{float}
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


    def runUntilCurrent(self):
        """Run all pending timed calls.
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
                except:
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
                self._cancellations-=1
                continue

            if call.delayed_time > 0:
                call.activate_delay()
                heappush(self._pendingTimedCalls, call)
                continue

            try:
                call.called = 1
                call.func(*call.args, **call.kw)
            except:
                log.deferr()
                if hasattr(call, "creator"):
                    e = "\n"
                    e += " C: previous exception occurred in " + \
                         "a DelayedCall created here:\n"
                    e += " C:"
                    e += "".join(call.creator).rstrip().replace("\n","\n C:")
                    e += "\n"
                    log.msg(e)


        if (self._cancellations > 50 and
             self._cancellations > len(self._pendingTimedCalls) >> 1):
            self._cancellations = 0
            self._pendingTimedCalls = [x for x in self._pendingTimedCalls
                                       if not x.cancelled]
            heapify(self._pendingTimedCalls)

        if self._justStopped:
            self._justStopped = False
            self.fireSystemEvent("shutdown")

    # IReactorProcess

    def _checkProcessArgs(self, args, env):
        """
        Check for valid arguments and environment to spawnProcess.

        @return: A two element tuple giving values to use when creating the
        process.  The first element of the tuple is a C{list} of C{str}
        giving the values for argv of the child process.  The second element
        of the tuple is either L{None} if C{env} was L{None} or a C{dict}
        mapping C{str} environment keys to C{str} environment values.
        """
        # Any unicode string which Python would successfully implicitly
        # encode to a byte string would have worked before these explicit
        # checks were added.  Anything which would have failed with a
        # UnicodeEncodeError during that implicit encoding step would have
        # raised an exception in the child process and that would have been
        # a pain in the butt to debug.
        #
        # So, we will explicitly attempt the same encoding which Python
        # would implicitly do later.  If it fails, we will report an error
        # without ever spawning a child process.  If it succeeds, we'll save
        # the result so that Python doesn't need to do it implicitly later.
        #
        # For any unicode which we can actually encode, we'll also issue a
        # deprecation warning, because no one should be passing unicode here
        # anyway.
        #
        # -exarkun
        defaultEncoding = sys.getdefaultencoding()

        # Common check function
        def argChecker(arg):
            """
            Return either a str or None.  If the given value is not
            allowable for some reason, None is returned.  Otherwise, a
            possibly different object which should be used in place of arg
            is returned.  This forces unicode encoding to happen now, rather
            than implicitly later.
            """
            if isinstance(arg, unicode):
                try:
                    arg = arg.encode(defaultEncoding)
                except UnicodeEncodeError:
                    return None
                warnings.warn(
                    "Argument strings and environment keys/values passed to "
                    "reactor.spawnProcess should be str, not unicode.",
                    category=DeprecationWarning,
                    stacklevel=4)
            if isinstance(arg, bytes) and b'\0' not in arg:
                return arg

            return None

        # Make a few tests to check input validity
        if not isinstance(args, (tuple, list)):
            raise TypeError("Arguments must be a tuple or list")

        outputArgs = []
        for arg in args:
            arg = argChecker(arg)
            if arg is None:
                raise TypeError("Arguments contain a non-string value")
            else:
                outputArgs.append(arg)

        outputEnv = None
        if env is not None:
            outputEnv = {}
            for key, val in iteritems(env):
                key = argChecker(key)
                if key is None:
                    raise TypeError("Environment contains a non-string key")
                val = argChecker(val)
                if val is None:
                    raise TypeError("Environment contains a non-string value")
                outputEnv[key] = val
        return outputArgs, outputEnv

    # IReactorThreads
    if platform.supportsThreads():
        threadpool = None
        # ID of the trigger starting the threadpool
        _threadpoolStartupID = None
        # ID of the trigger stopping the threadpool
        threadpoolShutdownID = None

        def _initThreads(self):
            self.usingThreads = True
            self.resolver = ThreadedResolver(self)

        def callFromThread(self, f, *args, **kw):
            """
            See
            L{twisted.internet.interfaces.IReactorFromThreads.callFromThread}.
            """
            assert callable(f), "%s is not callable" % (f,)
            # lists are thread-safe in CPython, but not in Jython
            # this is probably a bug in Jython, but until fixed this code
            # won't work in Jython.
            self.threadCallQueue.append((f, args, kw))
            self.wakeUp()

        def _initThreadPool(self):
            """
            Create the threadpool accessible with callFromThread.
            """
            from twisted.python import threadpool
            self.threadpool = threadpool.ThreadPool(
                0, 10, 'twisted.internet.reactor')
            self._threadpoolStartupID = self.callWhenRunning(
                self.threadpool.start)
            self.threadpoolShutdownID = self.addSystemEventTrigger(
                'during', 'shutdown', self._stopThreadPool)

        def _uninstallHandler(self):
            pass

        def _stopThreadPool(self):
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
            self.threadpool.stop()
            self.threadpool = None


        def getThreadPool(self):
            """
            See L{twisted.internet.interfaces.IReactorThreads.getThreadPool}.
            """
            if self.threadpool is None:
                self._initThreadPool()
            return self.threadpool


        def callInThread(self, _callable, *args, **kwargs):
            """
            See L{twisted.internet.interfaces.IReactorInThreads.callInThread}.
            """
            self.getThreadPool().callInThread(_callable, *args, **kwargs)

        def suggestThreadPoolSize(self, size):
            """
            See L{twisted.internet.interfaces.IReactorThreads.suggestThreadPoolSize}.
            """
            self.getThreadPool().adjustPoolsize(maxthreads=size)
    else:
        # This is for signal handlers.
        def callFromThread(self, f, *args, **kw):
            assert callable(f), "%s is not callable" % (f,)
            # See comment in the other callFromThread implementation.
            self.threadCallQueue.append((f, args, kw))

if platform.supportsThreads():
    classImplements(ReactorBase, IReactorThreads)


@implementer(IConnector)
class BaseConnector:
    """Basic implementation of connector.

    State can be: "connecting", "connected", "disconnected"
    """
    timeoutID = None
    factoryStarted = 0

    def __init__(self, factory, timeout, reactor):
        self.state = "disconnected"
        self.reactor = reactor
        self.factory = factory
        self.timeout = timeout

    def disconnect(self):
        """Disconnect whatever our state is."""
        if self.state == 'connecting':
            self.stopConnecting()
        elif self.state == 'connected':
            self.transport.loseConnection()

    def connect(self):
        """Start connection to remote server."""
        if self.state != "disconnected":
            raise RuntimeError("can't connect in this state")

        self.state = "connecting"
        if not self.factoryStarted:
            self.factory.doStart()
            self.factoryStarted = 1
        self.transport = transport = self._makeTransport()
        if self.timeout is not None:
            self.timeoutID = self.reactor.callLater(self.timeout, transport.failIfNotConnected, error.TimeoutError())
        self.factory.startedConnecting(self)

    def stopConnecting(self):
        """Stop attempting to connect."""
        if self.state != "connecting":
            raise error.NotConnectingError("we're not trying to connect")

        self.state = "disconnected"
        self.transport.failIfNotConnected(error.UserError())
        del self.transport

    def cancelTimeout(self):
        if self.timeoutID is not None:
            try:
                self.timeoutID.cancel()
            except ValueError:
                pass
            del self.timeoutID

    def buildProtocol(self, addr):
        self.state = "connected"
        self.cancelTimeout()
        return self.factory.buildProtocol(addr)

    def connectionFailed(self, reason):
        self.cancelTimeout()
        self.transport = None
        self.state = "disconnected"
        self.factory.clientConnectionFailed(self, reason)
        if self.state == "disconnected":
            # factory hasn't called our connect() method
            self.factory.doStop()
            self.factoryStarted = 0

    def connectionLost(self, reason):
        self.state = "disconnected"
        self.factory.clientConnectionLost(self, reason)
        if self.state == "disconnected":
            # factory hasn't called our connect() method
            self.factory.doStop()
            self.factoryStarted = 0

    def getDestination(self):
        raise NotImplementedError(
            reflect.qual(self.__class__) + " did not implement "
            "getDestination")



class BasePort(abstract.FileDescriptor):
    """Basic implementation of a ListeningPort.

    Note: This does not actually implement IListeningPort.
    """

    addressFamily = None
    socketType = None

    def createInternetSocket(self):
        s = socket.socket(self.addressFamily, self.socketType)
        s.setblocking(0)
        fdesc._setCloseOnExec(s.fileno())
        return s


    def doWrite(self):
        """Raises a RuntimeError"""
        raise RuntimeError(
            "doWrite called on a %s" % reflect.qual(self.__class__))



class _SignalReactorMixin(object):
    """
    Private mixin to manage signals: it installs signal handlers at start time,
    and define run method.

    It can only be used mixed in with L{ReactorBase}, and has to be defined
    first in the inheritance (so that method resolution order finds
    startRunning first).

    @type _installSignalHandlers: C{bool}
    @ivar _installSignalHandlers: A flag which indicates whether any signal
        handlers will be installed during startup.  This includes handlers for
        SIGCHLD to monitor child processes, and SIGINT, SIGTERM, and SIGBREAK
        to stop the reactor.
    """

    _installSignalHandlers = False

    def _handleSignals(self):
        """
        Install the signal handlers for the Twisted event loop.
        """
        try:
            import signal
        except ImportError:
            log.msg("Warning: signal module unavailable -- "
                    "not installing signal handlers.")
            return

        if signal.getsignal(signal.SIGINT) == signal.default_int_handler:
            # only handle if there isn't already a handler, e.g. for Pdb.
            signal.signal(signal.SIGINT, self.sigInt)
        signal.signal(signal.SIGTERM, self.sigTerm)

        # Catch Ctrl-Break in windows
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, self.sigBreak)


    def startRunning(self, installSignalHandlers=True):
        """
        Extend the base implementation in order to remember whether signal
        handlers should be installed later.

        @type installSignalHandlers: C{bool}
        @param installSignalHandlers: A flag which, if set, indicates that
            handlers for a number of (implementation-defined) signals should be
            installed during startup.
        """
        self._installSignalHandlers = installSignalHandlers
        ReactorBase.startRunning(self)


    def _reallyStartRunning(self):
        """
        Extend the base implementation by also installing signal handlers, if
        C{self._installSignalHandlers} is true.
        """
        ReactorBase._reallyStartRunning(self)
        if self._installSignalHandlers:
            # Make sure this happens before after-startup events, since the
            # expectation of after-startup is that the reactor is fully
            # initialized.  Don't do it right away for historical reasons
            # (perhaps some before-startup triggers don't want there to be a
            # custom SIGCHLD handler so that they can run child processes with
            # some blocking api).
            self._handleSignals()


    def run(self, installSignalHandlers=True):
        self.startRunning(installSignalHandlers=installSignalHandlers)
        self.mainLoop()


    def mainLoop(self):
        while self._started:
            try:
                while self._started:
                    # Advance simulation time in delayed event
                    # processors.
                    self.runUntilCurrent()
                    t2 = self.timeout()
                    t = self.running and t2
                    self.doIteration(t)
            except:
                log.msg("Unexpected error in main loop.")
                log.err()
            else:
                log.msg('Main loop terminated.')



__all__ = []
