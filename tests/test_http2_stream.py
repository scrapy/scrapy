from unittest import TestCase
from unittest.mock import Mock

from scrapy.core.http2.stream import Stream, StreamClosedError, StreamCloseReason
from scrapy.http import Request


class Http2StreamTestCase(TestCase):
    def test_close_when_stream_closed_server(self):
        stream = Stream(0, Request(url="http://fakeUrl.com"), Mock())
        stream.metadata["stream_closed_server"] = True

        self.assertRaises(StreamClosedError, stream.close, StreamCloseReason.ENDED)

    def test_close_with_invalid_reason(self):
        stream = Stream(0, Request(url="http://fakeUrl.com"), Mock())

        self.assertRaises(TypeError, stream.close, Mock())
