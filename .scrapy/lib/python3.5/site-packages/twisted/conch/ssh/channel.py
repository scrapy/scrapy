# -*- test-case-name: twisted.conch.test.test_channel -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
The parent class for all the SSH Channels.  Currently implemented channels
are session. direct-tcp, and forwarded-tcp.

Maintainer: Paul Swartz
"""

from __future__ import division, absolute_import

from zope.interface import implementer

from twisted.python import log
from twisted.python.compat import nativeString, intToBytes
from twisted.internet import interfaces



@implementer(interfaces.ITransport)
class SSHChannel(log.Logger):
    """
    A class that represents a multiplexed channel over an SSH connection.
    The channel has a local window which is the maximum amount of data it will
    receive, and a remote which is the maximum amount of data the remote side
    will accept.  There is also a maximum packet size for any individual data
    packet going each way.

    @ivar name: the name of the channel.
    @type name: L{bytes}
    @ivar localWindowSize: the maximum size of the local window in bytes.
    @type localWindowSize: L{int}
    @ivar localWindowLeft: how many bytes are left in the local window.
    @type localWindowLeft: L{int}
    @ivar localMaxPacket: the maximum size of packet we will accept in bytes.
    @type localMaxPacket: L{int}
    @ivar remoteWindowLeft: how many bytes are left in the remote window.
    @type remoteWindowLeft: L{int}
    @ivar remoteMaxPacket: the maximum size of a packet the remote side will
        accept in bytes.
    @type remoteMaxPacket: L{int}
    @ivar conn: the connection this channel is multiplexed through.
    @type conn: L{SSHConnection}
    @ivar data: any data to send to the other size when the channel is
        requested.
    @type data: L{bytes}
    @ivar avatar: an avatar for the logged-in user (if a server channel)
    @ivar localClosed: True if we aren't accepting more data.
    @type localClosed: L{bool}
    @ivar remoteClosed: True if the other size isn't accepting more data.
    @type remoteClosed: L{bool}
    """

    name = None # only needed for client channels

    def __init__(self, localWindow = 0, localMaxPacket = 0,
                       remoteWindow = 0, remoteMaxPacket = 0,
                       conn = None, data=None, avatar = None):
        self.localWindowSize = localWindow or 131072
        self.localWindowLeft = self.localWindowSize
        self.localMaxPacket = localMaxPacket or 32768
        self.remoteWindowLeft = remoteWindow
        self.remoteMaxPacket = remoteMaxPacket
        self.areWriting = 1
        self.conn = conn
        self.data = data
        self.avatar = avatar
        self.specificData = b''
        self.buf = b''
        self.extBuf = []
        self.closing = 0
        self.localClosed = 0
        self.remoteClosed = 0
        self.id = None # gets set later by SSHConnection


    def __str__(self):
        return nativeString(self.__bytes__())


    def __bytes__(self):
        """
        Return a byte string representation of the channel
        """
        name = self.name
        if not name:
            name = b'None'

        return (b'<SSHChannel ' + name +
                b' (lw ' + intToBytes(self.localWindowLeft) +
                b' rw ' + intToBytes(self.remoteWindowLeft) +
                b')>')


    def logPrefix(self):
        id = (self.id is not None and str(self.id)) or "unknown"
        name = self.name
        if name:
            name = nativeString(name)
        return "SSHChannel %s (%s) on %s" % (name, id,
                self.conn.logPrefix())


    def channelOpen(self, specificData):
        """
        Called when the channel is opened.  specificData is any data that the
        other side sent us when opening the channel.

        @type specificData: L{bytes}
        """
        log.msg('channel open')


    def openFailed(self, reason):
        """
        Called when the open failed for some reason.
        reason.desc is a string descrption, reason.code the SSH error code.

        @type reason: L{error.ConchError}
        """
        log.msg('other side refused open\nreason: %s'% reason)


    def addWindowBytes(self, data):
        """
        Called when bytes are added to the remote window.  By default it clears
        the data buffers.

        @type data:    L{bytes}
        """
        self.remoteWindowLeft = self.remoteWindowLeft+data
        if not self.areWriting and not self.closing:
            self.areWriting = True
            self.startWriting()
        if self.buf:
            b = self.buf
            self.buf = b''
            self.write(b)
        if self.extBuf:
            b = self.extBuf
            self.extBuf = []
            for (type, data) in b:
                self.writeExtended(type, data)


    def requestReceived(self, requestType, data):
        """
        Called when a request is sent to this channel.  By default it delegates
        to self.request_<requestType>.
        If this function returns true, the request succeeded, otherwise it
        failed.

        @type requestType:  L{bytes}
        @type data:         L{bytes}
        @rtype:             L{bool}
        """
        foo = nativeString(requestType.replace(b'-', b'_'))
        f = getattr(self, 'request_%s'%foo, None)
        if f:
            return f(data)
        log.msg('unhandled request for %s'%requestType)
        return 0


    def dataReceived(self, data):
        """
        Called when we receive data.

        @type data: L{bytes}
        """
        log.msg('got data %s'%repr(data))


    def extReceived(self, dataType, data):
        """
        Called when we receive extended data (usually standard error).

        @type dataType: L{int}
        @type data:     L{str}
        """
        log.msg('got extended data %s %s'%(dataType, repr(data)))


    def eofReceived(self):
        """
        Called when the other side will send no more data.
        """
        log.msg('remote eof')


    def closeReceived(self):
        """
        Called when the other side has closed the channel.
        """
        log.msg('remote close')
        self.loseConnection()


    def closed(self):
        """
        Called when the channel is closed.  This means that both our side and
        the remote side have closed the channel.
        """
        log.msg('closed')


    def write(self, data):
        """
        Write some data to the channel.  If there is not enough remote window
        available, buffer until it is.  Otherwise, split the data into
        packets of length remoteMaxPacket and send them.

        @type data: L{bytes}
        """
        if self.buf:
            self.buf += data
            return
        top = len(data)
        if top > self.remoteWindowLeft:
            data, self.buf = (data[:self.remoteWindowLeft],
                data[self.remoteWindowLeft:])
            self.areWriting = 0
            self.stopWriting()
            top = self.remoteWindowLeft
        rmp = self.remoteMaxPacket
        write = self.conn.sendData
        r = range(0, top, rmp)
        for offset in r:
            write(self, data[offset: offset+rmp])
        self.remoteWindowLeft -= top
        if self.closing and not self.buf:
            self.loseConnection() # try again


    def writeExtended(self, dataType, data):
        """
        Send extended data to this channel.  If there is not enough remote
        window available, buffer until there is.  Otherwise, split the data
        into packets of length remoteMaxPacket and send them.

        @type dataType: L{int}
        @type data:     L{bytes}
        """
        if self.extBuf:
            if self.extBuf[-1][0] == dataType:
                self.extBuf[-1][1] += data
            else:
                self.extBuf.append([dataType, data])
            return
        if len(data) > self.remoteWindowLeft:
            data, self.extBuf = (data[:self.remoteWindowLeft],
                                [[dataType, data[self.remoteWindowLeft:]]])
            self.areWriting = 0
            self.stopWriting()
        while len(data) > self.remoteMaxPacket:
            self.conn.sendExtendedData(self, dataType,
                                             data[:self.remoteMaxPacket])
            data = data[self.remoteMaxPacket:]
            self.remoteWindowLeft -= self.remoteMaxPacket
        if data:
            self.conn.sendExtendedData(self, dataType, data)
            self.remoteWindowLeft -= len(data)
        if self.closing:
            self.loseConnection() # try again


    def writeSequence(self, data):
        """
        Part of the Transport interface.  Write a list of strings to the
        channel.

        @type data: C{list} of L{str}
        """
        self.write(b''.join(data))


    def loseConnection(self):
        """
        Close the channel if there is no buferred data.  Otherwise, note the
        request and return.
        """
        self.closing = 1
        if not self.buf and not self.extBuf:
            self.conn.sendClose(self)


    def getPeer(self):
        """
        See: L{ITransport.getPeer}

        @return: The remote address of this connection.
        @rtype: L{SSHTransportAddress}.
        """
        return self.conn.transport.getPeer()


    def getHost(self):
        """
        See: L{ITransport.getHost}

        @return: An address describing this side of the connection.
        @rtype: L{SSHTransportAddress}.
        """
        return self.conn.transport.getHost()


    def stopWriting(self):
        """
        Called when the remote buffer is full, as a hint to stop writing.
        This can be ignored, but it can be helpful.
        """


    def startWriting(self):
        """
        Called when the remote buffer has more room, as a hint to continue
        writing.
        """
