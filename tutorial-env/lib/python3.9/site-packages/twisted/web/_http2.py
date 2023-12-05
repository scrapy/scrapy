# -*- test-case-name: twisted.web.test.test_http2 -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
HTTP2 Implementation

This is the basic server-side protocol implementation used by the Twisted
Web server for HTTP2.  This functionality is intended to be combined with the
HTTP/1.1 and HTTP/1.0 functionality in twisted.web.http to provide complete
protocol support for HTTP-type protocols.

This API is currently considered private because it's in early draft form. When
it has stabilised, it'll be made public.
"""


import io
from collections import deque
from typing import List

from zope.interface import implementer

import h2.config  # type: ignore[import]
import h2.connection  # type: ignore[import]
import h2.errors  # type: ignore[import]
import h2.events  # type: ignore[import]
import h2.exceptions  # type: ignore[import]
import priority  # type: ignore[import]

from twisted.internet._producer_helpers import _PullToPush
from twisted.internet.defer import Deferred
from twisted.internet.error import ConnectionLost
from twisted.internet.interfaces import (
    IConsumer,
    IProtocol,
    IPushProducer,
    ISSLTransport,
    ITransport,
)
from twisted.internet.protocol import Protocol
from twisted.logger import Logger
from twisted.protocols.policies import TimeoutMixin
from twisted.python.failure import Failure
from twisted.web.error import ExcessiveBufferingError

# This API is currently considered private.
__all__: List[str] = []


_END_STREAM_SENTINEL = object()


@implementer(IProtocol, IPushProducer)
class H2Connection(Protocol, TimeoutMixin):
    """
    A class representing a single HTTP/2 connection.

    This implementation of L{IProtocol} works hand in hand with L{H2Stream}.
    This is because we have the requirement to register multiple producers for
    a single HTTP/2 connection, one for each stream. The standard Twisted
    interfaces don't really allow for this, so instead there's a custom
    interface between the two objects that allows them to work hand-in-hand here.

    @ivar conn: The HTTP/2 connection state machine.
    @type conn: L{h2.connection.H2Connection}

    @ivar streams: A mapping of stream IDs to L{H2Stream} objects, used to call
        specific methods on streams when events occur.
    @type streams: L{dict}, mapping L{int} stream IDs to L{H2Stream} objects.

    @ivar priority: A HTTP/2 priority tree used to ensure that responses are
        prioritised appropriately.
    @type priority: L{priority.PriorityTree}

    @ivar _consumerBlocked: A flag tracking whether or not the L{IConsumer}
        that is consuming this data has asked us to stop producing.
    @type _consumerBlocked: L{bool}

    @ivar _sendingDeferred: A L{Deferred} used to restart the data-sending loop
        when more response data has been produced. Will not be present if there
        is outstanding data still to send.
    @type _consumerBlocked: A L{twisted.internet.defer.Deferred}, or L{None}

    @ivar _outboundStreamQueues: A map of stream IDs to queues, used to store
        data blocks that are yet to be sent on the connection. These are used
        both to handle producers that do not respect L{IConsumer} but also to
        allow priority to multiplex data appropriately.
    @type _outboundStreamQueues: A L{dict} mapping L{int} stream IDs to
        L{collections.deque} queues, which contain either L{bytes} objects or
        C{_END_STREAM_SENTINEL}.

    @ivar _sender: A handle to the data-sending loop, allowing it to be
        terminated if needed.
    @type _sender: L{twisted.internet.task.LoopingCall}

    @ivar abortTimeout: The number of seconds to wait after we attempt to shut
        the transport down cleanly to give up and forcibly terminate it. This
        is only used when we time a connection out, to prevent errors causing
        the FD to get leaked. If this is L{None}, we will wait forever.
    @type abortTimeout: L{int}

    @ivar _abortingCall: The L{twisted.internet.base.DelayedCall} that will be
        used to forcibly close the transport if it doesn't close cleanly.
    @type _abortingCall: L{twisted.internet.base.DelayedCall}
    """

    factory = None
    site = None
    abortTimeout = 15

    _log = Logger()
    _abortingCall = None

    def __init__(self, reactor=None):
        config = h2.config.H2Configuration(client_side=False, header_encoding=None)
        self.conn = h2.connection.H2Connection(config=config)
        self.streams = {}

        self.priority = priority.PriorityTree()
        self._consumerBlocked = None
        self._sendingDeferred = None
        self._outboundStreamQueues = {}
        self._streamCleanupCallbacks = {}
        self._stillProducing = True

        # Limit the number of buffered control frame (e.g. PING and
        # SETTINGS) bytes.
        self._maxBufferedControlFrameBytes = 1024 * 17
        self._bufferedControlFrames = deque()
        self._bufferedControlFrameBytes = 0

        if reactor is None:
            from twisted.internet import reactor
        self._reactor = reactor

        # Start the data sending function.
        self._reactor.callLater(0, self._sendPrioritisedData)

    # Implementation of IProtocol
    def connectionMade(self):
        """
        Called by the reactor when a connection is received. May also be called
        by the L{twisted.web.http._GenericHTTPChannelProtocol} during upgrade
        to HTTP/2.
        """
        self.setTimeout(self.timeOut)
        self.conn.initiate_connection()
        self.transport.write(self.conn.data_to_send())

    def dataReceived(self, data):
        """
        Called whenever a chunk of data is received from the transport.

        @param data: The data received from the transport.
        @type data: L{bytes}
        """
        try:
            events = self.conn.receive_data(data)
        except h2.exceptions.ProtocolError:
            stillActive = self._tryToWriteControlData()
            if stillActive:
                self.transport.loseConnection()
                self.connectionLost(Failure(), _cancelTimeouts=False)
            return

        # Only reset the timeout if we've received an actual H2
        # protocol message
        self.resetTimeout()

        for event in events:
            if isinstance(event, h2.events.RequestReceived):
                self._requestReceived(event)
            elif isinstance(event, h2.events.DataReceived):
                self._requestDataReceived(event)
            elif isinstance(event, h2.events.StreamEnded):
                self._requestEnded(event)
            elif isinstance(event, h2.events.StreamReset):
                self._requestAborted(event)
            elif isinstance(event, h2.events.WindowUpdated):
                self._handleWindowUpdate(event)
            elif isinstance(event, h2.events.PriorityUpdated):
                self._handlePriorityUpdate(event)
            elif isinstance(event, h2.events.ConnectionTerminated):
                self.transport.loseConnection()
                self.connectionLost(
                    Failure(ConnectionLost("Remote peer sent GOAWAY")),
                    _cancelTimeouts=False,
                )

        self._tryToWriteControlData()

    def timeoutConnection(self):
        """
        Called when the connection has been inactive for
        L{self.timeOut<twisted.protocols.policies.TimeoutMixin.timeOut>}
        seconds. Cleanly tears the connection down, attempting to notify the
        peer if needed.

        We override this method to add two extra bits of functionality:

         - We want to log the timeout.
         - We want to send a GOAWAY frame indicating that the connection is
           being terminated, and whether it was clean or not. We have to do this
           before the connection is torn down.
        """
        self._log.info("Timing out client {client}", client=self.transport.getPeer())

        # Check whether there are open streams. If there are, we're going to
        # want to use the error code PROTOCOL_ERROR. If there aren't, use
        # NO_ERROR.
        if self.conn.open_outbound_streams > 0 or self.conn.open_inbound_streams > 0:
            error_code = h2.errors.ErrorCodes.PROTOCOL_ERROR
        else:
            error_code = h2.errors.ErrorCodes.NO_ERROR

        self.conn.close_connection(error_code=error_code)
        self.transport.write(self.conn.data_to_send())

        # Don't let the client hold this connection open too long.
        if self.abortTimeout is not None:
            # We use self.callLater because that's what TimeoutMixin does, even
            # though we have a perfectly good reactor sitting around. See
            # https://twistedmatrix.com/trac/ticket/8488.
            self._abortingCall = self.callLater(
                self.abortTimeout, self.forceAbortClient
            )

        # We're done, throw the connection away.
        self.transport.loseConnection()

    def forceAbortClient(self):
        """
        Called if C{abortTimeout} seconds have passed since the timeout fired,
        and the connection still hasn't gone away. This can really only happen
        on extremely bad connections or when clients are maliciously attempting
        to keep connections open.
        """
        self._log.info(
            "Forcibly timing out client: {client}", client=self.transport.getPeer()
        )
        # We want to lose track of the _abortingCall so that no-one tries to
        # cancel it.
        self._abortingCall = None
        self.transport.abortConnection()

    def connectionLost(self, reason, _cancelTimeouts=True):
        """
        Called when the transport connection is lost.

        Informs all outstanding response handlers that the connection
        has been lost, and cleans up all internal state.

        @param reason: See L{IProtocol.connectionLost}

        @param _cancelTimeouts: Propagate the C{reason} to this
            connection's streams but don't cancel any timers, so that
            peers who never read the data we've written are eventually
            timed out.
        """
        self._stillProducing = False
        if _cancelTimeouts:
            self.setTimeout(None)

        for stream in self.streams.values():
            stream.connectionLost(reason)

        for streamID in list(self.streams.keys()):
            self._requestDone(streamID)

        # If we were going to force-close the transport, we don't have to now.
        if _cancelTimeouts and self._abortingCall is not None:
            self._abortingCall.cancel()
            self._abortingCall = None

    # Implementation of IPushProducer
    #
    # Here's how we handle IPushProducer. We have multiple outstanding
    # H2Streams. Each of these exposes an IConsumer interface to the response
    # handler that allows it to push data into the H2Stream. The H2Stream then
    # writes the data into the H2Connection object.
    #
    # The H2Connection needs to manage these writes to account for:
    #
    # - flow control
    # - priority
    #
    # We manage each of these in different ways.
    #
    # For flow control, we simply use the equivalent of the IPushProducer
    # interface. We simply tell the H2Stream: "Hey, you can't send any data
    # right now, sorry!". When that stream becomes unblocked, we free it up
    # again. This allows the H2Stream to propagate this backpressure up the
    # chain.
    #
    # For priority, we need to keep a backlog of data frames that we can send,
    # and interleave them appropriately. This backlog is most sensibly kept in
    # the H2Connection object itself. We keep one queue per stream, which is
    # where the writes go, and then we have a loop that manages popping these
    # streams off in priority order.
    #
    # Logically then, we go as follows:
    #
    # 1. Stream calls writeDataToStream(). This causes a DataFrame to be placed
    #    on the queue for that stream. It also informs the priority
    #    implementation that this stream is unblocked.
    # 2. The _sendPrioritisedData() function spins in a tight loop. Each
    #    iteration it asks the priority implementation which stream should send
    #    next, and pops a data frame off that stream's queue. If, after sending
    #    that frame, there is no data left on that stream's queue, the function
    #    informs the priority implementation that the stream is blocked.
    #
    # If all streams are blocked, or if there are no outstanding streams, the
    # _sendPrioritisedData function waits to be awoken when more data is ready
    # to send.
    #
    # Note that all of this only applies to *data*. Headers and other control
    # frames deliberately skip this processing as they are not subject to flow
    # control or priority constraints. Instead, they are stored in their own buffer
    # which is used primarily to detect excessive buffering.
    def stopProducing(self):
        """
        Stop producing data.

        This tells the L{H2Connection} that its consumer has died, so it must
        stop producing data for good.
        """
        self.connectionLost(Failure(ConnectionLost("Producing stopped")))

    def pauseProducing(self):
        """
        Pause producing data.

        Tells the L{H2Connection} that it has produced too much data to process
        for the time being, and to stop until resumeProducing() is called.
        """
        self._consumerBlocked = Deferred()
        # Ensure pending control data (if any) are sent first.
        self._consumerBlocked.addCallback(self._flushBufferedControlData)

    def resumeProducing(self):
        """
        Resume producing data.

        This tells the L{H2Connection} to re-add itself to the main loop and
        produce more data for the consumer.
        """
        if self._consumerBlocked is not None:
            d = self._consumerBlocked
            self._consumerBlocked = None
            d.callback(None)

    def _sendPrioritisedData(self, *args):
        """
        The data sending loop. This function repeatedly calls itself, either
        from L{Deferred}s or from
        L{reactor.callLater<twisted.internet.interfaces.IReactorTime.callLater>}

        This function sends data on streams according to the rules of HTTP/2
        priority. It ensures that the data from each stream is interleved
        according to the priority signalled by the client, making sure that the
        connection is used with maximal efficiency.

        This function will execute if data is available: if all data is
        exhausted, the function will place a deferred onto the L{H2Connection}
        object and wait until it is called to resume executing.
        """
        # If producing has stopped, we're done. Don't reschedule ourselves
        if not self._stillProducing:
            return

        stream = None

        while stream is None:
            try:
                stream = next(self.priority)
            except priority.DeadlockError:
                # All streams are currently blocked or not progressing. Wait
                # until a new one becomes available.
                assert self._sendingDeferred is None
                self._sendingDeferred = Deferred()
                self._sendingDeferred.addCallback(self._sendPrioritisedData)
                return

        # Wait behind the transport.
        if self._consumerBlocked is not None:
            self._consumerBlocked.addCallback(self._sendPrioritisedData)
            return

        self.resetTimeout()

        remainingWindow = self.conn.local_flow_control_window(stream)
        frameData = self._outboundStreamQueues[stream].popleft()
        maxFrameSize = min(self.conn.max_outbound_frame_size, remainingWindow)

        if frameData is _END_STREAM_SENTINEL:
            # There's no error handling here even though this can throw
            # ProtocolError because we really shouldn't encounter this problem.
            # If we do, that's a nasty bug.
            self.conn.end_stream(stream)
            self.transport.write(self.conn.data_to_send())

            # Clean up the stream
            self._requestDone(stream)
        else:
            # Respect the max frame size.
            if len(frameData) > maxFrameSize:
                excessData = frameData[maxFrameSize:]
                frameData = frameData[:maxFrameSize]
                self._outboundStreamQueues[stream].appendleft(excessData)

            # There's deliberately no error handling here, because this just
            # absolutely should not happen.
            # If for whatever reason the max frame length is zero and so we
            # have no frame data to send, don't send any.
            if frameData:
                self.conn.send_data(stream, frameData)
                self.transport.write(self.conn.data_to_send())

            # If there's no data left, this stream is now blocked.
            if not self._outboundStreamQueues[stream]:
                self.priority.block(stream)

            # Also, if the stream's flow control window is exhausted, tell it
            # to stop.
            if self.remainingOutboundWindow(stream) <= 0:
                self.streams[stream].flowControlBlocked()

        self._reactor.callLater(0, self._sendPrioritisedData)

    # Internal functions.
    def _requestReceived(self, event):
        """
        Internal handler for when a request has been received.

        @param event: The Hyper-h2 event that encodes information about the
            received request.
        @type event: L{h2.events.RequestReceived}
        """
        stream = H2Stream(
            event.stream_id,
            self,
            event.headers,
            self.requestFactory,
            self.site,
            self.factory,
        )
        self.streams[event.stream_id] = stream
        self._streamCleanupCallbacks[event.stream_id] = Deferred()
        self._outboundStreamQueues[event.stream_id] = deque()

        # Add the stream to the priority tree but immediately block it.
        try:
            self.priority.insert_stream(event.stream_id)
        except priority.DuplicateStreamError:
            # Stream already in the tree. This can happen if we received a
            # PRIORITY frame before a HEADERS frame. Just move on: we set the
            # stream up properly in _handlePriorityUpdate.
            pass
        else:
            self.priority.block(event.stream_id)

    def _requestDataReceived(self, event):
        """
        Internal handler for when a chunk of data is received for a given
        request.

        @param event: The Hyper-h2 event that encodes information about the
            received data.
        @type event: L{h2.events.DataReceived}
        """
        stream = self.streams[event.stream_id]
        stream.receiveDataChunk(event.data, event.flow_controlled_length)

    def _requestEnded(self, event):
        """
        Internal handler for when a request is complete, and we expect no
        further data for that request.

        @param event: The Hyper-h2 event that encodes information about the
            completed stream.
        @type event: L{h2.events.StreamEnded}
        """
        stream = self.streams[event.stream_id]
        stream.requestComplete()

    def _requestAborted(self, event):
        """
        Internal handler for when a request is aborted by a remote peer.

        @param event: The Hyper-h2 event that encodes information about the
            reset stream.
        @type event: L{h2.events.StreamReset}
        """
        stream = self.streams[event.stream_id]
        stream.connectionLost(
            Failure(ConnectionLost("Stream reset with code %s" % event.error_code))
        )
        self._requestDone(event.stream_id)

    def _handlePriorityUpdate(self, event):
        """
        Internal handler for when a stream priority is updated.

        @param event: The Hyper-h2 event that encodes information about the
            stream reprioritization.
        @type event: L{h2.events.PriorityUpdated}
        """
        try:
            self.priority.reprioritize(
                stream_id=event.stream_id,
                depends_on=event.depends_on or None,
                weight=event.weight,
                exclusive=event.exclusive,
            )
        except priority.MissingStreamError:
            # A PRIORITY frame arrived before the HEADERS frame that would
            # trigger us to insert the stream into the tree. That's fine: we
            # can create the stream here and mark it as blocked.
            self.priority.insert_stream(
                stream_id=event.stream_id,
                depends_on=event.depends_on or None,
                weight=event.weight,
                exclusive=event.exclusive,
            )
            self.priority.block(event.stream_id)

    def writeHeaders(self, version, code, reason, headers, streamID):
        """
        Called by L{twisted.web.http.Request} objects to write a complete set
        of HTTP headers to a stream.

        @param version: The HTTP version in use. Unused in HTTP/2.
        @type version: L{bytes}

        @param code: The HTTP status code to write.
        @type code: L{bytes}

        @param reason: The HTTP reason phrase to write. Unused in HTTP/2.
        @type reason: L{bytes}

        @param headers: The headers to write to the stream.
        @type headers: L{twisted.web.http_headers.Headers}

        @param streamID: The ID of the stream to write the headers to.
        @type streamID: L{int}
        """
        headers.insert(0, (b":status", code))

        try:
            self.conn.send_headers(streamID, headers)
        except h2.exceptions.StreamClosedError:
            # Stream was closed by the client at some point. We need to not
            # explode here: just swallow the error. That's what write() does
            # when a connection is lost, so that's what we do too.
            return
        else:
            self._tryToWriteControlData()

    def writeDataToStream(self, streamID, data):
        """
        May be called by L{H2Stream} objects to write response data to a given
        stream. Writes a single data frame.

        @param streamID: The ID of the stream to write the data to.
        @type streamID: L{int}

        @param data: The data chunk to write to the stream.
        @type data: L{bytes}
        """
        self._outboundStreamQueues[streamID].append(data)

        # There's obviously no point unblocking this stream and the sending
        # loop if the data can't actually be sent, so confirm that there's
        # some room to send data.
        if self.conn.local_flow_control_window(streamID) > 0:
            self.priority.unblock(streamID)
            if self._sendingDeferred is not None:
                d = self._sendingDeferred
                self._sendingDeferred = None
                d.callback(streamID)

        if self.remainingOutboundWindow(streamID) <= 0:
            self.streams[streamID].flowControlBlocked()

    def endRequest(self, streamID):
        """
        Called by L{H2Stream} objects to signal completion of a response.

        @param streamID: The ID of the stream to write the data to.
        @type streamID: L{int}
        """
        self._outboundStreamQueues[streamID].append(_END_STREAM_SENTINEL)
        self.priority.unblock(streamID)
        if self._sendingDeferred is not None:
            d = self._sendingDeferred
            self._sendingDeferred = None
            d.callback(streamID)

    def abortRequest(self, streamID):
        """
        Called by L{H2Stream} objects to request early termination of a stream.
        This emits a RstStream frame and then removes all stream state.

        @param streamID: The ID of the stream to write the data to.
        @type streamID: L{int}
        """
        self.conn.reset_stream(streamID)
        stillActive = self._tryToWriteControlData()
        if stillActive:
            self._requestDone(streamID)

    def _requestDone(self, streamID):
        """
        Called internally by the data sending loop to clean up state that was
        being used for the stream. Called when the stream is complete.

        @param streamID: The ID of the stream to clean up state for.
        @type streamID: L{int}
        """
        del self._outboundStreamQueues[streamID]
        self.priority.remove_stream(streamID)
        del self.streams[streamID]
        cleanupCallback = self._streamCleanupCallbacks.pop(streamID)
        cleanupCallback.callback(streamID)

    def remainingOutboundWindow(self, streamID):
        """
        Called to determine how much room is left in the send window for a
        given stream. Allows us to handle blocking and unblocking producers.

        @param streamID: The ID of the stream whose flow control window we'll
            check.
        @type streamID: L{int}

        @return: The amount of room remaining in the send window for the given
            stream, including the data queued to be sent.
        @rtype: L{int}
        """
        # TODO: This involves a fair bit of looping and computation for
        # something that is called a lot. Consider caching values somewhere.
        windowSize = self.conn.local_flow_control_window(streamID)
        sendQueue = self._outboundStreamQueues[streamID]
        alreadyConsumed = sum(
            len(chunk) for chunk in sendQueue if chunk is not _END_STREAM_SENTINEL
        )

        return windowSize - alreadyConsumed

    def _handleWindowUpdate(self, event):
        """
        Manage flow control windows.

        Streams that are blocked on flow control will register themselves with
        the connection. This will fire deferreds that wake those streams up and
        allow them to continue processing.

        @param event: The Hyper-h2 event that encodes information about the
            flow control window change.
        @type event: L{h2.events.WindowUpdated}
        """
        streamID = event.stream_id

        if streamID:
            if not self._streamIsActive(streamID):
                # We may have already cleaned up our stream state, making this
                # a late WINDOW_UPDATE frame. That's fine: the update is
                # unnecessary but benign. We'll ignore it.
                return

            # If we haven't got any data to send, don't unblock the stream. If
            # we do, we'll eventually get an exception inside the
            # _sendPrioritisedData loop some time later.
            if self._outboundStreamQueues.get(streamID):
                self.priority.unblock(streamID)
            self.streams[streamID].windowUpdated()
        else:
            # Update strictly applies to all streams.
            for stream in self.streams.values():
                stream.windowUpdated()

                # If we still have data to send for this stream, unblock it.
                if self._outboundStreamQueues.get(stream.streamID):
                    self.priority.unblock(stream.streamID)

    def getPeer(self):
        """
        Get the remote address of this connection.

        Treat this method with caution.  It is the unfortunate result of the
        CGI and Jabber standards, but should not be considered reliable for
        the usual host of reasons; port forwarding, proxying, firewalls, IP
        masquerading, etc.

        @return: An L{IAddress} provider.
        """
        return self.transport.getPeer()

    def getHost(self):
        """
        Similar to getPeer, but returns an address describing this side of the
        connection.

        @return: An L{IAddress} provider.
        """
        return self.transport.getHost()

    def openStreamWindow(self, streamID, increment):
        """
        Open the stream window by a given increment.

        @param streamID: The ID of the stream whose window needs to be opened.
        @type streamID: L{int}

        @param increment: The amount by which the stream window must be
        incremented.
        @type increment: L{int}
        """
        self.conn.acknowledge_received_data(increment, streamID)
        self._tryToWriteControlData()

    def _isSecure(self):
        """
        Returns L{True} if this channel is using a secure transport.

        @returns: L{True} if this channel is secure.
        @rtype: L{bool}
        """
        # A channel is secure if its transport is ISSLTransport.
        return ISSLTransport(self.transport, None) is not None

    def _send100Continue(self, streamID):
        """
        Sends a 100 Continue response, used to signal to clients that further
        processing will be performed.

        @param streamID: The ID of the stream that needs the 100 Continue
        response
        @type streamID: L{int}
        """
        headers = [(b":status", b"100")]
        self.conn.send_headers(headers=headers, stream_id=streamID)
        self._tryToWriteControlData()

    def _respondToBadRequestAndDisconnect(self, streamID):
        """
        This is a quick and dirty way of responding to bad requests.

        As described by HTTP standard we should be patient and accept the
        whole request from the client before sending a polite bad request
        response, even in the case when clients send tons of data.

        Unlike in the HTTP/1.1 case, this does not actually disconnect the
        underlying transport: there's no need. This instead just sends a 400
        response and terminates the stream.

        @param streamID: The ID of the stream that needs the 100 Continue
        response
        @type streamID: L{int}
        """
        headers = [(b":status", b"400")]
        self.conn.send_headers(headers=headers, stream_id=streamID, end_stream=True)
        stillActive = self._tryToWriteControlData()
        if stillActive:
            stream = self.streams[streamID]
            stream.connectionLost(Failure(ConnectionLost("Invalid request")))
            self._requestDone(streamID)

    def _streamIsActive(self, streamID):
        """
        Checks whether Twisted has still got state for a given stream and so
        can process events for that stream.

        @param streamID: The ID of the stream that needs processing.
        @type streamID: L{int}

        @return: Whether the stream still has state allocated.
        @rtype: L{bool}
        """
        return streamID in self.streams

    def _tryToWriteControlData(self):
        """
        Checks whether the connection is blocked on flow control and,
        if it isn't, writes any buffered control data.

        @return: L{True} if the connection is still active and
            L{False} if it was aborted because too many bytes have
            been written but not consumed by the other end.
        """
        bufferedBytes = self.conn.data_to_send()
        if not bufferedBytes:
            return True

        if self._consumerBlocked is None and not self._bufferedControlFrames:
            # The consumer isn't blocked, and we don't have any buffered frames:
            # write this directly.
            self.transport.write(bufferedBytes)
            return True
        else:
            # Either the consumer is blocked or we have buffered frames. If the
            # consumer is blocked, we'll write this when we unblock. If we have
            # buffered frames, we have presumably been re-entered from
            # transport.write, and so to avoid reordering issues we'll buffer anyway.
            self._bufferedControlFrames.append(bufferedBytes)
            self._bufferedControlFrameBytes += len(bufferedBytes)

            if self._bufferedControlFrameBytes >= self._maxBufferedControlFrameBytes:
                maxBuffCtrlFrameBytes = self._maxBufferedControlFrameBytes
                self._log.error(
                    "Maximum number of control frame bytes buffered: "
                    "{bufferedControlFrameBytes} > = "
                    "{maxBufferedControlFrameBytes}. "
                    "Aborting connection to client: {client} ",
                    bufferedControlFrameBytes=self._bufferedControlFrameBytes,
                    maxBufferedControlFrameBytes=maxBuffCtrlFrameBytes,
                    client=self.transport.getPeer(),
                )
                # We've exceeded a reasonable buffer size for max buffered
                # control frames. This is a denial of service risk, so we're
                # going to drop this connection.
                self.transport.abortConnection()
                self.connectionLost(Failure(ExcessiveBufferingError()))
                return False
            return True

    def _flushBufferedControlData(self, *args):
        """
        Called when the connection is marked writable again after being marked unwritable.
        Attempts to flush buffered control data if there is any.
        """
        # To respect backpressure here we send each write in order, paying attention to whether
        # we got blocked
        while self._consumerBlocked is None and self._bufferedControlFrames:
            nextWrite = self._bufferedControlFrames.popleft()
            self._bufferedControlFrameBytes -= len(nextWrite)
            self.transport.write(nextWrite)


@implementer(ITransport, IConsumer, IPushProducer)
class H2Stream:
    """
    A class representing a single HTTP/2 stream.

    This class works hand-in-hand with L{H2Connection}. It acts to provide an
    implementation of L{ITransport}, L{IConsumer}, and L{IProducer} that work
    for a single HTTP/2 connection, while tightly cleaving to the interface
    provided by those interfaces. It does this by having a tight coupling to
    L{H2Connection}, which allows associating many of the functions of
    L{ITransport}, L{IConsumer}, and L{IProducer} to objects on a
    stream-specific level.

    @ivar streamID: The numerical stream ID that this object corresponds to.
    @type streamID: L{int}

    @ivar producing: Whether this stream is currently allowed to produce data
        to its consumer.
    @type producing: L{bool}

    @ivar command: The HTTP verb used on the request.
    @type command: L{unicode}

    @ivar path: The HTTP path used on the request.
    @type path: L{unicode}

    @ivar producer: The object producing the response, if any.
    @type producer: L{IProducer}

    @ivar site: The L{twisted.web.server.Site} object this stream belongs to,
        if any.
    @type site: L{twisted.web.server.Site}

    @ivar factory: The L{twisted.web.http.HTTPFactory} object that constructed
        this stream's parent connection.
    @type factory: L{twisted.web.http.HTTPFactory}

    @ivar _producerProducing: Whether the producer stored in producer is
        currently producing data.
    @type _producerProducing: L{bool}

    @ivar _inboundDataBuffer: Any data that has been received from the network
        but has not yet been received by the consumer.
    @type _inboundDataBuffer: A L{collections.deque} containing L{bytes}

    @ivar _conn: A reference to the connection this stream belongs to.
    @type _conn: L{H2Connection}

    @ivar _request: A request object that this stream corresponds to.
    @type _request: L{twisted.web.iweb.IRequest}

    @ivar _buffer: A buffer containing data produced by the producer that could
        not be sent on the network at this time.
    @type _buffer: L{io.BytesIO}
    """

    # We need a transport property for t.w.h.Request, but HTTP/2 doesn't want
    # to expose it. So we just set it to None.
    transport = None

    def __init__(self, streamID, connection, headers, requestFactory, site, factory):
        """
        Initialize this HTTP/2 stream.

        @param streamID: The numerical stream ID that this object corresponds
            to.
        @type streamID: L{int}

        @param connection: The HTTP/2 connection this stream belongs to.
        @type connection: L{H2Connection}

        @param headers: The HTTP/2 request headers.
        @type headers: A L{list} of L{tuple}s of header name and header value,
            both as L{bytes}.

        @param requestFactory: A function that builds appropriate request
            request objects.
        @type requestFactory: A callable that returns a
            L{twisted.web.iweb.IRequest}.

        @param site: The L{twisted.web.server.Site} object this stream belongs
            to, if any.
        @type site: L{twisted.web.server.Site}

        @param factory: The L{twisted.web.http.HTTPFactory} object that
            constructed this stream's parent connection.
        @type factory: L{twisted.web.http.HTTPFactory}
        """

        self.streamID = streamID
        self.site = site
        self.factory = factory
        self.producing = True
        self.command = None
        self.path = None
        self.producer = None
        self._producerProducing = False
        self._hasStreamingProducer = None
        self._inboundDataBuffer = deque()
        self._conn = connection
        self._request = requestFactory(self, queued=False)
        self._buffer = io.BytesIO()

        self._convertHeaders(headers)

    def _convertHeaders(self, headers):
        """
        This method converts the HTTP/2 header set into something that looks
        like HTTP/1.1. In particular, it strips the 'special' headers and adds
        a Host: header.

        @param headers: The HTTP/2 header set.
        @type headers: A L{list} of L{tuple}s of header name and header value,
            both as L{bytes}.
        """
        gotLength = False

        for header in headers:
            if not header[0].startswith(b":"):
                gotLength = _addHeaderToRequest(self._request, header) or gotLength
            elif header[0] == b":method":
                self.command = header[1]
            elif header[0] == b":path":
                self.path = header[1]
            elif header[0] == b":authority":
                # This is essentially the Host: header from HTTP/1.1
                _addHeaderToRequest(self._request, (b"host", header[1]))

        if not gotLength:
            if self.command in (b"GET", b"HEAD"):
                self._request.gotLength(0)
            else:
                self._request.gotLength(None)

        self._request.parseCookies()
        expectContinue = self._request.requestHeaders.getRawHeaders(b"expect")
        if expectContinue and expectContinue[0].lower() == b"100-continue":
            self._send100Continue()

    # Methods called by the H2Connection
    def receiveDataChunk(self, data, flowControlledLength):
        """
        Called when the connection has received a chunk of data from the
        underlying transport. If the stream has been registered with a
        consumer, and is currently able to push data, immediately passes it
        through. Otherwise, buffers the chunk until we can start producing.

        @param data: The chunk of data that was received.
        @type data: L{bytes}

        @param flowControlledLength: The total flow controlled length of this
            chunk, which is used when we want to re-open the window. May be
            different to C{len(data)}.
        @type flowControlledLength: L{int}
        """
        if not self.producing:
            # Buffer data.
            self._inboundDataBuffer.append((data, flowControlledLength))
        else:
            self._request.handleContentChunk(data)
            self._conn.openStreamWindow(self.streamID, flowControlledLength)

    def requestComplete(self):
        """
        Called by the L{H2Connection} when the all data for a request has been
        received. Currently, with the legacy L{twisted.web.http.Request}
        object, just calls requestReceived unless the producer wants us to be
        quiet.
        """
        if self.producing:
            self._request.requestReceived(self.command, self.path, b"HTTP/2")
        else:
            self._inboundDataBuffer.append((_END_STREAM_SENTINEL, None))

    def connectionLost(self, reason):
        """
        Called by the L{H2Connection} when a connection is lost or a stream is
        reset.

        @param reason: The reason the connection was lost.
        @type reason: L{str}
        """
        self._request.connectionLost(reason)

    def windowUpdated(self):
        """
        Called by the L{H2Connection} when this stream's flow control window
        has been opened.
        """
        # If we don't have a producer, we have no-one to tell.
        if not self.producer:
            return

        # If we're not blocked on flow control, we don't care.
        if self._producerProducing:
            return

        # We check whether the stream's flow control window is actually above
        # 0, and then, if a producer is registered and we still have space in
        # the window, we unblock it.
        remainingWindow = self._conn.remainingOutboundWindow(self.streamID)
        if not remainingWindow > 0:
            return

        # We have a producer and space in the window, so that producer can
        # start producing again!
        self._producerProducing = True
        self.producer.resumeProducing()

    def flowControlBlocked(self):
        """
        Called by the L{H2Connection} when this stream's flow control window
        has been exhausted.
        """
        if not self.producer:
            return

        if self._producerProducing:
            self.producer.pauseProducing()
            self._producerProducing = False

    # Methods called by the consumer (usually an IRequest).
    def writeHeaders(self, version, code, reason, headers):
        """
        Called by the consumer to write headers to the stream.

        @param version: The HTTP version.
        @type version: L{bytes}

        @param code: The status code.
        @type code: L{int}

        @param reason: The reason phrase. Ignored in HTTP/2.
        @type reason: L{bytes}

        @param headers: The HTTP response headers.
        @type headers: Any iterable of two-tuples of L{bytes}, representing header
            names and header values.
        """
        self._conn.writeHeaders(version, code, reason, headers, self.streamID)

    def requestDone(self, request):
        """
        Called by a consumer to clean up whatever permanent state is in use.

        @param request: The request calling the method.
        @type request: L{twisted.web.iweb.IRequest}
        """
        self._conn.endRequest(self.streamID)

    def _send100Continue(self):
        """
        Sends a 100 Continue response, used to signal to clients that further
        processing will be performed.
        """
        self._conn._send100Continue(self.streamID)

    def _respondToBadRequestAndDisconnect(self):
        """
        This is a quick and dirty way of responding to bad requests.

        As described by HTTP standard we should be patient and accept the
        whole request from the client before sending a polite bad request
        response, even in the case when clients send tons of data.

        Unlike in the HTTP/1.1 case, this does not actually disconnect the
        underlying transport: there's no need. This instead just sends a 400
        response and terminates the stream.
        """
        self._conn._respondToBadRequestAndDisconnect(self.streamID)

    # Implementation: ITransport
    def write(self, data):
        """
        Write a single chunk of data into a data frame.

        @param data: The data chunk to send.
        @type data: L{bytes}
        """
        self._conn.writeDataToStream(self.streamID, data)
        return

    def writeSequence(self, iovec):
        """
        Write a sequence of chunks of data into data frames.

        @param iovec: A sequence of chunks to send.
        @type iovec: An iterable of L{bytes} chunks.
        """
        for chunk in iovec:
            self.write(chunk)

    def loseConnection(self):
        """
        Close the connection after writing all pending data.
        """
        self._conn.endRequest(self.streamID)

    def abortConnection(self):
        """
        Forcefully abort the connection by sending a RstStream frame.
        """
        self._conn.abortRequest(self.streamID)

    def getPeer(self):
        """
        Get information about the peer.
        """
        return self._conn.getPeer()

    def getHost(self):
        """
        Similar to getPeer, but for this side of the connection.
        """
        return self._conn.getHost()

    def isSecure(self):
        """
        Returns L{True} if this channel is using a secure transport.

        @returns: L{True} if this channel is secure.
        @rtype: L{bool}
        """
        return self._conn._isSecure()

    # Implementation: IConsumer
    def registerProducer(self, producer, streaming):
        """
        Register to receive data from a producer.

        This sets self to be a consumer for a producer.  When this object runs
        out of data (as when a send(2) call on a socket succeeds in moving the
        last data from a userspace buffer into a kernelspace buffer), it will
        ask the producer to resumeProducing().

        For L{IPullProducer} providers, C{resumeProducing} will be called once
        each time data is required.

        For L{IPushProducer} providers, C{pauseProducing} will be called
        whenever the write buffer fills up and C{resumeProducing} will only be
        called when it empties.

        @param producer: The producer to register.
        @type producer: L{IProducer} provider

        @param streaming: L{True} if C{producer} provides L{IPushProducer},
        L{False} if C{producer} provides L{IPullProducer}.
        @type streaming: L{bool}

        @raise RuntimeError: If a producer is already registered.

        @return: L{None}
        """
        if self.producer:
            raise ValueError(
                "registering producer %s before previous one (%s) was "
                "unregistered" % (producer, self.producer)
            )

        if not streaming:
            self.hasStreamingProducer = False
            producer = _PullToPush(producer, self)
            producer.startStreaming()
        else:
            self.hasStreamingProducer = True

        self.producer = producer
        self._producerProducing = True

    def unregisterProducer(self):
        """
        @see: L{IConsumer.unregisterProducer}
        """
        # When the producer is unregistered, we're done.
        if self.producer is not None and not self.hasStreamingProducer:
            self.producer.stopStreaming()

        self._producerProducing = False
        self.producer = None
        self.hasStreamingProducer = None

    # Implementation: IPushProducer
    def stopProducing(self):
        """
        @see: L{IProducer.stopProducing}
        """
        self.producing = False
        self.abortConnection()

    def pauseProducing(self):
        """
        @see: L{IPushProducer.pauseProducing}
        """
        self.producing = False

    def resumeProducing(self):
        """
        @see: L{IPushProducer.resumeProducing}
        """
        self.producing = True
        consumedLength = 0

        while self.producing and self._inboundDataBuffer:
            # Allow for pauseProducing to be called in response to a call to
            # resumeProducing.
            chunk, flowControlledLength = self._inboundDataBuffer.popleft()

            if chunk is _END_STREAM_SENTINEL:
                self.requestComplete()
            else:
                consumedLength += flowControlledLength
                self._request.handleContentChunk(chunk)

        self._conn.openStreamWindow(self.streamID, consumedLength)


def _addHeaderToRequest(request, header):
    """
    Add a header tuple to a request header object.

    @param request: The request to add the header tuple to.
    @type request: L{twisted.web.http.Request}

    @param header: The header tuple to add to the request.
    @type header: A L{tuple} with two elements, the header name and header
        value, both as L{bytes}.

    @return: If the header being added was the C{Content-Length} header.
    @rtype: L{bool}
    """
    requestHeaders = request.requestHeaders
    name, value = header
    values = requestHeaders.getRawHeaders(name)

    if values is not None:
        values.append(value)
    else:
        requestHeaders.setRawHeaders(name, [value])

    if name == b"content-length":
        request.gotLength(int(value))
        return True

    return False
