# -*- test-case-name: twisted.conch.test.test_connection -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
This module contains the implementation of the ssh-connection service, which
allows access to the shell and port-forwarding.

Maintainer: Paul Swartz
"""

import string
import struct

import twisted.internet.error
from twisted.conch import error
from twisted.conch.ssh import common, service
from twisted.internet import defer
from twisted.logger import Logger
from twisted.python.compat import nativeString, networkString


class SSHConnection(service.SSHService):
    """
    An implementation of the 'ssh-connection' service.  It is used to
    multiplex multiple channels over the single SSH connection.

    @ivar localChannelID: the next number to use as a local channel ID.
    @type localChannelID: L{int}
    @ivar channels: a L{dict} mapping a local channel ID to C{SSHChannel}
        subclasses.
    @type channels: L{dict}
    @ivar localToRemoteChannel: a L{dict} mapping a local channel ID to a
        remote channel ID.
    @type localToRemoteChannel: L{dict}
    @ivar channelsToRemoteChannel: a L{dict} mapping a C{SSHChannel} subclass
        to remote channel ID.
    @type channelsToRemoteChannel: L{dict}
    @ivar deferreds: a L{dict} mapping a local channel ID to a C{list} of
        C{Deferreds} for outstanding channel requests.  Also, the 'global'
        key stores the C{list} of pending global request C{Deferred}s.
    """

    name = b"ssh-connection"
    _log = Logger()

    def __init__(self):
        self.localChannelID = 0  # this is the current # to use for channel ID
        # local channel ID -> remote channel ID
        self.localToRemoteChannel = {}
        # local channel ID -> subclass of SSHChannel
        self.channels = {}
        # subclass of SSHChannel -> remote channel ID
        self.channelsToRemoteChannel = {}
        # local channel -> list of deferreds for pending requests
        # or 'global' -> list of deferreds for global requests
        self.deferreds = {"global": []}

        self.transport = None  # gets set later

    def serviceStarted(self):
        if hasattr(self.transport, "avatar"):
            self.transport.avatar.conn = self

    def serviceStopped(self):
        """
        Called when the connection is stopped.
        """
        # Close any fully open channels
        for channel in list(self.channelsToRemoteChannel.keys()):
            self.channelClosed(channel)
        # Indicate failure to any channels that were in the process of
        # opening but not yet open.
        while self.channels:
            (_, channel) = self.channels.popitem()
            channel.openFailed(twisted.internet.error.ConnectionLost())
        # Errback any unfinished global requests.
        self._cleanupGlobalDeferreds()

    def _cleanupGlobalDeferreds(self):
        """
        All pending requests that have returned a deferred must be errbacked
        when this service is stopped, otherwise they might be left uncalled and
        uncallable.
        """
        for d in self.deferreds["global"]:
            d.errback(error.ConchError("Connection stopped."))
        del self.deferreds["global"][:]

    # packet methods
    def ssh_GLOBAL_REQUEST(self, packet):
        """
        The other side has made a global request.  Payload::
            string  request type
            bool    want reply
            <request specific data>

        This dispatches to self.gotGlobalRequest.
        """
        requestType, rest = common.getNS(packet)
        wantReply, rest = ord(rest[0:1]), rest[1:]
        ret = self.gotGlobalRequest(requestType, rest)
        if wantReply:
            reply = MSG_REQUEST_FAILURE
            data = b""
            if ret:
                reply = MSG_REQUEST_SUCCESS
                if isinstance(ret, (tuple, list)):
                    data = ret[1]
            self.transport.sendPacket(reply, data)

    def ssh_REQUEST_SUCCESS(self, packet):
        """
        Our global request succeeded.  Get the appropriate Deferred and call
        it back with the packet we received.
        """
        self._log.debug("global request success")
        self.deferreds["global"].pop(0).callback(packet)

    def ssh_REQUEST_FAILURE(self, packet):
        """
        Our global request failed.  Get the appropriate Deferred and errback
        it with the packet we received.
        """
        self._log.debug("global request failure")
        self.deferreds["global"].pop(0).errback(
            error.ConchError("global request failed", packet)
        )

    def ssh_CHANNEL_OPEN(self, packet):
        """
        The other side wants to get a channel.  Payload::
            string  channel name
            uint32  remote channel number
            uint32  remote window size
            uint32  remote maximum packet size
            <channel specific data>

        We get a channel from self.getChannel(), give it a local channel number
        and notify the other side.  Then notify the channel by calling its
        channelOpen method.
        """
        channelType, rest = common.getNS(packet)
        senderChannel, windowSize, maxPacket = struct.unpack(">3L", rest[:12])
        packet = rest[12:]
        try:
            channel = self.getChannel(channelType, windowSize, maxPacket, packet)
            localChannel = self.localChannelID
            self.localChannelID += 1
            channel.id = localChannel
            self.channels[localChannel] = channel
            self.channelsToRemoteChannel[channel] = senderChannel
            self.localToRemoteChannel[localChannel] = senderChannel
            openConfirmPacket = (
                struct.pack(
                    ">4L",
                    senderChannel,
                    localChannel,
                    channel.localWindowSize,
                    channel.localMaxPacket,
                )
                + channel.specificData
            )
            self.transport.sendPacket(MSG_CHANNEL_OPEN_CONFIRMATION, openConfirmPacket)
            channel.channelOpen(packet)
        except Exception as e:
            self._log.failure("channel open failed")
            if isinstance(e, error.ConchError):
                textualInfo, reason = e.args
                if isinstance(textualInfo, int):
                    # See #3657 and #3071
                    textualInfo, reason = reason, textualInfo
            else:
                reason = OPEN_CONNECT_FAILED
                textualInfo = "unknown failure"
            self.transport.sendPacket(
                MSG_CHANNEL_OPEN_FAILURE,
                struct.pack(">2L", senderChannel, reason)
                + common.NS(networkString(textualInfo))
                + common.NS(b""),
            )

    def ssh_CHANNEL_OPEN_CONFIRMATION(self, packet):
        """
        The other side accepted our MSG_CHANNEL_OPEN request.  Payload::
            uint32  local channel number
            uint32  remote channel number
            uint32  remote window size
            uint32  remote maximum packet size
            <channel specific data>

        Find the channel using the local channel number and notify its
        channelOpen method.
        """
        (localChannel, remoteChannel, windowSize, maxPacket) = struct.unpack(
            ">4L", packet[:16]
        )
        specificData = packet[16:]
        channel = self.channels[localChannel]
        channel.conn = self
        self.localToRemoteChannel[localChannel] = remoteChannel
        self.channelsToRemoteChannel[channel] = remoteChannel
        channel.remoteWindowLeft = windowSize
        channel.remoteMaxPacket = maxPacket
        channel.channelOpen(specificData)

    def ssh_CHANNEL_OPEN_FAILURE(self, packet):
        """
        The other side did not accept our MSG_CHANNEL_OPEN request.  Payload::
            uint32  local channel number
            uint32  reason code
            string  reason description

        Find the channel using the local channel number and notify it by
        calling its openFailed() method.
        """
        localChannel, reasonCode = struct.unpack(">2L", packet[:8])
        reasonDesc = common.getNS(packet[8:])[0]
        channel = self.channels[localChannel]
        del self.channels[localChannel]
        channel.conn = self
        reason = error.ConchError(reasonDesc, reasonCode)
        channel.openFailed(reason)

    def ssh_CHANNEL_WINDOW_ADJUST(self, packet):
        """
        The other side is adding bytes to its window.  Payload::
            uint32  local channel number
            uint32  bytes to add

        Call the channel's addWindowBytes() method to add new bytes to the
        remote window.
        """
        localChannel, bytesToAdd = struct.unpack(">2L", packet[:8])
        channel = self.channels[localChannel]
        channel.addWindowBytes(bytesToAdd)

    def ssh_CHANNEL_DATA(self, packet):
        """
        The other side is sending us data.  Payload::
            uint32 local channel number
            string data

        Check to make sure the other side hasn't sent too much data (more
        than what's in the window, or more than the maximum packet size).  If
        they have, close the channel.  Otherwise, decrease the available
        window and pass the data to the channel's dataReceived().
        """
        localChannel, dataLength = struct.unpack(">2L", packet[:8])
        channel = self.channels[localChannel]
        # XXX should this move to dataReceived to put client in charge?
        if (
            dataLength > channel.localWindowLeft or dataLength > channel.localMaxPacket
        ):  # more data than we want
            self._log.error("too much data")
            self.sendClose(channel)
            return
            # packet = packet[:channel.localWindowLeft+4]
        data = common.getNS(packet[4:])[0]
        channel.localWindowLeft -= dataLength
        if channel.localWindowLeft < channel.localWindowSize // 2:
            self.adjustWindow(
                channel, channel.localWindowSize - channel.localWindowLeft
            )
        channel.dataReceived(data)

    def ssh_CHANNEL_EXTENDED_DATA(self, packet):
        """
        The other side is sending us exteneded data.  Payload::
            uint32  local channel number
            uint32  type code
            string  data

        Check to make sure the other side hasn't sent too much data (more
        than what's in the window, or than the maximum packet size).  If
        they have, close the channel.  Otherwise, decrease the available
        window and pass the data and type code to the channel's
        extReceived().
        """
        localChannel, typeCode, dataLength = struct.unpack(">3L", packet[:12])
        channel = self.channels[localChannel]
        if dataLength > channel.localWindowLeft or dataLength > channel.localMaxPacket:
            self._log.error("too much extdata")
            self.sendClose(channel)
            return
        data = common.getNS(packet[8:])[0]
        channel.localWindowLeft -= dataLength
        if channel.localWindowLeft < channel.localWindowSize // 2:
            self.adjustWindow(
                channel, channel.localWindowSize - channel.localWindowLeft
            )
        channel.extReceived(typeCode, data)

    def ssh_CHANNEL_EOF(self, packet):
        """
        The other side is not sending any more data.  Payload::
            uint32  local channel number

        Notify the channel by calling its eofReceived() method.
        """
        localChannel = struct.unpack(">L", packet[:4])[0]
        channel = self.channels[localChannel]
        channel.eofReceived()

    def ssh_CHANNEL_CLOSE(self, packet):
        """
        The other side is closing its end; it does not want to receive any
        more data.  Payload::
            uint32  local channel number

        Notify the channnel by calling its closeReceived() method.  If
        the channel has also sent a close message, call self.channelClosed().
        """
        localChannel = struct.unpack(">L", packet[:4])[0]
        channel = self.channels[localChannel]
        channel.closeReceived()
        channel.remoteClosed = True
        if channel.localClosed and channel.remoteClosed:
            self.channelClosed(channel)

    def ssh_CHANNEL_REQUEST(self, packet):
        """
        The other side is sending a request to a channel.  Payload::
            uint32  local channel number
            string  request name
            bool    want reply
            <request specific data>

        Pass the message to the channel's requestReceived method.  If the
        other side wants a reply, add callbacks which will send the
        reply.
        """
        localChannel = struct.unpack(">L", packet[:4])[0]
        requestType, rest = common.getNS(packet[4:])
        wantReply = ord(rest[0:1])
        channel = self.channels[localChannel]
        d = defer.maybeDeferred(channel.requestReceived, requestType, rest[1:])
        if wantReply:
            d.addCallback(self._cbChannelRequest, localChannel)
            d.addErrback(self._ebChannelRequest, localChannel)
            return d

    def _cbChannelRequest(self, result, localChannel):
        """
        Called back if the other side wanted a reply to a channel request.  If
        the result is true, send a MSG_CHANNEL_SUCCESS.  Otherwise, raise
        a C{error.ConchError}

        @param result: the value returned from the channel's requestReceived()
            method.  If it's False, the request failed.
        @type result: L{bool}
        @param localChannel: the local channel ID of the channel to which the
            request was made.
        @type localChannel: L{int}
        @raises ConchError: if the result is False.
        """
        if not result:
            raise error.ConchError("failed request")
        self.transport.sendPacket(
            MSG_CHANNEL_SUCCESS,
            struct.pack(">L", self.localToRemoteChannel[localChannel]),
        )

    def _ebChannelRequest(self, result, localChannel):
        """
        Called if the other wisde wanted a reply to the channel requeset and
        the channel request failed.

        @param result: a Failure, but it's not used.
        @param localChannel: the local channel ID of the channel to which the
            request was made.
        @type localChannel: L{int}
        """
        self.transport.sendPacket(
            MSG_CHANNEL_FAILURE,
            struct.pack(">L", self.localToRemoteChannel[localChannel]),
        )

    def ssh_CHANNEL_SUCCESS(self, packet):
        """
        Our channel request to the other side succeeded.  Payload::
            uint32  local channel number

        Get the C{Deferred} out of self.deferreds and call it back.
        """
        localChannel = struct.unpack(">L", packet[:4])[0]
        if self.deferreds.get(localChannel):
            d = self.deferreds[localChannel].pop(0)
            d.callback("")

    def ssh_CHANNEL_FAILURE(self, packet):
        """
        Our channel request to the other side failed.  Payload::
            uint32  local channel number

        Get the C{Deferred} out of self.deferreds and errback it with a
        C{error.ConchError}.
        """
        localChannel = struct.unpack(">L", packet[:4])[0]
        if self.deferreds.get(localChannel):
            d = self.deferreds[localChannel].pop(0)
            d.errback(error.ConchError("channel request failed"))

    # methods for users of the connection to call

    def sendGlobalRequest(self, request, data, wantReply=0):
        """
        Send a global request for this connection.  Current this is only used
        for remote->local TCP forwarding.

        @type request:      L{bytes}
        @type data:         L{bytes}
        @type wantReply:    L{bool}
        @rtype:             C{Deferred}/L{None}
        """
        self.transport.sendPacket(
            MSG_GLOBAL_REQUEST,
            common.NS(request) + (wantReply and b"\xff" or b"\x00") + data,
        )
        if wantReply:
            d = defer.Deferred()
            self.deferreds["global"].append(d)
            return d

    def openChannel(self, channel, extra=b""):
        """
        Open a new channel on this connection.

        @type channel:  subclass of C{SSHChannel}
        @type extra:    L{bytes}
        """
        self._log.info(
            "opening channel {id} with {localWindowSize} {localMaxPacket}",
            id=self.localChannelID,
            localWindowSize=channel.localWindowSize,
            localMaxPacket=channel.localMaxPacket,
        )
        self.transport.sendPacket(
            MSG_CHANNEL_OPEN,
            common.NS(channel.name)
            + struct.pack(
                ">3L",
                self.localChannelID,
                channel.localWindowSize,
                channel.localMaxPacket,
            )
            + extra,
        )
        channel.id = self.localChannelID
        self.channels[self.localChannelID] = channel
        self.localChannelID += 1

    def sendRequest(self, channel, requestType, data, wantReply=0):
        """
        Send a request to a channel.

        @type channel:      subclass of C{SSHChannel}
        @type requestType:  L{bytes}
        @type data:         L{bytes}
        @type wantReply:    L{bool}
        @rtype:             C{Deferred}/L{None}
        """
        if channel.localClosed:
            return
        self._log.debug("sending request {requestType}", requestType=requestType)
        self.transport.sendPacket(
            MSG_CHANNEL_REQUEST,
            struct.pack(">L", self.channelsToRemoteChannel[channel])
            + common.NS(requestType)
            + (b"\1" if wantReply else b"\0")
            + data,
        )
        if wantReply:
            d = defer.Deferred()
            self.deferreds.setdefault(channel.id, []).append(d)
            return d

    def adjustWindow(self, channel, bytesToAdd):
        """
        Tell the other side that we will receive more data.  This should not
        normally need to be called as it is managed automatically.

        @type channel:      subclass of L{SSHChannel}
        @type bytesToAdd:   L{int}
        """
        if channel.localClosed:
            return  # we're already closed
        packet = struct.pack(">2L", self.channelsToRemoteChannel[channel], bytesToAdd)
        self.transport.sendPacket(MSG_CHANNEL_WINDOW_ADJUST, packet)
        self._log.debug(
            "adding {bytesToAdd} to {localWindowLeft} in channel {id}",
            bytesToAdd=bytesToAdd,
            localWindowLeft=channel.localWindowLeft,
            id=channel.id,
        )
        channel.localWindowLeft += bytesToAdd

    def sendData(self, channel, data):
        """
        Send data to a channel.  This should not normally be used: instead use
        channel.write(data) as it manages the window automatically.

        @type channel:  subclass of L{SSHChannel}
        @type data:     L{bytes}
        """
        if channel.localClosed:
            return  # we're already closed
        self.transport.sendPacket(
            MSG_CHANNEL_DATA,
            struct.pack(">L", self.channelsToRemoteChannel[channel]) + common.NS(data),
        )

    def sendExtendedData(self, channel, dataType, data):
        """
        Send extended data to a channel.  This should not normally be used:
        instead use channel.writeExtendedData(data, dataType) as it manages
        the window automatically.

        @type channel:  subclass of L{SSHChannel}
        @type dataType: L{int}
        @type data:     L{bytes}
        """
        if channel.localClosed:
            return  # we're already closed
        self.transport.sendPacket(
            MSG_CHANNEL_EXTENDED_DATA,
            struct.pack(">2L", self.channelsToRemoteChannel[channel], dataType)
            + common.NS(data),
        )

    def sendEOF(self, channel):
        """
        Send an EOF (End of File) for a channel.

        @type channel:  subclass of L{SSHChannel}
        """
        if channel.localClosed:
            return  # we're already closed
        self._log.debug("sending eof")
        self.transport.sendPacket(
            MSG_CHANNEL_EOF, struct.pack(">L", self.channelsToRemoteChannel[channel])
        )

    def sendClose(self, channel):
        """
        Close a channel.

        @type channel:  subclass of L{SSHChannel}
        """
        if channel.localClosed:
            return  # we're already closed
        self._log.info("sending close {id}", id=channel.id)
        self.transport.sendPacket(
            MSG_CHANNEL_CLOSE, struct.pack(">L", self.channelsToRemoteChannel[channel])
        )
        channel.localClosed = True
        if channel.localClosed and channel.remoteClosed:
            self.channelClosed(channel)

    # methods to override
    def getChannel(self, channelType, windowSize, maxPacket, data):
        """
        The other side requested a channel of some sort.
        channelType is the type of channel being requested,
        windowSize is the initial size of the remote window,
        maxPacket is the largest packet we should send,
        data is any other packet data (often nothing).

        We return a subclass of L{SSHChannel}.

        By default, this dispatches to a method 'channel_channelType' with any
        non-alphanumerics in the channelType replace with _'s.  If it cannot
        find a suitable method, it returns an OPEN_UNKNOWN_CHANNEL_TYPE error.
        The method is called with arguments of windowSize, maxPacket, data.

        @type channelType:  L{bytes}
        @type windowSize:   L{int}
        @type maxPacket:    L{int}
        @type data:         L{bytes}
        @rtype:             subclass of L{SSHChannel}/L{tuple}
        """
        self._log.debug("got channel {channelType!r} request", channelType=channelType)
        if hasattr(self.transport, "avatar"):  # this is a server!
            chan = self.transport.avatar.lookupChannel(
                channelType, windowSize, maxPacket, data
            )
        else:
            channelType = channelType.translate(TRANSLATE_TABLE)
            attr = "channel_%s" % nativeString(channelType)
            f = getattr(self, attr, None)
            if f is not None:
                chan = f(windowSize, maxPacket, data)
            else:
                chan = None
        if chan is None:
            raise error.ConchError("unknown channel", OPEN_UNKNOWN_CHANNEL_TYPE)
        else:
            chan.conn = self
            return chan

    def gotGlobalRequest(self, requestType, data):
        """
        We got a global request.  pretty much, this is just used by the client
        to request that we forward a port from the server to the client.
        Returns either:
            - 1: request accepted
            - 1, <data>: request accepted with request specific data
            - 0: request denied

        By default, this dispatches to a method 'global_requestType' with
        -'s in requestType replaced with _'s.  The found method is passed data.
        If this method cannot be found, this method returns 0.  Otherwise, it
        returns the return value of that method.

        @type requestType:  L{bytes}
        @type data:         L{bytes}
        @rtype:             L{int}/L{tuple}
        """
        self._log.debug("got global {requestType} request", requestType=requestType)
        if hasattr(self.transport, "avatar"):  # this is a server!
            return self.transport.avatar.gotGlobalRequest(requestType, data)

        requestType = nativeString(requestType.replace(b"-", b"_"))
        f = getattr(self, "global_%s" % requestType, None)
        if not f:
            return 0
        return f(data)

    def channelClosed(self, channel):
        """
        Called when a channel is closed.
        It clears the local state related to the channel, and calls
        channel.closed().
        MAKE SURE YOU CALL THIS METHOD, even if you subclass L{SSHConnection}.
        If you don't, things will break mysteriously.

        @type channel: L{SSHChannel}
        """
        if channel in self.channelsToRemoteChannel:  # actually open
            channel.localClosed = channel.remoteClosed = True
            del self.localToRemoteChannel[channel.id]
            del self.channels[channel.id]
            del self.channelsToRemoteChannel[channel]
            for d in self.deferreds.pop(channel.id, []):
                d.errback(error.ConchError("Channel closed."))
            channel.closed()


MSG_GLOBAL_REQUEST = 80
MSG_REQUEST_SUCCESS = 81
MSG_REQUEST_FAILURE = 82
MSG_CHANNEL_OPEN = 90
MSG_CHANNEL_OPEN_CONFIRMATION = 91
MSG_CHANNEL_OPEN_FAILURE = 92
MSG_CHANNEL_WINDOW_ADJUST = 93
MSG_CHANNEL_DATA = 94
MSG_CHANNEL_EXTENDED_DATA = 95
MSG_CHANNEL_EOF = 96
MSG_CHANNEL_CLOSE = 97
MSG_CHANNEL_REQUEST = 98
MSG_CHANNEL_SUCCESS = 99
MSG_CHANNEL_FAILURE = 100

OPEN_ADMINISTRATIVELY_PROHIBITED = 1
OPEN_CONNECT_FAILED = 2
OPEN_UNKNOWN_CHANNEL_TYPE = 3
OPEN_RESOURCE_SHORTAGE = 4

# From RFC 4254
EXTENDED_DATA_STDERR = 1

messages = {}
for name, value in locals().copy().items():
    if name[:4] == "MSG_":
        messages[value] = name  # Doesn't handle doubles

alphanums = networkString(string.ascii_letters + string.digits)
TRANSLATE_TABLE = bytes(i if i in alphanums else ord("_") for i in range(256))
SSHConnection.protocolMessages = messages
