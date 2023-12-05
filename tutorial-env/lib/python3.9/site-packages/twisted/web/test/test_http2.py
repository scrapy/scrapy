# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test HTTP/2 support.
"""


import itertools

from zope.interface import directlyProvides, providedBy

from twisted.internet import defer, error, reactor, task
from twisted.internet.address import IPv4Address
from twisted.internet.testing import MemoryReactorClock, StringTransport
from twisted.python import failure
from twisted.python.compat import iterbytes
from twisted.test.test_internet import DummyProducer
from twisted.trial import unittest
from twisted.web import http
from twisted.web.test.test_http import (
    DelayedHTTPHandler,
    DelayedHTTPHandlerProxy,
    DummyHTTPHandler,
    DummyHTTPHandlerProxy,
    DummyPullProducerHandlerProxy,
    _IDeprecatedHTTPChannelToRequestInterfaceProxy,
    _makeRequestProxyFactory,
)

skipH2 = None

try:
    # These third-party imports are guaranteed to be present if HTTP/2 support
    # is compiled in. We do not use them in the main code: only in the tests.
    import h2  # type: ignore[import]
    import h2.errors  # type: ignore[import]
    import h2.exceptions  # type: ignore[import]
    import hyperframe
    import priority  # type: ignore[import]
    from hpack.hpack import Decoder, Encoder  # type: ignore[import]

    from twisted.web._http2 import H2Connection
except ImportError:
    skipH2 = "HTTP/2 support not enabled"


# Define some helpers for the rest of these tests.
class FrameFactory:
    """
    A class containing lots of helper methods and state to build frames. This
    allows test cases to easily build correct HTTP/2 frames to feed to
    hyper-h2.
    """

    def __init__(self):
        self.encoder = Encoder()

    def refreshEncoder(self):
        self.encoder = Encoder()

    def clientConnectionPreface(self):
        return b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"

    def buildHeadersFrame(self, headers, flags=[], streamID=1, **priorityKwargs):
        """
        Builds a single valid headers frame out of the contained headers.
        """
        f = hyperframe.frame.HeadersFrame(streamID)
        f.data = self.encoder.encode(headers)
        f.flags.add("END_HEADERS")
        for flag in flags:
            f.flags.add(flag)

        for k, v in priorityKwargs.items():
            setattr(f, k, v)

        return f

    def buildDataFrame(self, data, flags=None, streamID=1):
        """
        Builds a single data frame out of a chunk of data.
        """
        flags = set(flags) if flags is not None else set()
        f = hyperframe.frame.DataFrame(streamID)
        f.data = data
        f.flags = flags
        return f

    def buildSettingsFrame(self, settings, ack=False):
        """
        Builds a single settings frame.
        """
        f = hyperframe.frame.SettingsFrame(0)
        if ack:
            f.flags.add("ACK")

        f.settings = settings
        return f

    def buildWindowUpdateFrame(self, streamID, increment):
        """
        Builds a single WindowUpdate frame.
        """
        f = hyperframe.frame.WindowUpdateFrame(streamID)
        f.window_increment = increment
        return f

    def buildGoAwayFrame(self, lastStreamID, errorCode=0, additionalData=b""):
        """
        Builds a single GOAWAY frame.
        """
        f = hyperframe.frame.GoAwayFrame(0)
        f.error_code = errorCode
        f.last_stream_id = lastStreamID
        f.additional_data = additionalData
        return f

    def buildRstStreamFrame(self, streamID, errorCode=0):
        """
        Builds a single RST_STREAM frame.
        """
        f = hyperframe.frame.RstStreamFrame(streamID)
        f.error_code = errorCode
        return f

    def buildPriorityFrame(self, streamID, weight, dependsOn=0, exclusive=False):
        """
        Builds a single priority frame.
        """
        f = hyperframe.frame.PriorityFrame(streamID)
        f.depends_on = dependsOn
        f.stream_weight = weight
        f.exclusive = exclusive
        return f

    def buildPushPromiseFrame(self, streamID, promisedStreamID, headers, flags=[]):
        """
        Builds a single Push Promise frame.
        """
        f = hyperframe.frame.PushPromiseFrame(streamID)
        f.promised_stream_id = promisedStreamID
        f.data = self.encoder.encode(headers)
        f.flags = set(flags)
        f.flags.add("END_HEADERS")
        return f


class FrameBuffer:
    """
    A test object that converts data received from Twisted's HTTP/2 stack and
    turns it into a sequence of hyperframe frame objects.

    This is primarily used to make it easier to write and debug tests: rather
    than have to serialize the expected frames and then do byte-level
    comparison (which can be unclear in debugging output), this object makes it
    possible to work with the frames directly.

    It also ensures that headers are properly decompressed.
    """

    def __init__(self):
        self.decoder = Decoder()
        self._data = b""

    def receiveData(self, data):
        self._data += data

    def __iter__(self):
        return self

    def next(self):
        if len(self._data) < 9:
            raise StopIteration()

        frame, length = hyperframe.frame.Frame.parse_frame_header(self._data[:9])
        if len(self._data) < length + 9:
            raise StopIteration()

        frame.parse_body(memoryview(self._data[9 : 9 + length]))
        self._data = self._data[9 + length :]

        if isinstance(frame, hyperframe.frame.HeadersFrame):
            frame.data = self.decoder.decode(frame.data, raw=True)

        return frame

    __next__ = next


def buildRequestFrames(headers, data, frameFactory=None, streamID=1):
    """
    Provides a sequence of HTTP/2 frames that encode a single HTTP request.
    This should be used when you want to control the serialization yourself,
    e.g. because you want to interleave other frames with these. If that's not
    necessary, prefer L{buildRequestBytes}.

    @param headers: The HTTP/2 headers to send.
    @type headers: L{list} of L{tuple} of L{bytes}

    @param data: The HTTP data to send. Each list entry will be sent in its own
    frame.
    @type data: L{list} of L{bytes}

    @param frameFactory: The L{FrameFactory} that will be used to construct the
    frames.
    @type frameFactory: L{FrameFactory}

    @param streamID: The ID of the stream on which to send the request.
    @type streamID: L{int}
    """
    if frameFactory is None:
        frameFactory = FrameFactory()

    frames = []
    frames.append(frameFactory.buildHeadersFrame(headers=headers, streamID=streamID))
    frames.extend(
        frameFactory.buildDataFrame(chunk, streamID=streamID) for chunk in data
    )
    frames[-1].flags.add("END_STREAM")
    return frames


def buildRequestBytes(headers, data, frameFactory=None, streamID=1):
    """
    Provides the byte sequence for a collection of HTTP/2 frames representing
    the provided request.

    @param headers: The HTTP/2 headers to send.
    @type headers: L{list} of L{tuple} of L{bytes}

    @param data: The HTTP data to send. Each list entry will be sent in its own
    frame.
    @type data: L{list} of L{bytes}

    @param frameFactory: The L{FrameFactory} that will be used to construct the
    frames.
    @type frameFactory: L{FrameFactory}

    @param streamID: The ID of the stream on which to send the request.
    @type streamID: L{int}
    """
    frames = buildRequestFrames(headers, data, frameFactory, streamID)
    return b"".join(f.serialize() for f in frames)


def framesFromBytes(data):
    """
    Given a sequence of bytes, decodes them into frames.

    Note that this method should almost always be called only once, before
    making some assertions. This is because decoding HTTP/2 frames is extremely
    stateful, and this function doesn't preserve any of that state between
    calls.

    @param data: The serialized HTTP/2 frames.
    @type data: L{bytes}

    @returns: A list of HTTP/2 frames.
    @rtype: L{list} of L{hyperframe.frame.Frame} subclasses.
    """
    buffer = FrameBuffer()
    buffer.receiveData(data)
    return list(buffer)


class ChunkedHTTPHandler(http.Request):
    """
    A HTTP request object that writes chunks of data back to the network based
    on the URL.

    Must be called with a path /chunked/<num_chunks>
    """

    chunkData = b"hello world!"

    def process(self):
        chunks = int(self.uri.split(b"/")[-1])
        self.setResponseCode(200)

        for _ in range(chunks):
            self.write(self.chunkData)

        self.finish()


ChunkedHTTPHandlerProxy = _makeRequestProxyFactory(ChunkedHTTPHandler)


class ConsumerDummyHandler(http.Request):
    """
    This is a HTTP request handler that works with the C{IPushProducer}
    implementation in the L{H2Stream} object. No current IRequest object does
    that, but in principle future implementations could: that codepath should
    therefore be tested.
    """

    def __init__(self, *args, **kwargs):
        http.Request.__init__(self, *args, **kwargs)

        # Production starts paused.
        self.channel.pauseProducing()
        self._requestReceived = False
        self._data = None

    def acceptData(self):
        """
        Start the data pipe.
        """
        self.channel.resumeProducing()

    def requestReceived(self, *args, **kwargs):
        self._requestReceived = True
        return http.Request.requestReceived(self, *args, **kwargs)

    def process(self):
        self.setResponseCode(200)
        self._data = self.content.read()
        returnData = b"this is a response from a consumer dummy handler"
        self.write(returnData)
        self.finish()


ConsumerDummyHandlerProxy = _makeRequestProxyFactory(ConsumerDummyHandler)


class AbortingConsumerDummyHandler(ConsumerDummyHandler):
    """
    This is a HTTP request handler that works with the C{IPushProducer}
    implementation in the L{H2Stream} object. The difference between this and
    the ConsumerDummyHandler is that after resuming production it immediately
    aborts it again.
    """

    def acceptData(self):
        """
        Start and then immediately stop the data pipe.
        """
        self.channel.resumeProducing()
        self.channel.stopProducing()


AbortingConsumerDummyHandlerProxy = _makeRequestProxyFactory(
    AbortingConsumerDummyHandler
)


class DummyProducerHandler(http.Request):
    """
    An HTTP request handler that registers a dummy producer to serve the body.

    The owner must call C{finish} to complete the response.
    """

    def process(self):
        self.setResponseCode(200)
        self.registerProducer(DummyProducer(), True)


DummyProducerHandlerProxy = _makeRequestProxyFactory(DummyProducerHandler)


class NotifyingRequestFactory:
    """
    A L{http.Request} factory that calls L{http.Request.notifyFinish} on all
    L{http.Request} objects before it returns them, and squirrels the resulting
    L{defer.Deferred} away on the class for later use. This is done as early
    as possible to ensure that we always see the result.
    """

    def __init__(self, wrappedFactory):
        self.results = []
        self._wrappedFactory = wrappedFactory

        # Add interfaces provided by the factory we are wrapping. We expect
        # this only to be INonQueuedRequestFactory, but we don't want to
        # hard-code that rule.
        for interface in providedBy(self._wrappedFactory):
            directlyProvides(self, interface)

    def __call__(self, *args, **kwargs):
        req = self._wrappedFactory(*args, **kwargs)
        self.results.append(req.notifyFinish())
        return _IDeprecatedHTTPChannelToRequestInterfaceProxy(req)


NotifyingRequestFactoryProxy = _makeRequestProxyFactory(NotifyingRequestFactory)


class HTTP2TestHelpers:
    """
    A superclass that contains no tests but provides test helpers for HTTP/2
    tests.
    """

    if skipH2:
        skip = skipH2

    def assertAllStreamsBlocked(self, connection):
        """
        Confirm that all streams are blocked: that is, the priority tree
        believes that none of the streams have data ready to send.
        """
        self.assertRaises(priority.DeadlockError, next, connection.priority)


class HTTP2ServerTests(unittest.TestCase, HTTP2TestHelpers):
    getRequestHeaders = [
        (b":method", b"GET"),
        (b":authority", b"localhost"),
        (b":path", b"/"),
        (b":scheme", b"https"),
        (b"user-agent", b"twisted-test-code"),
        (b"custom-header", b"1"),
        (b"custom-header", b"2"),
    ]

    postRequestHeaders = [
        (b":method", b"POST"),
        (b":authority", b"localhost"),
        (b":path", b"/post_endpoint"),
        (b":scheme", b"https"),
        (b"user-agent", b"twisted-test-code"),
        (b"content-length", b"25"),
    ]

    postRequestData = [b"hello ", b"world, ", b"it's ", b"http/2!"]

    getResponseHeaders = [
        (b":status", b"200"),
        (b"request", b"/"),
        (b"command", b"GET"),
        (b"version", b"HTTP/2"),
        (b"content-length", b"13"),
    ]

    getResponseData = b"'''\nNone\n'''\n"

    postResponseHeaders = [
        (b":status", b"200"),
        (b"request", b"/post_endpoint"),
        (b"command", b"POST"),
        (b"version", b"HTTP/2"),
        (b"content-length", b"36"),
    ]

    postResponseData = b"'''\n25\nhello world, it's http/2!'''\n"

    def connectAndReceive(self, connection, headers, body):
        """
        Takes a single L{H2Connection} object and connects it to a
        L{StringTransport} using a brand new L{FrameFactory}.

        @param connection: The L{H2Connection} object to connect.
        @type connection: L{H2Connection}

        @param headers: The headers to send on the first request.
        @type headers: L{Iterable} of L{tuple} of C{(bytes, bytes)}

        @param body: Chunks of body to send, if any.
        @type body: L{Iterable} of L{bytes}

        @return: A tuple of L{FrameFactory}, L{StringTransport}
        """
        frameFactory = FrameFactory()
        transport = StringTransport()

        requestBytes = frameFactory.clientConnectionPreface()
        requestBytes += buildRequestBytes(headers, body, frameFactory)

        connection.makeConnection(transport)
        # One byte at a time, to stress the implementation.
        for byte in iterbytes(requestBytes):
            connection.dataReceived(byte)

        return frameFactory, transport

    def test_basicRequest(self):
        """
        Send request over a TCP connection and confirm that we get back the
        expected data in the order and style we expect.
        """
        # This test is complex because it validates the data very closely: it
        # specifically checks frame ordering and type.
        connection = H2Connection()
        connection.requestFactory = DummyHTTPHandlerProxy
        _, transport = self.connectAndReceive(connection, self.getRequestHeaders, [])

        def validate(streamID):
            frames = framesFromBytes(transport.value())

            self.assertEqual(len(frames), 4)
            self.assertTrue(all(f.stream_id == 1 for f in frames[1:]))

            self.assertTrue(isinstance(frames[1], hyperframe.frame.HeadersFrame))
            self.assertTrue(isinstance(frames[2], hyperframe.frame.DataFrame))
            self.assertTrue(isinstance(frames[3], hyperframe.frame.DataFrame))

            self.assertEqual(dict(frames[1].data), dict(self.getResponseHeaders))
            self.assertEqual(frames[2].data, self.getResponseData)
            self.assertEqual(frames[3].data, b"")
            self.assertTrue("END_STREAM" in frames[3].flags)

        return connection._streamCleanupCallbacks[1].addCallback(validate)

    def test_postRequest(self):
        """
        Send a POST request and confirm that the data is safely transferred.
        """
        connection = H2Connection()
        connection.requestFactory = DummyHTTPHandlerProxy
        _, transport = self.connectAndReceive(
            connection, self.postRequestHeaders, self.postRequestData
        )

        def validate(streamID):
            frames = framesFromBytes(transport.value())

            # One Settings frame, one Headers frame and two Data frames.
            self.assertEqual(len(frames), 4)
            self.assertTrue(all(f.stream_id == 1 for f in frames[-3:]))

            self.assertTrue(isinstance(frames[-3], hyperframe.frame.HeadersFrame))
            self.assertTrue(isinstance(frames[-2], hyperframe.frame.DataFrame))
            self.assertTrue(isinstance(frames[-1], hyperframe.frame.DataFrame))

            self.assertEqual(dict(frames[-3].data), dict(self.postResponseHeaders))
            self.assertEqual(frames[-2].data, self.postResponseData)
            self.assertEqual(frames[-1].data, b"")
            self.assertTrue("END_STREAM" in frames[-1].flags)

        return connection._streamCleanupCallbacks[1].addCallback(validate)

    def test_postRequestNoLength(self):
        """
        Send a POST request without length and confirm that the data is safely
        transferred.
        """
        postResponseHeaders = [
            (b":status", b"200"),
            (b"request", b"/post_endpoint"),
            (b"command", b"POST"),
            (b"version", b"HTTP/2"),
            (b"content-length", b"38"),
        ]
        postResponseData = b"'''\nNone\nhello world, it's http/2!'''\n"

        # Strip the content-length header.
        postRequestHeaders = [
            (x, y) for x, y in self.postRequestHeaders if x != b"content-length"
        ]

        connection = H2Connection()
        connection.requestFactory = DummyHTTPHandlerProxy
        _, transport = self.connectAndReceive(
            connection, postRequestHeaders, self.postRequestData
        )

        def validate(streamID):
            frames = framesFromBytes(transport.value())

            # One Settings frame, one Headers frame, and two Data frames
            self.assertEqual(len(frames), 4)
            self.assertTrue(all(f.stream_id == 1 for f in frames[-3:]))

            self.assertTrue(isinstance(frames[-3], hyperframe.frame.HeadersFrame))
            self.assertTrue(isinstance(frames[-2], hyperframe.frame.DataFrame))
            self.assertTrue(isinstance(frames[-1], hyperframe.frame.DataFrame))

            self.assertEqual(dict(frames[-3].data), dict(postResponseHeaders))
            self.assertEqual(frames[-2].data, postResponseData)
            self.assertEqual(frames[-1].data, b"")
            self.assertTrue("END_STREAM" in frames[-1].flags)

        return connection._streamCleanupCallbacks[1].addCallback(validate)

    def test_interleavedRequests(self):
        """
        Many interleaved POST requests all get received and responded to
        appropriately.
        """
        # Unfortunately this test is pretty complex.
        REQUEST_COUNT = 40

        f = FrameFactory()
        b = StringTransport()
        a = H2Connection()
        a.requestFactory = DummyHTTPHandlerProxy

        # Stream IDs are always odd numbers.
        streamIDs = list(range(1, REQUEST_COUNT * 2, 2))
        frames = [
            buildRequestFrames(
                self.postRequestHeaders, self.postRequestData, f, streamID
            )
            for streamID in streamIDs
        ]

        requestBytes = f.clientConnectionPreface()

        # Interleave the frames. That is, send one frame from each stream at a
        # time. This wacky line lets us do that.
        frames = itertools.chain.from_iterable(zip(*frames))
        requestBytes += b"".join(frame.serialize() for frame in frames)
        a.makeConnection(b)
        # one byte at a time, to stress the implementation.
        for byte in iterbytes(requestBytes):
            a.dataReceived(byte)

        def validate(results):
            frames = framesFromBytes(b.value())

            # We expect 1 Settings frame for the connection, and then 3 frames
            # *per stream* (1 Headers frame, 2 Data frames). This doesn't send
            # enough data to trigger a window update.
            self.assertEqual(len(frames), 1 + (3 * 40))

            # Let's check the data is ok. We need the non-WindowUpdate frames
            # for each stream.
            for streamID in streamIDs:
                streamFrames = [
                    f
                    for f in frames
                    if f.stream_id == streamID
                    and not isinstance(f, hyperframe.frame.WindowUpdateFrame)
                ]

                self.assertEqual(len(streamFrames), 3)

                self.assertEqual(
                    dict(streamFrames[0].data), dict(self.postResponseHeaders)
                )
                self.assertEqual(streamFrames[1].data, self.postResponseData)
                self.assertEqual(streamFrames[2].data, b"")
                self.assertTrue("END_STREAM" in streamFrames[2].flags)

        return defer.DeferredList(list(a._streamCleanupCallbacks.values())).addCallback(
            validate
        )

    def test_sendAccordingToPriority(self):
        """
        Data in responses is interleaved according to HTTP/2 priorities.
        """
        # We want to start three parallel GET requests that will each return
        # four chunks of data. These chunks will be interleaved according to
        # HTTP/2 priorities. Stream 1 will be set to weight 64, Stream 3 to
        # weight 32, and Stream 5 to weight 16 but dependent on Stream 1.
        # That will cause data frames for these streams to be emitted in this
        # order: 1, 3, 1, 1, 3, 1, 1, 3, 5, 3, 5, 3, 5, 5, 5.
        #
        # The reason there are so many frames is because the implementation
        # interleaves stream completion according to priority order as well,
        # because it is sent on a Data frame.
        #
        # This doesn't fully test priority, but tests *almost* enough of it to
        # be worthwhile.
        f = FrameFactory()
        b = StringTransport()
        a = H2Connection()
        a.requestFactory = ChunkedHTTPHandlerProxy
        getRequestHeaders = self.getRequestHeaders
        getRequestHeaders[2] = (":path", "/chunked/4")

        frames = [
            buildRequestFrames(getRequestHeaders, [], f, streamID)
            for streamID in [1, 3, 5]
        ]

        # Set the priorities. The first two will use their HEADERS frame, the
        # third will have a PRIORITY frame sent before the headers.
        frames[0][0].flags.add("PRIORITY")
        frames[0][0].stream_weight = 64

        frames[1][0].flags.add("PRIORITY")
        frames[1][0].stream_weight = 32

        priorityFrame = f.buildPriorityFrame(
            streamID=5,
            weight=16,
            dependsOn=1,
            exclusive=True,
        )
        frames[2].insert(0, priorityFrame)

        frames = itertools.chain.from_iterable(frames)
        requestBytes = f.clientConnectionPreface()
        requestBytes += b"".join(frame.serialize() for frame in frames)

        a.makeConnection(b)
        # one byte at a time, to stress the implementation.
        for byte in iterbytes(requestBytes):
            a.dataReceived(byte)

        def validate(results):
            frames = framesFromBytes(b.value())

            # We expect 1 Settings frame for the connection, and then 6 frames
            # per stream (1 Headers frame, 5 data frames), for a total of 19.
            self.assertEqual(len(frames), 19)

            streamIDs = [
                f.stream_id for f in frames if isinstance(f, hyperframe.frame.DataFrame)
            ]
            expectedOrder = [1, 3, 1, 1, 3, 1, 1, 3, 5, 3, 5, 3, 5, 5, 5]
            self.assertEqual(streamIDs, expectedOrder)

        return defer.DeferredList(list(a._streamCleanupCallbacks.values())).addCallback(
            validate
        )

    def test_protocolErrorTerminatesConnection(self):
        """
        A protocol error from the remote peer terminates the connection.
        """
        f = FrameFactory()
        b = StringTransport()
        a = H2Connection()
        a.requestFactory = DummyHTTPHandlerProxy

        # We're going to open a stream and then send a PUSH_PROMISE frame,
        # which is forbidden.
        requestBytes = f.clientConnectionPreface()
        requestBytes += buildRequestBytes(self.getRequestHeaders, [], f)
        requestBytes += f.buildPushPromiseFrame(
            streamID=1,
            promisedStreamID=2,
            headers=self.getRequestHeaders,
            flags=["END_HEADERS"],
        ).serialize()

        a.makeConnection(b)
        # one byte at a time, to stress the implementation.
        for byte in iterbytes(requestBytes):
            a.dataReceived(byte)

            # Check whether the transport got shut down: if it did, stop
            # sending more data.
            if b.disconnecting:
                break

        frames = framesFromBytes(b.value())

        # The send loop never gets to terminate the stream, but *some* data
        # does get sent. We get a Settings frame, a Headers frame, and then the
        # GoAway frame.
        self.assertEqual(len(frames), 3)
        self.assertTrue(isinstance(frames[-1], hyperframe.frame.GoAwayFrame))
        self.assertTrue(b.disconnecting)

    def test_streamProducingData(self):
        """
        The H2Stream data implements IPushProducer, and can have its data
        production controlled by the Request if the Request chooses to.
        """
        connection = H2Connection()
        connection.requestFactory = ConsumerDummyHandlerProxy
        _, transport = self.connectAndReceive(
            connection, self.postRequestHeaders, self.postRequestData
        )

        # At this point no data should have been received by the request *or*
        # the response. We need to dig the request out of the tree of objects.
        request = connection.streams[1]._request.original
        self.assertFalse(request._requestReceived)

        # We should have only received the Settings frame. It's important that
        # the WindowUpdate frames don't land before data is delivered to the
        # Request.
        frames = framesFromBytes(transport.value())
        self.assertEqual(len(frames), 1)

        # At this point, we can kick off the producing. This will force the
        # H2Stream object to deliver the request data all at once, so check
        # that it was delivered correctly.
        request.acceptData()
        self.assertTrue(request._requestReceived)
        self.assertTrue(request._data, b"hello world, it's http/2!")

        # *That* will have also caused the H2Connection object to emit almost
        # all the data it needs. That'll be a Headers frame, as well as the
        # original SETTINGS frame.
        frames = framesFromBytes(transport.value())
        self.assertEqual(len(frames), 2)

        def validate(streamID):
            # Confirm that the response is ok.
            frames = framesFromBytes(transport.value())

            # The only new frames here are the two Data frames.
            self.assertEqual(len(frames), 4)
            self.assertTrue("END_STREAM" in frames[-1].flags)

        return connection._streamCleanupCallbacks[1].addCallback(validate)

    def test_abortStreamProducingData(self):
        """
        The H2Stream data implements IPushProducer, and can have its data
        production controlled by the Request if the Request chooses to.
        When the production is stopped, that causes the stream connection to
        be lost.
        """
        f = FrameFactory()
        b = StringTransport()
        a = H2Connection()
        a.requestFactory = AbortingConsumerDummyHandlerProxy

        # We're going to send in a POST request.
        frames = buildRequestFrames(self.postRequestHeaders, self.postRequestData, f)
        frames[-1].flags = set()  # Remove END_STREAM flag.
        requestBytes = f.clientConnectionPreface()
        requestBytes += b"".join(f.serialize() for f in frames)
        a.makeConnection(b)
        # one byte at a time, to stress the implementation.
        for byte in iterbytes(requestBytes):
            a.dataReceived(byte)

        # At this point no data should have been received by the request *or*
        # the response. We need to dig the request out of the tree of objects.
        request = a.streams[1]._request.original
        self.assertFalse(request._requestReceived)

        # Save off the cleanup deferred now, it'll be removed when the
        # RstStream frame is sent.
        cleanupCallback = a._streamCleanupCallbacks[1]

        # At this point, we can kick off the production and immediate abort.
        request.acceptData()

        # The stream will now have been aborted.
        def validate(streamID):
            # Confirm that the response is ok.
            frames = framesFromBytes(b.value())

            # We expect a Settings frame and a RstStream frame.
            self.assertEqual(len(frames), 2)
            self.assertTrue(isinstance(frames[-1], hyperframe.frame.RstStreamFrame))
            self.assertEqual(frames[-1].stream_id, 1)

        return cleanupCallback.addCallback(validate)

    def test_terminatedRequest(self):
        """
        When a RstStream frame is received, the L{H2Connection} and L{H2Stream}
        objects tear down the L{http.Request} and swallow all outstanding
        writes.
        """
        # Here we want to use the DummyProducerHandler primarily for the side
        # effect it has of not writing to the connection. That means we can
        # delay some writes until *after* the RstStream frame is received.
        connection = H2Connection()
        connection.requestFactory = DummyProducerHandlerProxy
        frameFactory, transport = self.connectAndReceive(
            connection, self.getRequestHeaders, []
        )

        # Get the request object.
        request = connection.streams[1]._request.original

        # Send two writes in.
        request.write(b"first chunk")
        request.write(b"second chunk")

        # Save off the cleanup deferred now, it'll be removed when the
        # RstStream frame is received.
        cleanupCallback = connection._streamCleanupCallbacks[1]

        # Now fire the RstStream frame.
        connection.dataReceived(
            frameFactory.buildRstStreamFrame(1, errorCode=1).serialize()
        )

        # This should have cancelled the request.
        self.assertTrue(request._disconnected)
        self.assertTrue(request.channel is None)

        # This should not raise an exception, the function will just return
        # immediately, and do nothing
        request.write(b"third chunk")

        # Check that everything is fine.
        # We expect that only the Settings and Headers frames will have been
        # emitted. The two writes are lost because the delayed call never had
        # another chance to execute before the RstStream frame got processed.
        def validate(streamID):
            frames = framesFromBytes(transport.value())

            self.assertEqual(len(frames), 2)
            self.assertEqual(frames[1].stream_id, 1)

            self.assertTrue(isinstance(frames[1], hyperframe.frame.HeadersFrame))

        return cleanupCallback.addCallback(validate)

    def test_terminatedConnection(self):
        """
        When a GoAway frame is received, the L{H2Connection} and L{H2Stream}
        objects tear down all outstanding L{http.Request} objects and stop all
        writing.
        """
        # Here we want to use the DummyProducerHandler primarily for the side
        # effect it has of not writing to the connection. That means we can
        # delay some writes until *after* the GoAway frame is received.
        connection = H2Connection()
        connection.requestFactory = DummyProducerHandlerProxy
        frameFactory, transport = self.connectAndReceive(
            connection, self.getRequestHeaders, []
        )

        # Get the request object.
        request = connection.streams[1]._request.original

        # Send two writes in.
        request.write(b"first chunk")
        request.write(b"second chunk")

        # Save off the cleanup deferred now, it'll be removed when the
        # GoAway frame is received.
        cleanupCallback = connection._streamCleanupCallbacks[1]

        # Now fire the GoAway frame.
        connection.dataReceived(
            frameFactory.buildGoAwayFrame(lastStreamID=0).serialize()
        )

        # This should have cancelled the request.
        self.assertTrue(request._disconnected)
        self.assertTrue(request.channel is None)

        # It should also have cancelled the sending loop.
        self.assertFalse(connection._stillProducing)

        # Check that everything is fine.
        # We expect that only the Settings and Headers frames will have been
        # emitted. The writes are lost because the callLater never had
        # a chance to execute before the GoAway frame got processed.
        def validate(streamID):
            frames = framesFromBytes(transport.value())

            self.assertEqual(len(frames), 2)
            self.assertEqual(frames[1].stream_id, 1)

            self.assertTrue(isinstance(frames[1], hyperframe.frame.HeadersFrame))

        return cleanupCallback.addCallback(validate)

    def test_respondWith100Continue(self):
        """
        Requests containing Expect: 100-continue cause provisional 100
        responses to be emitted.
        """
        connection = H2Connection()
        connection.requestFactory = DummyHTTPHandlerProxy

        # Add Expect: 100-continue for this request.
        headers = self.getRequestHeaders + [(b"expect", b"100-continue")]

        _, transport = self.connectAndReceive(connection, headers, [])

        # We expect 5 frames now: Settings, two Headers frames, and two Data
        # frames. We're only really interested in validating the first Headers
        # frame which contains the 100.
        def validate(streamID):
            frames = framesFromBytes(transport.value())

            self.assertEqual(len(frames), 5)
            self.assertTrue(all(f.stream_id == 1 for f in frames[1:]))

            self.assertTrue(isinstance(frames[1], hyperframe.frame.HeadersFrame))
            self.assertEqual(frames[1].data, [(b":status", b"100")])
            self.assertTrue("END_STREAM" in frames[-1].flags)

        return connection._streamCleanupCallbacks[1].addCallback(validate)

    def test_respondWith400(self):
        """
        Triggering the call to L{H2Stream._respondToBadRequestAndDisconnect}
        leads to a 400 error being sent automatically and the stream being torn
        down.
        """
        # The only "natural" way to trigger this in the current codebase is to
        # send a multipart/form-data request that the cgi module doesn't like.
        # That's absurdly hard, so instead we'll just call it ourselves. For
        # this reason we use the DummyProducerHandler, which doesn't write the
        # headers straight away.
        connection = H2Connection()
        connection.requestFactory = DummyProducerHandlerProxy
        _, transport = self.connectAndReceive(connection, self.getRequestHeaders, [])

        # Grab the request and the completion callback.
        stream = connection.streams[1]
        request = stream._request.original
        cleanupCallback = connection._streamCleanupCallbacks[1]

        # Abort the stream.
        stream._respondToBadRequestAndDisconnect()

        # This should have cancelled the request.
        self.assertTrue(request._disconnected)
        self.assertTrue(request.channel is None)

        # We expect 2 frames Settings and the 400 Headers.
        def validate(streamID):
            frames = framesFromBytes(transport.value())

            self.assertEqual(len(frames), 2)

            self.assertTrue(isinstance(frames[1], hyperframe.frame.HeadersFrame))
            self.assertEqual(frames[1].data, [(b":status", b"400")])
            self.assertTrue("END_STREAM" in frames[-1].flags)

        return cleanupCallback.addCallback(validate)

    def test_loseH2StreamConnection(self):
        """
        Calling L{Request.loseConnection} causes all data that has previously
        been sent to be flushed, and then the stream cleanly closed.
        """
        # Here we again want to use the DummyProducerHandler because it doesn't
        # close the connection on its own.
        connection = H2Connection()
        connection.requestFactory = DummyProducerHandlerProxy
        _, transport = self.connectAndReceive(connection, self.getRequestHeaders, [])

        # Grab the request.
        stream = connection.streams[1]
        request = stream._request.original

        # Send in some writes.
        dataChunks = [b"hello", b"world", b"here", b"are", b"some", b"writes"]
        for chunk in dataChunks:
            request.write(chunk)

        # Now lose the connection.
        request.loseConnection()

        # Check that the data was all written out correctly and that the stream
        # state is cleaned up.
        def validate(streamID):
            frames = framesFromBytes(transport.value())

            # Settings, Headers, 7 Data frames.
            self.assertEqual(len(frames), 9)
            self.assertTrue(all(f.stream_id == 1 for f in frames[1:]))

            self.assertTrue(isinstance(frames[1], hyperframe.frame.HeadersFrame))
            self.assertTrue("END_STREAM" in frames[-1].flags)

            receivedDataChunks = [
                f.data for f in frames if isinstance(f, hyperframe.frame.DataFrame)
            ]
            self.assertEqual(
                receivedDataChunks,
                dataChunks + [b""],
            )

        return connection._streamCleanupCallbacks[1].addCallback(validate)

    def test_cannotRegisterTwoProducers(self):
        """
        The L{H2Stream} object forbids registering two producers.
        """
        connection = H2Connection()
        connection.requestFactory = DummyProducerHandlerProxy
        self.connectAndReceive(connection, self.getRequestHeaders, [])

        # Grab the request.
        stream = connection.streams[1]
        request = stream._request.original

        self.assertRaises(ValueError, stream.registerProducer, request, True)

    def test_handlesPullProducer(self):
        """
        L{Request} objects that have registered pull producers get blocked and
        unblocked according to HTTP/2 flow control.
        """
        connection = H2Connection()
        connection.requestFactory = DummyPullProducerHandlerProxy
        _, transport = self.connectAndReceive(connection, self.getRequestHeaders, [])

        # Get the producer completion deferred and ensure we call
        # request.finish.
        stream = connection.streams[1]
        request = stream._request.original
        producerComplete = request._actualProducer.result
        producerComplete.addCallback(lambda x: request.finish())

        # Check that the sending loop sends all the appropriate data.
        def validate(streamID):
            frames = framesFromBytes(transport.value())

            # Check that the stream is correctly terminated.
            self.assertTrue("END_STREAM" in frames[-1].flags)

            # Grab the data from the frames.
            dataChunks = [
                f.data for f in frames if isinstance(f, hyperframe.frame.DataFrame)
            ]
            self.assertEqual(
                dataChunks,
                [b"0", b"1", b"2", b"3", b"4", b"5", b"6", b"7", b"8", b"9", b""],
            )

        return connection._streamCleanupCallbacks[1].addCallback(validate)

    def test_isSecureWorksProperly(self):
        """
        L{Request} objects can correctly ask isSecure on HTTP/2.
        """
        connection = H2Connection()
        connection.requestFactory = DelayedHTTPHandlerProxy
        self.connectAndReceive(connection, self.getRequestHeaders, [])

        request = connection.streams[1]._request.original
        self.assertFalse(request.isSecure())
        connection.streams[1].abortConnection()

    def test_lateCompletionWorks(self):
        """
        L{H2Connection} correctly unblocks when a stream is ended.
        """
        connection = H2Connection()
        connection.requestFactory = DelayedHTTPHandlerProxy
        _, transport = self.connectAndReceive(connection, self.getRequestHeaders, [])

        # Delay a call to end request, forcing the connection to block because
        # it has no data to send.
        request = connection.streams[1]._request.original
        reactor.callLater(0.01, request.finish)

        def validateComplete(*args):
            frames = framesFromBytes(transport.value())

            # Check that the stream is correctly terminated.
            self.assertEqual(len(frames), 3)
            self.assertTrue("END_STREAM" in frames[-1].flags)

        return connection._streamCleanupCallbacks[1].addCallback(validateComplete)

    def test_writeSequenceForChannels(self):
        """
        L{H2Stream} objects can send a series of frames via C{writeSequence}.
        """
        connection = H2Connection()
        connection.requestFactory = DelayedHTTPHandlerProxy
        _, transport = self.connectAndReceive(connection, self.getRequestHeaders, [])

        stream = connection.streams[1]
        request = stream._request.original

        request.setResponseCode(200)
        stream.writeSequence([b"Hello", b",", b"world!"])
        request.finish()

        completionDeferred = connection._streamCleanupCallbacks[1]

        def validate(streamID):
            frames = framesFromBytes(transport.value())

            # Check that the stream is correctly terminated.
            self.assertTrue("END_STREAM" in frames[-1].flags)

            # Grab the data from the frames.
            dataChunks = [
                f.data for f in frames if isinstance(f, hyperframe.frame.DataFrame)
            ]
            self.assertEqual(dataChunks, [b"Hello", b",", b"world!", b""])

        return completionDeferred.addCallback(validate)

    def test_delayWrites(self):
        """
        Delaying writes from L{Request} causes the L{H2Connection} to block on
        sending until data is available. However, data is *not* sent if there's
        no room in the flow control window.
        """
        # Here we again want to use the DummyProducerHandler because it doesn't
        # close the connection on its own.
        f = FrameFactory()
        b = StringTransport()
        a = H2Connection()
        a.requestFactory = DelayedHTTPHandlerProxy

        requestBytes = f.clientConnectionPreface()
        requestBytes += f.buildSettingsFrame(
            {h2.settings.SettingCodes.INITIAL_WINDOW_SIZE: 5}
        ).serialize()
        requestBytes += buildRequestBytes(self.getRequestHeaders, [], f)
        a.makeConnection(b)
        # one byte at a time, to stress the implementation.
        for byte in iterbytes(requestBytes):
            a.dataReceived(byte)

        # Grab the request.
        stream = a.streams[1]
        request = stream._request.original

        # Write the first 5 bytes.
        request.write(b"fiver")
        dataChunks = [b"here", b"are", b"some", b"writes"]

        def write_chunks():
            # Send in some writes.
            for chunk in dataChunks:
                request.write(chunk)
            request.finish()

        d = task.deferLater(reactor, 0.01, write_chunks)
        d.addCallback(
            lambda *args: a.dataReceived(
                f.buildWindowUpdateFrame(streamID=1, increment=50).serialize()
            )
        )

        # Check that the data was all written out correctly and that the stream
        # state is cleaned up.
        def validate(streamID):
            frames = framesFromBytes(b.value())

            # 2 Settings, Headers, 7 Data frames.
            self.assertEqual(len(frames), 9)
            self.assertTrue(all(f.stream_id == 1 for f in frames[2:]))

            self.assertTrue(isinstance(frames[2], hyperframe.frame.HeadersFrame))
            self.assertTrue("END_STREAM" in frames[-1].flags)

            receivedDataChunks = [
                f.data for f in frames if isinstance(f, hyperframe.frame.DataFrame)
            ]
            self.assertEqual(
                receivedDataChunks,
                [b"fiver"] + dataChunks + [b""],
            )

        return a._streamCleanupCallbacks[1].addCallback(validate)

    def test_resetAfterBody(self):
        """
        A client that immediately resets after sending the body causes Twisted
        to send no response.
        """
        frameFactory = FrameFactory()
        transport = StringTransport()
        a = H2Connection()
        a.requestFactory = DummyHTTPHandlerProxy

        requestBytes = frameFactory.clientConnectionPreface()
        requestBytes += buildRequestBytes(
            headers=self.getRequestHeaders, data=[], frameFactory=frameFactory
        )
        requestBytes += frameFactory.buildRstStreamFrame(streamID=1).serialize()
        a.makeConnection(transport)
        a.dataReceived(requestBytes)

        frames = framesFromBytes(transport.value())

        self.assertEqual(len(frames), 1)
        self.assertNotIn(1, a._streamCleanupCallbacks)

    def test_RequestRequiringFactorySiteInConstructor(self):
        """
        A custom L{Request} subclass that requires the site and factory in the
        constructor is able to get them.
        """
        d = defer.Deferred()

        class SuperRequest(DummyHTTPHandler):
            def __init__(self, *args, **kwargs):
                DummyHTTPHandler.__init__(self, *args, **kwargs)
                d.callback((self.channel.site, self.channel.factory))

        connection = H2Connection()
        httpFactory = http.HTTPFactory()
        connection.requestFactory = _makeRequestProxyFactory(SuperRequest)

        # Create some sentinels to look for.
        connection.factory = httpFactory
        connection.site = object()

        self.connectAndReceive(connection, self.getRequestHeaders, [])

        def validateFactoryAndSite(args):
            site, factory = args
            self.assertIs(site, connection.site)
            self.assertIs(factory, connection.factory)

        d.addCallback(validateFactoryAndSite)

        # We need to wait for the stream cleanup callback to drain the
        # response.
        cleanupCallback = connection._streamCleanupCallbacks[1]
        return defer.gatherResults([d, cleanupCallback])

    def test_notifyOnCompleteRequest(self):
        """
        A request sent to a HTTP/2 connection fires the
        L{http.Request.notifyFinish} callback with a L{None} value.
        """
        connection = H2Connection()
        connection.requestFactory = NotifyingRequestFactory(DummyHTTPHandler)
        _, transport = self.connectAndReceive(connection, self.getRequestHeaders, [])

        deferreds = connection.requestFactory.results
        self.assertEqual(len(deferreds), 1)

        def validate(result):
            self.assertIsNone(result)

        d = deferreds[0]
        d.addCallback(validate)

        # We need to wait for the stream cleanup callback to drain the
        # response.
        cleanupCallback = connection._streamCleanupCallbacks[1]
        return defer.gatherResults([d, cleanupCallback])

    def test_notifyOnResetStream(self):
        """
        A HTTP/2 reset stream fires the L{http.Request.notifyFinish} deferred
        with L{ConnectionLost}.
        """
        connection = H2Connection()
        connection.requestFactory = NotifyingRequestFactory(DelayedHTTPHandler)
        frameFactory, transport = self.connectAndReceive(
            connection, self.getRequestHeaders, []
        )

        deferreds = connection.requestFactory.results
        self.assertEqual(len(deferreds), 1)

        # We need this to errback with a Failure indicating the RSTSTREAM
        # frame.
        def callback(ign):
            self.fail("Didn't errback, called back instead")

        def errback(reason):
            self.assertIsInstance(reason, failure.Failure)
            self.assertIs(reason.type, error.ConnectionLost)
            return None  # Trap the error

        d = deferreds[0]
        d.addCallbacks(callback, errback)

        # Now send the RSTSTREAM frame.
        invalidData = frameFactory.buildRstStreamFrame(streamID=1).serialize()
        connection.dataReceived(invalidData)

        return d

    def test_failWithProtocolError(self):
        """
        A HTTP/2 protocol error triggers the L{http.Request.notifyFinish}
        deferred for all outstanding requests with a Failure that contains the
        underlying exception.
        """
        # We need to set up two requests concurrently so that we can validate
        # that these all fail. connectAndReceive will set up one: we will need
        # to manually send the rest.
        connection = H2Connection()
        connection.requestFactory = NotifyingRequestFactory(DelayedHTTPHandler)
        frameFactory, transport = self.connectAndReceive(
            connection, self.getRequestHeaders, []
        )

        secondRequest = buildRequestBytes(
            self.getRequestHeaders, [], frameFactory=frameFactory, streamID=3
        )
        connection.dataReceived(secondRequest)

        # Now we want to grab the deferreds from the notifying factory.
        deferreds = connection.requestFactory.results
        self.assertEqual(len(deferreds), 2)

        # We need these to errback with a Failure representing the
        # ProtocolError.
        def callback(ign):
            self.fail("Didn't errback, called back instead")

        def errback(reason):
            self.assertIsInstance(reason, failure.Failure)
            self.assertIsInstance(reason.value, h2.exceptions.ProtocolError)
            return None  # Trap the error

        for d in deferreds:
            d.addCallbacks(callback, errback)

        # Now trigger the protocol error. The easiest protocol error to trigger
        # is to send a data frame for a non-existent stream.
        invalidData = frameFactory.buildDataFrame(data=b"yo", streamID=0xF0).serialize()
        connection.dataReceived(invalidData)

        return defer.gatherResults(deferreds)

    def test_failOnGoaway(self):
        """
        A HTTP/2 GoAway triggers the L{http.Request.notifyFinish}
        deferred for all outstanding requests with a Failure that contains a
        RemoteGoAway error.
        """
        # We need to set up two requests concurrently so that we can validate
        # that these all fail. connectAndReceive will set up one: we will need
        # to manually send the rest.
        connection = H2Connection()
        connection.requestFactory = NotifyingRequestFactory(DelayedHTTPHandler)
        frameFactory, transport = self.connectAndReceive(
            connection, self.getRequestHeaders, []
        )

        secondRequest = buildRequestBytes(
            self.getRequestHeaders, [], frameFactory=frameFactory, streamID=3
        )
        connection.dataReceived(secondRequest)

        # Now we want to grab the deferreds from the notifying factory.
        deferreds = connection.requestFactory.results
        self.assertEqual(len(deferreds), 2)

        # We need these to errback with a Failure indicating the GOAWAY frame.
        def callback(ign):
            self.fail("Didn't errback, called back instead")

        def errback(reason):
            self.assertIsInstance(reason, failure.Failure)
            self.assertIs(reason.type, error.ConnectionLost)
            return None  # Trap the error

        for d in deferreds:
            d.addCallbacks(callback, errback)

        # Now send the GoAway frame.
        invalidData = frameFactory.buildGoAwayFrame(lastStreamID=3).serialize()
        connection.dataReceived(invalidData)

        return defer.gatherResults(deferreds)

    def test_failOnStopProducing(self):
        """
        The transport telling the HTTP/2 connection to stop producing will
        fire all L{http.Request.notifyFinish} errbacks with L{error.}
        """
        # We need to set up two requests concurrently so that we can validate
        # that these all fail. connectAndReceive will set up one: we will need
        # to manually send the rest.
        connection = H2Connection()
        connection.requestFactory = NotifyingRequestFactory(DelayedHTTPHandler)
        frameFactory, transport = self.connectAndReceive(
            connection, self.getRequestHeaders, []
        )

        secondRequest = buildRequestBytes(
            self.getRequestHeaders, [], frameFactory=frameFactory, streamID=3
        )
        connection.dataReceived(secondRequest)

        # Now we want to grab the deferreds from the notifying factory.
        deferreds = connection.requestFactory.results
        self.assertEqual(len(deferreds), 2)

        # We need these to errback with a Failure indicating the consumer
        # aborted our data production.
        def callback(ign):
            self.fail("Didn't errback, called back instead")

        def errback(reason):
            self.assertIsInstance(reason, failure.Failure)
            self.assertIs(reason.type, error.ConnectionLost)
            return None  # Trap the error

        for d in deferreds:
            d.addCallbacks(callback, errback)

        # Now call stopProducing.
        connection.stopProducing()

        return defer.gatherResults(deferreds)

    def test_notifyOnFast400(self):
        """
        A HTTP/2 stream that has had _respondToBadRequestAndDisconnect called
        on it from a request handler calls the L{http.Request.notifyFinish}
        errback with L{ConnectionLost}.
        """
        connection = H2Connection()
        connection.requestFactory = NotifyingRequestFactory(DelayedHTTPHandler)
        frameFactory, transport = self.connectAndReceive(
            connection, self.getRequestHeaders, []
        )

        deferreds = connection.requestFactory.results
        self.assertEqual(len(deferreds), 1)

        # We need this to errback with a Failure indicating the loss of the
        # connection.
        def callback(ign):
            self.fail("Didn't errback, called back instead")

        def errback(reason):
            self.assertIsInstance(reason, failure.Failure)
            self.assertIs(reason.type, error.ConnectionLost)
            return None  # Trap the error

        d = deferreds[0]
        d.addCallbacks(callback, errback)

        # Abort the stream. The only "natural" way to trigger this in the
        # current codebase is to send a multipart/form-data request that the
        # cgi module doesn't like.
        # That's absurdly hard, so instead we'll just call it ourselves. For
        # this reason we use the DummyProducerHandler, which doesn't write the
        # headers straight away.
        stream = connection.streams[1]
        stream._respondToBadRequestAndDisconnect()

        return d

    def test_fast400WithCircuitBreaker(self):
        """
        A HTTP/2 stream that has had _respondToBadRequestAndDisconnect
        called on it does not write control frame data if its
        transport is paused and its control frame limit has been
        reached.
        """
        # Set the connection up.
        memoryReactor = MemoryReactorClock()
        connection = H2Connection(memoryReactor)
        connection.callLater = memoryReactor.callLater
        # Use the DelayedHTTPHandler to prevent the connection from
        # writing any response bytes after receiving a request that
        # establishes the stream.
        connection.requestFactory = DelayedHTTPHandler

        streamID = 1

        frameFactory = FrameFactory()
        transport = StringTransport()

        # Establish the connection
        clientConnectionPreface = frameFactory.clientConnectionPreface()
        connection.makeConnection(transport)
        connection.dataReceived(clientConnectionPreface)
        # Establish the stream.
        connection.dataReceived(
            buildRequestBytes(
                self.getRequestHeaders, [], frameFactory, streamID=streamID
            )
        )

        # Pause the connection and limit the number of outbound bytes
        # to 0, so that attempting to send the 400 aborts the
        # connection.
        connection.pauseProducing()
        connection._maxBufferedControlFrameBytes = 0

        connection._respondToBadRequestAndDisconnect(streamID)

        self.assertTrue(transport.disconnected)

    def test_bufferingAutomaticFrameData(self):
        """
        If a the L{H2Connection} has been paused by the transport, it will
        not write automatic frame data triggered by writes.
        """
        # Set the connection up.
        connection = H2Connection()
        connection.requestFactory = DummyHTTPHandlerProxy
        frameFactory = FrameFactory()
        transport = StringTransport()

        clientConnectionPreface = frameFactory.clientConnectionPreface()
        connection.makeConnection(transport)
        connection.dataReceived(clientConnectionPreface)

        # Now we're going to pause the producer.
        connection.pauseProducing()

        # Now we're going to send a bunch of empty SETTINGS frames. This
        # should not cause writes.
        for _ in range(0, 100):
            connection.dataReceived(frameFactory.buildSettingsFrame({}).serialize())

        frames = framesFromBytes(transport.value())
        self.assertEqual(len(frames), 1)

        # Re-enable the transport.
        connection.resumeProducing()
        frames = framesFromBytes(transport.value())
        self.assertEqual(len(frames), 101)

    def test_bufferingAutomaticFrameDataWithCircuitBreaker(self):
        """
        If the L{H2Connection} has been paused by the transport, it will
        not write automatic frame data triggered by writes. If this buffer
        gets too large, the connection will be dropped.
        """
        # Set the connection up.
        connection = H2Connection()
        connection.requestFactory = DummyHTTPHandlerProxy
        frameFactory = FrameFactory()
        transport = StringTransport()

        clientConnectionPreface = frameFactory.clientConnectionPreface()
        connection.makeConnection(transport)
        connection.dataReceived(clientConnectionPreface)

        # Now we're going to pause the producer.
        connection.pauseProducing()

        # Now we're going to limit the outstanding buffered bytes to
        # 100 bytes.
        connection._maxBufferedControlFrameBytes = 100

        # Now we're going to send 11 empty SETTINGS frames. This
        # should not cause writes, or a close.
        self.assertFalse(transport.disconnecting)
        for _ in range(0, 11):
            connection.dataReceived(frameFactory.buildSettingsFrame({}).serialize())
        self.assertFalse(transport.disconnecting)

        # Send a last settings frame, which will push us over the buffer limit.
        connection.dataReceived(frameFactory.buildSettingsFrame({}).serialize())
        self.assertTrue(transport.disconnected)

    def test_bufferingContinuesIfProducerIsPausedOnWrite(self):
        """
        If the L{H2Connection} has buffered control frames, is unpaused, and then
        paused while unbuffering, it persists the buffer and stops trying to write.
        """

        class AutoPausingStringTransport(StringTransport):
            def write(self, *args, **kwargs):
                StringTransport.write(self, *args, **kwargs)
                self.producer.pauseProducing()

        # Set the connection up.
        connection = H2Connection()
        connection.requestFactory = DummyHTTPHandlerProxy
        frameFactory = FrameFactory()
        transport = AutoPausingStringTransport()
        transport.registerProducer(connection, True)

        clientConnectionPreface = frameFactory.clientConnectionPreface()
        connection.makeConnection(transport)
        connection.dataReceived(clientConnectionPreface)

        # The connection should already be paused.
        self.assertIsNotNone(connection._consumerBlocked)
        frames = framesFromBytes(transport.value())
        self.assertEqual(len(frames), 1)
        self.assertEqual(connection._bufferedControlFrameBytes, 0)

        # Now we're going to send 11 empty SETTINGS frames. This should produce
        # no output, but some buffered settings ACKs.
        for _ in range(0, 11):
            connection.dataReceived(frameFactory.buildSettingsFrame({}).serialize())

        frames = framesFromBytes(transport.value())
        self.assertEqual(len(frames), 1)
        self.assertEqual(connection._bufferedControlFrameBytes, 9 * 11)

        # Ok, now we're going to unpause the producer. This should write only one of the
        # SETTINGS ACKs, as the connection gets repaused.
        connection.resumeProducing()

        frames = framesFromBytes(transport.value())
        self.assertEqual(len(frames), 2)
        self.assertEqual(connection._bufferedControlFrameBytes, 9 * 10)

    def test_circuitBreakerAbortsAfterProtocolError(self):
        """
        A client that triggers a L{h2.exceptions.ProtocolError} over a
        paused connection that's reached its buffered control frame
        limit causes that connection to be aborted.
        """
        memoryReactor = MemoryReactorClock()
        connection = H2Connection(memoryReactor)
        connection.callLater = memoryReactor.callLater

        frameFactory = FrameFactory()
        transport = StringTransport()

        # Establish the connection.
        clientConnectionPreface = frameFactory.clientConnectionPreface()
        connection.makeConnection(transport)
        connection.dataReceived(clientConnectionPreface)

        # Pause it and limit the number of outbound bytes to 0, so
        # that a ProtocolError aborts the connection
        connection.pauseProducing()
        connection._maxBufferedControlFrameBytes = 0

        # Trigger a ProtocolError with a data frame that refers to an
        # unknown stream.
        invalidData = frameFactory.buildDataFrame(data=b"yo", streamID=0xF0).serialize()

        # The frame should have aborted the connection.
        connection.dataReceived(invalidData)
        self.assertTrue(transport.disconnected)


class H2FlowControlTests(unittest.TestCase, HTTP2TestHelpers):
    """
    Tests that ensure that we handle HTTP/2 flow control limits appropriately.
    """

    getRequestHeaders = [
        (b":method", b"GET"),
        (b":authority", b"localhost"),
        (b":path", b"/"),
        (b":scheme", b"https"),
        (b"user-agent", b"twisted-test-code"),
    ]

    getResponseData = b"'''\nNone\n'''\n"

    postRequestHeaders = [
        (b":method", b"POST"),
        (b":authority", b"localhost"),
        (b":path", b"/post_endpoint"),
        (b":scheme", b"https"),
        (b"user-agent", b"twisted-test-code"),
        (b"content-length", b"25"),
    ]

    postRequestData = [b"hello ", b"world, ", b"it's ", b"http/2!"]

    postResponseData = b"'''\n25\nhello world, it's http/2!'''\n"

    def test_bufferExcessData(self):
        """
        When a L{Request} object is not using C{IProducer} to generate data and
        so is not having backpressure exerted on it, the L{H2Stream} object
        will buffer data until the flow control window is opened.
        """
        f = FrameFactory()
        b = StringTransport()
        a = H2Connection()
        a.requestFactory = DummyHTTPHandlerProxy

        # Shrink the window to 5 bytes, then send the request.
        requestBytes = f.clientConnectionPreface()
        requestBytes += f.buildSettingsFrame(
            {h2.settings.SettingCodes.INITIAL_WINDOW_SIZE: 5}
        ).serialize()
        requestBytes += buildRequestBytes(self.getRequestHeaders, [], f)
        a.makeConnection(b)
        # one byte at a time, to stress the implementation.
        for byte in iterbytes(requestBytes):
            a.dataReceived(byte)

        # Send in WindowUpdate frames that open the window one byte at a time,
        # to repeatedly temporarily unbuffer data. 5 bytes will have already
        # been sent.
        bonusFrames = len(self.getResponseData) - 5
        for _ in range(bonusFrames):
            frame = f.buildWindowUpdateFrame(streamID=1, increment=1)
            a.dataReceived(frame.serialize())

        # Give the sending loop a chance to catch up!
        def validate(streamID):
            frames = framesFromBytes(b.value())

            # Check that the stream is correctly terminated.
            self.assertTrue("END_STREAM" in frames[-1].flags)

            # Put the Data frames together to confirm we're all good.
            actualResponseData = b"".join(
                f.data for f in frames if isinstance(f, hyperframe.frame.DataFrame)
            )
            self.assertEqual(self.getResponseData, actualResponseData)

        return a._streamCleanupCallbacks[1].addCallback(validate)

    def test_producerBlockingUnblocking(self):
        """
        L{Request} objects that have registered producers get blocked and
        unblocked according to HTTP/2 flow control.
        """
        f = FrameFactory()
        b = StringTransport()
        a = H2Connection()
        a.requestFactory = DummyProducerHandlerProxy

        # Shrink the window to 5 bytes, then send the request.
        requestBytes = f.clientConnectionPreface()
        requestBytes += f.buildSettingsFrame(
            {h2.settings.SettingCodes.INITIAL_WINDOW_SIZE: 5}
        ).serialize()
        requestBytes += buildRequestBytes(self.getRequestHeaders, [], f)
        a.makeConnection(b)
        # one byte at a time, to stress the implementation.
        for byte in iterbytes(requestBytes):
            a.dataReceived(byte)

        # Grab the request object.
        stream = a.streams[1]
        request = stream._request.original

        # Confirm that the stream believes the producer is producing.
        self.assertTrue(stream._producerProducing)

        # Write 10 bytes to the connection.
        request.write(b"helloworld")

        # The producer should have been paused.
        self.assertFalse(stream._producerProducing)
        self.assertEqual(request.producer.events, ["pause"])

        # Open the flow control window by 5 bytes. This should not unpause the
        # producer.
        a.dataReceived(f.buildWindowUpdateFrame(streamID=1, increment=5).serialize())
        self.assertFalse(stream._producerProducing)
        self.assertEqual(request.producer.events, ["pause"])

        # Open the connection window by 5 bytes as well. This should also not
        # unpause the producer.
        a.dataReceived(f.buildWindowUpdateFrame(streamID=0, increment=5).serialize())
        self.assertFalse(stream._producerProducing)
        self.assertEqual(request.producer.events, ["pause"])

        # Open it by five more bytes. This should unpause the producer.
        a.dataReceived(f.buildWindowUpdateFrame(streamID=1, increment=5).serialize())
        self.assertTrue(stream._producerProducing)
        self.assertEqual(request.producer.events, ["pause", "resume"])

        # Write another 10 bytes, which should force us to pause again. When
        # written this chunk will be sent as one lot, simply because of the
        # fact that the sending loop is not currently running.
        request.write(b"helloworld")
        self.assertFalse(stream._producerProducing)
        self.assertEqual(request.producer.events, ["pause", "resume", "pause"])

        # Open the window wide and then complete the request.
        a.dataReceived(f.buildWindowUpdateFrame(streamID=1, increment=50).serialize())
        self.assertTrue(stream._producerProducing)
        self.assertEqual(
            request.producer.events, ["pause", "resume", "pause", "resume"]
        )
        request.unregisterProducer()
        request.finish()

        # Check that the sending loop sends all the appropriate data.
        def validate(streamID):
            frames = framesFromBytes(b.value())

            # Check that the stream is correctly terminated.
            self.assertTrue("END_STREAM" in frames[-1].flags)

            # Grab the data from the frames.
            dataChunks = [
                f.data for f in frames if isinstance(f, hyperframe.frame.DataFrame)
            ]
            self.assertEqual(dataChunks, [b"helloworld", b"helloworld", b""])

        return a._streamCleanupCallbacks[1].addCallback(validate)

    def test_flowControlExact(self):
        """
        Exactly filling the flow control window still blocks producers.
        """
        f = FrameFactory()
        b = StringTransport()
        a = H2Connection()
        a.requestFactory = DummyProducerHandlerProxy

        # Shrink the window to 5 bytes, then send the request.
        requestBytes = f.clientConnectionPreface()
        requestBytes += f.buildSettingsFrame(
            {h2.settings.SettingCodes.INITIAL_WINDOW_SIZE: 5}
        ).serialize()
        requestBytes += buildRequestBytes(self.getRequestHeaders, [], f)
        a.makeConnection(b)
        # one byte at a time, to stress the implementation.
        for byte in iterbytes(requestBytes):
            a.dataReceived(byte)

        # Grab the request object.
        stream = a.streams[1]
        request = stream._request.original

        # Confirm that the stream believes the producer is producing.
        self.assertTrue(stream._producerProducing)

        # Write 10 bytes to the connection. This should block the producer
        # immediately.
        request.write(b"helloworld")
        self.assertFalse(stream._producerProducing)
        self.assertEqual(request.producer.events, ["pause"])

        # Despite the producer being blocked, write one more byte. This should
        # not get sent or force any other data to be sent.
        request.write(b"h")

        # Open the window wide and then complete the request. We do this by
        # means of callLater to ensure that the sending loop has time to run.
        def window_open():
            a.dataReceived(
                f.buildWindowUpdateFrame(streamID=1, increment=50).serialize()
            )
            self.assertTrue(stream._producerProducing)
            self.assertEqual(request.producer.events, ["pause", "resume"])
            request.unregisterProducer()
            request.finish()

        windowDefer = task.deferLater(reactor, 0, window_open)

        # Check that the sending loop sends all the appropriate data.
        def validate(streamID):
            frames = framesFromBytes(b.value())

            # Check that the stream is correctly terminated.
            self.assertTrue("END_STREAM" in frames[-1].flags)

            # Grab the data from the frames.
            dataChunks = [
                f.data for f in frames if isinstance(f, hyperframe.frame.DataFrame)
            ]
            self.assertEqual(dataChunks, [b"hello", b"world", b"h", b""])

        validateDefer = a._streamCleanupCallbacks[1].addCallback(validate)
        return defer.DeferredList([windowDefer, validateDefer])

    def test_endingBlockedStream(self):
        """
        L{Request} objects that end a stream that is currently blocked behind
        flow control can still end the stream and get cleaned up.
        """
        f = FrameFactory()
        b = StringTransport()
        a = H2Connection()
        a.requestFactory = DummyProducerHandlerProxy

        # Shrink the window to 5 bytes, then send the request.
        requestBytes = f.clientConnectionPreface()
        requestBytes += f.buildSettingsFrame(
            {h2.settings.SettingCodes.INITIAL_WINDOW_SIZE: 5}
        ).serialize()
        requestBytes += buildRequestBytes(self.getRequestHeaders, [], f)
        a.makeConnection(b)
        # one byte at a time, to stress the implementation.
        for byte in iterbytes(requestBytes):
            a.dataReceived(byte)

        # Grab the request object.
        stream = a.streams[1]
        request = stream._request.original

        # Confirm that the stream believes the producer is producing.
        self.assertTrue(stream._producerProducing)

        # Write 10 bytes to the connection, then complete the connection.
        request.write(b"helloworld")
        request.unregisterProducer()
        request.finish()

        # This should have completed the request.
        self.assertTrue(request.finished)

        # Open the window wide and then complete the request.
        reactor.callLater(
            0,
            a.dataReceived,
            f.buildWindowUpdateFrame(streamID=1, increment=50).serialize(),
        )

        # Check that the sending loop sends all the appropriate data.
        def validate(streamID):
            frames = framesFromBytes(b.value())

            # Check that the stream is correctly terminated.
            self.assertTrue("END_STREAM" in frames[-1].flags)

            # Grab the data from the frames.
            dataChunks = [
                f.data for f in frames if isinstance(f, hyperframe.frame.DataFrame)
            ]
            self.assertEqual(dataChunks, [b"hello", b"world", b""])

        return a._streamCleanupCallbacks[1].addCallback(validate)

    def test_responseWithoutBody(self):
        """
        We safely handle responses without bodies.
        """
        f = FrameFactory()
        b = StringTransport()
        a = H2Connection()

        # We use the DummyProducerHandler just because we can guarantee that it
        # doesn't end up with a body.
        a.requestFactory = DummyProducerHandlerProxy

        # Send the request.
        requestBytes = f.clientConnectionPreface()
        requestBytes += buildRequestBytes(self.getRequestHeaders, [], f)
        a.makeConnection(b)
        # one byte at a time, to stress the implementation.
        for byte in iterbytes(requestBytes):
            a.dataReceived(byte)

        # Grab the request object and the stream completion callback.
        stream = a.streams[1]
        request = stream._request.original
        cleanupCallback = a._streamCleanupCallbacks[1]

        # Complete the connection immediately.
        request.unregisterProducer()
        request.finish()

        # This should have completed the request.
        self.assertTrue(request.finished)

        # Check that the sending loop sends all the appropriate data.
        def validate(streamID):
            frames = framesFromBytes(b.value())

            self.assertEqual(len(frames), 3)

            # Check that the stream is correctly terminated.
            self.assertTrue("END_STREAM" in frames[-1].flags)

            # Grab the data from the frames.
            dataChunks = [
                f.data for f in frames if isinstance(f, hyperframe.frame.DataFrame)
            ]
            self.assertEqual(
                dataChunks,
                [b""],
            )

        return cleanupCallback.addCallback(validate)

    def test_windowUpdateForCompleteStream(self):
        """
        WindowUpdate frames received after we've completed the stream are
        safely handled.
        """
        # To test this with the data sending loop working the way it does, we
        # need to send *no* body on the response. That's unusual, but fine.
        f = FrameFactory()
        b = StringTransport()
        a = H2Connection()

        # We use the DummyProducerHandler just because we can guarantee that it
        # doesn't end up with a body.
        a.requestFactory = DummyProducerHandlerProxy

        # Send the request.
        requestBytes = f.clientConnectionPreface()
        requestBytes += buildRequestBytes(self.getRequestHeaders, [], f)
        a.makeConnection(b)
        # one byte at a time, to stress the implementation.
        for byte in iterbytes(requestBytes):
            a.dataReceived(byte)

        # Grab the request object and the stream completion callback.
        stream = a.streams[1]
        request = stream._request.original
        cleanupCallback = a._streamCleanupCallbacks[1]

        # Complete the connection immediately.
        request.unregisterProducer()
        request.finish()

        # This should have completed the request.
        self.assertTrue(request.finished)

        # Now open the flow control window a bit. This should cause no
        # problems.
        a.dataReceived(f.buildWindowUpdateFrame(streamID=1, increment=50).serialize())

        # Check that the sending loop sends all the appropriate data.
        def validate(streamID):
            frames = framesFromBytes(b.value())

            self.assertEqual(len(frames), 3)

            # Check that the stream is correctly terminated.
            self.assertTrue("END_STREAM" in frames[-1].flags)

            # Grab the data from the frames.
            dataChunks = [
                f.data for f in frames if isinstance(f, hyperframe.frame.DataFrame)
            ]
            self.assertEqual(
                dataChunks,
                [b""],
            )

        return cleanupCallback.addCallback(validate)

    def test_producerUnblocked(self):
        """
        L{Request} objects that have registered producers that are not blocked
        behind flow control do not have their producer notified.
        """
        f = FrameFactory()
        b = StringTransport()
        a = H2Connection()
        a.requestFactory = DummyProducerHandlerProxy

        # Shrink the window to 5 bytes, then send the request.
        requestBytes = f.clientConnectionPreface()
        requestBytes += f.buildSettingsFrame(
            {h2.settings.SettingCodes.INITIAL_WINDOW_SIZE: 5}
        ).serialize()
        requestBytes += buildRequestBytes(self.getRequestHeaders, [], f)
        a.makeConnection(b)
        # one byte at a time, to stress the implementation.
        for byte in iterbytes(requestBytes):
            a.dataReceived(byte)

        # Grab the request object.
        stream = a.streams[1]
        request = stream._request.original

        # Confirm that the stream believes the producer is producing.
        self.assertTrue(stream._producerProducing)

        # Write 4 bytes to the connection, leaving space in the window.
        request.write(b"word")

        # The producer should not have been paused.
        self.assertTrue(stream._producerProducing)
        self.assertEqual(request.producer.events, [])

        # Open the flow control window by 5 bytes. This should not notify the
        # producer.
        a.dataReceived(f.buildWindowUpdateFrame(streamID=1, increment=5).serialize())
        self.assertTrue(stream._producerProducing)
        self.assertEqual(request.producer.events, [])

        # Open the window wide complete the request.
        request.unregisterProducer()
        request.finish()

        # Check that the sending loop sends all the appropriate data.
        def validate(streamID):
            frames = framesFromBytes(b.value())

            # Check that the stream is correctly terminated.
            self.assertTrue("END_STREAM" in frames[-1].flags)

            # Grab the data from the frames.
            dataChunks = [
                f.data for f in frames if isinstance(f, hyperframe.frame.DataFrame)
            ]
            self.assertEqual(dataChunks, [b"word", b""])

        return a._streamCleanupCallbacks[1].addCallback(validate)

    def test_unnecessaryWindowUpdate(self):
        """
        When a WindowUpdate frame is received for the whole connection but no
        data is currently waiting, nothing exciting happens.
        """
        f = FrameFactory()
        b = StringTransport()
        a = H2Connection()
        a.requestFactory = DummyHTTPHandlerProxy

        # Send the request.
        frames = buildRequestFrames(self.postRequestHeaders, self.postRequestData, f)
        frames.insert(1, f.buildWindowUpdateFrame(streamID=0, increment=5))
        requestBytes = f.clientConnectionPreface()
        requestBytes += b"".join(f.serialize() for f in frames)
        a.makeConnection(b)
        # one byte at a time, to stress the implementation.
        for byte in iterbytes(requestBytes):
            a.dataReceived(byte)

        # Give the sending loop a chance to catch up!
        def validate(streamID):
            frames = framesFromBytes(b.value())

            # Check that the stream is correctly terminated.
            self.assertTrue("END_STREAM" in frames[-1].flags)

            # Put the Data frames together to confirm we're all good.
            actualResponseData = b"".join(
                f.data for f in frames if isinstance(f, hyperframe.frame.DataFrame)
            )
            self.assertEqual(self.postResponseData, actualResponseData)

        return a._streamCleanupCallbacks[1].addCallback(validate)

    def test_unnecessaryWindowUpdateForStream(self):
        """
        When a WindowUpdate frame is received for a stream but no data is
        currently waiting, that stream is not marked as unblocked and the
        priority tree continues to assert that no stream can progress.
        """
        f = FrameFactory()
        transport = StringTransport()
        conn = H2Connection()
        conn.requestFactory = DummyHTTPHandlerProxy

        # Send a request that implies a body is coming. Twisted doesn't send a
        # response until the entire request is received, so it won't queue any
        # data yet. Then, fire off a WINDOW_UPDATE frame.
        frames = []
        frames.append(f.buildHeadersFrame(headers=self.postRequestHeaders, streamID=1))
        frames.append(f.buildWindowUpdateFrame(streamID=1, increment=5))
        data = f.clientConnectionPreface()
        data += b"".join(f.serialize() for f in frames)

        conn.makeConnection(transport)
        conn.dataReceived(data)

        self.assertAllStreamsBlocked(conn)

    def test_windowUpdateAfterTerminate(self):
        """
        When a WindowUpdate frame is received for a stream that has been
        aborted it is ignored.
        """
        f = FrameFactory()
        b = StringTransport()
        a = H2Connection()
        a.requestFactory = DummyHTTPHandlerProxy

        # Send the request.
        frames = buildRequestFrames(self.postRequestHeaders, self.postRequestData, f)
        requestBytes = f.clientConnectionPreface()
        requestBytes += b"".join(f.serialize() for f in frames)
        a.makeConnection(b)
        # one byte at a time, to stress the implementation.
        for byte in iterbytes(requestBytes):
            a.dataReceived(byte)

        # Abort the connection.
        a.streams[1].abortConnection()

        # Send a WindowUpdate
        windowUpdateFrame = f.buildWindowUpdateFrame(streamID=1, increment=5)
        a.dataReceived(windowUpdateFrame.serialize())

        # Give the sending loop a chance to catch up!
        frames = framesFromBytes(b.value())

        # Check that the stream is terminated.
        self.assertTrue(isinstance(frames[-1], hyperframe.frame.RstStreamFrame))

    def test_windowUpdateAfterComplete(self):
        """
        When a WindowUpdate frame is received for a stream that has been
        completed it is ignored.
        """
        f = FrameFactory()
        b = StringTransport()
        a = H2Connection()
        a.requestFactory = DummyHTTPHandlerProxy

        # Send the request.
        frames = buildRequestFrames(self.postRequestHeaders, self.postRequestData, f)
        requestBytes = f.clientConnectionPreface()
        requestBytes += b"".join(f.serialize() for f in frames)
        a.makeConnection(b)
        # one byte at a time, to stress the implementation.
        for byte in iterbytes(requestBytes):
            a.dataReceived(byte)

        def update_window(*args):
            # Send a WindowUpdate
            windowUpdateFrame = f.buildWindowUpdateFrame(streamID=1, increment=5)
            a.dataReceived(windowUpdateFrame.serialize())

        def validate(*args):
            # Give the sending loop a chance to catch up!
            frames = framesFromBytes(b.value())

            # Check that the stream is ended neatly.
            self.assertIn("END_STREAM", frames[-1].flags)

        d = a._streamCleanupCallbacks[1].addCallback(update_window)
        return d.addCallback(validate)

    def test_dataAndRstStream(self):
        """
        When a DATA frame is received at the same time as RST_STREAM,
        Twisted does not send WINDOW_UPDATE frames for the stream.
        """
        frameFactory = FrameFactory()
        transport = StringTransport()
        a = H2Connection()
        a.requestFactory = DummyHTTPHandlerProxy

        # Send the request, but instead of the last frame send a RST_STREAM
        # frame instead. This needs to be very long to actually force the
        # WINDOW_UPDATE frames out.
        frameData = [b"\x00" * (2 ** 14)] * 4
        bodyLength = f"{sum(len(data) for data in frameData)}"
        headers = self.postRequestHeaders[:-1] + [("content-length", bodyLength)]
        frames = buildRequestFrames(
            headers=headers, data=frameData, frameFactory=frameFactory
        )
        del frames[-1]
        frames.append(
            frameFactory.buildRstStreamFrame(
                streamID=1, errorCode=h2.errors.ErrorCodes.INTERNAL_ERROR
            )
        )

        requestBytes = frameFactory.clientConnectionPreface()
        requestBytes += b"".join(f.serialize() for f in frames)
        a.makeConnection(transport)

        # Feed all the bytes at once. This is important: if they arrive slowly,
        # Twisted doesn't have any problems.
        a.dataReceived(requestBytes)

        # Check the frames we got. We expect a WINDOW_UPDATE frame only for the
        # connection, because Twisted knew the stream was going to be reset.
        frames = framesFromBytes(transport.value())

        # Check that the only WINDOW_UPDATE frame came for the connection.
        windowUpdateFrameIDs = [
            f.stream_id
            for f in frames
            if isinstance(f, hyperframe.frame.WindowUpdateFrame)
        ]
        self.assertEqual([0], windowUpdateFrameIDs)

        # While we're here: we shouldn't have received HEADERS or DATA for this
        # either.
        headersFrames = [
            f for f in frames if isinstance(f, hyperframe.frame.HeadersFrame)
        ]
        dataFrames = [f for f in frames if isinstance(f, hyperframe.frame.DataFrame)]
        self.assertFalse(headersFrames)
        self.assertFalse(dataFrames)

    def test_abortRequestWithCircuitBreaker(self):
        """
        Aborting a request associated with a paused connection that's
        reached its buffered control frame limit causes that
        connection to be aborted.
        """
        memoryReactor = MemoryReactorClock()
        connection = H2Connection(memoryReactor)
        connection.callLater = memoryReactor.callLater
        connection.requestFactory = DummyHTTPHandlerProxy

        frameFactory = FrameFactory()
        transport = StringTransport()

        # Establish the connection.
        clientConnectionPreface = frameFactory.clientConnectionPreface()
        connection.makeConnection(transport)
        connection.dataReceived(clientConnectionPreface)

        # Send a headers frame for a stream
        streamID = 1
        headersFrameData = frameFactory.buildHeadersFrame(
            headers=self.postRequestHeaders, streamID=streamID
        ).serialize()
        connection.dataReceived(headersFrameData)

        # Pause it and limit the number of outbound bytes to 1, so
        # that a ProtocolError aborts the connection
        connection.pauseProducing()
        connection._maxBufferedControlFrameBytes = 0

        # Remove anything sent by the preceding frames.
        transport.clear()

        # Abort the request.
        connection.abortRequest(streamID)

        # No RST_STREAM frame was sent...
        self.assertFalse(transport.value())
        # ...and the transport was disconnected (abortConnection was
        # called)
        self.assertTrue(transport.disconnected)


class HTTP2TransportChecking(unittest.TestCase, HTTP2TestHelpers):
    getRequestHeaders = [
        (b":method", b"GET"),
        (b":authority", b"localhost"),
        (b":path", b"/"),
        (b":scheme", b"https"),
        (b"user-agent", b"twisted-test-code"),
        (b"custom-header", b"1"),
        (b"custom-header", b"2"),
    ]

    def test_registerProducerWithTransport(self):
        """
        L{H2Connection} can be registered with the transport as a producer.
        """
        b = StringTransport()
        a = H2Connection()
        a.requestFactory = DummyHTTPHandlerProxy

        b.registerProducer(a, True)
        self.assertTrue(b.producer is a)

    def test_pausingProducerPreventsDataSend(self):
        """
        L{H2Connection} can be paused by its consumer. When paused it stops
        sending data to the transport.
        """
        f = FrameFactory()
        b = StringTransport()
        a = H2Connection()
        a.requestFactory = DummyHTTPHandlerProxy

        # Send the request.
        frames = buildRequestFrames(self.getRequestHeaders, [], f)
        requestBytes = f.clientConnectionPreface()
        requestBytes += b"".join(f.serialize() for f in frames)
        a.makeConnection(b)
        b.registerProducer(a, True)

        # one byte at a time, to stress the implementation.
        for byte in iterbytes(requestBytes):
            a.dataReceived(byte)

        # The headers will be sent immediately, but the body will be waiting
        # until the reactor gets to spin. Before it does we'll pause
        # production.
        a.pauseProducing()

        # Now we want to build up a whole chain of Deferreds. We want to
        # 1. deferLater for a moment to let the sending loop run, which should
        #    block.
        # 2. After that deferred fires, we want to validate that no data has
        #    been sent yet.
        # 3. Then we want to resume the production.
        # 4. Then, we want to wait for the stream completion deferred.
        # 5. Validate that the data is correct.
        cleanupCallback = a._streamCleanupCallbacks[1]

        def validateNotSent(*args):
            frames = framesFromBytes(b.value())

            self.assertEqual(len(frames), 2)
            self.assertFalse(isinstance(frames[-1], hyperframe.frame.DataFrame))
            a.resumeProducing()

            # Resume producing is a no-op, so let's call it a bunch more times.
            a.resumeProducing()
            a.resumeProducing()
            a.resumeProducing()
            a.resumeProducing()
            return cleanupCallback

        def validateComplete(*args):
            frames = framesFromBytes(b.value())

            # Check that the stream is correctly terminated.
            self.assertEqual(len(frames), 4)
            self.assertTrue("END_STREAM" in frames[-1].flags)

        d = task.deferLater(reactor, 0.01, validateNotSent)
        d.addCallback(validateComplete)

        return d

    def test_stopProducing(self):
        """
        L{H2Connection} can be stopped by its producer. That causes it to lose
        its transport.
        """
        f = FrameFactory()
        b = StringTransport()
        a = H2Connection()
        a.requestFactory = DummyHTTPHandlerProxy

        # Send the request.
        frames = buildRequestFrames(self.getRequestHeaders, [], f)
        requestBytes = f.clientConnectionPreface()
        requestBytes += b"".join(f.serialize() for f in frames)
        a.makeConnection(b)
        b.registerProducer(a, True)

        # one byte at a time, to stress the implementation.
        for byte in iterbytes(requestBytes):
            a.dataReceived(byte)

        # The headers will be sent immediately, but the body will be waiting
        # until the reactor gets to spin. Before it does we'll stop production.
        a.stopProducing()

        frames = framesFromBytes(b.value())

        self.assertEqual(len(frames), 2)
        self.assertFalse(isinstance(frames[-1], hyperframe.frame.DataFrame))
        self.assertFalse(a._stillProducing)

    def test_passthroughHostAndPeer(self):
        """
        A L{H2Stream} object correctly passes through host and peer information
        from its L{H2Connection}.
        """
        hostAddress = IPv4Address("TCP", "17.52.24.8", 443)
        peerAddress = IPv4Address("TCP", "17.188.0.12", 32008)

        frameFactory = FrameFactory()
        transport = StringTransport(hostAddress=hostAddress, peerAddress=peerAddress)
        connection = H2Connection()
        connection.requestFactory = DummyHTTPHandlerProxy
        connection.makeConnection(transport)

        frames = buildRequestFrames(self.getRequestHeaders, [], frameFactory)
        requestBytes = frameFactory.clientConnectionPreface()
        requestBytes += b"".join(frame.serialize() for frame in frames)

        for byte in iterbytes(requestBytes):
            connection.dataReceived(byte)

        # The stream is present. Go grab the stream object.
        stream = connection.streams[1]
        self.assertEqual(stream.getHost(), hostAddress)
        self.assertEqual(stream.getPeer(), peerAddress)

        # Allow the stream to finish up and check the result.
        cleanupCallback = connection._streamCleanupCallbacks[1]

        def validate(*args):
            self.assertEqual(stream.getHost(), hostAddress)
            self.assertEqual(stream.getPeer(), peerAddress)

        return cleanupCallback.addCallback(validate)


class HTTP2SchedulingTests(unittest.TestCase, HTTP2TestHelpers):
    """
    The H2Connection object schedules certain events (mostly its data sending
    loop) using callbacks from the reactor. These tests validate that the calls
    are scheduled correctly.
    """

    def test_initiallySchedulesOneDataCall(self):
        """
        When a H2Connection is established it schedules one call to be run as
        soon as the reactor has time.
        """
        reactor = task.Clock()
        a = H2Connection(reactor)

        calls = reactor.getDelayedCalls()
        self.assertEqual(len(calls), 1)
        call = calls[0]

        # Validate that the call is scheduled for right now, but hasn't run,
        # and that it's correct.
        self.assertTrue(call.active())
        self.assertEqual(call.time, 0)
        self.assertEqual(call.func, a._sendPrioritisedData)
        self.assertEqual(call.args, ())
        self.assertEqual(call.kw, {})


class HTTP2TimeoutTests(unittest.TestCase, HTTP2TestHelpers):
    """
    The L{H2Connection} object times out idle connections.
    """

    getRequestHeaders = [
        (b":method", b"GET"),
        (b":authority", b"localhost"),
        (b":path", b"/"),
        (b":scheme", b"https"),
        (b"user-agent", b"twisted-test-code"),
        (b"custom-header", b"1"),
        (b"custom-header", b"2"),
    ]

    # A sentinel object used to flag default timeouts
    _DEFAULT = object()

    def patch_TimeoutMixin_clock(self, connection, reactor):
        """
        Unfortunately, TimeoutMixin does not allow passing an explicit reactor
        to test timeouts. For that reason, we need to monkeypatch the method
        set up by the TimeoutMixin.

        @param connection: The HTTP/2 connection object to patch.
        @type connection: L{H2Connection}

        @param reactor: The reactor whose callLater method we want.
        @type reactor: An object implementing
            L{twisted.internet.interfaces.IReactorTime}
        """
        connection.callLater = reactor.callLater

    def initiateH2Connection(self, initialData, requestFactory):
        """
        Performs test setup by building a HTTP/2 connection object, a transport
        to back it, a reactor to run in, and sending in some initial data as
        needed.

        @param initialData: The initial HTTP/2 data to be fed into the
            connection after setup.
        @type initialData: L{bytes}

        @param requestFactory: The L{Request} factory to use with the
            connection.
        """
        reactor = task.Clock()
        conn = H2Connection(reactor)
        conn.timeOut = 100
        self.patch_TimeoutMixin_clock(conn, reactor)

        transport = StringTransport()
        conn.requestFactory = _makeRequestProxyFactory(requestFactory)
        conn.makeConnection(transport)

        # one byte at a time, to stress the implementation.
        for byte in iterbytes(initialData):
            conn.dataReceived(byte)

        return (reactor, conn, transport)

    def assertTimedOut(self, data, frameCount, errorCode, lastStreamID):
        """
        Confirm that the data that was sent matches what we expect from a
        timeout: namely, that it ends with a GOAWAY frame carrying an
        appropriate error code and last stream ID.
        """
        frames = framesFromBytes(data)

        self.assertEqual(len(frames), frameCount)
        self.assertTrue(isinstance(frames[-1], hyperframe.frame.GoAwayFrame))
        self.assertEqual(frames[-1].error_code, errorCode)
        self.assertEqual(frames[-1].last_stream_id, lastStreamID)

    def prepareAbortTest(self, abortTimeout=_DEFAULT):
        """
        Does the common setup for tests that want to test the aborting
        functionality of the HTTP/2 stack.

        @param abortTimeout: The value to use for the abortTimeout. Defaults to
            whatever is set on L{H2Connection.abortTimeout}.
        @type abortTimeout: L{int} or L{None}

        @return: A tuple of the reactor being used for the connection, the
            connection itself, and the transport.
        """
        if abortTimeout is self._DEFAULT:
            abortTimeout = H2Connection.abortTimeout

        frameFactory = FrameFactory()
        initialData = frameFactory.clientConnectionPreface()

        reactor, conn, transport = self.initiateH2Connection(
            initialData,
            requestFactory=DummyHTTPHandler,
        )
        conn.abortTimeout = abortTimeout

        # Advance the clock.
        reactor.advance(100)

        self.assertTimedOut(
            transport.value(),
            frameCount=2,
            errorCode=h2.errors.ErrorCodes.NO_ERROR,
            lastStreamID=0,
        )
        self.assertTrue(transport.disconnecting)
        self.assertFalse(transport.disconnected)

        return reactor, conn, transport

    def test_timeoutAfterInactivity(self):
        """
        When a L{H2Connection} does not receive any data for more than the
        time out interval, it closes the connection cleanly.
        """
        frameFactory = FrameFactory()
        initialData = frameFactory.clientConnectionPreface()

        reactor, conn, transport = self.initiateH2Connection(
            initialData,
            requestFactory=DummyHTTPHandler,
        )

        # Save the response preamble.
        preamble = transport.value()

        # Advance the clock.
        reactor.advance(99)

        # Everything is fine, no extra data got sent.
        self.assertEqual(preamble, transport.value())
        self.assertFalse(transport.disconnecting)

        # Advance the clock.
        reactor.advance(2)

        self.assertTimedOut(
            transport.value(),
            frameCount=2,
            errorCode=h2.errors.ErrorCodes.NO_ERROR,
            lastStreamID=0,
        )
        self.assertTrue(transport.disconnecting)

    def test_timeoutResetByRequestData(self):
        """
        When a L{H2Connection} receives data, the timeout is reset.
        """
        # Don't send any initial data, we'll send the preamble manually.
        frameFactory = FrameFactory()
        initialData = b""

        reactor, conn, transport = self.initiateH2Connection(
            initialData,
            requestFactory=DummyHTTPHandler,
        )

        # Send one byte of the preamble every 99 'seconds'.
        for byte in iterbytes(frameFactory.clientConnectionPreface()):
            conn.dataReceived(byte)

            # Advance the clock.
            reactor.advance(99)

            # Everything is fine.
            self.assertFalse(transport.disconnecting)

        # Advance the clock.
        reactor.advance(2)

        self.assertTimedOut(
            transport.value(),
            frameCount=2,
            errorCode=h2.errors.ErrorCodes.NO_ERROR,
            lastStreamID=0,
        )
        self.assertTrue(transport.disconnecting)

    def test_timeoutResetByResponseData(self):
        """
        When a L{H2Connection} sends data, the timeout is reset.
        """
        # Don't send any initial data, we'll send the preamble manually.
        frameFactory = FrameFactory()
        initialData = b""
        requests = []

        frames = buildRequestFrames(self.getRequestHeaders, [], frameFactory)
        initialData = frameFactory.clientConnectionPreface()
        initialData += b"".join(f.serialize() for f in frames)

        def saveRequest(stream, queued):
            req = DelayedHTTPHandler(stream, queued=queued)
            requests.append(req)
            return req

        reactor, conn, transport = self.initiateH2Connection(
            initialData,
            requestFactory=saveRequest,
        )

        conn.dataReceived(frameFactory.clientConnectionPreface())

        # Advance the clock.
        reactor.advance(99)
        self.assertEquals(len(requests), 1)

        for x in range(10):
            # It doesn't time out as it's being written...
            requests[0].write(b"some bytes")
            reactor.advance(99)
            self.assertFalse(transport.disconnecting)

        # but the timer is still running, and it times out when it idles.
        reactor.advance(2)
        self.assertTimedOut(
            transport.value(),
            frameCount=13,
            errorCode=h2.errors.ErrorCodes.PROTOCOL_ERROR,
            lastStreamID=1,
        )

    def test_timeoutWithProtocolErrorIfStreamsOpen(self):
        """
        When a L{H2Connection} times out with active streams, the error code
        returned is L{h2.errors.ErrorCodes.PROTOCOL_ERROR}.
        """
        frameFactory = FrameFactory()
        frames = buildRequestFrames(self.getRequestHeaders, [], frameFactory)
        initialData = frameFactory.clientConnectionPreface()
        initialData += b"".join(f.serialize() for f in frames)

        reactor, conn, transport = self.initiateH2Connection(
            initialData,
            requestFactory=DummyProducerHandler,
        )

        # Advance the clock to time out the request.
        reactor.advance(101)

        self.assertTimedOut(
            transport.value(),
            frameCount=2,
            errorCode=h2.errors.ErrorCodes.PROTOCOL_ERROR,
            lastStreamID=1,
        )
        self.assertTrue(transport.disconnecting)

    def test_noTimeoutIfConnectionLost(self):
        """
        When a L{H2Connection} loses its connection it cancels its timeout.
        """
        frameFactory = FrameFactory()
        frames = buildRequestFrames(self.getRequestHeaders, [], frameFactory)
        initialData = frameFactory.clientConnectionPreface()
        initialData += b"".join(f.serialize() for f in frames)

        reactor, conn, transport = self.initiateH2Connection(
            initialData,
            requestFactory=DummyProducerHandler,
        )

        sentData = transport.value()
        oldCallCount = len(reactor.getDelayedCalls())

        # Now lose the connection.
        conn.connectionLost("reason")

        # There should be one fewer call than there was.
        currentCallCount = len(reactor.getDelayedCalls())
        self.assertEqual(oldCallCount - 1, currentCallCount)

        # Advancing the clock should do nothing.
        reactor.advance(101)
        self.assertEqual(transport.value(), sentData)

    def test_timeoutEventuallyForcesConnectionClosed(self):
        """
        When a L{H2Connection} has timed the connection out, and the transport
        doesn't get torn down within 15 seconds, it gets forcibly closed.
        """
        reactor, conn, transport = self.prepareAbortTest()

        # Advance the clock to see that we abort the connection.
        reactor.advance(14)
        self.assertTrue(transport.disconnecting)
        self.assertFalse(transport.disconnected)
        reactor.advance(1)
        self.assertTrue(transport.disconnecting)
        self.assertTrue(transport.disconnected)

    def test_losingConnectionCancelsTheAbort(self):
        """
        When a L{H2Connection} has timed the connection out, getting
        C{connectionLost} called on it cancels the forcible connection close.
        """
        reactor, conn, transport = self.prepareAbortTest()

        # Advance the clock, but right before the end fire connectionLost.
        reactor.advance(14)
        conn.connectionLost(None)

        # Check that the transport isn't forcibly closed.
        reactor.advance(1)
        self.assertTrue(transport.disconnecting)
        self.assertFalse(transport.disconnected)

    def test_losingConnectionWithNoAbortTimeOut(self):
        """
        When a L{H2Connection} has timed the connection out but the
        C{abortTimeout} is set to L{None}, the connection is never aborted.
        """
        reactor, conn, transport = self.prepareAbortTest(abortTimeout=None)

        # Advance the clock an arbitrarily long way, and confirm it never
        # aborts.
        reactor.advance(2 ** 32)
        self.assertTrue(transport.disconnecting)
        self.assertFalse(transport.disconnected)

    def test_connectionLostAfterForceClose(self):
        """
        If a timed out transport doesn't close after 15 seconds, the
        L{HTTPChannel} will forcibly close it.
        """
        reactor, conn, transport = self.prepareAbortTest()

        # Force the follow-on forced closure.
        reactor.advance(15)
        self.assertTrue(transport.disconnecting)
        self.assertTrue(transport.disconnected)

        # Now call connectionLost on the protocol. This is done by some
        # transports, including TCP and TLS. We don't have anything we can
        # assert on here: this just must not explode.
        conn.connectionLost(error.ConnectionDone)

    def test_timeOutClientThatSendsOnlyInvalidFrames(self):
        """
        A client that sends only invalid frames is eventually timed out.
        """
        memoryReactor = MemoryReactorClock()

        connection = H2Connection(memoryReactor)
        connection.callLater = memoryReactor.callLater
        connection.timeOut = 60

        frameFactory = FrameFactory()
        transport = StringTransport()

        clientConnectionPreface = frameFactory.clientConnectionPreface()
        connection.makeConnection(transport)
        connection.dataReceived(clientConnectionPreface)

        # Send data until both the loseConnection and abortConnection
        # timeouts have elapsed.
        for _ in range(connection.timeOut + connection.abortTimeout):
            connection.dataReceived(frameFactory.buildRstStreamFrame(1).serialize())
            memoryReactor.advance(1)

        # Invalid frames don't reset any timeouts, so the above has
        # forcibly disconnected us via abortConnection.
        self.assertTrue(transport.disconnected)
