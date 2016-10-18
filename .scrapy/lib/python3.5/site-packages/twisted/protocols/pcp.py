# -*- test-case-name: twisted.test.test_pcp -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Producer-Consumer Proxy.
"""

from zope.interface import implementer

from twisted.internet import interfaces


@implementer(interfaces.IProducer, interfaces.IConsumer)
class BasicProducerConsumerProxy:
    """
    I can act as a man in the middle between any Producer and Consumer.

    @ivar producer: the Producer I subscribe to.
    @type producer: L{IProducer<interfaces.IProducer>}
    @ivar consumer: the Consumer I publish to.
    @type consumer: L{IConsumer<interfaces.IConsumer>}
    @ivar paused: As a Producer, am I paused?
    @type paused: bool
    """
    consumer = None
    producer = None
    producerIsStreaming = None
    iAmStreaming = True
    outstandingPull = False
    paused = False
    stopped = False

    def __init__(self, consumer):
        self._buffer = []
        if consumer is not None:
            self.consumer = consumer
            consumer.registerProducer(self, self.iAmStreaming)

    # Producer methods:

    def pauseProducing(self):
        self.paused = True
        if self.producer:
            self.producer.pauseProducing()

    def resumeProducing(self):
        self.paused = False
        if self._buffer:
            # TODO: Check to see if consumer supports writeSeq.
            self.consumer.write(''.join(self._buffer))
            self._buffer[:] = []
        else:
            if not self.iAmStreaming:
                self.outstandingPull = True

        if self.producer is not None:
            self.producer.resumeProducing()

    def stopProducing(self):
        if self.producer is not None:
            self.producer.stopProducing()
        if self.consumer is not None:
            del self.consumer

    # Consumer methods:

    def write(self, data):
        if self.paused or (not self.iAmStreaming and not self.outstandingPull):
            # We could use that fifo queue here.
            self._buffer.append(data)

        elif self.consumer is not None:
            self.consumer.write(data)
            self.outstandingPull = False

    def finish(self):
        if self.consumer is not None:
            self.consumer.finish()
        self.unregisterProducer()

    def registerProducer(self, producer, streaming):
        self.producer = producer
        self.producerIsStreaming = streaming

    def unregisterProducer(self):
        if self.producer is not None:
            del self.producer
            del self.producerIsStreaming
        if self.consumer:
            self.consumer.unregisterProducer()

    def __repr__(self):
        return '<%s@%x around %s>' % (self.__class__, id(self), self.consumer)


class ProducerConsumerProxy(BasicProducerConsumerProxy):
    """ProducerConsumerProxy with a finite buffer.

    When my buffer fills up, I have my parent Producer pause until my buffer
    has room in it again.
    """
    # Copies much from abstract.FileDescriptor
    bufferSize = 2**2**2**2

    producerPaused = False
    unregistered = False

    def pauseProducing(self):
        # Does *not* call up to ProducerConsumerProxy to relay the pause
        # message through to my parent Producer.
        self.paused = True

    def resumeProducing(self):
        self.paused = False
        if self._buffer:
            data = ''.join(self._buffer)
            bytesSent = self._writeSomeData(data)
            if bytesSent < len(data):
                unsent = data[bytesSent:]
                assert not self.iAmStreaming, (
                    "Streaming producer did not write all its data.")
                self._buffer[:] = [unsent]
            else:
                self._buffer[:] = []
        else:
            bytesSent = 0

        if (self.unregistered and bytesSent and not self._buffer and
            self.consumer is not None):
            self.consumer.unregisterProducer()

        if not self.iAmStreaming:
            self.outstandingPull = not bytesSent

        if self.producer is not None:
            bytesBuffered = sum([len(s) for s in self._buffer])
            # TODO: You can see here the potential for high and low
            # watermarks, where bufferSize would be the high mark when we
            # ask the upstream producer to pause, and we wouldn't have
            # it resume again until it hit the low mark.  Or if producer
            # is Pull, maybe we'd like to pull from it as much as necessary
            # to keep our buffer full to the low mark, so we're never caught
            # without something to send.
            if self.producerPaused and (bytesBuffered < self.bufferSize):
                # Now that our buffer is empty,
                self.producerPaused = False
                self.producer.resumeProducing()
            elif self.outstandingPull:
                # I did not have any data to write in response to a pull,
                # so I'd better pull some myself.
                self.producer.resumeProducing()

    def write(self, data):
        if self.paused or (not self.iAmStreaming and not self.outstandingPull):
            # We could use that fifo queue here.
            self._buffer.append(data)

        elif self.consumer is not None:
            assert not self._buffer, (
                "Writing fresh data to consumer before my buffer is empty!")
            # I'm going to use _writeSomeData here so that there is only one
            # path to self.consumer.write.  But it doesn't actually make sense,
            # if I am streaming, for some data to not be all data.  But maybe I
            # am not streaming, but I am writing here anyway, because there was
            # an earlier request for data which was not answered.
            bytesSent = self._writeSomeData(data)
            self.outstandingPull = False
            if not bytesSent == len(data):
                assert not self.iAmStreaming, (
                    "Streaming producer did not write all its data.")
                self._buffer.append(data[bytesSent:])

        if (self.producer is not None) and self.producerIsStreaming:
            bytesBuffered = sum([len(s) for s in self._buffer])
            if bytesBuffered >= self.bufferSize:

                self.producer.pauseProducing()
                self.producerPaused = True

    def registerProducer(self, producer, streaming):
        self.unregistered = False
        BasicProducerConsumerProxy.registerProducer(self, producer, streaming)
        if not streaming:
            producer.resumeProducing()

    def unregisterProducer(self):
        if self.producer is not None:
            del self.producer
            del self.producerIsStreaming
        self.unregistered = True
        if self.consumer and not self._buffer:
            self.consumer.unregisterProducer()

    def _writeSomeData(self, data):
        """Write as much of this data as possible.

        @returns: The number of bytes written.
        """
        if self.consumer is None:
            return 0
        self.consumer.write(data)
        return len(data)
