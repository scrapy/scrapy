# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
An epoll() based implementation of the twisted main loop.

To install the event loop (and you should do this before any connections,
listeners or connectors are added)::

    from twisted.internet import epollreactor
    epollreactor.install()
"""

from __future__ import division, absolute_import

from select import epoll, EPOLLHUP, EPOLLERR, EPOLLIN, EPOLLOUT
import errno

from zope.interface import implementer

from twisted.internet.interfaces import IReactorFDSet

from twisted.python import log
from twisted.internet import posixbase



@implementer(IReactorFDSet)
class _ContinuousPolling(posixbase._PollLikeMixin,
                         posixbase._DisconnectSelectableMixin):
    """
    Schedule reads and writes based on the passage of time, rather than
    notification.

    This is useful for supporting polling filesystem files, which C{epoll(7)}
    does not support.

    The implementation uses L{posixbase._PollLikeMixin}, which is a bit hacky,
    but re-implementing and testing the relevant code yet again is
    unappealing.

    @ivar _reactor: The L{EPollReactor} that is using this instance.

    @ivar _loop: A C{LoopingCall} that drives the polling, or L{None}.

    @ivar _readers: A C{set} of C{FileDescriptor} objects that should be read
        from.

    @ivar _writers: A C{set} of C{FileDescriptor} objects that should be
        written to.
    """

    # Attributes for _PollLikeMixin
    _POLL_DISCONNECTED = 1
    _POLL_IN = 2
    _POLL_OUT = 4


    def __init__(self, reactor):
        self._reactor = reactor
        self._loop = None
        self._readers = set()
        self._writers = set()


    def _checkLoop(self):
        """
        Start or stop a C{LoopingCall} based on whether there are readers and
        writers.
        """
        if self._readers or self._writers:
            if self._loop is None:
                from twisted.internet.task import LoopingCall, _EPSILON
                self._loop = LoopingCall(self.iterate)
                self._loop.clock = self._reactor
                # LoopingCall seems unhappy with timeout of 0, so use very
                # small number:
                self._loop.start(_EPSILON, now=False)
        elif self._loop:
            self._loop.stop()
            self._loop = None


    def iterate(self):
        """
        Call C{doRead} and C{doWrite} on all readers and writers respectively.
        """
        for reader in list(self._readers):
            self._doReadOrWrite(reader, reader, self._POLL_IN)
        for reader in list(self._writers):
            self._doReadOrWrite(reader, reader, self._POLL_OUT)


    def addReader(self, reader):
        """
        Add a C{FileDescriptor} for notification of data available to read.
        """
        self._readers.add(reader)
        self._checkLoop()


    def addWriter(self, writer):
        """
        Add a C{FileDescriptor} for notification of data available to write.
        """
        self._writers.add(writer)
        self._checkLoop()


    def removeReader(self, reader):
        """
        Remove a C{FileDescriptor} from notification of data available to read.
        """
        try:
            self._readers.remove(reader)
        except KeyError:
            return
        self._checkLoop()


    def removeWriter(self, writer):
        """
        Remove a C{FileDescriptor} from notification of data available to
        write.
        """
        try:
            self._writers.remove(writer)
        except KeyError:
            return
        self._checkLoop()


    def removeAll(self):
        """
        Remove all readers and writers.
        """
        result = list(self._readers | self._writers)
        # Don't reset to new value, since self.isWriting and .isReading refer
        # to the existing instance:
        self._readers.clear()
        self._writers.clear()
        return result


    def getReaders(self):
        """
        Return a list of the readers.
        """
        return list(self._readers)


    def getWriters(self):
        """
        Return a list of the writers.
        """
        return list(self._writers)


    def isReading(self, fd):
        """
        Checks if the file descriptor is currently being observed for read
        readiness.

        @param fd: The file descriptor being checked.
        @type fd: L{twisted.internet.abstract.FileDescriptor}
        @return: C{True} if the file descriptor is being observed for read
            readiness, C{False} otherwise.
        @rtype: C{bool}
        """
        return fd in self._readers


    def isWriting(self, fd):
        """
        Checks if the file descriptor is currently being observed for write
        readiness.

        @param fd: The file descriptor being checked.
        @type fd: L{twisted.internet.abstract.FileDescriptor}
        @return: C{True} if the file descriptor is being observed for write
            readiness, C{False} otherwise.
        @rtype: C{bool}
        """
        return fd in self._writers



@implementer(IReactorFDSet)
class EPollReactor(posixbase.PosixReactorBase, posixbase._PollLikeMixin):
    """
    A reactor that uses epoll(7).

    @ivar _poller: A C{epoll} which will be used to check for I/O
        readiness.

    @ivar _selectables: A dictionary mapping integer file descriptors to
        instances of C{FileDescriptor} which have been registered with the
        reactor.  All C{FileDescriptors} which are currently receiving read or
        write readiness notifications will be present as values in this
        dictionary.

    @ivar _reads: A set containing integer file descriptors.  Values in this
        set will be registered with C{_poller} for read readiness notifications
        which will be dispatched to the corresponding C{FileDescriptor}
        instances in C{_selectables}.

    @ivar _writes: A set containing integer file descriptors.  Values in this
        set will be registered with C{_poller} for write readiness
        notifications which will be dispatched to the corresponding
        C{FileDescriptor} instances in C{_selectables}.

    @ivar _continuousPolling: A L{_ContinuousPolling} instance, used to handle
        file descriptors (e.g. filesystem files) that are not supported by
        C{epoll(7)}.
    """

    # Attributes for _PollLikeMixin
    _POLL_DISCONNECTED = (EPOLLHUP | EPOLLERR)
    _POLL_IN = EPOLLIN
    _POLL_OUT = EPOLLOUT

    def __init__(self):
        """
        Initialize epoll object, file descriptor tracking dictionaries, and the
        base class.
        """
        # Create the poller we're going to use.  The 1024 here is just a hint
        # to the kernel, it is not a hard maximum.  After Linux 2.6.8, the size
        # argument is completely ignored.
        self._poller = epoll(1024)
        self._reads = set()
        self._writes = set()
        self._selectables = {}
        self._continuousPolling = _ContinuousPolling(self)
        posixbase.PosixReactorBase.__init__(self)


    def _add(self, xer, primary, other, selectables, event, antievent):
        """
        Private method for adding a descriptor from the event loop.

        It takes care of adding it if  new or modifying it if already added
        for another state (read -> read/write for example).
        """
        fd = xer.fileno()
        if fd not in primary:
            flags = event
            # epoll_ctl can raise all kinds of IOErrors, and every one
            # indicates a bug either in the reactor or application-code.
            # Let them all through so someone sees a traceback and fixes
            # something.  We'll do the same thing for every other call to
            # this method in this file.
            if fd in other:
                flags |= antievent
                self._poller.modify(fd, flags)
            else:
                self._poller.register(fd, flags)

            # Update our own tracking state *only* after the epoll call has
            # succeeded.  Otherwise we may get out of sync.
            primary.add(fd)
            selectables[fd] = xer


    def addReader(self, reader):
        """
        Add a FileDescriptor for notification of data available to read.
        """
        try:
            self._add(reader, self._reads, self._writes, self._selectables,
                      EPOLLIN, EPOLLOUT)
        except IOError as e:
            if e.errno == errno.EPERM:
                # epoll(7) doesn't support certain file descriptors,
                # e.g. filesystem files, so for those we just poll
                # continuously:
                self._continuousPolling.addReader(reader)
            else:
                raise


    def addWriter(self, writer):
        """
        Add a FileDescriptor for notification of data available to write.
        """
        try:
            self._add(writer, self._writes, self._reads, self._selectables,
                      EPOLLOUT, EPOLLIN)
        except IOError as e:
            if e.errno == errno.EPERM:
                # epoll(7) doesn't support certain file descriptors,
                # e.g. filesystem files, so for those we just poll
                # continuously:
                self._continuousPolling.addWriter(writer)
            else:
                raise


    def _remove(self, xer, primary, other, selectables, event, antievent):
        """
        Private method for removing a descriptor from the event loop.

        It does the inverse job of _add, and also add a check in case of the fd
        has gone away.
        """
        fd = xer.fileno()
        if fd == -1:
            for fd, fdes in selectables.items():
                if xer is fdes:
                    break
            else:
                return
        if fd in primary:
            if fd in other:
                flags = antievent
                # See comment above modify call in _add.
                self._poller.modify(fd, flags)
            else:
                del selectables[fd]
                # See comment above _control call in _add.
                self._poller.unregister(fd)
            primary.remove(fd)


    def removeReader(self, reader):
        """
        Remove a Selectable for notification of data available to read.
        """
        if self._continuousPolling.isReading(reader):
            self._continuousPolling.removeReader(reader)
            return
        self._remove(reader, self._reads, self._writes, self._selectables,
                     EPOLLIN, EPOLLOUT)


    def removeWriter(self, writer):
        """
        Remove a Selectable for notification of data available to write.
        """
        if self._continuousPolling.isWriting(writer):
            self._continuousPolling.removeWriter(writer)
            return
        self._remove(writer, self._writes, self._reads, self._selectables,
                     EPOLLOUT, EPOLLIN)


    def removeAll(self):
        """
        Remove all selectables, and return a list of them.
        """
        return (self._removeAll(
                [self._selectables[fd] for fd in self._reads],
                [self._selectables[fd] for fd in self._writes]) +
                self._continuousPolling.removeAll())


    def getReaders(self):
        return ([self._selectables[fd] for fd in self._reads] +
                self._continuousPolling.getReaders())


    def getWriters(self):
        return ([self._selectables[fd] for fd in self._writes] +
                self._continuousPolling.getWriters())


    def doPoll(self, timeout):
        """
        Poll the poller for new events.
        """
        if timeout is None:
            timeout = -1  # Wait indefinitely.

        try:
            # Limit the number of events to the number of io objects we're
            # currently tracking (because that's maybe a good heuristic) and
            # the amount of time we block to the value specified by our
            # caller.
            l = self._poller.poll(timeout, len(self._selectables))
        except IOError as err:
            if err.errno == errno.EINTR:
                return
            # See epoll_wait(2) for documentation on the other conditions
            # under which this can fail.  They can only be due to a serious
            # programming error on our part, so let's just announce them
            # loudly.
            raise

        _drdw = self._doReadOrWrite
        for fd, event in l:
            try:
                selectable = self._selectables[fd]
            except KeyError:
                pass
            else:
                log.callWithLogger(selectable, _drdw, selectable, fd, event)

    doIteration = doPoll


def install():
    """
    Install the epoll() reactor.
    """
    p = EPollReactor()
    from twisted.internet.main import installReactor
    installReactor(p)


__all__ = ["EPollReactor", "install"]
