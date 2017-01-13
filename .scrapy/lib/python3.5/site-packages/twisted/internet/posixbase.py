# -*- test-case-name: twisted.test.test_internet,twisted.internet.test.test_posixbase -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Posix reactor base class
"""

from __future__ import division, absolute_import

import socket
import errno
import os
import sys

from zope.interface import implementer, classImplements

from twisted.internet import error, udp, tcp
from twisted.internet.base import ReactorBase, _SignalReactorMixin
from twisted.internet.main import CONNECTION_DONE, CONNECTION_LOST
from twisted.internet.interfaces import IReactorUNIX, IReactorUNIXDatagram
from twisted.internet.interfaces import IReactorTCP, IReactorUDP, IReactorSSL
from twisted.internet.interfaces import IReactorSocket, IHalfCloseableDescriptor
from twisted.internet.interfaces import IReactorProcess, IReactorMulticast

from twisted.python import log, failure, util
from twisted.python.runtime import platformType, platform

# Exceptions that doSelect might return frequently
_NO_FILENO = error.ConnectionFdescWentAway('Handler has no fileno method')
_NO_FILEDESC = error.ConnectionFdescWentAway('File descriptor lost')


try:
    from twisted.protocols import tls
except ImportError:
    tls = None
    try:
        from twisted.internet import ssl
    except ImportError:
        ssl = None

unixEnabled = (platformType == 'posix')

processEnabled = False
if unixEnabled:
    from twisted.internet import fdesc, unix
    from twisted.internet import process, _signals
    processEnabled = True


if platform.isWindows():
    try:
        import win32process
        processEnabled = True
    except ImportError:
        win32process = None


class _SocketWaker(log.Logger):
    """
    The I{self-pipe trick<http://cr.yp.to/docs/selfpipe.html>}, implemented
    using a pair of sockets rather than pipes (due to the lack of support in
    select() on Windows for pipes), used to wake up the main loop from
    another thread.
    """
    disconnected = 0

    def __init__(self, reactor):
        """Initialize.
        """
        self.reactor = reactor
        # Following select_trigger (from asyncore)'s example;
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        client.connect(server.getsockname())
        reader, clientaddr = server.accept()
        client.setblocking(0)
        reader.setblocking(0)
        self.r = reader
        self.w = client
        self.fileno = self.r.fileno

    def wakeUp(self):
        """Send a byte to my connection.
        """
        try:
            util.untilConcludes(self.w.send, b'x')
        except socket.error as e:
            if e.args[0] != errno.WSAEWOULDBLOCK:
                raise

    def doRead(self):
        """Read some data from my connection.
        """
        try:
            self.r.recv(8192)
        except socket.error:
            pass

    def connectionLost(self, reason):
        self.r.close()
        self.w.close()



class _FDWaker(log.Logger, object):
    """
    The I{self-pipe trick<http://cr.yp.to/docs/selfpipe.html>}, used to wake
    up the main loop from another thread or a signal handler.

    L{_FDWaker} is a base class for waker implementations based on
    writing to a pipe being monitored by the reactor.

    @ivar o: The file descriptor for the end of the pipe which can be
        written to wake up a reactor monitoring this waker.

    @ivar i: The file descriptor which should be monitored in order to
        be awoken by this waker.
    """
    disconnected = 0

    i = None
    o = None

    def __init__(self, reactor):
        """Initialize.
        """
        self.reactor = reactor
        self.i, self.o = os.pipe()
        fdesc.setNonBlocking(self.i)
        fdesc._setCloseOnExec(self.i)
        fdesc.setNonBlocking(self.o)
        fdesc._setCloseOnExec(self.o)
        self.fileno = lambda: self.i


    def doRead(self):
        """
        Read some bytes from the pipe and discard them.
        """
        fdesc.readFromFD(self.fileno(), lambda data: None)


    def connectionLost(self, reason):
        """Close both ends of my pipe.
        """
        if not hasattr(self, "o"):
            return
        for fd in self.i, self.o:
            try:
                os.close(fd)
            except IOError:
                pass
        del self.i, self.o



class _UnixWaker(_FDWaker):
    """
    This class provides a simple interface to wake up the event loop.

    This is used by threads or signals to wake up the event loop.
    """

    def wakeUp(self):
        """Write one byte to the pipe, and flush it.
        """
        # We don't use fdesc.writeToFD since we need to distinguish
        # between EINTR (try again) and EAGAIN (do nothing).
        if self.o is not None:
            try:
                util.untilConcludes(os.write, self.o, b'x')
            except OSError as e:
                # XXX There is no unit test for raising the exception
                # for other errnos. See #4285.
                if e.errno != errno.EAGAIN:
                    raise



if platformType == 'posix':
    _Waker = _UnixWaker
else:
    # Primarily Windows and Jython.
    _Waker = _SocketWaker


class _SIGCHLDWaker(_FDWaker):
    """
    L{_SIGCHLDWaker} can wake up a reactor whenever C{SIGCHLD} is
    received.

    @see: L{twisted.internet._signals}
    """
    def __init__(self, reactor):
        _FDWaker.__init__(self, reactor)


    def install(self):
        """
        Install the handler necessary to make this waker active.
        """
        _signals.installHandler(self.o)


    def uninstall(self):
        """
        Remove the handler which makes this waker active.
        """
        _signals.installHandler(-1)


    def doRead(self):
        """
        Having woken up the reactor in response to receipt of
        C{SIGCHLD}, reap the process which exited.

        This is called whenever the reactor notices the waker pipe is
        writeable, which happens soon after any call to the C{wakeUp}
        method.
        """
        _FDWaker.doRead(self)
        process.reapAllProcesses()




class _DisconnectSelectableMixin(object):
    """
    Mixin providing the C{_disconnectSelectable} method.
    """

    def _disconnectSelectable(self, selectable, why, isRead, faildict={
        error.ConnectionDone: failure.Failure(error.ConnectionDone()),
        error.ConnectionLost: failure.Failure(error.ConnectionLost())
        }):
        """
        Utility function for disconnecting a selectable.

        Supports half-close notification, isRead should be boolean indicating
        whether error resulted from doRead().
        """
        self.removeReader(selectable)
        f = faildict.get(why.__class__)
        if f:
            if (isRead and why.__class__ ==  error.ConnectionDone
                and IHalfCloseableDescriptor.providedBy(selectable)):
                selectable.readConnectionLost(f)
            else:
                self.removeWriter(selectable)
                selectable.connectionLost(f)
        else:
            self.removeWriter(selectable)
            selectable.connectionLost(failure.Failure(why))



@implementer(IReactorTCP, IReactorUDP, IReactorMulticast)
class PosixReactorBase(_SignalReactorMixin, _DisconnectSelectableMixin,
                       ReactorBase):
    """
    A basis for reactors that use file descriptors.

    @ivar _childWaker: L{None} or a reference to the L{_SIGCHLDWaker}
        which is used to properly notice child process termination.
    """

    # Callable that creates a waker, overrideable so that subclasses can
    # substitute their own implementation:
    _wakerFactory = _Waker

    def installWaker(self):
        """
        Install a `waker' to allow threads and signals to wake up the IO thread.

        We use the self-pipe trick (http://cr.yp.to/docs/selfpipe.html) to wake
        the reactor. On Windows we use a pair of sockets.
        """
        if not self.waker:
            self.waker = self._wakerFactory(self)
            self._internalReaders.add(self.waker)
            self.addReader(self.waker)


    _childWaker = None
    def _handleSignals(self):
        """
        Extend the basic signal handling logic to also support
        handling SIGCHLD to know when to try to reap child processes.
        """
        _SignalReactorMixin._handleSignals(self)
        if platformType == 'posix' and processEnabled:
            if not self._childWaker:
                self._childWaker = _SIGCHLDWaker(self)
                self._internalReaders.add(self._childWaker)
                self.addReader(self._childWaker)
            self._childWaker.install()
            # Also reap all processes right now, in case we missed any
            # signals before we installed the SIGCHLD waker/handler.
            # This should only happen if someone used spawnProcess
            # before calling reactor.run (and the process also exited
            # already).
            process.reapAllProcesses()

    def _uninstallHandler(self):
        """
        If a child waker was created and installed, uninstall it now.

        Since this disables reactor functionality and is only called
        when the reactor is stopping, it doesn't provide any directly
        useful functionality, but the cleanup of reactor-related
        process-global state that it does helps in unit tests
        involving multiple reactors and is generally just a nice
        thing.
        """
        # XXX This would probably be an alright place to put all of
        # the cleanup code for all internal readers (here and in the
        # base class, anyway).  See #3063 for that cleanup task.
        if self._childWaker:
            self._childWaker.uninstall()

    # IReactorProcess

    def spawnProcess(self, processProtocol, executable, args=(),
                     env={}, path=None,
                     uid=None, gid=None, usePTY=0, childFDs=None):
        args, env = self._checkProcessArgs(args, env)
        if platformType == 'posix':
            if usePTY:
                if childFDs is not None:
                    raise ValueError("Using childFDs is not supported with usePTY=True.")
                return process.PTYProcess(self, executable, args, env, path,
                                          processProtocol, uid, gid, usePTY)
            else:
                return process.Process(self, executable, args, env, path,
                                       processProtocol, uid, gid, childFDs)
        elif platformType == "win32":
            if uid is not None:
                raise ValueError("Setting UID is unsupported on this platform.")
            if gid is not None:
                raise ValueError("Setting GID is unsupported on this platform.")
            if usePTY:
                raise ValueError("The usePTY parameter is not supported on Windows.")
            if childFDs:
                raise ValueError("Customizing childFDs is not supported on Windows.")

            if win32process:
                from twisted.internet._dumbwin32proc import Process
                return Process(self, processProtocol, executable, args, env, path)
            else:
                raise NotImplementedError(
                    "spawnProcess not available since pywin32 is not installed.")
        else:
            raise NotImplementedError(
                "spawnProcess only available on Windows or POSIX.")

    # IReactorUDP

    def listenUDP(self, port, protocol, interface='', maxPacketSize=8192):
        """Connects a given L{DatagramProtocol} to the given numeric UDP port.

        @returns: object conforming to L{IListeningPort}.
        """
        p = udp.Port(port, protocol, interface, maxPacketSize, self)
        p.startListening()
        return p

    # IReactorMulticast

    def listenMulticast(self, port, protocol, interface='', maxPacketSize=8192, listenMultiple=False):
        """Connects a given DatagramProtocol to the given numeric UDP port.

        EXPERIMENTAL.

        @returns: object conforming to IListeningPort.
        """
        p = udp.MulticastPort(port, protocol, interface, maxPacketSize, self, listenMultiple)
        p.startListening()
        return p


    # IReactorUNIX

    def connectUNIX(self, address, factory, timeout=30, checkPID=0):
        assert unixEnabled, "UNIX support is not present"
        c = unix.Connector(address, factory, timeout, self, checkPID)
        c.connect()
        return c

    def listenUNIX(self, address, factory, backlog=50, mode=0o666, wantPID=0):
        assert unixEnabled, "UNIX support is not present"
        p = unix.Port(address, factory, backlog, mode, self, wantPID)
        p.startListening()
        return p


    # IReactorUNIXDatagram

    def listenUNIXDatagram(self, address, protocol, maxPacketSize=8192,
                           mode=0o666):
        """
        Connects a given L{DatagramProtocol} to the given path.

        EXPERIMENTAL.

        @returns: object conforming to L{IListeningPort}.
        """
        assert unixEnabled, "UNIX support is not present"
        p = unix.DatagramPort(address, protocol, maxPacketSize, mode, self)
        p.startListening()
        return p

    def connectUNIXDatagram(self, address, protocol, maxPacketSize=8192,
                            mode=0o666, bindAddress=None):
        """
        Connects a L{ConnectedDatagramProtocol} instance to a path.

        EXPERIMENTAL.
        """
        assert unixEnabled, "UNIX support is not present"
        p = unix.ConnectedDatagramPort(address, protocol, maxPacketSize, mode, bindAddress, self)
        p.startListening()
        return p


    # IReactorSocket (but not on Windows)

    def adoptStreamPort(self, fileDescriptor, addressFamily, factory):
        """
        Create a new L{IListeningPort} from an already-initialized socket.

        This just dispatches to a suitable port implementation (eg from
        L{IReactorTCP}, etc) based on the specified C{addressFamily}.

        @see: L{twisted.internet.interfaces.IReactorSocket.adoptStreamPort}
        """
        if addressFamily not in (socket.AF_INET, socket.AF_INET6):
            raise error.UnsupportedAddressFamily(addressFamily)

        p = tcp.Port._fromListeningDescriptor(
            self, fileDescriptor, addressFamily, factory)
        p.startListening()
        return p

    def adoptStreamConnection(self, fileDescriptor, addressFamily, factory):
        """
        @see:
            L{twisted.internet.interfaces.IReactorSocket.adoptStreamConnection}
        """
        if addressFamily not in (socket.AF_INET, socket.AF_INET6):
            raise error.UnsupportedAddressFamily(addressFamily)

        return tcp.Server._fromConnectedSocket(
            fileDescriptor, addressFamily, factory, self)


    def adoptDatagramPort(self, fileDescriptor, addressFamily, protocol,
                          maxPacketSize=8192):
        if addressFamily not in (socket.AF_INET, socket.AF_INET6):
            raise error.UnsupportedAddressFamily(addressFamily)

        p = udp.Port._fromListeningDescriptor(
            self, fileDescriptor, addressFamily, protocol,
            maxPacketSize=maxPacketSize)
        p.startListening()
        return p



    # IReactorTCP

    def listenTCP(self, port, factory, backlog=50, interface=''):
        p = tcp.Port(port, factory, backlog, interface, self)
        p.startListening()
        return p

    def connectTCP(self, host, port, factory, timeout=30, bindAddress=None):
        c = tcp.Connector(host, port, factory, timeout, bindAddress, self)
        c.connect()
        return c

    # IReactorSSL (sometimes, not implemented)

    def connectSSL(self, host, port, factory, contextFactory, timeout=30, bindAddress=None):
        if tls is not None:
            tlsFactory = tls.TLSMemoryBIOFactory(contextFactory, True, factory)
            return self.connectTCP(host, port, tlsFactory, timeout, bindAddress)
        elif ssl is not None:
            c = ssl.Connector(
                host, port, factory, contextFactory, timeout, bindAddress, self)
            c.connect()
            return c
        else:
            assert False, "SSL support is not present"



    def listenSSL(self, port, factory, contextFactory, backlog=50, interface=''):
        if tls is not None:
            tlsFactory = tls.TLSMemoryBIOFactory(contextFactory, False, factory)
            port = self.listenTCP(port, tlsFactory, backlog, interface)
            port._type = 'TLS'
            return port
        elif ssl is not None:
            p = ssl.Port(
                port, factory, contextFactory, backlog, interface, self)
            p.startListening()
            return p
        else:
            assert False, "SSL support is not present"


    def _removeAll(self, readers, writers):
        """
        Remove all readers and writers, and list of removed L{IReadDescriptor}s
        and L{IWriteDescriptor}s.

        Meant for calling from subclasses, to implement removeAll, like::

          def removeAll(self):
              return self._removeAll(self._reads, self._writes)

        where C{self._reads} and C{self._writes} are iterables.
        """
        removedReaders = set(readers) - self._internalReaders
        for reader in removedReaders:
            self.removeReader(reader)

        removedWriters = set(writers)
        for writer in removedWriters:
            self.removeWriter(writer)

        return list(removedReaders | removedWriters)


class _PollLikeMixin(object):
    """
    Mixin for poll-like reactors.

    Subclasses must define the following attributes::

      - _POLL_DISCONNECTED - Bitmask for events indicating a connection was
        lost.
      - _POLL_IN - Bitmask for events indicating there is input to read.
      - _POLL_OUT - Bitmask for events indicating output can be written.

    Must be mixed in to a subclass of PosixReactorBase (for
    _disconnectSelectable).
    """

    def _doReadOrWrite(self, selectable, fd, event):
        """
        fd is available for read or write, do the work and raise errors if
        necessary.
        """
        why = None
        inRead = False
        if event & self._POLL_DISCONNECTED and not (event & self._POLL_IN):
            # Handle disconnection.  But only if we finished processing all
            # the pending input.
            if fd in self._reads:
                # If we were reading from the descriptor then this is a
                # clean shutdown.  We know there are no read events pending
                # because we just checked above.  It also might be a
                # half-close (which is why we have to keep track of inRead).
                inRead = True
                why = CONNECTION_DONE
            else:
                # If we weren't reading, this is an error shutdown of some
                # sort.
                why = CONNECTION_LOST
        else:
            # Any non-disconnect event turns into a doRead or a doWrite.
            try:
                # First check to see if the descriptor is still valid.  This
                # gives fileno() a chance to raise an exception, too.
                # Ideally, disconnection would always be indicated by the
                # return value of doRead or doWrite (or an exception from
                # one of those methods), but calling fileno here helps make
                # buggy applications more transparent.
                if selectable.fileno() == -1:
                    # -1 is sort of a historical Python artifact.  Python
                    # files and sockets used to change their file descriptor
                    # to -1 when they closed.  For the time being, we'll
                    # continue to support this anyway in case applications
                    # replicated it, plus abstract.FileDescriptor.fileno
                    # returns -1.  Eventually it'd be good to deprecate this
                    # case.
                    why = _NO_FILEDESC
                else:
                    if event & self._POLL_IN:
                        # Handle a read event.
                        why = selectable.doRead()
                        inRead = True
                    if not why and event & self._POLL_OUT:
                        # Handle a write event, as long as doRead didn't
                        # disconnect us.
                        why = selectable.doWrite()
                        inRead = False
            except:
                # Any exception from application code gets logged and will
                # cause us to disconnect the selectable.
                why = sys.exc_info()[1]
                log.err()
        if why:
            self._disconnectSelectable(selectable, why, inRead)



if tls is not None or ssl is not None:
    classImplements(PosixReactorBase, IReactorSSL)
if unixEnabled:
    classImplements(PosixReactorBase, IReactorUNIX, IReactorUNIXDatagram)
if processEnabled:
    classImplements(PosixReactorBase, IReactorProcess)
if getattr(socket, 'fromfd', None) is not None:
    classImplements(PosixReactorBase, IReactorSocket)

__all__ = ["PosixReactorBase"]
