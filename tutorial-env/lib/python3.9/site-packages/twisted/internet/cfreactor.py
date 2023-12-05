# -*- test-case-name: twisted.internet.test.test_core -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
A reactor for integrating with U{CFRunLoop<http://bit.ly/cfrunloop>}, the
CoreFoundation main loop used by macOS.

This is useful for integrating Twisted with U{PyObjC<http://pyobjc.sf.net/>}
applications.
"""

__all__ = ["install", "CFReactor"]

import sys

from zope.interface import implementer

from CFNetwork import (  # type: ignore[import]
    CFSocketCreateRunLoopSource,
    CFSocketCreateWithNative,
    CFSocketDisableCallBacks,
    CFSocketEnableCallBacks,
    CFSocketInvalidate,
    CFSocketSetSocketFlags,
    kCFSocketAutomaticallyReenableReadCallBack,
    kCFSocketAutomaticallyReenableWriteCallBack,
    kCFSocketConnectCallBack,
    kCFSocketReadCallBack,
    kCFSocketWriteCallBack,
)
from CoreFoundation import (  # type: ignore[import]
    CFAbsoluteTimeGetCurrent,
    CFRunLoopAddSource,
    CFRunLoopAddTimer,
    CFRunLoopGetMain,
    CFRunLoopRemoveSource,
    CFRunLoopRun,
    CFRunLoopStop,
    CFRunLoopTimerCreate,
    CFRunLoopTimerInvalidate,
    kCFAllocatorDefault,
    kCFRunLoopCommonModes,
)

from twisted.internet.interfaces import IReactorFDSet
from twisted.internet.posixbase import _NO_FILEDESC, PosixReactorBase
from twisted.python import log

# We know that we're going to run on macOS so we can just pick the
# POSIX-appropriate waker.  This also avoids having a dynamic base class and
# so lets more things get type checked.
from ._signals import _UnixWaker

_READ = 0
_WRITE = 1
_preserveSOError = 1 << 6


class _WakerPlus(_UnixWaker):
    """
    The normal Twisted waker will simply wake up the main loop, which causes an
    iteration to run, which in turn causes L{ReactorBase.runUntilCurrent}
    to get invoked.

    L{CFReactor} has a slightly different model of iteration, though: rather
    than have each iteration process the thread queue, then timed calls, then
    file descriptors, each callback is run as it is dispatched by the CFRunLoop
    observer which triggered it.

    So this waker needs to not only unblock the loop, but also make sure the
    work gets done; so, it reschedules the invocation of C{runUntilCurrent} to
    be immediate (0 seconds from now) even if there is no timed call work to
    do.
    """

    def doRead(self):
        """
        Wake up the loop and force C{runUntilCurrent} to run immediately in the
        next timed iteration.
        """
        result = super().doRead()
        self.reactor._scheduleSimulate(True)
        return result


@implementer(IReactorFDSet)
class CFReactor(PosixReactorBase):
    """
    The CoreFoundation reactor.

    You probably want to use this via the L{install} API.

    @ivar _fdmap: a dictionary, mapping an integer (a file descriptor) to a
        4-tuple of:

            - source: a C{CFRunLoopSource}; the source associated with this
              socket.
            - socket: a C{CFSocket} wrapping the file descriptor.
            - descriptor: an L{IReadDescriptor} and/or L{IWriteDescriptor}
              provider.
            - read-write: a 2-C{list} of booleans: respectively, whether this
              descriptor is currently registered for reading or registered for
              writing.

    @ivar _idmap: a dictionary, mapping the id() of an L{IReadDescriptor} or
        L{IWriteDescriptor} to a C{fd} in L{_fdmap}.  Implemented in this
        manner so that we don't have to rely (even more) on the hashability of
        L{IReadDescriptor} providers, and we know that they won't be collected
        since these are kept in sync with C{_fdmap}.  Necessary because the
        .fileno() of a file descriptor may change at will, so we need to be
        able to look up what its file descriptor I{used} to be, so that we can
        look it up in C{_fdmap}

    @ivar _cfrunloop: the C{CFRunLoop} pyobjc object wrapped
        by this reactor.

    @ivar _inCFLoop: Is C{CFRunLoopRun} currently running?

    @type _inCFLoop: L{bool}

    @ivar _currentSimulator: if a CFTimer is currently scheduled with the CF
        run loop to run Twisted callLater calls, this is a reference to it.
        Otherwise, it is L{None}
    """

    def __init__(self, runLoop=None, runner=None):
        self._fdmap = {}
        self._idmap = {}
        if runner is None:
            runner = CFRunLoopRun
        self._runner = runner

        if runLoop is None:
            runLoop = CFRunLoopGetMain()
        self._cfrunloop = runLoop
        PosixReactorBase.__init__(self)

    def installWaker(self):
        """
        Override C{installWaker} in order to use L{_WakerPlus}; otherwise this
        should be exactly the same as the parent implementation.
        """
        if not self.waker:
            self.waker = _WakerPlus(self)
            self._internalReaders.add(self.waker)
            self.addReader(self.waker)

    def _socketCallback(
        self, cfSocket, callbackType, ignoredAddress, ignoredData, context
    ):
        """
        The socket callback issued by CFRunLoop.  This will issue C{doRead} or
        C{doWrite} calls to the L{IReadDescriptor} and L{IWriteDescriptor}
        registered with the file descriptor that we are being notified of.

        @param cfSocket: The C{CFSocket} which has got some activity.

        @param callbackType: The type of activity that we are being notified
            of.  Either C{kCFSocketReadCallBack} or C{kCFSocketWriteCallBack}.

        @param ignoredAddress: Unused, because this is not used for either of
            the callback types we register for.

        @param ignoredData: Unused, because this is not used for either of the
            callback types we register for.

        @param context: The data associated with this callback by
            C{CFSocketCreateWithNative} (in C{CFReactor._watchFD}).  A 2-tuple
            of C{(int, CFRunLoopSource)}.
        """
        (fd, smugglesrc) = context
        if fd not in self._fdmap:
            # Spurious notifications seem to be generated sometimes if you
            # CFSocketDisableCallBacks in the middle of an event.  I don't know
            # about this FD, any more, so let's get rid of it.
            CFRunLoopRemoveSource(self._cfrunloop, smugglesrc, kCFRunLoopCommonModes)
            return

        src, skt, readWriteDescriptor, rw = self._fdmap[fd]

        def _drdw():
            why = None
            isRead = False

            try:
                if readWriteDescriptor.fileno() == -1:
                    why = _NO_FILEDESC
                else:
                    isRead = callbackType == kCFSocketReadCallBack
                    # CFSocket seems to deliver duplicate read/write
                    # notifications sometimes, especially a duplicate
                    # writability notification when first registering the
                    # socket.  This bears further investigation, since I may
                    # have been mis-interpreting the behavior I was seeing.
                    # (Running the full Twisted test suite, while thorough, is
                    # not always entirely clear.) Until this has been more
                    # thoroughly investigated , we consult our own
                    # reading/writing state flags to determine whether we
                    # should actually attempt a doRead/doWrite first.  -glyph
                    if isRead:
                        if rw[_READ]:
                            why = readWriteDescriptor.doRead()
                    else:
                        if rw[_WRITE]:
                            why = readWriteDescriptor.doWrite()
            except BaseException:
                why = sys.exc_info()[1]
                log.err()
            if why:
                self._disconnectSelectable(readWriteDescriptor, why, isRead)

        log.callWithLogger(readWriteDescriptor, _drdw)

    def _watchFD(self, fd, descr, flag):
        """
        Register a file descriptor with the C{CFRunLoop}, or modify its state
        so that it's listening for both notifications (read and write) rather
        than just one; used to implement C{addReader} and C{addWriter}.

        @param fd: The file descriptor.

        @type fd: L{int}

        @param descr: the L{IReadDescriptor} or L{IWriteDescriptor}

        @param flag: the flag to register for callbacks on, either
            C{kCFSocketReadCallBack} or C{kCFSocketWriteCallBack}
        """
        if fd == -1:
            raise RuntimeError("Invalid file descriptor.")
        if fd in self._fdmap:
            src, cfs, gotdescr, rw = self._fdmap[fd]
            # do I need to verify that it's the same descr?
        else:
            ctx = []
            ctx.append(fd)
            cfs = CFSocketCreateWithNative(
                kCFAllocatorDefault,
                fd,
                kCFSocketReadCallBack
                | kCFSocketWriteCallBack
                | kCFSocketConnectCallBack,
                self._socketCallback,
                ctx,
            )
            CFSocketSetSocketFlags(
                cfs,
                kCFSocketAutomaticallyReenableReadCallBack
                | kCFSocketAutomaticallyReenableWriteCallBack
                |
                # This extra flag is to ensure that CF doesn't (destructively,
                # because destructively is the only way to do it) retrieve
                # SO_ERROR and thereby break twisted.internet.tcp.BaseClient,
                # which needs SO_ERROR to tell it whether or not it needs to
                # call connect_ex a second time.
                _preserveSOError,
            )
            src = CFSocketCreateRunLoopSource(kCFAllocatorDefault, cfs, 0)
            ctx.append(src)
            CFRunLoopAddSource(self._cfrunloop, src, kCFRunLoopCommonModes)
            CFSocketDisableCallBacks(
                cfs,
                kCFSocketReadCallBack
                | kCFSocketWriteCallBack
                | kCFSocketConnectCallBack,
            )
            rw = [False, False]
            self._idmap[id(descr)] = fd
            self._fdmap[fd] = src, cfs, descr, rw
        rw[self._flag2idx(flag)] = True
        CFSocketEnableCallBacks(cfs, flag)

    def _flag2idx(self, flag):
        """
        Convert a C{kCFSocket...} constant to an index into the read/write
        state list (C{_READ} or C{_WRITE}) (the 4th element of the value of
        C{self._fdmap}).

        @param flag: C{kCFSocketReadCallBack} or C{kCFSocketWriteCallBack}

        @return: C{_READ} or C{_WRITE}
        """
        return {kCFSocketReadCallBack: _READ, kCFSocketWriteCallBack: _WRITE}[flag]

    def _unwatchFD(self, fd, descr, flag):
        """
        Unregister a file descriptor with the C{CFRunLoop}, or modify its state
        so that it's listening for only one notification (read or write) as
        opposed to both; used to implement C{removeReader} and C{removeWriter}.

        @param fd: a file descriptor

        @type fd: C{int}

        @param descr: an L{IReadDescriptor} or L{IWriteDescriptor}

        @param flag: C{kCFSocketWriteCallBack} C{kCFSocketReadCallBack}
        """
        if id(descr) not in self._idmap:
            return
        if fd == -1:
            # need to deal with it in this case, I think.
            realfd = self._idmap[id(descr)]
        else:
            realfd = fd
        src, cfs, descr, rw = self._fdmap[realfd]
        CFSocketDisableCallBacks(cfs, flag)
        rw[self._flag2idx(flag)] = False
        if not rw[_READ] and not rw[_WRITE]:
            del self._idmap[id(descr)]
            del self._fdmap[realfd]
            CFRunLoopRemoveSource(self._cfrunloop, src, kCFRunLoopCommonModes)
            CFSocketInvalidate(cfs)

    def addReader(self, reader):
        """
        Implement L{IReactorFDSet.addReader}.
        """
        self._watchFD(reader.fileno(), reader, kCFSocketReadCallBack)

    def addWriter(self, writer):
        """
        Implement L{IReactorFDSet.addWriter}.
        """
        self._watchFD(writer.fileno(), writer, kCFSocketWriteCallBack)

    def removeReader(self, reader):
        """
        Implement L{IReactorFDSet.removeReader}.
        """
        self._unwatchFD(reader.fileno(), reader, kCFSocketReadCallBack)

    def removeWriter(self, writer):
        """
        Implement L{IReactorFDSet.removeWriter}.
        """
        self._unwatchFD(writer.fileno(), writer, kCFSocketWriteCallBack)

    def removeAll(self):
        """
        Implement L{IReactorFDSet.removeAll}.
        """
        allDesc = {descr for src, cfs, descr, rw in self._fdmap.values()}
        allDesc -= set(self._internalReaders)
        for desc in allDesc:
            self.removeReader(desc)
            self.removeWriter(desc)
        return list(allDesc)

    def getReaders(self):
        """
        Implement L{IReactorFDSet.getReaders}.
        """
        return [descr for src, cfs, descr, rw in self._fdmap.values() if rw[_READ]]

    def getWriters(self):
        """
        Implement L{IReactorFDSet.getWriters}.
        """
        return [descr for src, cfs, descr, rw in self._fdmap.values() if rw[_WRITE]]

    def _moveCallLaterSooner(self, tple):
        """
        Override L{PosixReactorBase}'s implementation of L{IDelayedCall.reset}
        so that it will immediately reschedule.  Normally
        C{_moveCallLaterSooner} depends on the fact that C{runUntilCurrent} is
        always run before the mainloop goes back to sleep, so this forces it to
        immediately recompute how long the loop needs to stay asleep.
        """
        result = PosixReactorBase._moveCallLaterSooner(self, tple)
        self._scheduleSimulate()
        return result

    _inCFLoop = False

    def mainLoop(self):
        """
        Run the runner (C{CFRunLoopRun} or something that calls it), which runs
        the run loop until C{crash()} is called.
        """
        self._inCFLoop = True
        try:
            self._runner()
        finally:
            self._inCFLoop = False

    _currentSimulator = None

    def _scheduleSimulate(self, force=False):
        """
        Schedule a call to C{self.runUntilCurrent}.  This will cancel the
        currently scheduled call if it is already scheduled.

        @param force: Even if there are no timed calls, make sure that
            C{runUntilCurrent} runs immediately (in a 0-seconds-from-now
            C{CFRunLoopTimer}).  This is necessary for calls which need to
            trigger behavior of C{runUntilCurrent} other than running timed
            calls, such as draining the thread call queue or calling C{crash()}
            when the appropriate flags are set.

        @type force: C{bool}
        """
        if self._currentSimulator is not None:
            CFRunLoopTimerInvalidate(self._currentSimulator)
            self._currentSimulator = None
        timeout = self.timeout()
        if force:
            timeout = 0.0
        if timeout is not None:
            fireDate = CFAbsoluteTimeGetCurrent() + timeout

            def simulate(cftimer, extra):
                self._currentSimulator = None
                self.runUntilCurrent()
                self._scheduleSimulate()

            c = self._currentSimulator = CFRunLoopTimerCreate(
                kCFAllocatorDefault, fireDate, 0, 0, 0, simulate, None
            )
            CFRunLoopAddTimer(self._cfrunloop, c, kCFRunLoopCommonModes)

    def callLater(self, _seconds, _f, *args, **kw):
        """
        Implement L{IReactorTime.callLater}.
        """
        delayedCall = PosixReactorBase.callLater(self, _seconds, _f, *args, **kw)
        self._scheduleSimulate()
        return delayedCall

    def stop(self):
        """
        Implement L{IReactorCore.stop}.
        """
        PosixReactorBase.stop(self)
        self._scheduleSimulate(True)

    def crash(self):
        """
        Implement L{IReactorCore.crash}
        """
        wasStarted = self._started
        PosixReactorBase.crash(self)
        if self._inCFLoop:
            self._stopNow()
        else:
            if wasStarted:
                self.callLater(0, self._stopNow)

    def _stopNow(self):
        """
        Immediately stop the CFRunLoop (which must be running!).
        """
        CFRunLoopStop(self._cfrunloop)

    def iterate(self, delay=0):
        """
        Emulate the behavior of C{iterate()} for things that want to call it,
        by letting the loop run for a little while and then scheduling a timed
        call to exit it.
        """
        self.callLater(delay, self._stopNow)
        self.mainLoop()


def install(runLoop=None, runner=None):
    """
    Configure the twisted mainloop to be run inside CFRunLoop.

    @param runLoop: the run loop to use.

    @param runner: the function to call in order to actually invoke the main
        loop.  This will default to C{CFRunLoopRun} if not specified.  However,
        this is not an appropriate choice for GUI applications, as you need to
        run NSApplicationMain (or something like it).  For example, to run the
        Twisted mainloop in a PyObjC application, your C{main.py} should look
        something like this::

            from PyObjCTools import AppHelper
            from twisted.internet.cfreactor import install
            install(runner=AppHelper.runEventLoop)
            # initialize your application
            reactor.run()

    @return: The installed reactor.

    @rtype: C{CFReactor}
    """

    reactor = CFReactor(runLoop=runLoop, runner=runner)
    from twisted.internet.main import installReactor

    installReactor(reactor)
    return reactor
