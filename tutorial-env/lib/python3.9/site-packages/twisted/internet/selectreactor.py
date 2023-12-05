# -*- test-case-name: twisted.test.test_internet -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Select reactor
"""


import select
import sys
from errno import EBADF, EINTR
from time import sleep
from typing import Type

from zope.interface import implementer

from twisted.internet import posixbase
from twisted.internet.interfaces import IReactorFDSet
from twisted.python import log
from twisted.python.runtime import platformType


def win32select(r, w, e, timeout=None):
    """Win32 select wrapper."""
    if not (r or w):
        # windows select() exits immediately when no sockets
        if timeout is None:
            timeout = 0.01
        else:
            timeout = min(timeout, 0.001)
        sleep(timeout)
        return [], [], []
    # windows doesn't process 'signals' inside select(), so we set a max
    # time or ctrl-c will never be recognized
    if timeout is None or timeout > 0.5:
        timeout = 0.5
    r, w, e = select.select(r, w, w, timeout)
    return r, w + e, []


if platformType == "win32":
    _select = win32select
else:
    _select = select.select


try:
    from twisted.internet.win32eventreactor import _ThreadedWin32EventsMixin
except ImportError:
    _extraBase: Type[object] = object
else:
    _extraBase = _ThreadedWin32EventsMixin


@implementer(IReactorFDSet)
class SelectReactor(posixbase.PosixReactorBase, _extraBase):  # type: ignore[misc,valid-type]
    """
    A select() based reactor - runs on all POSIX platforms and on Win32.

    @ivar _reads: A set containing L{FileDescriptor} instances which will be
        checked for read events.

    @ivar _writes: A set containing L{FileDescriptor} instances which will be
        checked for writability.
    """

    def __init__(self):
        """
        Initialize file descriptor tracking dictionaries and the base class.
        """
        self._reads = set()
        self._writes = set()
        posixbase.PosixReactorBase.__init__(self)

    def _preenDescriptors(self):
        log.msg("Malformed file descriptor found.  Preening lists.")
        readers = list(self._reads)
        writers = list(self._writes)
        self._reads.clear()
        self._writes.clear()
        for selSet, selList in ((self._reads, readers), (self._writes, writers)):
            for selectable in selList:
                try:
                    select.select([selectable], [selectable], [selectable], 0)
                except Exception as e:
                    log.msg("bad descriptor %s" % selectable)
                    self._disconnectSelectable(selectable, e, False)
                else:
                    selSet.add(selectable)

    def doSelect(self, timeout):
        """
        Run one iteration of the I/O monitor loop.

        This will run all selectables who had input or output readiness
        waiting for them.
        """
        try:
            r, w, ignored = _select(self._reads, self._writes, [], timeout)
        except ValueError:
            # Possibly a file descriptor has gone negative?
            self._preenDescriptors()
            return
        except TypeError:
            # Something *totally* invalid (object w/o fileno, non-integral
            # result) was passed
            log.err()
            self._preenDescriptors()
            return
        except OSError as se:
            # select(2) encountered an error, perhaps while calling the fileno()
            # method of a socket.  (Python 2.6 socket.error is an IOError
            # subclass, but on Python 2.5 and earlier it is not.)
            if se.args[0] in (0, 2):
                # windows does this if it got an empty list
                if (not self._reads) and (not self._writes):
                    return
                else:
                    raise
            elif se.args[0] == EINTR:
                return
            elif se.args[0] == EBADF:
                self._preenDescriptors()
                return
            else:
                # OK, I really don't know what's going on.  Blow up.
                raise

        _drdw = self._doReadOrWrite
        _logrun = log.callWithLogger
        for selectables, method, fdset in (
            (r, "doRead", self._reads),
            (w, "doWrite", self._writes),
        ):
            for selectable in selectables:
                # if this was disconnected in another thread, kill it.
                # ^^^^ --- what the !@#*?  serious!  -exarkun
                if selectable not in fdset:
                    continue
                # This for pausing input when we're not ready for more.
                _logrun(selectable, _drdw, selectable, method)

    doIteration = doSelect

    def _doReadOrWrite(self, selectable, method):
        try:
            why = getattr(selectable, method)()
        except BaseException:
            why = sys.exc_info()[1]
            log.err()
        if why:
            self._disconnectSelectable(selectable, why, method == "doRead")

    def addReader(self, reader):
        """
        Add a FileDescriptor for notification of data available to read.
        """
        self._reads.add(reader)

    def addWriter(self, writer):
        """
        Add a FileDescriptor for notification of data available to write.
        """
        self._writes.add(writer)

    def removeReader(self, reader):
        """
        Remove a Selectable for notification of data available to read.
        """
        self._reads.discard(reader)

    def removeWriter(self, writer):
        """
        Remove a Selectable for notification of data available to write.
        """
        self._writes.discard(writer)

    def removeAll(self):
        return self._removeAll(self._reads, self._writes)

    def getReaders(self):
        return list(self._reads)

    def getWriters(self):
        return list(self._writes)


def install():
    """Configure the twisted mainloop to be run using the select() reactor."""
    reactor = SelectReactor()
    from twisted.internet.main import installReactor

    installReactor(reactor)


__all__ = ["install"]
