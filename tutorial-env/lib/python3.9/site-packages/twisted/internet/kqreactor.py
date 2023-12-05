# -*- test-case-name: twisted.test.test_kqueuereactor -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
A kqueue()/kevent() based implementation of the Twisted main loop.

To use this reactor, start your application specifying the kqueue reactor::

   twistd --reactor kqueue ...

To install the event loop from code (and you should do this before any
connections, listeners or connectors are added)::

   from twisted.internet import kqreactor
   kqreactor.install()
"""

import errno
import select

from zope.interface import Attribute, Interface, declarations, implementer

from twisted.internet import main, posixbase
from twisted.internet.interfaces import IReactorDaemonize, IReactorFDSet
from twisted.python import failure, log

try:
    # This is to keep mypy from complaining
    # We don't use type: ignore[attr-defined] on import, because mypy only complains
    # on on some platforms, and then the unused ignore is an issue if the undefined
    # attribute isn't.
    KQ_EV_ADD = getattr(select, "KQ_EV_ADD")
    KQ_EV_DELETE = getattr(select, "KQ_EV_DELETE")
    KQ_EV_EOF = getattr(select, "KQ_EV_EOF")
    KQ_FILTER_READ = getattr(select, "KQ_FILTER_READ")
    KQ_FILTER_WRITE = getattr(select, "KQ_FILTER_WRITE")
except AttributeError as e:
    raise ImportError(e)


class _IKQueue(Interface):
    """
    An interface for KQueue implementations.
    """

    kqueue = Attribute("An implementation of kqueue(2).")
    kevent = Attribute("An implementation of kevent(2).")


declarations.directlyProvides(select, _IKQueue)


@implementer(IReactorFDSet, IReactorDaemonize)
class KQueueReactor(posixbase.PosixReactorBase):
    """
    A reactor that uses kqueue(2)/kevent(2) and relies on Python 2.6 or higher
    which has built in support for kqueue in the select module.

    @ivar _kq: A C{kqueue} which will be used to check for I/O readiness.

    @ivar _impl: The implementation of L{_IKQueue} to use.

    @ivar _selectables: A dictionary mapping integer file descriptors to
        instances of L{FileDescriptor} which have been registered with the
        reactor.  All L{FileDescriptor}s which are currently receiving read or
        write readiness notifications will be present as values in this
        dictionary.

    @ivar _reads: A set containing integer file descriptors.  Values in this
        set will be registered with C{_kq} for read readiness notifications
        which will be dispatched to the corresponding L{FileDescriptor}
        instances in C{_selectables}.

    @ivar _writes: A set containing integer file descriptors.  Values in this
        set will be registered with C{_kq} for write readiness notifications
        which will be dispatched to the corresponding L{FileDescriptor}
        instances in C{_selectables}.
    """

    def __init__(self, _kqueueImpl=select):
        """
        Initialize kqueue object, file descriptor tracking dictionaries, and
        the base class.

        See:
            - http://docs.python.org/library/select.html
            - www.freebsd.org/cgi/man.cgi?query=kqueue
            - people.freebsd.org/~jlemon/papers/kqueue.pdf

        @param _kqueueImpl: The implementation of L{_IKQueue} to use. A
            hook for testing.
        """
        self._impl = _kqueueImpl
        self._kq = self._impl.kqueue()
        self._reads = set()
        self._writes = set()
        self._selectables = {}
        posixbase.PosixReactorBase.__init__(self)

    def _updateRegistration(self, fd, filter, op):
        """
        Private method for changing kqueue registration on a given FD
        filtering for events given filter/op. This will never block and
        returns nothing.
        """
        self._kq.control([self._impl.kevent(fd, filter, op)], 0, 0)

    def beforeDaemonize(self):
        """
        Implement L{IReactorDaemonize.beforeDaemonize}.
        """
        # Twisted-internal method called during daemonization (when application
        # is started via twistd). This is called right before the magic double
        # forking done for daemonization. We cleanly close the kqueue() and later
        # recreate it. This is needed since a) kqueue() are not inherited across
        # forks and b) twistd will create the reactor already before daemonization
        # (and will also add at least 1 reader to the reactor, an instance of
        # twisted.internet.posixbase._UnixWaker).
        #
        # See: twisted.scripts._twistd_unix.daemonize()
        self._kq.close()
        self._kq = None

    def afterDaemonize(self):
        """
        Implement L{IReactorDaemonize.afterDaemonize}.
        """
        # Twisted-internal method called during daemonization. This is called right
        # after daemonization and recreates the kqueue() and any readers/writers
        # that were added before. Note that you MUST NOT call any reactor methods
        # in between beforeDaemonize() and afterDaemonize()!
        self._kq = self._impl.kqueue()
        for fd in self._reads:
            self._updateRegistration(fd, KQ_FILTER_READ, KQ_EV_ADD)
        for fd in self._writes:
            self._updateRegistration(fd, KQ_FILTER_WRITE, KQ_EV_ADD)

    def addReader(self, reader):
        """
        Implement L{IReactorFDSet.addReader}.
        """
        fd = reader.fileno()
        if fd not in self._reads:
            try:
                self._updateRegistration(fd, KQ_FILTER_READ, KQ_EV_ADD)
            except OSError:
                pass
            finally:
                self._selectables[fd] = reader
                self._reads.add(fd)

    def addWriter(self, writer):
        """
        Implement L{IReactorFDSet.addWriter}.
        """
        fd = writer.fileno()
        if fd not in self._writes:
            try:
                self._updateRegistration(fd, KQ_FILTER_WRITE, KQ_EV_ADD)
            except OSError:
                pass
            finally:
                self._selectables[fd] = writer
                self._writes.add(fd)

    def removeReader(self, reader):
        """
        Implement L{IReactorFDSet.removeReader}.
        """
        wasLost = False
        try:
            fd = reader.fileno()
        except BaseException:
            fd = -1
        if fd == -1:
            for fd, fdes in self._selectables.items():
                if reader is fdes:
                    wasLost = True
                    break
            else:
                return
        if fd in self._reads:
            self._reads.remove(fd)
            if fd not in self._writes:
                del self._selectables[fd]
            if not wasLost:
                try:
                    self._updateRegistration(fd, KQ_FILTER_READ, KQ_EV_DELETE)
                except OSError:
                    pass

    def removeWriter(self, writer):
        """
        Implement L{IReactorFDSet.removeWriter}.
        """
        wasLost = False
        try:
            fd = writer.fileno()
        except BaseException:
            fd = -1
        if fd == -1:
            for fd, fdes in self._selectables.items():
                if writer is fdes:
                    wasLost = True
                    break
            else:
                return
        if fd in self._writes:
            self._writes.remove(fd)
            if fd not in self._reads:
                del self._selectables[fd]
            if not wasLost:
                try:
                    self._updateRegistration(fd, KQ_FILTER_WRITE, KQ_EV_DELETE)
                except OSError:
                    pass

    def removeAll(self):
        """
        Implement L{IReactorFDSet.removeAll}.
        """
        return self._removeAll(
            [self._selectables[fd] for fd in self._reads],
            [self._selectables[fd] for fd in self._writes],
        )

    def getReaders(self):
        """
        Implement L{IReactorFDSet.getReaders}.
        """
        return [self._selectables[fd] for fd in self._reads]

    def getWriters(self):
        """
        Implement L{IReactorFDSet.getWriters}.
        """
        return [self._selectables[fd] for fd in self._writes]

    def doKEvent(self, timeout):
        """
        Poll the kqueue for new events.
        """
        if timeout is None:
            timeout = 1

        try:
            events = self._kq.control([], len(self._selectables), timeout)
        except OSError as e:
            # Since this command blocks for potentially a while, it's possible
            # EINTR can be raised for various reasons (for example, if the user
            # hits ^C).
            if e.errno == errno.EINTR:
                return
            else:
                raise

        _drdw = self._doWriteOrRead
        for event in events:
            fd = event.ident
            try:
                selectable = self._selectables[fd]
            except KeyError:
                # Handles the infrequent case where one selectable's
                # handler disconnects another.
                continue
            else:
                log.callWithLogger(selectable, _drdw, selectable, fd, event)

    def _doWriteOrRead(self, selectable, fd, event):
        """
        Private method called when a FD is ready for reading, writing or was
        lost. Do the work and raise errors where necessary.
        """
        why = None
        inRead = False
        (filter, flags, data, fflags) = (
            event.filter,
            event.flags,
            event.data,
            event.fflags,
        )

        if flags & KQ_EV_EOF and data and fflags:
            why = main.CONNECTION_LOST
        else:
            try:
                if selectable.fileno() == -1:
                    inRead = False
                    why = posixbase._NO_FILEDESC
                else:
                    if filter == KQ_FILTER_READ:
                        inRead = True
                        why = selectable.doRead()
                    if filter == KQ_FILTER_WRITE:
                        inRead = False
                        why = selectable.doWrite()
            except BaseException:
                # Any exception from application code gets logged and will
                # cause us to disconnect the selectable.
                why = failure.Failure()
                log.err(
                    why,
                    "An exception was raised from application code"
                    " while processing a reactor selectable",
                )

        if why:
            self._disconnectSelectable(selectable, why, inRead)

    doIteration = doKEvent


def install():
    """
    Install the kqueue() reactor.
    """
    p = KQueueReactor()
    from twisted.internet.main import installReactor

    installReactor(p)


__all__ = ["KQueueReactor", "install"]
