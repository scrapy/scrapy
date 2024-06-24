import unittest
from unittest.mock import Mock, patch
from scrapy.core.http2.protocol import H2ClientProtocol, Stream  # Replace 'some_module' with the actual module name
from h2.events import WindowUpdated

class TestH2ClientProtocol(unittest.TestCase):
    def setUp(self):
        self.uri = Mock()
        self.settings = Mock()
        self.settings.getint = Mock(return_value=1024)
        self.conn_lost_deferred = Mock()
        self.protocol = H2ClientProtocol(self.uri, self.settings, self.conn_lost_deferred)

        self.stream1 = Mock(spec=Stream)
        self.stream2 = Mock(spec=Stream)

        self.protocol.streams[1] = self.stream1
        self.protocol.streams[3] = self.stream2

    def test_window_updated_specific_stream(self):
        event = WindowUpdated()
        event.stream_id = 1

        self.protocol.window_updated(event)

        self.stream1.receive_window_update.assert_called_once()
        self.stream2.receive_window_update.assert_not_called()

    def test_window_updated_all_streams(self):
        event = WindowUpdated()
        event.stream_id = 0

        self.protocol.window_updated(event)

        self.stream1.receive_window_update.assert_called_once()
        self.stream2.receive_window_update.assert_called_once()

if __name__ == '__main__':
    unittest.main()
