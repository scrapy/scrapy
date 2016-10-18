# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
A win32event based implementation of the Twisted main loop.

This requires pywin32 (formerly win32all) or ActivePython to be installed.

To install the event loop (and you should do this before any connections,
listeners or connectors are added)::

    from twisted.internet import win32eventreactor
    win32eventreactor.install()

LIMITATIONS:
 1. WaitForMultipleObjects and thus the event loop can only handle 64 objects.
 2. Process running has some problems (see L{twisted.internet.process} docstring).


TODO:
 1. Event loop handling of writes is *very* problematic (this is causing failed tests).
    Switch to doing it the correct way, whatever that means (see below).
 2. Replace icky socket loopback waker with event based waker (use dummyEvent object)
 3. Switch everyone to using Free Software so we don't have to deal with proprietary APIs.


ALTERNATIVE SOLUTIONS:
 - IIRC, sockets can only be registered once. So we switch to a structure
   like the poll() reactor, thus allowing us to deal with write events in
   a decent fashion. This should allow us to pass tests, but we're still
   limited to 64 events.

Or:

 - Instead of doing a reactor, we make this an addon to the select reactor.
   The WFMO event loop runs in a separate thread. This means no need to maintain
   separate code for networking, 64 event limit doesn't apply to sockets,
   we can run processes and other win32 stuff in default event loop. The
   only problem is that we're stuck with the icky socket based waker.
   Another benefit is that this could be extended to support >64 events
   in a simpler manner than the previous solution.

