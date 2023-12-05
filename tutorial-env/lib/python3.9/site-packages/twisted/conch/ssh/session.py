# -*- test-case-name: twisted.conch.test.test_session -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
This module contains the implementation of SSHSession, which (by default)
allows access to a shell and a python interpreter over SSH.

Maintainer: Paul Swartz
"""


import os
import signal
import struct
import sys

from zope.interface import implementer

from twisted.conch.interfaces import (
    EnvironmentVariableNotPermitted,
    ISession,
    ISessionSetEnv,
)
from twisted.conch.ssh import channel, common, connection
from twisted.internet import interfaces, protocol
from twisted.logger import Logger
from twisted.python.compat import networkString

log = Logger()


class SSHSession(channel.SSHChannel):
    """
    A generalized implementation of an SSH session.

    See RFC 4254, section 6.

    The precise implementation of the various operations that the remote end
    can send is left up to the avatar, usually via an adapter to an
    interface such as L{ISession}.

    @ivar buf: a buffer for data received before making a connection to a
        client.
    @type buf: L{bytes}
    @ivar client: a protocol for communication with a shell, an application
        program, or a subsystem (see RFC 4254, section 6.5).
    @type client: L{SSHSessionProcessProtocol}
    @ivar session: an object providing concrete implementations of session
        operations.
    @type session: L{ISession}
    """

    name = b"session"

    def __init__(self, *args, **kw):
        channel.SSHChannel.__init__(self, *args, **kw)
        self.buf = b""
        self.client = None
        self.session = None

    def request_subsystem(self, data):
        subsystem, ignored = common.getNS(data)
        log.info('Asking for subsystem "{subsystem}"', subsystem=subsystem)
        client = self.avatar.lookupSubsystem(subsystem, data)
        if client:
            pp = SSHSessionProcessProtocol(self)
            proto = wrapProcessProtocol(pp)
            client.makeConnection(proto)
            pp.makeConnection(wrapProtocol(client))
            self.client = pp
            return 1
        else:
            log.error("Failed to get subsystem")
            return 0

    def request_shell(self, data):
        log.info("Getting shell")
        if not self.session:
            self.session = ISession(self.avatar)
        try:
            pp = SSHSessionProcessProtocol(self)
            self.session.openShell(pp)
        except Exception:
            log.failure("Error getting shell")
            return 0
        else:
            self.client = pp
            return 1

    def request_exec(self, data):
        if not self.session:
            self.session = ISession(self.avatar)
        f, data = common.getNS(data)
        log.info('Executing command "{f}"', f=f)
        try:
            pp = SSHSessionProcessProtocol(self)
            self.session.execCommand(pp, f)
        except Exception:
            log.failure('Error executing command "{f}"', f=f)
            return 0
        else:
            self.client = pp
            return 1

    def request_pty_req(self, data):
        if not self.session:
            self.session = ISession(self.avatar)
        term, windowSize, modes = parseRequest_pty_req(data)
        log.info(
            "Handling pty request: {term!r} {windowSize!r}",
            term=term,
            windowSize=windowSize,
        )
        try:
            self.session.getPty(term, windowSize, modes)
        except Exception:
            log.failure("Error handling pty request")
            return 0
        else:
            return 1

    def request_env(self, data):
        """
        Process a request to pass an environment variable.

        @param data: The environment variable name and value, each encoded
            as an SSH protocol string and concatenated.
        @type data: L{bytes}
        @return: A true value if the request to pass this environment
            variable was accepted, otherwise a false value.
        """
        if not self.session:
            self.session = ISession(self.avatar)
        if not ISessionSetEnv.providedBy(self.session):
            return 0
        name, value, data = common.getNS(data, 2)
        try:
            self.session.setEnv(name, value)
        except EnvironmentVariableNotPermitted:
            return 0
        except Exception:
            log.failure("Error setting environment variable {name}", name=name)
            return 0
        else:
            return 1

    def request_window_change(self, data):
        if not self.session:
            self.session = ISession(self.avatar)
        winSize = parseRequest_window_change(data)
        try:
            self.session.windowChanged(winSize)
        except Exception:
            log.failure("Error changing window size")
            return 0
        else:
            return 1

    def dataReceived(self, data):
        if not self.client:
            # self.conn.sendClose(self)
            self.buf += data
            return
        self.client.transport.write(data)

    def extReceived(self, dataType, data):
        if dataType == connection.EXTENDED_DATA_STDERR:
            if self.client and hasattr(self.client.transport, "writeErr"):
                self.client.transport.writeErr(data)
        else:
            log.warn("Weird extended data: {dataType}", dataType=dataType)

    def eofReceived(self):
        # If we have a session, tell it that EOF has been received and
        # expect it to send a close message (it may need to send other
        # messages such as exit-status or exit-signal first).  If we don't
        # have a session, then just send a close message directly.
        if self.session:
            self.session.eofReceived()
        elif self.client:
            self.conn.sendClose(self)

    def closed(self):
        if self.client and self.client.transport:
            self.client.transport.loseConnection()
        if self.session:
            self.session.closed()

    # def closeReceived(self):
    #    self.loseConnection() # don't know what to do with this

    def loseConnection(self):
        if self.client:
            self.client.transport.loseConnection()
        channel.SSHChannel.loseConnection(self)


class _ProtocolWrapper(protocol.ProcessProtocol):
    """
    This class wraps a L{Protocol} instance in a L{ProcessProtocol} instance.
    """

    def __init__(self, proto):
        self.proto = proto

    def connectionMade(self):
        self.proto.connectionMade()

    def outReceived(self, data):
        self.proto.dataReceived(data)

    def processEnded(self, reason):
        self.proto.connectionLost(reason)


class _DummyTransport:
    def __init__(self, proto):
        self.proto = proto

    def dataReceived(self, data):
        self.proto.transport.write(data)

    def write(self, data):
        self.proto.dataReceived(data)

    def writeSequence(self, seq):
        self.write(b"".join(seq))

    def loseConnection(self):
        self.proto.connectionLost(protocol.connectionDone)


def wrapProcessProtocol(inst):
    if isinstance(inst, protocol.Protocol):
        return _ProtocolWrapper(inst)
    else:
        return inst


def wrapProtocol(proto):
    return _DummyTransport(proto)


# SUPPORTED_SIGNALS is a list of signals that every session channel is supposed
# to accept.  See RFC 4254
SUPPORTED_SIGNALS = [
    "ABRT",
    "ALRM",
    "FPE",
    "HUP",
    "ILL",
    "INT",
    "KILL",
    "PIPE",
    "QUIT",
    "SEGV",
    "TERM",
    "USR1",
    "USR2",
]


@implementer(interfaces.ITransport)
class SSHSessionProcessProtocol(protocol.ProcessProtocol):
    """I am both an L{IProcessProtocol} and an L{ITransport}.

    I am a transport to the remote endpoint and a process protocol to the
    local subsystem.
    """

    # once initialized, a dictionary mapping signal values to strings
    # that follow RFC 4254.
    _signalValuesToNames = None

    def __init__(self, session):
        self.session = session
        self.lostOutOrErrFlag = False

    def connectionMade(self):
        if self.session.buf:
            self.transport.write(self.session.buf)
            self.session.buf = None

    def outReceived(self, data):
        self.session.write(data)

    def errReceived(self, err):
        self.session.writeExtended(connection.EXTENDED_DATA_STDERR, err)

    def outConnectionLost(self):
        """
        EOF should only be sent when both STDOUT and STDERR have been closed.
        """
        if self.lostOutOrErrFlag:
            self.session.conn.sendEOF(self.session)
        else:
            self.lostOutOrErrFlag = True

    def errConnectionLost(self):
        """
        See outConnectionLost().
        """
        self.outConnectionLost()

    def connectionLost(self, reason=None):
        self.session.loseConnection()

    def _getSignalName(self, signum):
        """
        Get a signal name given a signal number.
        """
        if self._signalValuesToNames is None:
            self._signalValuesToNames = {}
            # make sure that the POSIX ones are the defaults
            for signame in SUPPORTED_SIGNALS:
                signame = "SIG" + signame
                sigvalue = getattr(signal, signame, None)
                if sigvalue is not None:
                    self._signalValuesToNames[sigvalue] = signame
            for k, v in signal.__dict__.items():
                # Check for platform specific signals, ignoring Python specific
                # SIG_DFL and SIG_IGN
                if k.startswith("SIG") and not k.startswith("SIG_"):
                    if v not in self._signalValuesToNames:
                        self._signalValuesToNames[v] = k + "@" + sys.platform
        return self._signalValuesToNames[signum]

    def processEnded(self, reason=None):
        """
        When we are told the process ended, try to notify the other side about
        how the process ended using the exit-signal or exit-status requests.
        Also, close the channel.
        """
        if reason is not None:
            err = reason.value
            if err.signal is not None:
                signame = self._getSignalName(err.signal)
                if getattr(os, "WCOREDUMP", None) is not None and os.WCOREDUMP(
                    err.status
                ):
                    log.info("exitSignal: {signame} (core dumped)", signame=signame)
                    coreDumped = True
                else:
                    log.info("exitSignal: {}", signame=signame)
                    coreDumped = False
                self.session.conn.sendRequest(
                    self.session,
                    b"exit-signal",
                    common.NS(networkString(signame[3:]))
                    + (b"\1" if coreDumped else b"\0")
                    + common.NS(b"")
                    + common.NS(b""),
                )
            elif err.exitCode is not None:
                log.info("exitCode: {exitCode!r}", exitCode=err.exitCode)
                self.session.conn.sendRequest(
                    self.session, b"exit-status", struct.pack(">L", err.exitCode)
                )
        self.session.loseConnection()

    def getHost(self):
        """
        Return the host from my session's transport.
        """
        return self.session.conn.transport.getHost()

    def getPeer(self):
        """
        Return the peer from my session's transport.
        """
        return self.session.conn.transport.getPeer()

    def write(self, data):
        self.session.write(data)

    def writeSequence(self, seq):
        self.session.write(b"".join(seq))

    def loseConnection(self):
        self.session.loseConnection()


class SSHSessionClient(protocol.Protocol):
    def dataReceived(self, data):
        if self.transport:
            self.transport.write(data)


# methods factored out to make live easier on server writers
def parseRequest_pty_req(data):
    """Parse the data from a pty-req request into usable data.

    @returns: a tuple of (terminal type, (rows, cols, xpixel, ypixel), modes)
    """
    term, rest = common.getNS(data)
    cols, rows, xpixel, ypixel = struct.unpack(">4L", rest[:16])
    modes, ignored = common.getNS(rest[16:])
    winSize = (rows, cols, xpixel, ypixel)
    modes = [
        (ord(modes[i : i + 1]), struct.unpack(">L", modes[i + 1 : i + 5])[0])
        for i in range(0, len(modes) - 1, 5)
    ]
    return term, winSize, modes


def packRequest_pty_req(term, geometry, modes):
    """
    Pack a pty-req request so that it is suitable for sending.

    NOTE: modes must be packed before being sent here.

    @type geometry: L{tuple}
    @param geometry: A tuple of (rows, columns, xpixel, ypixel)
    """
    (rows, cols, xpixel, ypixel) = geometry
    termPacked = common.NS(term)
    winSizePacked = struct.pack(">4L", cols, rows, xpixel, ypixel)
    modesPacked = common.NS(modes)  # depend on the client packing modes
    return termPacked + winSizePacked + modesPacked


def parseRequest_window_change(data):
    """Parse the data from a window-change request into usuable data.

    @returns: a tuple of (rows, cols, xpixel, ypixel)
    """
    cols, rows, xpixel, ypixel = struct.unpack(">4L", data)
    return rows, cols, xpixel, ypixel


def packRequest_window_change(geometry):
    """
    Pack a window-change request so that it is suitable for sending.

    @type geometry: L{tuple}
    @param geometry: A tuple of (rows, columns, xpixel, ypixel)
    """
    (rows, cols, xpixel, ypixel) = geometry
    return struct.pack(">4L", cols, rows, xpixel, ypixel)
