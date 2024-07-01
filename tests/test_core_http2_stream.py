import unittest
from unittest.mock import Mock, patch
from io import BytesIO
from scrapy.core.http2.stream import Stream  
import unittest
from io import BytesIO
import unittest
from io import BytesIO
from unittest.mock import MagicMock
from scrapy.custom_coverage import coverage

class TestStream(unittest.TestCase):
    def setUp(self):
        # Create a Stream instance for testing
        self.stream = Stream(
            stream_id=1,
            request=self.create_mock_request(),
            protocol=self.create_mock_protocol()
        )

    def create_mock_protocol(self):
        class MockProtocol:
            def send_headers(self, stream_id, headers, end_stream=False):
                pass  

        return MockProtocol()
    
    def create_mock_request(self):
        mock_request = MagicMock()
        mock_request.body = b"Some request body" 
        mock_request.meta = {} 
        return mock_request
    


    def test_initiate_request_if_branch(self):
        self.stream.check_request_url = Mock(return_value=True) 
        self.stream._get_request_headers = Mock(return_value={"header1": "value1", "header2": "value2"})
        self.stream._protocol = Mock()
        
        self.stream.send_data = Mock()

        self.stream.initiate_request()

        self.assertTrue(hasattr(self.stream._protocol, "send_headers"))

        self.assertTrue(self.stream.metadata["request_sent"])

    def test_initiate_request_else_branch(self):
        self.stream.check_request_url = Mock(return_value=False) 

        self.stream.close = Mock()

        self.stream.initiate_request()

        self.assertFalse(self.stream.metadata["request_sent"])

if __name__ == "__main__":
    unittest.main()
