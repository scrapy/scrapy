"""
Tests for L{twisted.trial._dist.stream}.
"""

from random import Random
from typing import Awaitable, Dict, List, TypeVar, Union

from hamcrest import (
    all_of,
    assert_that,
    calling,
    equal_to,
    has_length,
    is_,
    less_than_or_equal_to,
    raises,
)
from hypothesis import given
from hypothesis.strategies import binary, integers, just, lists, randoms, text

from twisted.internet.defer import Deferred, fail
from twisted.internet.interfaces import IProtocol
from twisted.internet.protocol import Protocol
from twisted.protocols.amp import AMP
from twisted.python.failure import Failure
from twisted.test.iosim import FakeTransport, connect
from twisted.trial.unittest import SynchronousTestCase
from ..stream import StreamOpen, StreamReceiver, StreamWrite, chunk, stream
from .matchers import HasSum, IsSequenceOf

T = TypeVar("T")


class StreamReceiverTests(SynchronousTestCase):
    """
    Tests for L{StreamReceiver}
    """

    @given(lists(lists(binary())), randoms())
    def test_streamReceived(self, streams: List[List[bytes]], random: Random) -> None:
        """
        All data passed to L{StreamReceiver.write} is returned by a call to
        L{StreamReceiver.finish} with a matching C{streamId}.
        """
        receiver = StreamReceiver()
        streamIds = [receiver.open() for _ in streams]

        # uncorrelate the results with open() order
        random.shuffle(streamIds)

        expectedData = dict(zip(streamIds, streams))
        for streamId, strings in expectedData.items():
            for s in strings:
                receiver.write(streamId, s)

        # uncorrelate the results with write() order
        random.shuffle(streamIds)

        actualData = {streamId: receiver.finish(streamId) for streamId in streamIds}

        assert_that(actualData, is_(equal_to(expectedData)))

    @given(integers(), just("data"))
    def test_writeBadStreamId(self, streamId: int, data: str) -> None:
        """
        L{StreamReceiver.write} raises L{KeyError} if called with a
        streamId not associated with an open stream.
        """
        receiver = StreamReceiver()
        assert_that(calling(receiver.write).with_args(streamId, data), raises(KeyError))

    @given(integers())
    def test_badFinishStreamId(self, streamId: int) -> None:
        """
        L{StreamReceiver.finish} raises L{KeyError} if called with a
        streamId not associated with an open stream.
        """
        receiver = StreamReceiver()
        assert_that(calling(receiver.finish).with_args(streamId), raises(KeyError))

    def test_finishRemovesStream(self) -> None:
        """
        L{StreamReceiver.finish} removes the identified stream.
        """
        receiver = StreamReceiver()
        streamId = receiver.open()
        receiver.finish(streamId)
        assert_that(calling(receiver.finish).with_args(streamId), raises(KeyError))


class ChunkTests(SynchronousTestCase):
    """
    Tests for ``chunk``.
    """

    @given(data=text(), chunkSize=integers(min_value=1))
    def test_chunk(self, data, chunkSize):
        """
        L{chunk} returns an iterable of L{str} where each element is no
        longer than the given limit.  The concatenation of the strings is also
        equal to the original input string.
        """
        chunks = list(chunk(data, chunkSize))
        assert_that(
            chunks,
            all_of(
                IsSequenceOf(
                    has_length(less_than_or_equal_to(chunkSize)),
                ),
                HasSum(equal_to(data), data[:0]),
            ),
        )


class AMPStreamReceiver(AMP):
    """
    A simple AMP interface to L{StreamReceiver}.
    """

    def __init__(self, streams: StreamReceiver) -> None:
        self.streams = streams

    @StreamOpen.responder
    def streamOpen(self) -> Dict[str, object]:
        return {"streamId": self.streams.open()}

    @StreamWrite.responder
    def streamWrite(self, streamId: int, data: bytes) -> Dict[str, object]:
        self.streams.write(streamId, data)
        return {}


def interact(server: IProtocol, client: IProtocol, interaction: Awaitable[T]) -> T:
    """
    Let C{server} and C{client} exchange bytes while C{interaction} runs.
    """
    finished = False
    result: Union[Failure, T]

    async def to_coroutine() -> T:
        return await interaction

    def collect_result(r: Union[Failure, T]) -> None:
        nonlocal result, finished
        finished = True
        result = r

    pump = connect(
        server,
        FakeTransport(server, isServer=True),
        client,
        FakeTransport(client, isServer=False),
    )
    interacting = Deferred.fromCoroutine(to_coroutine())
    interacting.addBoth(collect_result)

    pump.flush()

    if finished:
        if isinstance(result, Failure):
            result.raiseException()
        return result
    raise Exception("Interaction failed to produce a result.")


class InteractTests(SynchronousTestCase):
    """
    Tests for the test helper L{interact}.
    """

    def test_failure(self):
        """
        If the interaction results in a failure then L{interact} raises an
        exception.
        """

        class ArbitraryException(Exception):
            pass

        with self.assertRaises(ArbitraryException):
            interact(Protocol(), Protocol(), fail(ArbitraryException()))

    def test_incomplete(self):
        """
        If the interaction fails to produce a result then L{interact} raises
        an exception.
        """
        with self.assertRaises(Exception):
            interact(Protocol(), Protocol(), Deferred())


class StreamTests(SynchronousTestCase):
    """
    Tests for L{stream}.
    """

    @given(lists(binary()))
    def test_stream(self, chunks: List[bytes]) -> None:
        """
        All of the chunks passed to L{stream} are sent in order over a
        stream using the given AMP connection.
        """
        sender = AMP()
        streams = StreamReceiver()
        streamId = interact(
            AMPStreamReceiver(streams), sender, stream(sender, iter(chunks))
        )
        assert_that(streams.finish(streamId), is_(equal_to(chunks)))