The 2nd solution is probably what will get implemented.
"""

# System imports
import time
import sys
from threading import Thread
from weakref import WeakKeyDictionary

from zope.interface import implementer

# Win32 imports
from win32file import FD_READ, FD_CLOSE, FD_ACCEPT, FD_CONNECT, WSAEventSelect
try:
    # WSAEnumNetworkEvents was added in pywin32 215
    from win32file import WSAEnumNetworkEvents
except ImportError:
    import warnings
    warnings.warn(
        'Reliable disconnection notification requires pywin32 215 or later',
        category=UserWarning)
    def WSAEnumNetworkEvents(fd, event):
        return set([FD_READ])

from win32event import CreateEvent, MsgWaitForMultipleObjects
from win32event import WAIT_OBJECT_0, WAIT_TIMEOUT, QS_ALLINPUT

import win32gui

# Twisted imports
from twisted.internet import posixbase
from twisted.python import log, threadable, failure
from twisted.internet.interfaces import IReactorFDSet
from twisted.internet.interfaces import IReactorWin32Events
from twisted.internet.threads import blockingCallFromThread


@implementer(IReactorFDSet, IReactorWin32Events)
class Win32Reactor(posixbase.PosixReactorBase):
    """
    Reactor that uses Win32 event APIs.

    @ivar _reads: A dictionary mapping L{FileDescriptor} instances to a
        win32 event object used to check for read events for that descriptor.

    @ivar _writes: A dictionary mapping L{FileDescriptor} instances to a
        arbitrary value.  Keys in this dictionary will be given a chance to
        write out their data.

    @ivar _events: A dictionary mapping win32 event object to tuples of
        L{FileDescriptor} instances and event masks.

    @ivar _closedAndReading: Along with C{_closedAndNotReading}, keeps track of
        descriptors which have had close notification delivered from the OS but
        which we have not finished reading data from.  MsgWaitForMultipleObjects
        will only deliver close notification to us once, so we remember it in
        these two dictionaries until we're ready to act on it.  The OS has
        delivered close notification for each descriptor in this dictionary, and
        the descriptors are marked as allowed to handle read events in the
        reactor, so they can be processed.  When a descriptor is marked as not
        allowed to handle read events in the reactor (ie, it is passed to
        L{IReactorFDSet.removeReader}), it is moved out of this dictionary and
        into C{_closedAndNotReading}.  The descriptors are keys in this
        dictionary.  The values are arbitrary.
    @type _closedAndReading: C{dict}

    @ivar _closedAndNotReading: These descriptors have had close notification
        delivered from the OS, but are not marked as allowed to handle read
        events in the reactor.  They are saved here to record their closed
        state, but not processed at all.  When one of these descriptors is
        passed to L{IReactorFDSet.addReader}, it is moved out of this dictionary
        and into C{_closedAndReading}.  The descriptors are keys in this
        dictionary.  The values are arbitrary.  This is a weak key dictionary so
        that if an application tells the reactor to stop reading from a
        descriptor and then forgets about that descriptor itself, the reactor
        will also forget about it.
    @type _closedAndNotReading: C{WeakKeyDictionary}
    """
    dummyEvent = CreateEvent(None, 0, 0, None)

    def __init__(self):
        self._reads = {}
        self._writes = {}
        self._events = {}
        self._closedAndReading = {}
        self._closedAndNotReading = WeakKeyDictionary()
        posixbase.PosixReactorBase.__init__(self)


    def _makeSocketEvent(self, fd, action, why):
        """
        Make a win32 event object for a socket.
        """
        event = CreateEvent(None, 0, 0, None)
        WSAEventSelect(fd, event, why)
        self._events[event] = (fd, action)
        return event


    def addEvent(self, event, fd, action):
        """
        Add a new win32 event to the event loop.
        """
        self._events[event] = (fd, action)


    def removeEvent(self, event):
        """
        Remove an event.
        """
        del self._events[event]


    def addReader(self, reader):
        """
        Add a socket FileDescriptor for notification of data available to read.
        """
        if reader not in self._reads:
            self._reads[reader] = self._makeSocketEvent(
                reader, 'doRead', FD_READ | FD_ACCEPT | FD_CONNECT | FD_CLOSE)
            # If the reader is closed, move it over to the dictionary of reading
            # descriptors.
            if reader in self._closedAndNotReading:
                self._closedAndReading[reader] = True
                del self._closedAndNotReading[reader]


    def addWriter(self, writer):
        """
        Add a socket FileDescriptor for notification of data available to write.
        """
        if writer not in self._writes:
            self._writes[writer] = 1


    def removeReader(self, reader):
        """Remove a Selectable for notification of data available to read.
        """
        if reader in self._reads:
            del self._events[self._reads[reader]]
            del self._reads[reader]

            # If the descriptor is closed, move it out of the dictionary of
            # reading descriptors into the dictionary of waiting descriptors.
            if reader in self._closedAndReading:
                self._closedAndNotReading[reader] = True
                del self._closedAndReading[reader]


    def removeWriter(self, writer):
        """Remove a Selectable for notification of data available to write.
        """
        if writer in self._writes:
            del self._writes[writer]


    def removeAll(self):
        """
        Remove all selectables, and return a list of them.
        """
        return self._removeAll(self._reads, self._writes)


    def getReaders(self):
        return list(self._reads.keys())


    def getWriters(self):
        return list(self._writes.keys())


    def doWaitForMultipleEvents(self, timeout):
        log.msg(channel='system', event='iteration', reactor=self)
        if timeout is None:
            timeout = 100

        # Keep track of whether we run any application code before we get to the
        # MsgWaitForMultipleObjects.  If so, there's a chance it will schedule a
        # new timed call or stop the reactor or do something else that means we
        # shouldn't block in MsgWaitForMultipleObjects for the full timeout.
        ranUserCode = False

        # If any descriptors are trying to close, try to get them out of the way
        # first.
        for reader in list(self._closedAndReading.keys()):
            ranUserCode = True
            self._runAction('doRead', reader)

        for fd in list(self._writes.keys()):
            ranUserCode = True
            log.callWithLogger(fd, self._runWrite, fd)

        if ranUserCode:
            # If application code *might* have scheduled an event, assume it
            # did.  If we're wrong, we'll get back here shortly anyway.  If
            # we're right, we'll be sure to handle the event (including reactor
            # shutdown) in a timely manner.
            timeout = 0

        if not (self._events or self._writes):
            # sleep so we don't suck up CPU time
            time.sleep(timeout)
            return

        handles = list(self._events.keys()) or [self.dummyEvent]
        timeout = int(timeout * 1000)
        val = MsgWaitForMultipleObjects(handles, 0, timeout, QS_ALLINPUT)
        if val == WAIT_TIMEOUT:
            return
        elif val == WAIT_OBJECT_0 + len(handles):
            exit = win32gui.PumpWaitingMessages()
            if exit:
                self.callLater(0, self.stop)
                return
        elif val >= WAIT_OBJECT_0 and val < WAIT_OBJECT_0 + len(handles):
            event = handles[val - WAIT_OBJECT_0]
            fd, action = self._events[event]

            if fd in self._reads:
                # Before anything, make sure it's still a valid file descriptor.
                fileno = fd.fileno()
                if fileno == -1:
                    self._disconnectSelectable(fd, posixbase._NO_FILEDESC, False)
                    return

                # Since it's a socket (not another arbitrary event added via
                # addEvent) and we asked for FD_READ | FD_CLOSE, check to see if
                # we actually got FD_CLOSE.  This needs a special check because
                # it only gets delivered once.  If we miss it, it's gone forever
                # and we'll never know that the connection is closed.
                events = WSAEnumNetworkEvents(fileno, event)
                if FD_CLOSE in events:
                    self._closedAndReading[fd] = True
            log.callWithLogger(fd, self._runAction, action, fd)


    def _runWrite(self, fd):
        closed = 0
        try:
            closed = fd.doWrite()
        except:
            closed = sys.exc_info()[1]
            log.deferr()

        if closed:
            self.removeReader(fd)
            self.removeWriter(fd)
            try:
                fd.connectionLost(failure.Failure(closed))
            except:
                log.deferr()
        elif closed is None:
            return 1

    def _runAction(self, action, fd):
        try:
            closed = getattr(fd, action)()
        except:
            closed = sys.exc_info()[1]
            log.deferr()
        if closed:
            self._disconnectSelectable(fd, closed, action == 'doRead')

    doIteration = doWaitForMultipleEvents



class _ThreadFDWrapper(object):
    """
    This wraps an event handler and translates notification in the helper
    L{Win32Reactor} thread into a notification in the primary reactor thread.

    @ivar _reactor: The primary reactor, the one to which event notification
        will be sent.

    @ivar _fd: The L{FileDescriptor} to which the event will be dispatched.

    @ivar _action: A C{str} giving the method of C{_fd} which handles the event.

    @ivar _logPrefix: The pre-fetched log prefix string for C{_fd}, so that
        C{_fd.logPrefix} does not need to be called in a non-main thread.
    """
    def __init__(self, reactor, fd, action, logPrefix):
        self._reactor = reactor
        self._fd = fd
        self._action = action
        self._logPrefix = logPrefix


    def logPrefix(self):
        """
        Return the original handler's log prefix, as it was given to
        C{__init__}.
        """
        return self._logPrefix


    def _execute(self):
        """
        Callback fired when the associated event is set.  Run the C{action}
        callback on the wrapped descriptor in the main reactor thread and raise
        or return whatever it raises or returns to cause this event handler to
        be removed from C{self._reactor} if appropriate.
        """
        return blockingCallFromThread(
            self._reactor, lambda: getattr(self._fd, self._action)())


    def connectionLost(self, reason):
        """
        Pass through to the wrapped descriptor, but in the main reactor thread
        instead of the helper C{Win32Reactor} thread.
        """
        self._reactor.callFromThread(self._fd.connectionLost, reason)



@implementer(IReactorWin32Events)
class _ThreadedWin32EventsMixin(object):
    """
    This mixin implements L{IReactorWin32Events} for another reactor by running
    a L{Win32Reactor} in a separate thread and dispatching work to it.

    @ivar _reactor: The L{Win32Reactor} running in the other thread.  This is
        L{None} until it is actually needed.

    @ivar _reactorThread: The L{threading.Thread} which is running the
        L{Win32Reactor}.  This is L{None} until it is actually needed.
    """

    _reactor = None
    _reactorThread = None


    def _unmakeHelperReactor(self):
        """
        Stop and discard the reactor started by C{_makeHelperReactor}.
        """
        self._reactor.callFromThread(self._reactor.stop)
        self._reactor = None


    def _makeHelperReactor(self):
        """
        Create and (in a new thread) start a L{Win32Reactor} instance to use for
        the implementation of L{IReactorWin32Events}.
        """
        self._reactor = Win32Reactor()
        # This is a helper reactor, it is not the global reactor and its thread
        # is not "the" I/O thread.  Prevent it from registering it as such.
        self._reactor._registerAsIOThread = False
        self._reactorThread = Thread(
            target=self._reactor.run, args=(False,))
        self.addSystemEventTrigger(
            'after', 'shutdown', self._unmakeHelperReactor)
        self._reactorThread.start()


    def addEvent(self, event, fd, action):
        """
        @see: L{IReactorWin32Events}
        """
        if self._reactor is None:
            self._makeHelperReactor()
        self._reactor.callFromThread(
            self._reactor.addEvent,
            event, _ThreadFDWrapper(self, fd, action, fd.logPrefix()),
            "_execute")


    def removeEvent(self, event):
        """
        @see: L{IReactorWin32Events}
        """
        self._reactor.callFromThread(self._reactor.removeEvent, event)



def install():
    threadable.init(1)
    r = Win32Reactor()
    from . import main
    main.installReactor(r)


__all__ = ["Win32Reactor", "install"]
