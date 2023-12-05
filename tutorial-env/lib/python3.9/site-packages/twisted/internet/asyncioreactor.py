# -*- test-case-name: twisted.test.test_internet -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
asyncio-based reactor implementation.
"""


import errno
import sys
from asyncio import AbstractEventLoop, get_event_loop
from typing import Dict, Optional, Type

from zope.interface import implementer

from twisted.internet.abstract import FileDescriptor
from twisted.internet.interfaces import IReactorFDSet
from twisted.internet.posixbase import (
    _NO_FILEDESC,
    PosixReactorBase,
    _ContinuousPolling,
)
from twisted.logger import Logger
from twisted.python.log import callWithLogger


@implementer(IReactorFDSet)
class AsyncioSelectorReactor(PosixReactorBase):
    """
    Reactor running on top of L{asyncio.SelectorEventLoop}.

    On POSIX platforms, the default event loop is
    L{asyncio.SelectorEventLoop}.
    On Windows, the default event loop on Python 3.7 and older
    is C{asyncio.WindowsSelectorEventLoop}, but on Python 3.8 and newer
    the default event loop is C{asyncio.WindowsProactorEventLoop} which
    is incompatible with L{AsyncioSelectorReactor}.
    Applications that use L{AsyncioSelectorReactor} on Windows
    with Python 3.8+ must call
    C{asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())}
    before instantiating and running L{AsyncioSelectorReactor}.
    """

    _asyncClosed = False
    _log = Logger()

    def __init__(self, eventloop: Optional[AbstractEventLoop] = None):
        if eventloop is None:
            _eventloop: AbstractEventLoop = get_event_loop()
        else:
            _eventloop = eventloop

        # On Python 3.8+, asyncio.get_event_loop() on
        # Windows was changed to return a ProactorEventLoop
        # unless the loop policy has been changed.
        if sys.platform == "win32":
            from asyncio import ProactorEventLoop

            if isinstance(_eventloop, ProactorEventLoop):
                raise TypeError(
                    f"ProactorEventLoop is not supported, got: {_eventloop}"
                )

        self._asyncioEventloop: AbstractEventLoop = _eventloop
        self._writers: Dict[Type[FileDescriptor], int] = {}
        self._readers: Dict[Type[FileDescriptor], int] = {}
        self._continuousPolling = _ContinuousPolling(self)

        self._scheduledAt = None
        self._timerHandle = None

        super().__init__()

    def _unregisterFDInAsyncio(self, fd):
        """
        Compensate for a bug in asyncio where it will not unregister a FD that
        it cannot handle in the epoll loop. It touches internal asyncio code.

        A description of the bug by markrwilliams:

        The C{add_writer} method of asyncio event loops isn't atomic because
        all the Selector classes in the selector module internally record a
        file object before passing it to the platform's selector
        implementation. If the platform's selector decides the file object
        isn't acceptable, the resulting exception doesn't cause the Selector to
        un-track the file object.

        The failing/hanging stdio test goes through the following sequence of
        events (roughly):

        * The first C{connection.write(intToByte(value))} call hits the asyncio
        reactor's C{addWriter} method.

        * C{addWriter} calls the asyncio loop's C{add_writer} method, which
        happens to live on C{_BaseSelectorEventLoop}.

        * The asyncio loop's C{add_writer} method checks if the file object has
        been registered before via the selector's C{get_key} method.

        * It hasn't, so the KeyError block runs and calls the selector's
        register method

        * Code examples that follow use EpollSelector, but the code flow holds
        true for any other selector implementation. The selector's register
        method first calls through to the next register method in the MRO

        * That next method is always C{_BaseSelectorImpl.register} which
        creates a C{SelectorKey} instance for the file object, stores it under
        the file object's file descriptor, and then returns it.

        * Control returns to the concrete selector implementation, which asks
        the operating system to track the file descriptor using the right API.

        * The operating system refuses! An exception is raised that, in this
        case, the asyncio reactor handles by creating a C{_ContinuousPolling}
        object to watch the file descriptor.

        * The second C{connection.write(intToByte(value))} call hits the
        asyncio reactor's C{addWriter} method, which hits the C{add_writer}
        method. But the loop's selector's get_key method now returns a
        C{SelectorKey}! Now the asyncio reactor's C{addWriter} method thinks
        the asyncio loop will watch the file descriptor, even though it won't.
        """
        try:
            self._asyncioEventloop._selector.unregister(fd)
        except BaseException:
            pass

    def _readOrWrite(self, selectable, read):
        method = selectable.doRead if read else selectable.doWrite

        if selectable.fileno() == -1:
            self._disconnectSelectable(selectable, _NO_FILEDESC, read)
            return

        try:
            why = method()
        except Exception as e:
            why = e
            self._log.failure(None)
        if why:
            self._disconnectSelectable(selectable, why, read)

    def addReader(self, reader):
        if reader in self._readers.keys() or reader in self._continuousPolling._readers:
            return

        fd = reader.fileno()
        try:
            self._asyncioEventloop.add_reader(
                fd, callWithLogger, reader, self._readOrWrite, reader, True
            )
            self._readers[reader] = fd
        except OSError as e:
            self._unregisterFDInAsyncio(fd)
            if e.errno == errno.EPERM:
                # epoll(7) doesn't support certain file descriptors,
                # e.g. filesystem files, so for those we just poll
                # continuously:
                self._continuousPolling.addReader(reader)
            else:
                raise

    def addWriter(self, writer):
        if writer in self._writers.keys() or writer in self._continuousPolling._writers:
            return

        fd = writer.fileno()
        try:
            self._asyncioEventloop.add_writer(
                fd, callWithLogger, writer, self._readOrWrite, writer, False
            )
            self._writers[writer] = fd
        except PermissionError:
            self._unregisterFDInAsyncio(fd)
            # epoll(7) doesn't support certain file descriptors,
            # e.g. filesystem files, so for those we just poll
            # continuously:
            self._continuousPolling.addWriter(writer)
        except BrokenPipeError:
            # The kqueuereactor will raise this if there is a broken pipe
            self._unregisterFDInAsyncio(fd)
        except BaseException:
            self._unregisterFDInAsyncio(fd)
            raise

    def removeReader(self, reader):

        # First, see if they're trying to remove a reader that we don't have.
        if not (
            reader in self._readers.keys() or self._continuousPolling.isReading(reader)
        ):
            # We don't have it, so just return OK.
            return

        # If it was a cont. polling reader, check there first.
        if self._continuousPolling.isReading(reader):
            self._continuousPolling.removeReader(reader)
            return

        fd = reader.fileno()
        if fd == -1:
            # If the FD is -1, we want to know what its original FD was, to
            # remove it.
            fd = self._readers.pop(reader)
        else:
            self._readers.pop(reader)

        self._asyncioEventloop.remove_reader(fd)

    def removeWriter(self, writer):

        # First, see if they're trying to remove a writer that we don't have.
        if not (
            writer in self._writers.keys() or self._continuousPolling.isWriting(writer)
        ):
            # We don't have it, so just return OK.
            return

        # If it was a cont. polling writer, check there first.
        if self._continuousPolling.isWriting(writer):
            self._continuousPolling.removeWriter(writer)
            return

        fd = writer.fileno()

        if fd == -1:
            # If the FD is -1, we want to know what its original FD was, to
            # remove it.
            fd = self._writers.pop(writer)
        else:
            self._writers.pop(writer)

        self._asyncioEventloop.remove_writer(fd)

    def removeAll(self):
        return (
            self._removeAll(self._readers.keys(), self._writers.keys())
            + self._continuousPolling.removeAll()
        )

    def getReaders(self):
        return list(self._readers.keys()) + self._continuousPolling.getReaders()

    def getWriters(self):
        return list(self._writers.keys()) + self._continuousPolling.getWriters()

    def iterate(self, timeout):
        self._asyncioEventloop.call_later(timeout + 0.01, self._asyncioEventloop.stop)
        self._asyncioEventloop.run_forever()

    def run(self, installSignalHandlers=True):
        self.startRunning(installSignalHandlers=installSignalHandlers)
        self._asyncioEventloop.run_forever()
        if self._justStopped:
            self._justStopped = False

    def stop(self):
        super().stop()
        # This will cause runUntilCurrent which in its turn
        # will call fireSystemEvent("shutdown")
        self.callLater(0, lambda: None)

    def crash(self):
        super().crash()
        self._asyncioEventloop.stop()

    def _onTimer(self):
        self._scheduledAt = None
        self.runUntilCurrent()
        self._reschedule()

    def _reschedule(self):
        timeout = self.timeout()
        if timeout is not None:
            abs_time = self._asyncioEventloop.time() + timeout
            self._scheduledAt = abs_time
            if self._timerHandle is not None:
                self._timerHandle.cancel()
            self._timerHandle = self._asyncioEventloop.call_at(abs_time, self._onTimer)

    def _moveCallLaterSooner(self, tple):
        PosixReactorBase._moveCallLaterSooner(self, tple)
        self._reschedule()

    def callLater(self, seconds, f, *args, **kwargs):
        dc = PosixReactorBase.callLater(self, seconds, f, *args, **kwargs)
        abs_time = self._asyncioEventloop.time() + self.timeout()
        if self._scheduledAt is None or abs_time < self._scheduledAt:
            self._reschedule()
        return dc

    def callFromThread(self, f, *args, **kwargs):
        g = lambda: self.callLater(0, f, *args, **kwargs)
        self._asyncioEventloop.call_soon_threadsafe(g)


def install(eventloop=None):
    """
    Install an asyncio-based reactor.

    @param eventloop: The asyncio eventloop to wrap. If default, the global one
        is selected.
    """
    reactor = AsyncioSelectorReactor(eventloop)
    from twisted.internet.main import installReactor

    installReactor(reactor)
