# -*- test-case-name: twisted.internet.test.test_iocp -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Reactor that uses IO completion ports
"""


import socket
import sys
import warnings
from typing import Tuple, Type

from zope.interface import implementer

from twisted.internet import base, error, interfaces, main
from twisted.internet._dumbwin32proc import Process
from twisted.internet.iocpreactor import iocpsupport as _iocp, tcp, udp
from twisted.internet.iocpreactor.const import WAIT_TIMEOUT
from twisted.internet.win32eventreactor import _ThreadedWin32EventsMixin
from twisted.python import failure, log

try:
    from twisted.protocols.tls import TLSMemoryBIOFactory as _TLSMemoryBIOFactory
except ImportError:
    TLSMemoryBIOFactory = None
    # Either pyOpenSSL isn't installed, or it is too old for this code to work.
    # The reactor won't provide IReactorSSL.
    _extraInterfaces: Tuple[Type[interfaces.IReactorSSL], ...] = ()
    warnings.warn(
        "pyOpenSSL 0.10 or newer is required for SSL support in iocpreactor. "
        "It is missing, so the reactor will not support SSL APIs."
    )
else:
    TLSMemoryBIOFactory = _TLSMemoryBIOFactory
    _extraInterfaces = (interfaces.IReactorSSL,)

MAX_TIMEOUT = 2000  # 2 seconds, see doIteration for explanation

EVENTS_PER_LOOP = 1000  # XXX: what's a good value here?

# keys to associate with normal and waker events
KEY_NORMAL, KEY_WAKEUP = range(2)

_NO_GETHANDLE = error.ConnectionFdescWentAway("Handler has no getFileHandle method")
_NO_FILEDESC = error.ConnectionFdescWentAway("Filedescriptor went away")


@implementer(
    interfaces.IReactorTCP,
    interfaces.IReactorUDP,
    interfaces.IReactorMulticast,
    interfaces.IReactorProcess,
    *_extraInterfaces,
)
class IOCPReactor(
    base._SignalReactorMixin, base.ReactorBase, _ThreadedWin32EventsMixin
):

    port = None

    def __init__(self):
        base.ReactorBase.__init__(self)
        self.port = _iocp.CompletionPort()
        self.handles = set()

    def addActiveHandle(self, handle):
        self.handles.add(handle)

    def removeActiveHandle(self, handle):
        self.handles.discard(handle)

    def doIteration(self, timeout):
        """
        Poll the IO completion port for new events.
        """
        # This function sits and waits for an IO completion event.
        #
        # There are two requirements: process IO events as soon as they arrive
        # and process ctrl-break from the user in a reasonable amount of time.
        #
        # There are three kinds of waiting.
        # 1) GetQueuedCompletionStatus (self.port.getEvent) to wait for IO
        # events only.
        # 2) Msg* family of wait functions that can stop waiting when
        # ctrl-break is detected (then, I think, Python converts it into a
        # KeyboardInterrupt)
        # 3) *Ex family of wait functions that put the thread into an
        # "alertable" wait state which is supposedly triggered by IO completion
        #
        # 2) and 3) can be combined. Trouble is, my IO completion is not
        # causing 3) to trigger, possibly because I do not use an IO completion
        # callback. Windows is weird.
        # There are two ways to handle this. I could use MsgWaitForSingleObject
        # here and GetQueuedCompletionStatus in a thread. Or I could poll with
        # a reasonable interval. Guess what! Threads are hard.

        processed_events = 0
        if timeout is None:
            timeout = MAX_TIMEOUT
        else:
            timeout = min(MAX_TIMEOUT, int(1000 * timeout))
        rc, numBytes, key, evt = self.port.getEvent(timeout)
        while 1:
            if rc == WAIT_TIMEOUT:
                break
            if key != KEY_WAKEUP:
                assert key == KEY_NORMAL
                log.callWithLogger(
                    evt.owner, self._callEventCallback, rc, numBytes, evt
                )
                processed_events += 1
            if processed_events >= EVENTS_PER_LOOP:
                break
            rc, numBytes, key, evt = self.port.getEvent(0)

    def _callEventCallback(self, rc, numBytes, evt):
        owner = evt.owner
        why = None
        try:
            evt.callback(rc, numBytes, evt)
            handfn = getattr(owner, "getFileHandle", None)
            if not handfn:
                why = _NO_GETHANDLE
            elif handfn() == -1:
                why = _NO_FILEDESC
            if why:
                return  # ignore handles that were closed
        except BaseException:
            why = sys.exc_info()[1]
            log.err()
        if why:
            owner.loseConnection(failure.Failure(why))

    def installWaker(self):
        pass

    def wakeUp(self):
        self.port.postEvent(0, KEY_WAKEUP, None)

    def registerHandle(self, handle):
        self.port.addHandle(handle, KEY_NORMAL)

    def createSocket(self, af, stype):
        skt = socket.socket(af, stype)
        self.registerHandle(skt.fileno())
        return skt

    def listenTCP(self, port, factory, backlog=50, interface=""):
        """
        @see: twisted.internet.interfaces.IReactorTCP.listenTCP
        """
        p = tcp.Port(port, factory, backlog, interface, self)
        p.startListening()
        return p

    def connectTCP(self, host, port, factory, timeout=30, bindAddress=None):
        """
        @see: twisted.internet.interfaces.IReactorTCP.connectTCP
        """
        c = tcp.Connector(host, port, factory, timeout, bindAddress, self)
        c.connect()
        return c

    if TLSMemoryBIOFactory is not None:

        def listenSSL(self, port, factory, contextFactory, backlog=50, interface=""):
            """
            @see: twisted.internet.interfaces.IReactorSSL.listenSSL
            """
            port = self.listenTCP(
                port,
                TLSMemoryBIOFactory(contextFactory, False, factory),
                backlog,
                interface,
            )
            port._type = "TLS"
            return port

        def connectSSL(
            self, host, port, factory, contextFactory, timeout=30, bindAddress=None
        ):
            """
            @see: twisted.internet.interfaces.IReactorSSL.connectSSL
            """
            return self.connectTCP(
                host,
                port,
                TLSMemoryBIOFactory(contextFactory, True, factory),
                timeout,
                bindAddress,
            )

    else:

        def listenSSL(self, port, factory, contextFactory, backlog=50, interface=""):
            """
            Non-implementation of L{IReactorSSL.listenSSL}.  Some dependency
            is not satisfied.  This implementation always raises
            L{NotImplementedError}.
            """
            raise NotImplementedError(
                "pyOpenSSL 0.10 or newer is required for SSL support in "
                "iocpreactor. It is missing, so the reactor does not support "
                "SSL APIs."
            )

        def connectSSL(
            self, host, port, factory, contextFactory, timeout=30, bindAddress=None
        ):
            """
            Non-implementation of L{IReactorSSL.connectSSL}.  Some dependency
            is not satisfied.  This implementation always raises
            L{NotImplementedError}.
            """
            raise NotImplementedError(
                "pyOpenSSL 0.10 or newer is required for SSL support in "
                "iocpreactor. It is missing, so the reactor does not support "
                "SSL APIs."
            )

    def listenUDP(self, port, protocol, interface="", maxPacketSize=8192):
        """
        Connects a given L{DatagramProtocol} to the given numeric UDP port.

        @returns: object conforming to L{IListeningPort}.
        """
        p = udp.Port(port, protocol, interface, maxPacketSize, self)
        p.startListening()
        return p

    def listenMulticast(
        self, port, protocol, interface="", maxPacketSize=8192, listenMultiple=False
    ):
        """
        Connects a given DatagramProtocol to the given numeric UDP port.

        EXPERIMENTAL.

        @returns: object conforming to IListeningPort.
        """
        p = udp.MulticastPort(
            port, protocol, interface, maxPacketSize, self, listenMultiple
        )
        p.startListening()
        return p

    def spawnProcess(
        self,
        processProtocol,
        executable,
        args=(),
        env={},
        path=None,
        uid=None,
        gid=None,
        usePTY=0,
        childFDs=None,
    ):
        """
        Spawn a process.
        """
        if uid is not None:
            raise ValueError("Setting UID is unsupported on this platform.")
        if gid is not None:
            raise ValueError("Setting GID is unsupported on this platform.")
        if usePTY:
            raise ValueError("PTYs are unsupported on this platform.")
        if childFDs is not None:
            raise ValueError(
                "Custom child file descriptor mappings are unsupported on "
                "this platform."
            )
        return Process(self, processProtocol, executable, args, env, path)

    def removeAll(self):
        res = list(self.handles)
        self.handles.clear()
        return res


def install():
    r = IOCPReactor()
    main.installReactor(r)


__all__ = ["IOCPReactor", "install"]
